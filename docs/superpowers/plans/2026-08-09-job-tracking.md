# Job Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independent job favorites and traceable application-status tracking to the Career database, HTTP API, MCP tools, and the existing job radar GUI.

**Architecture:** Schema v7 adds a current-state `job_tracking` row and append-only `job_application_events`. A pure domain validator normalizes patches; a dedicated repository and service implement short `BEGIN IMMEDIATE` transactions with optimistic versions. Existing job queries left-join tracking, while HTTP, MCP, and GUI share the same service contract.

**Tech Stack:** Python 3.12, SQLite, FastAPI, FastMCP, React 18, TypeScript, Vitest, pytest

---

## File Map

**Create**

- `extensions/career_mcp/domain/job_tracking.py`: status constants and pure patch validation.
- `extensions/career_mcp/database/job_tracking_repository.py`: current tracking, event history, insert and CAS update SQL.
- `extensions/career_mcp/services/job_tracking.py`: transaction, clock, stable errors, default records.
- `extensions/career_mcp/tests/test_job_tracking.py`: pure domain tests.
- `extensions/career_mcp/tests/test_job_tracking_service.py`: persistence, CAS, service behavior, and transaction tests.

**Modify**

- `extensions/career_mcp/database/migrations.py`: schema v7 tables and indexes.
- `extensions/career_mcp/tests/test_migrations.py`: v7 migration assertions.
- `extensions/career_mcp/domain/models.py`: tracking filters on `JobSearchFilters`.
- `extensions/career_mcp/database/repository.py`: tracking join, filters, and public row mapping.
- `extensions/career_mcp/services/jobs.py`: pass tracking filters and enrich detail.
- `extensions/career_mcp/tests/test_jobs_service.py`: service query integration.
- `coworker/server/app.py`: tracking HTTP routes and stable error mapping.
- `tests/test_career_jobs_api.py`: HTTP contract and conflict tests.
- `extensions/career_mcp/server.py`: three tracking MCP tools.
- `extensions/career_mcp/tests/test_resume_tools.py`: MCP wrapper tests.
- `tests/test_mcp.py`: MCP discovery count and tool names.
- `surfaces/gui/src/api.ts`: tracking types, filters, and PATCH client.
- `surfaces/gui/src/careerJobsApi.test.ts`: URL and PATCH request tests.
- `surfaces/gui/src/components/CareerJobsView.tsx`: filters, favorite action, editor, timeline.
- `surfaces/gui/src/components/CareerJobsView.test.tsx`: GUI behavior and rollback.
- `surfaces/gui/src/uiChineseAudit.test.ts`: new user-facing text audit.
- `docs/11_DEVELOPMENT_LOG.md`: implementation and acceptance evidence.
- `docs/12_TONIGHT_PROGRESS.md`: stage gate status.

### Task 1: Schema v7 and Pure Tracking Validation

- [ ] **Step 1: Write migration and domain red tests**

Add to `extensions/career_mcp/tests/test_migrations.py`:

```python
def test_schema_v7_adds_job_tracking_and_events(tmp_path: Path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert schema_version(connection) == 7
    assert {"job_tracking", "job_application_events"} <= tables
    assert {
        row["name"]
        for row in connection.execute("PRAGMA table_info(job_tracking)")
    } == {
        "job_id",
        "is_favorite",
        "favorited_at",
        "application_status",
        "applied_at",
        "note",
        "version",
        "created_at",
        "updated_at",
    }
    connection.close()
```

Create `extensions/career_mcp/tests/test_job_tracking.py`:

```python
import pytest

from extensions.career_mcp.domain.job_tracking import (
    TrackingValidationError,
    normalize_tracking_patch,
)


def test_normalize_tracking_patch_accepts_supported_fields():
    assert normalize_tracking_patch(
        {
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "preparing",
            "note": "  本周完成材料  ",
        }
    ) == {
        "expected_version": 0,
        "is_favorite": True,
        "application_status": "preparing",
        "note": "本周完成材料",
    }


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"expected_version": -1, "is_favorite": True}, "INVALID_INPUT"),
        ({"expected_version": 0}, "INVALID_INPUT"),
        (
            {"expected_version": 0, "application_status": "unknown"},
            "INVALID_STATUS",
        ),
        ({"expected_version": 0, "is_favorite": 1}, "INVALID_INPUT"),
        (
            {"expected_version": 0, "note": "x" * 2001},
            "INVALID_INPUT",
        ),
    ],
)
def test_normalize_tracking_patch_rejects_invalid_values(patch, code):
    with pytest.raises(TrackingValidationError) as error:
        normalize_tracking_patch(patch)

    assert error.value.code == code
```

- [ ] **Step 2: Run the red tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_migrations.py::test_schema_v7_adds_job_tracking_and_events \
  extensions/career_mcp/tests/test_job_tracking.py
```

Expected: FAIL because schema version remains 6 and `domain.job_tracking` does not exist.

- [ ] **Step 3: Implement schema v7**

In `extensions/career_mcp/database/migrations.py`, set `SCHEMA_VERSION = 7` and add the following guarded block after v6:

```python
if version < 7 <= SCHEMA_VERSION:
    connection.executescript(
        """
        CREATE TABLE job_tracking (
            job_id TEXT PRIMARY KEY REFERENCES jobs(id),
            is_favorite INTEGER NOT NULL DEFAULT 0
                CHECK(is_favorite IN (0, 1)),
            favorited_at TEXT,
            application_status TEXT NOT NULL DEFAULT 'not_started'
                CHECK(application_status IN (
                    'not_started', 'preparing', 'applied', 'assessment',
                    'interviewing', 'offer', 'accepted', 'rejected',
                    'withdrawn'
                )),
            applied_at TEXT,
            note TEXT,
            version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX job_tracking_favorite
            ON job_tracking(is_favorite, updated_at DESC);
        CREATE INDEX job_tracking_application_status
            ON job_tracking(application_status, updated_at DESC);
        CREATE TABLE job_application_events (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES job_tracking(job_id),
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX job_application_events_job
            ON job_application_events(job_id, occurred_at DESC, id DESC);
        """
    )
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (7, utc_now_iso()),
    )
```

- [ ] **Step 4: Implement pure validation**

Create `extensions/career_mcp/domain/job_tracking.py`:

```python
from __future__ import annotations

APPLICATION_STATUSES = (
    "not_started",
    "preparing",
    "applied",
    "assessment",
    "interviewing",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
)
APPLIED_STATUSES = frozenset(APPLICATION_STATUSES[2:])
_MUTABLE_FIELDS = ("is_favorite", "application_status", "note")


class TrackingValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_tracking_patch(patch: object) -> dict:
    if not isinstance(patch, dict):
        raise TrackingValidationError("INVALID_INPUT", "patch must be an object")
    version = patch.get("expected_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise TrackingValidationError(
            "INVALID_INPUT",
            "expected_version must be a non-negative integer",
        )
    if not any(field in patch for field in _MUTABLE_FIELDS):
        raise TrackingValidationError(
            "INVALID_INPUT",
            "at least one tracking field is required",
        )
    result: dict = {"expected_version": version}
    if "is_favorite" in patch:
        favorite = patch["is_favorite"]
        if not isinstance(favorite, bool):
            raise TrackingValidationError(
                "INVALID_INPUT",
                "is_favorite must be a boolean",
            )
        result["is_favorite"] = favorite
    if "application_status" in patch:
        status = patch["application_status"]
        if status not in APPLICATION_STATUSES:
            raise TrackingValidationError(
                "INVALID_STATUS",
                "unsupported application status",
            )
        result["application_status"] = status
    if "note" in patch:
        note = patch["note"]
        if not isinstance(note, str) or len(note.strip()) > 2000:
            raise TrackingValidationError(
                "INVALID_INPUT",
                "note must contain at most 2000 characters",
            )
        result["note"] = note.strip() or None
    return result
```

- [ ] **Step 5: Run Task 1 tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_job_tracking.py
```

Expected: all tests pass and existing migration assertions expect schema 7.

Before running, update both existing
`schema_version(connection) == 6` assertions in
`extensions/career_mcp/tests/test_migrations.py` to expect `7`.

- [ ] **Step 6: Commit Task 1**

```bash
git add \
  extensions/career_mcp/database/migrations.py \
  extensions/career_mcp/domain/job_tracking.py \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_job_tracking.py
git commit -m "feat: add job tracking schema"
```

### Task 2: Repository and Transactional Service

- [ ] **Step 1: Write repository and service red tests**

Create `extensions/career_mcp/tests/test_job_tracking_service.py` with tests that seed one manual job through `JobService`, then assert:

```python
from datetime import datetime, timezone

import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.services.job_tracking import (
    JobTrackingService,
    JobTrackingServiceError,
)
from extensions.career_mcp.services.jobs import JobService

NOW = datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc)
JD = """职位：AI 工程师
公司：DeepSeek
任职要求：
1. 熟悉 Python
"""


@pytest.fixture
def seeded_tracking(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    job_id = JobService(config).import_manual_jd(
        raw_text=JD,
        source_url="https://careers.deepseek.com/jobs/tracking",
        company_name="DeepSeek",
        title="AI 工程师",
        confirmed=True,
    )["job_id"]
    service = JobTrackingService(config, clock=lambda: NOW)
    inspection = connect(config.database_path)
    try:
        yield service, inspection, job_id
    finally:
        inspection.close()


def test_tracking_defaults_without_persisting(seeded_tracking):
    service, connection, job_id = seeded_tracking

    result = service.get(job_id)

    assert result["application_status"] == "not_started"
    assert result["is_favorite"] is False
    assert result["version"] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM job_tracking"
    ).fetchone()[0] == 0


def test_tracking_updates_with_cas_and_appends_status_events(
    seeded_tracking,
):
    service, connection, job_id = seeded_tracking

    first = service.update(
        job_id,
        {
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "preparing",
        },
    )
    second = service.update(
        job_id,
        {
            "expected_version": first["version"],
            "application_status": "applied",
            "note": "已完成官网投递",
        },
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert second["applied_at"] == "2026-08-09T01:00:00Z"
    assert [event["to_status"] for event in second["events"]] == [
        "applied",
        "preparing",
    ]


def test_tracking_rejects_stale_version(seeded_tracking):
    service, _, job_id = seeded_tracking
    service.update(job_id, {"expected_version": 0, "is_favorite": True})

    with pytest.raises(JobTrackingServiceError) as error:
        service.update(
            job_id,
            {"expected_version": 0, "application_status": "applied"},
        )

    assert error.value.code == "VERSION_CONFLICT"


def test_tracking_rejects_missing_job(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = JobTrackingService(config, clock=lambda: NOW)

    with pytest.raises(JobTrackingServiceError) as error:
        service.update(
            "missing",
            {"expected_version": 0, "is_favorite": True},
        )

    assert error.value.code == "JOB_NOT_FOUND"


def test_tracking_same_status_does_not_duplicate_event(seeded_tracking):
    service, connection, job_id = seeded_tracking
    first = service.update(
        job_id,
        {"expected_version": 0, "application_status": "preparing"},
    )
    second = service.update(
        job_id,
        {
            "expected_version": first["version"],
            "application_status": "preparing",
            "note": "保留当前阶段",
        },
    )

    assert second["note"] == "保留当前阶段"
    assert connection.execute(
        "SELECT COUNT(*) FROM job_application_events WHERE job_id = ?",
        (job_id,),
    ).fetchone()[0] == 1


def test_tracking_survives_job_becoming_inactive(seeded_tracking):
    service, connection, job_id = seeded_tracking
    saved = service.update(
        job_id,
        {"expected_version": 0, "is_favorite": True},
    )
    connection.execute(
        "UPDATE jobs SET status = 'inactive' WHERE id = ?",
        (job_id,),
    )
    connection.commit()

    assert service.get(job_id)["version"] == saved["version"]
    assert service.get(job_id)["is_favorite"] is True


def test_tracking_migrates_fresh_database_before_locking(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = JobTrackingService(config, clock=lambda: NOW)

    with pytest.raises(JobTrackingServiceError) as error:
        service.get("missing")

    assert error.value.code == "JOB_NOT_FOUND"
    with connect(config.database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
```

Add this direct rollback assertion to
`extensions/career_mcp/tests/test_job_tracking_service.py`:

```python
def test_status_event_and_version_roll_back_together(
    seeded_tracking,
    monkeypatch,
):
    service, connection, job_id = seeded_tracking
    original = JobTrackingRepository.add_status_event

    def fail_event(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise sqlite3.OperationalError("simulated event failure")

    monkeypatch.setattr(
        JobTrackingRepository,
        "add_status_event",
        fail_event,
    )

    with pytest.raises(sqlite3.OperationalError):
        service.update(
            job_id,
            {"expected_version": 0, "application_status": "preparing"},
        )

    assert connection.execute(
        "SELECT COUNT(*) FROM job_tracking WHERE job_id = ?",
        (job_id,),
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM job_application_events WHERE job_id = ?",
        (job_id,),
    ).fetchone()[0] == 0
```

- [ ] **Step 2: Run the red tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_job_tracking_service.py
```

Expected: FAIL because repository and service modules do not exist.

- [ ] **Step 3: Implement repository**

Create `extensions/career_mcp/database/job_tracking_repository.py` with:

```python
class JobTrackingRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        migrate(connection)

    def job_exists(self, job_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone() is not None

    def get(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM job_tracking WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return self._tracking_row(row) if row else None

    def list_events(self, job_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, from_status, to_status, occurred_at
            FROM job_application_events
            WHERE job_id = ?
            ORDER BY occurred_at DESC, id DESC
            """,
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]
```

Implement the write methods with parameterized SQL:

```python
def insert(self, tracking: dict) -> None:
    self.connection.execute(
        """
        INSERT INTO job_tracking(
            job_id, is_favorite, favorited_at, application_status,
            applied_at, note, version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            tracking["job_id"],
            int(tracking["is_favorite"]),
            tracking["favorited_at"],
            tracking["application_status"],
            tracking["applied_at"],
            tracking["note"],
            tracking["created_at"],
            tracking["updated_at"],
        ),
    )


def update_if_version(self, tracking: dict, expected_version: int) -> bool:
    cursor = self.connection.execute(
        """
        UPDATE job_tracking
        SET is_favorite = ?, favorited_at = ?, application_status = ?,
            applied_at = ?, note = ?, version = version + 1,
            updated_at = ?
        WHERE job_id = ? AND version = ?
        """,
        (
            int(tracking["is_favorite"]),
            tracking["favorited_at"],
            tracking["application_status"],
            tracking["applied_at"],
            tracking["note"],
            tracking["updated_at"],
            tracking["job_id"],
            expected_version,
        ),
    )
    return cursor.rowcount == 1


def add_status_event(
    self,
    *,
    event_id: str,
    job_id: str,
    from_status: str,
    to_status: str,
    occurred_at: str,
) -> None:
    self.connection.execute(
        """
        INSERT INTO job_application_events(
            id, job_id, from_status, to_status, occurred_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (event_id, job_id, from_status, to_status, occurred_at),
    )
```

- [ ] **Step 4: Implement service**

Create `extensions/career_mcp/services/job_tracking.py` with:

```python
class JobTrackingServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JobTrackingService:
    def __init__(self, config=None, *, clock=None) -> None:
        self.config = config or CareerConfig.from_env()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def get(self, job_id: str) -> dict:
        normalized_id = self._job_id(job_id)
        connection = connect(self.config.database_path)
        try:
            repository = JobTrackingRepository(connection)
            if not repository.job_exists(normalized_id):
                raise JobTrackingServiceError(
                    "JOB_NOT_FOUND",
                    "job not found",
                )
            current = repository.get(normalized_id)
            result = current or self._default(normalized_id)
            return {
                **result,
                "events": repository.list_events(normalized_id),
            }
        finally:
            connection.close()
```

Implement `update()` with this transaction order:

```python
def update(self, job_id: str, patch: object) -> dict:
    normalized_id = self._job_id(job_id)
    try:
        values = normalize_tracking_patch(patch)
    except TrackingValidationError as exc:
        raise JobTrackingServiceError(exc.code, str(exc)) from exc
    connection = connect(self.config.database_path)
    try:
        repository = JobTrackingRepository(connection)
        connection.execute("BEGIN IMMEDIATE")
        if not repository.job_exists(normalized_id):
            raise JobTrackingServiceError("JOB_NOT_FOUND", "job not found")
        current = repository.get(normalized_id)
        base = current or self._default(normalized_id)
        if values["expected_version"] != base["version"]:
            raise JobTrackingServiceError(
                "VERSION_CONFLICT",
                "tracking record changed",
            )
        now = self._iso(self._clock())
        favorite = values.get("is_favorite", base["is_favorite"])
        status = values.get(
            "application_status",
            base["application_status"],
        )
        note = values.get("note", base["note"])
        changed = (
            favorite != base["is_favorite"]
            or status != base["application_status"]
            or note != base["note"]
        )
        if not changed:
            connection.commit()
            return {**base, "events": repository.list_events(normalized_id)}
        tracking = {
            **base,
            "is_favorite": favorite,
            "favorited_at": (
                base["favorited_at"] or now if favorite else None
            ),
            "application_status": status,
            "applied_at": (
                base["applied_at"]
                or (now if status in APPLIED_STATUSES else None)
            ),
            "note": note,
            "created_at": base["created_at"] or now,
            "updated_at": now,
        }
        if current is None:
            repository.insert(tracking)
        elif not repository.update_if_version(
            tracking,
            values["expected_version"],
        ):
            raise JobTrackingServiceError(
                "VERSION_CONFLICT",
                "tracking record changed",
            )
        if status != base["application_status"]:
            repository.add_status_event(
                event_id=str(uuid4()),
                job_id=normalized_id,
                from_status=base["application_status"],
                to_status=status,
                occurred_at=now,
            )
        connection.commit()
        saved = repository.get(normalized_id)
        assert saved is not None
        return {
            **saved,
            "events": repository.list_events(normalized_id),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
```

- [ ] **Step 5: Run Task 2 tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_job_tracking.py \
  extensions/career_mcp/tests/test_job_tracking_service.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  extensions/career_mcp/database/job_tracking_repository.py \
  extensions/career_mcp/services/job_tracking.py \
  extensions/career_mcp/tests/test_job_tracking_service.py
git commit -m "feat: persist job tracking history"
```

### Task 3: Integrate Tracking Into Job Search and Detail

- [ ] **Step 1: Write query integration red tests**

Extend `extensions/career_mcp/tests/test_jobs_service.py` to seed three jobs with default, favorite, and applied tracking. Assert:

```python
def test_job_search_filters_tracking_before_pagination(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    jobs = JobService(config)
    tracking = JobTrackingService(config)
    job_ids = []
    for index in range(3):
        created = jobs.import_manual_jd(
            raw_text=RAW_JD + f"\n序号：{index}",
            source_url=f"https://careers.example.com/jobs/{index}",
            company_name="示例 AI 公司",
            title=f"AI 产品经理 {index}",
            confirmed=True,
        )
        job_ids.append(created["job_id"])
    favorite_job_id = job_ids[1]
    applied_job_id = job_ids[2]
    tracking.update(
        favorite_job_id,
        {"expected_version": 0, "is_favorite": True},
    )
    tracking.update(
        applied_job_id,
        {"expected_version": 0, "application_status": "applied"},
    )

    favorite = jobs.search_jobs(
        favorite_only=True,
        limit=1,
        offset=0,
    )
    applied = jobs.search_jobs(application_status="applied")

    assert favorite["total"] == 1
    assert [job["id"] for job in favorite["jobs"]] == [favorite_job_id]
    assert [job["id"] for job in applied["jobs"]] == [applied_job_id]
    assert favorite["jobs"][0]["tracking"]["is_favorite"] is True
    assert jobs.get_job(applied_job_id)["tracking"]["events"][0][
        "to_status"
    ] == "applied"


def test_job_search_rejects_unknown_application_status(tmp_path):
    service = JobService(CareerConfig(data_dir=tmp_path / "career"))

    with pytest.raises(ValueError):
        service.search_jobs(application_status="unknown")
```

- [ ] **Step 2: Run the red tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_jobs_service.py -k tracking
```

Expected: FAIL because `JobSearchFilters`, repository SQL, and public rows lack tracking.

- [ ] **Step 3: Extend filters and repository SQL**

Add to `JobSearchFilters`:

```python
favorite_only: bool = False
application_status: str | None = None
```

In `JobRepository.search_jobs()`, left-join:

```sql
LEFT JOIN job_tracking tracking ON tracking.job_id = jobs.id
```

Add conditions only when requested:

```sql
tracking.is_favorite = 1
tracking.application_status = ?
```

Return this defaulted summary from `_job_row()`:

```python
"tracking": (
    {
        "is_favorite": bool(row["tracking_is_favorite"] or 0),
        "application_status": (
            row["tracking_application_status"] or "not_started"
        ),
        "version": int(row["tracking_version"] or 0),
        "updated_at": row["tracking_updated_at"],
    }
    if "tracking_is_favorite" in row.keys()
    else {
        "is_favorite": False,
        "application_status": "not_started",
        "version": 0,
        "updated_at": None,
    }
),
```

- [ ] **Step 4: Enrich detail and validate status**

In `JobService.search_jobs()`, pop and validate tracking filters before
constructing `JobSearchFilters`:

```python
favorite_only = kwargs.pop("favorite_only", False)
application_status = kwargs.pop("application_status", None)
if not isinstance(favorite_only, bool):
    raise ValueError("favorite_only must be a boolean")
if (
    application_status is not None
    and application_status not in APPLICATION_STATUSES
):
    raise ValueError("unsupported application status")
filters = JobSearchFilters(
    limit=limit,
    offset=offset,
    favorite_only=favorite_only,
    application_status=application_status,
    **kwargs,
)
```

In `JobService.get_job()`, add:

```python
detail["tracking"] = JobTrackingService(self.config).get(job_id)
```

- [ ] **Step 5: Run Task 3 tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_jobs_service.py \
  extensions/career_mcp/tests/test_job_tracking_service.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add \
  extensions/career_mcp/domain/models.py \
  extensions/career_mcp/database/repository.py \
  extensions/career_mcp/services/jobs.py \
  extensions/career_mcp/tests/test_jobs_service.py
git commit -m "feat: filter jobs by tracking state"
```

### Task 4: HTTP and MCP Contracts

- [ ] **Step 1: Write HTTP red tests**

Extend `tests/test_career_jobs_api.py`:

```python
def test_job_tracking_api_updates_and_filters(tmp_path, monkeypatch):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)

    initial = client.get(f"/v1/career/jobs/{job_id}/tracking")
    updated = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "preparing",
            "note": "准备申请",
        },
    )
    filtered = client.get(
        "/v1/career/jobs",
        params={"favorite_only": "true", "status": ""},
    )

    assert initial.json()["tracking"]["version"] == 0
    assert updated.json()["tracking"]["version"] == 1
    assert filtered.json()["total"] == 1
    assert filtered.json()["jobs"][0]["id"] == job_id
```

Add these explicit error assertions:

```python
def test_job_tracking_api_returns_stable_errors(tmp_path, monkeypatch):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)
    created = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={"expected_version": 0, "is_favorite": True},
    )
    invalid = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={"expected_version": 1, "application_status": "unknown"},
    )
    stale = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={"expected_version": 0, "application_status": "applied"},
    )
    missing = client.get("/v1/career/jobs/missing/tracking")

    assert created.status_code == 200
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_STATUS"
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert "sqlite" not in str(stale.json()).lower()
```

- [ ] **Step 2: Write MCP red tests**

Extend `extensions/career_mcp/tests/test_resume_tools.py`:

```python
def test_job_tracking_mcp_tools_use_shared_services(monkeypatch):
    calls = []
    tracking = SimpleNamespace(
        get=lambda job_id: calls.append(("get", job_id)) or {
            "job_id": job_id,
            "version": 0,
        },
        update=lambda job_id, patch: (
            calls.append(("update", job_id, patch))
            or {"job_id": job_id, "version": 1}
        ),
    )
    jobs = SimpleNamespace(
        search_jobs=lambda **filters: (
            calls.append(("list", filters))
            or {"jobs": [], "total": 0, "limit": 20, "offset": 0}
        )
    )
    monkeypatch.setattr(server, "_job_tracking_service", lambda: tracking)
    monkeypatch.setattr(server, "_job_service", lambda: jobs)

    read = server.get_job_tracking("job-1")
    listed = server.list_tracked_jobs(True, "preparing", 20, 0)
    updated = server.update_job_tracking(
        "job-1",
        0,
        True,
        "preparing",
        "准备材料",
    )

    assert read["data"]["version"] == 0
    assert listed["data"]["total"] == 0
    assert updated["data"]["version"] == 1
    assert calls == [
        ("get", "job-1"),
        (
            "list",
            {
                "favorite_only": True,
                "application_status": "preparing",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "update",
            "job-1",
            {
                "expected_version": 0,
                "is_favorite": True,
                "application_status": "preparing",
                "note": "准备材料",
            },
        ),
    ]
```

Extend the existing discovered-name assertion in `tests/test_mcp.py`:

```python
assert {
    "get_job_tracking",
    "list_tracked_jobs",
    "update_job_tracking",
} <= discovered_tool_names
```

- [ ] **Step 3: Run red tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_career_jobs_api.py -k tracking \
  extensions/career_mcp/tests/test_resume_tools.py -k tracking \
  tests/test_mcp.py -k career
```

Expected: FAIL because routes and tools are absent.

- [ ] **Step 4: Implement HTTP routes**

In `coworker/server/app.py`, add `career_tracking_service()` and `career_tracking_error()`. Map:

```python
statuses = {
    "INVALID_INPUT": 400,
    "INVALID_STATUS": 400,
    "JOB_NOT_FOUND": 404,
    "VERSION_CONFLICT": 409,
    "PERSISTENCE_ERROR": 409,
}
```

Add:

```python
@app.get("/v1/career/jobs/{job_id}/tracking")
def career_job_tracking_get(job_id: str):
    try:
        return {
            "ok": True,
            "tracking": career_tracking_service().get(job_id),
        }
    except Exception as exc:
        return career_tracking_error(exc)


@app.patch("/v1/career/jobs/{job_id}/tracking")
def career_job_tracking_patch(job_id: str, body: dict):
    try:
        return {
            "ok": True,
            "tracking": career_tracking_service().update(
                job_id,
                body or {},
            ),
        }
    except Exception as exc:
        return career_tracking_error(exc)
```

Extend the list route with strict `favorite_only: bool = False` and `application_status: str = ""`.

- [ ] **Step 5: Implement MCP tools**

Add `_job_service()` returning `JobService()` and
`_job_tracking_service()` returning `JobTrackingService()`, then add:

```python
def get_job_tracking(job_id: str) -> dict:
    try:
        return _ok(_job_tracking_service().get(job_id))
    except JobTrackingServiceError as exc:
        return _error(exc.code, str(exc))


def list_tracked_jobs(
    favorite_only: bool = False,
    application_status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    try:
        return _ok(
            _job_service().search_jobs(
                favorite_only=favorite_only,
                application_status=application_status,
                limit=limit,
                offset=offset,
            )
        )
    except (ValueError, JobTrackingServiceError) as exc:
        return _error(getattr(exc, "code", "INVALID_INPUT"), str(exc))


def update_job_tracking(
    job_id: str,
    expected_version: int,
    is_favorite: bool | None = None,
    application_status: str | None = None,
    note: str | None = None,
) -> dict:
    patch = {"expected_version": expected_version}
    if is_favorite is not None:
        patch["is_favorite"] = is_favorite
    if application_status is not None:
        patch["application_status"] = application_status
    if note is not None:
        patch["note"] = note
    try:
        return _ok(_job_tracking_service().update(job_id, patch))
    except JobTrackingServiceError as exc:
        return _error(exc.code, str(exc))
```

Register all three with `mcp.tool()`.

- [ ] **Step 6: Run Task 4 tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_career_jobs_api.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py
```

Expected: all tests pass and stdio tool discovery includes the new tools.

- [ ] **Step 7: Commit Task 4**

```bash
git add \
  coworker/server/app.py \
  extensions/career_mcp/server.py \
  tests/test_career_jobs_api.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py
git commit -m "feat: expose job tracking APIs"
```

### Task 5: Job Radar GUI

- [ ] **Step 1: Write API client red tests**

Extend `surfaces/gui/src/careerJobsApi.test.ts`:

```typescript
it("encodes tracking filters and patches a versioned record", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    json: async () => ({ ok: true }),
  });
  vi.stubGlobal("fetch", fetchMock);

  await getCareerJobs({
    favoriteOnly: true,
    applicationStatus: "interviewing",
  });
  await updateCareerJobTracking("job/one", {
    expected_version: 3,
    is_favorite: false,
  });

  expect(String(fetchMock.mock.calls[0][0])).toContain(
    "favorite_only=true",
  );
  expect(String(fetchMock.mock.calls[0][0])).toContain(
    "application_status=interviewing",
  );
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "PATCH" });
  expect(fetchMock.mock.calls[1][1].body).toBe(
    JSON.stringify({ expected_version: 3, is_favorite: false }),
  );
});
```

- [ ] **Step 2: Write component red tests**

Extend the mocked API with `updateCareerJobTracking` and add this tracking fixture to each test job:

```typescript
tracking: {
  is_favorite: false,
  application_status: "not_started",
  version: 0,
  updated_at: null,
},
```

Verify favorite clicks do not select another detail:

```typescript
fireEvent.click(screen.getByRole("button", { name: "收藏岗位" }));
await waitFor(() =>
  expect(api.updateCareerJobTracking).toHaveBeenCalledWith("job-1", {
    expected_version: 0,
    is_favorite: true,
  }),
);
expect(api.getCareerJob).toHaveBeenCalledTimes(1);
```

Add server-filter and editor assertions:

```typescript
fireEvent.click(screen.getByLabelText("仅看收藏"));
fireEvent.change(screen.getByLabelText("申请进度"), {
  target: { value: "interviewing" },
});
await waitFor(() =>
  expect(api.getCareerJobs).toHaveBeenLastCalledWith(
    expect.objectContaining({
      favoriteOnly: true,
      applicationStatus: "interviewing",
      offset: 0,
    }),
  ),
);

fireEvent.change(screen.getByLabelText("我的申请进度"), {
  target: { value: "applied" },
});
fireEvent.change(screen.getByLabelText("申请备注"), {
  target: { value: "已完成官网投递" },
});
fireEvent.click(screen.getByRole("button", { name: "保存申请进度" }));
await waitFor(() =>
  expect(api.updateCareerJobTracking).toHaveBeenCalledWith("job-1", {
    expected_version: 0,
    application_status: "applied",
    note: "已完成官网投递",
  }),
);
expect(screen.queryByText("applied")).toBeNull();
expect(screen.getByText("已投递")).toBeTruthy();
```

Add failed optimistic update and conflict assertions:

```typescript
api.updateCareerJobTracking.mockResolvedValueOnce({
  ok: false,
  error: { code: "PERSISTENCE_ERROR", message: "保存失败。" },
});
fireEvent.click(screen.getByRole("button", { name: "收藏岗位" }));
expect(screen.getByRole("button", { name: "取消收藏" })).toBeDisabled();
await screen.findByText("保存失败。");
expect(screen.getByRole("button", { name: "收藏岗位" })).toBeTruthy();

api.updateCareerJobTracking.mockResolvedValueOnce({
  ok: false,
  error: {
    code: "VERSION_CONFLICT",
    message: "记录已在其他入口更新。",
  },
});
fireEvent.click(screen.getByRole("button", { name: "保存申请进度" }));
expect(
  await screen.findByText(
    "记录已在其他入口更新，请确认最新内容后重试。",
  ),
).toBeTruthy();
await waitFor(() =>
  expect(api.getCareerJob).toHaveBeenCalledTimes(2),
);
```

Set detail events in reverse chronological order and assert the visible Chinese labels occur in that same DOM order:

```typescript
const timeline = screen.getByTestId("application-timeline");
expect(timeline.textContent?.indexOf("已投递")).toBeLessThan(
  timeline.textContent?.indexOf("准备材料") || 0,
);
```

- [ ] **Step 3: Run GUI red tests**

Run:

```bash
cd surfaces/gui && npm test -- \
  src/careerJobsApi.test.ts \
  src/components/CareerJobsView.test.tsx
```

Expected: FAIL because tracking types, API client, and controls are absent.

- [ ] **Step 4: Implement frontend API types**

Add:

```typescript
export type CareerApplicationStatus =
  | "not_started"
  | "preparing"
  | "applied"
  | "assessment"
  | "interviewing"
  | "offer"
  | "accepted"
  | "rejected"
  | "withdrawn";

export interface CareerJobTracking {
  job_id?: string;
  is_favorite: boolean;
  favorited_at?: string | null;
  application_status: CareerApplicationStatus;
  applied_at?: string | null;
  note?: string | null;
  version: number;
  updated_at?: string | null;
  events?: CareerApplicationEvent[];
}

export interface CareerApplicationEvent {
  id: string;
  from_status: CareerApplicationStatus;
  to_status: CareerApplicationStatus;
  occurred_at: string;
}

export interface CareerJobTrackingResult {
  ok: boolean;
  error?: { code: string; message: string };
  tracking?: CareerJobTracking;
}
```

Add `tracking` to job summaries, `favoriteOnly` and `applicationStatus` to queries. Append these query pairs:

```typescript
["favorite_only", filters.favoriteOnly ? "true" : undefined],
["application_status", filters.applicationStatus],
```

Implement:

```typescript
export async function updateCareerJobTracking(
  jobId: string,
  patch: {
    expected_version: number;
    is_favorite?: boolean;
    application_status?: CareerApplicationStatus;
    note?: string;
  },
): Promise<CareerJobTrackingResult> {
  const res = await fetch(
    `${httpBase()}/v1/career/jobs/${encodeURIComponent(jobId)}/tracking`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
  return res.json();
}
```

- [ ] **Step 5: Implement CareerJobsView controls**

Add one status map:

```typescript
const APPLICATION_STATUS_NAMES: Record<CareerApplicationStatus, string> = {
  not_started: "未开始",
  preparing: "准备材料",
  applied: "已投递",
  assessment: "笔试/测评",
  interviewing: "面试中",
  offer: "已获 Offer",
  accepted: "已接受 Offer",
  rejected: "未通过",
  withdrawn: "已撤回",
};
```

Use state:

```typescript
const [favoriteOnly, setFavoriteOnly] = useState(false);
const [applicationStatus, setApplicationStatus] =
  useState<CareerApplicationStatus | "">("");
const [trackingPending, setTrackingPending] = useState(false);
const [trackingError, setTrackingError] = useState("");
const [draftStatus, setDraftStatus] =
  useState<CareerApplicationStatus>("not_started");
const [draftNote, setDraftNote] = useState("");
```

Keep list and detail synchronized:

```typescript
const applyTracking = (jobId: string, tracking: CareerJobTracking) => {
  setJobs((current) =>
    current.map((job) =>
      job.id === jobId ? { ...job, tracking } : job,
    ),
  );
  setDetail((current) =>
    current?.id === jobId ? { ...current, tracking } : current,
  );
};
```

Implement the favorite handler:

```typescript
// Add MouseEvent to the existing react imports.
const toggleFavorite = async (
  event: MouseEvent,
  job: CareerJobSummary,
) => {
  event.stopPropagation();
  if (trackingPending) return;
  const previous = job.tracking;
  const target = !previous.is_favorite;
  setTrackingPending(true);
  setTrackingError("");
  applyTracking(job.id, { ...previous, is_favorite: target });
  try {
    const result = await updateCareerJobTracking(job.id, {
      expected_version: previous.version,
      is_favorite: target,
    });
    if (!result.ok || !result.tracking) {
      applyTracking(job.id, previous);
      setTrackingError(result.error?.message || "收藏状态保存失败。");
      return;
    }
    applyTracking(job.id, result.tracking);
    if (favoriteOnly && !target) {
      setJobs((current) => current.filter((item) => item.id !== job.id));
      setTotal((current) => Math.max(0, current - 1));
    }
  } catch {
    applyTracking(job.id, previous);
    setTrackingError("无法连接本地岗位服务。");
  } finally {
    setTrackingPending(false);
  }
};
```

Implement the save handler:

```typescript
const saveTracking = async () => {
  if (!detail || trackingPending) return;
  setTrackingPending(true);
  setTrackingError("");
  const result = await updateCareerJobTracking(detail.id, {
    expected_version: detail.tracking.version,
    application_status: draftStatus,
    note: draftNote,
  });
  if (result.ok && result.tracking) {
    applyTracking(detail.id, result.tracking);
  } else if (result.error?.code === "VERSION_CONFLICT") {
    setTrackingError(
      "记录已在其他入口更新，请确认最新内容后重试。",
    );
    const refreshed = await getCareerJob(detail.id);
    if (refreshed.ok && refreshed.job) setDetail(refreshed.job);
  } else {
    setTrackingError(result.error?.message || "申请进度保存失败。");
  }
  setTrackingPending(false);
};
```

On `VERSION_CONFLICT`, set the exact Chinese conflict message and call `getCareerJob(detail.id)` before enabling save again. Render event labels from `APPLICATION_STATUS_NAMES` inside an element with `data-testid="application-timeline"`. Do not add an `App.tsx` surface or sidebar item.

- [ ] **Step 6: Run Task 5 tests and build**

Run:

```bash
cd surfaces/gui && npm test -- \
  src/careerJobsApi.test.ts \
  src/components/CareerJobsView.test.tsx \
  src/uiChineseAudit.test.ts
npm run build
```

Expected: all tests pass; build may retain the existing chunk-size warning but no errors.

- [ ] **Step 7: Commit Task 5**

```bash
git add \
  surfaces/gui/src/api.ts \
  surfaces/gui/src/careerJobsApi.test.ts \
  surfaces/gui/src/components/CareerJobsView.tsx \
  surfaces/gui/src/components/CareerJobsView.test.tsx \
  surfaces/gui/src/uiChineseAudit.test.ts
git commit -m "feat: manage job tracking in radar"
```

### Task 6: Real Acceptance, Regression, and Adversarial Gate

- [ ] **Step 1: Run the complete backend gate**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py \
  tests/test_mcp.py \
  tests/test_skills.py \
  tests/test_builtin_personas.py
```

Expected: all tests pass; only the existing Starlette/httpx deprecation warning is accepted.

- [ ] **Step 2: Run the complete GUI gate**

```bash
cd surfaces/gui && npm test -- --run
npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 3: Verify a real DeepSeek tracking flow**

Run:

```bash
CAREER_DATA_DIR="$PWD/career" .venv/bin/python - <<'PY'
from extensions.career_mcp.services.job_tracking import JobTrackingService
from extensions.career_mcp.services.jobs import JobService

job_id = "ad9b82d1-e411-4677-bbe8-8ca535357a71"
tracking = JobTrackingService()
jobs = JobService()
original = tracking.get(job_id)
first = tracking.update(
    job_id,
    {
        "expected_version": original["version"],
        "is_favorite": True,
        "application_status": "preparing",
    },
)
second = tracking.update(
    job_id,
    {
        "expected_version": first["version"],
        "application_status": "applied",
    },
)
favorite = jobs.search_jobs(favorite_only=True, limit=100)
assert job_id in {job["id"] for job in favorite["jobs"]}
assert [event["to_status"] for event in second["events"][:2]] == [
    "applied",
    "preparing",
]
restored = tracking.update(
    job_id,
    {
        "expected_version": second["version"],
        "is_favorite": original["is_favorite"],
        "application_status": original["application_status"],
        "note": original["note"] or "",
    },
)
print({
    "job_id": job_id,
    "version": restored["version"],
    "events": len(restored["events"]),
})
PY
```

Expected: no crawler-managed job field changes.

- [ ] **Step 4: Verify schema and repository integrity**

```bash
.venv/bin/python - <<'PY'
import sqlite3
with sqlite3.connect("career/career.sqlite3") as connection:
    print(connection.execute("PRAGMA user_version").fetchone()[0])
    print(connection.execute("PRAGMA foreign_key_check").fetchall())
PY
git diff --check
```

Expected: schema `7`, empty foreign-key result, and no whitespace errors.

- [ ] **Step 5: Run an independent adversarial review**

Review only these attack classes:

- stale `expected_version` from concurrent GUI and MCP writes;
- invalid or mixed-type application statuses;
- note text containing HTML/script payloads;
- crawler transition to inactive while tracking exists;
- repeated identical status update;
- fresh database migration before write lock.

Any critical or major finding requires a new failing test, minimal fix, and rerun of Steps 1–4.

- [ ] **Step 6: Update stage documentation**

Append exact test counts, real job evidence, schema version, review findings, warnings, and next task “定制材料导出” to:

- `docs/11_DEVELOPMENT_LOG.md`
- `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 7: Commit documentation**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record job tracking acceptance"
```
