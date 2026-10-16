# Stage 2 Closeout And Stage 3 Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the visible Stage 2 GUI acceptance, then add an offline, fixture-tested crawler pipeline that records deterministic job state transitions.

**Architecture:** Stage 2 uses the existing Career GUI session, MCP approval cards, and `JobService` without changing the Agent loop. Stage 3 adds a crawler domain layer and service that receive adapter snapshots, normalize them, decide transitions, and persist them through new repository methods and a versioned SQLite migration.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, dataclasses, FastMCP, pytest, local JSON fixtures, OpenWorker GUI.

---

## File Structure

| Path | Responsibility |
|---|---|
| `docs/11_DEVELOPMENT_LOG.md` | Commands, GUI evidence, artifact path, and completed acceptance entries |
| `docs/12_TONIGHT_PROGRESS.md` | Stage gate status and next smallest task |
| `extensions/career_mcp/domain/crawler.py` | Immutable snapshot, normalized job, transition, and result values |
| `extensions/career_mcp/crawler/adapters.py` | `JobAdapter` protocol and fixture-only `FakeAdapter` |
| `extensions/career_mcp/crawler/normalize.py` | Pure identity and content-hash normalization |
| `extensions/career_mcp/database/migrations.py` | Schema version 2 migration |
| `extensions/career_mcp/database/repository.py` | Sources, runs, state reads, and transactional transition writes |
| `extensions/career_mcp/services/crawler.py` | Adapter orchestration and missing/offline protection |
| `extensions/career_mcp/server.py` | `list_sources`, `list_recent_job_events`, and approval-gated `crawl_source` |
| `extensions/career_mcp/tests/test_crawler_*.py` | Offline unit, repository, service, and MCP tests |
| `extensions/career_mcp/tests/fixtures/fake_source_jobs.json` | Deterministic snapshot fixture |

### Task 1: Complete Stage 2 GUI Acceptance

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`
- Create: `artifacts/stage2-gui-job-brief.md`

- [ ] **Step 1: Start isolated Local Server and GUI**

Run:
```bash
COWORKER_STATE_DIR="$PWD/.local-state" CAREER_DATA_DIR="$PWD/career" \
  .venv/bin/openworker-server --cwd "$PWD" --port 8765
```

Run in `surfaces/gui`:
```bash
COWORKER_STATE_DIR="$PWD/.local-state" CAREER_DATA_DIR="$PWD/career" \
  npm run dev -- --host 127.0.0.1
```

- [ ] **Step 2: Execute the fixed GUI MCP sequence**

Use one fresh Career session and this unique raw JD:
```text
职位：Stage2 GUI 验收实习生
公司：OpenWorker Career Stage2 验收公司
工作地点：北京
岗位职责：
1. 验收 Career MCP 的手动 JD 写入
任职要求：
1. 熟悉 Python
2. 每周实习 4 天
```

Approve only Career MCP and file-write cards. Record the returned job id and verify, in order: preview, `created=true`, detail, filtered search, `duplicate=true`, and the approved `artifacts/stage2-gui-job-brief.md` write.

- [ ] **Step 3: Record the actual evidence**

Append the exact job id, GUI screenshot paths, server `CallToolRequest` lines, test command result, and brief path to `docs/11_DEVELOPMENT_LOG.md`. Change the Stage 2 row in `docs/12_TONIGHT_PROGRESS.md` to `通过` only when all six assertions succeed.

- [ ] **Step 4: Run Stage 2 regressions**

Run:
```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests \
  tests/test_skills.py tests/test_builtin_personas.py -q
```

Expected: all tests pass; no network requests are made.

### Task 2: Define Offline Crawler Values And Adapter Boundary

**Files:**
- Create: `extensions/career_mcp/domain/crawler.py`
- Create: `extensions/career_mcp/crawler/__init__.py`
- Create: `extensions/career_mcp/crawler/adapters.py`
- Create: `extensions/career_mcp/crawler/normalize.py`
- Create: `extensions/career_mcp/tests/test_crawler_normalize.py`

- [ ] **Step 1: Write failing normalization tests**

```python
from extensions.career_mcp.crawler.normalize import normalize_snapshot
from extensions.career_mcp.domain.crawler import JobSnapshot

def test_normalize_snapshot_has_stable_identity_and_content_hash():
    snapshot = JobSnapshot(
        external_job_id="42",
        title="Agent Engineer",
        description_raw="Build tools",
        source_url="https://jobs.example/42",
        observed_at="2026-08-05T00:00:00Z",
        location_raw="北京",
        recruitment_type="internship",
    )

    job = normalize_snapshot("fake-source", snapshot)

    assert job.identity == "fake-source:42"
    assert job.content_hash == normalize_snapshot("fake-source", snapshot).content_hash
    assert job.locations == ["北京"]
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_crawler_normalize.py -q
```

Expected: import error because crawler modules do not exist.

- [ ] **Step 3: Add the minimal domain and pure normalizer**

```python
# extensions/career_mcp/domain/crawler.py
@dataclass(frozen=True)
class JobSnapshot:
    external_job_id: str
    title: str
    description_raw: str
    source_url: str
    observed_at: str
    location_raw: str | None = None
    recruitment_type: str | None = None

@dataclass(frozen=True)
class NormalizedJob:
    identity: str
    external_job_id: str
    title: str
    description_raw: str
    source_url: str
    observed_at: str
    locations: list[str]
    recruitment_type: str | None
    content_hash: str
```

```python
# extensions/career_mcp/crawler/normalize.py
def normalize_snapshot(source_slug: str, snapshot: JobSnapshot) -> NormalizedJob:
    normalized = "\n".join(
        part.strip() for part in (snapshot.title, snapshot.description_raw) if part.strip()
    )
    return NormalizedJob(
        identity=f"{source_slug}:{snapshot.external_job_id}",
        external_job_id=snapshot.external_job_id,
        title=snapshot.title.strip(),
        description_raw=snapshot.description_raw.strip(),
        source_url=snapshot.source_url,
        observed_at=snapshot.observed_at,
        locations=[snapshot.location_raw.strip()] if snapshot.location_raw else [],
        recruitment_type=snapshot.recruitment_type,
        content_hash=sha256(normalized.encode("utf-8")).hexdigest(),
    )
```

Implement `JobAdapter(Protocol)` with `fetch_jobs(self) -> list[JobSnapshot]`, and `FakeAdapter` returning its injected snapshots.

- [ ] **Step 4: Run the normalizer tests**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_crawler_normalize.py -q
```

Expected: `1 passed`.

### Task 3: Add Version 2 Schema And Crawler Repository Operations

**Files:**
- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/database/repository.py`
- Create: `extensions/career_mcp/tests/test_crawler_repository.py`

- [ ] **Step 1: Write failing migration and persistence tests**

```python
def test_version_two_creates_crawl_tables_and_preserves_manual_tables(tmp_path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)
    tables = {row["name"] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    assert schema_version(connection) == 2
    assert {"crawl_sources", "crawl_runs", "jobs", "job_events"} <= tables
```

- [ ] **Step 2: Run the repository test to confirm it fails**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_crawler_repository.py -q
```

Expected: schema version assertion fails because the current version is 1.

- [ ] **Step 3: Implement migration 2 and repository operations**

Set `SCHEMA_VERSION = 2`. Apply migration 1 only when `user_version < 1`; apply migration 2 only when `user_version < 2`. Migration 2 creates:

```sql
CREATE TABLE crawl_sources (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  missing_threshold INTEGER NOT NULL,
  enabled INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE crawl_runs (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES crawl_sources(id),
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  observed_count INTEGER NOT NULL,
  invalid_count INTEGER NOT NULL,
  error_summary TEXT
);
ALTER TABLE jobs ADD COLUMN crawl_source_id TEXT REFERENCES crawl_sources(id);
ALTER TABLE jobs ADD COLUMN missing_count INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX jobs_crawl_identity
  ON jobs(crawl_source_id, external_job_id)
  WHERE crawl_source_id IS NOT NULL;
```

Add repository methods `ensure_crawl_source`, `start_crawl_run`, `complete_crawl_run`, `find_crawled_job`, `create_crawled_job`, `mark_seen`, `append_changed_version`, `mark_missing`, `mark_offline`, and `reopen_job`. Each accepts domain values and performs SQL only; each event row has one of `created`, `changed`, `missing`, `offline`, or `reopened`.

- [ ] **Step 4: Run migration and existing repository tests**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_repository.py \
  extensions/career_mcp/tests/test_crawler_repository.py -q
```

Expected: all tests pass and migration 1 manual-JD behavior remains compatible.

### Task 4: Implement The Transactional Pipeline And State Tests

**Files:**
- Create: `extensions/career_mcp/services/crawler.py`
- Create: `extensions/career_mcp/tests/fixtures/fake_source_jobs.json`
- Create: `extensions/career_mcp/tests/test_crawler_service.py`

- [ ] **Step 1: Write failing state-machine tests**

```python
def test_successive_runs_cover_created_unchanged_changed_missing_offline_and_reopened(tmp_path):
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"))
    created = service.crawl(FakeAdapter("fake-source", [snapshot("v1")]))
    unchanged = service.crawl(FakeAdapter("fake-source", [snapshot("v1")]))
    changed = service.crawl(FakeAdapter("fake-source", [snapshot("v2")]))
    missing = service.crawl(FakeAdapter("fake-source", []))
    offline = service.crawl(FakeAdapter("fake-source", []))
    reopened = service.crawl(FakeAdapter("fake-source", [snapshot("v2")]))

    assert created.transitions == {"created": 1}
    assert unchanged.transitions == {"unchanged": 1}
    assert changed.transitions == {"changed": 1}
    assert missing.transitions == {"missing": 1}
    assert offline.transitions == {"offline": 1}
    assert reopened.transitions == {"reopened": 1}
```

Add a separate failing test where `FakeAdapter` raises `RuntimeError("fixture failure")`; assert the run is failed and the stored job remains active with unchanged `missing_count`.

- [ ] **Step 2: Run the service tests to confirm failure**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_crawler_service.py -q
```

Expected: import error because `CrawlerService` does not exist.

- [ ] **Step 3: Implement minimal orchestration**

```python
class CrawlerService:
    def crawl(self, adapter: JobAdapter, *, dry_run: bool = False) -> CrawlResult:
        snapshots = adapter.fetch_jobs()
        normalized = [normalize_snapshot(adapter.source_slug, item) for item in snapshots]
        if dry_run:
            return self._preview_transitions(adapter.source_slug, normalized)
        return self._persist_successful_run(adapter.source_slug, normalized)
```

`_persist_successful_run` starts one `BEGIN` transaction, writes one successful `crawl_runs` row, processes observed identities, then evaluates absence only after all snapshots normalize successfully. The adapter exception path writes a failed run in its own transaction and returns without absence processing.

- [ ] **Step 4: Run state-machine tests**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_crawler_service.py -q
```

Expected: all transition and adapter-failure tests pass offline.

### Task 5: Expose Minimal Stage 3 MCP Read And Crawl Tools

**Files:**
- Modify: `extensions/career_mcp/services/crawler.py`
- Modify: `extensions/career_mcp/server.py`
- Create: `extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] **Step 1: Write failing MCP envelope tests**

```python
def test_list_sources_and_recent_events_return_envelopes(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    assert server.list_sources()["ok"] is True
    assert server.list_recent_job_events(limit=20)["ok"] is True

def test_crawl_source_dry_run_does_not_create_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    result = server.crawl_source(source_slug="fake-source", dry_run=True)
    assert result["ok"] is True
    assert not (tmp_path / "career" / "career.sqlite3").exists()
```

- [ ] **Step 2: Run MCP tests to confirm failure**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_stage3_tools.py -q
```

Expected: missing-tool import errors.

- [ ] **Step 3: Register minimal MCP tools**

```python
def list_sources() -> dict:
    return _ok(CrawlerService().list_sources())

def list_recent_job_events(limit: int = 20) -> dict:
    return _ok(CrawlerService().list_recent_events(limit=limit))

def crawl_source(source_slug: str, dry_run: bool = False) -> dict:
    return _ok(CrawlerService().crawl_registered_source(source_slug, dry_run=dry_run))
```

Validate `limit` in the service as `1 <= limit <= 100`. Return `INVALID_INPUT`, `SOURCE_NOT_FOUND`, and `PERSISTENCE_ERROR` through existing envelope helpers. Register all three with `mcp.tool()`. Do not add a scheduler or a real network adapter.

- [ ] **Step 4: Run Stage 3 MCP tests**

Run:
```bash
.venv/bin/pytest extensions/career_mcp/tests/test_stage3_tools.py -q
```

Expected: all tests pass.

### Task 6: Full Regression, Documentation, And Gate Update

**Files:**
- Modify: `README.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Document Stage 3 local-only usage**

Add a README section identifying `FakeAdapter` as test-only, `crawl_source(..., dry_run=true)` as non-persistent, and the absence of real adapters or default network access.

- [ ] **Step 2: Run all affected tests**

Run:
```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests \
  tests/test_skills.py tests/test_builtin_personas.py -q
git diff --check
```

Expected: all selected tests pass and diff check prints no errors.

- [ ] **Step 3: Update progress only after tests pass**

Record the exact test total, fixture-only guarantee, transition coverage, and remaining Stage 4 gate in `docs/11_DEVELOPMENT_LOG.md`. Mark Stage 3 as `通过` in `docs/12_TONIGHT_PROGRESS.md` only after all seven transition cases pass. Set the next smallest task to researching one public official source without implementing an adapter.

- [ ] **Step 4: Create focused commits**

```bash
git add extensions/career_mcp/domain/crawler.py \
  extensions/career_mcp/crawler \
  extensions/career_mcp/tests/test_crawler_normalize.py
git commit -m "feat(crawler): add offline snapshot normalization"
```

```bash
git add extensions/career_mcp/database extensions/career_mcp/services/crawler.py \
  extensions/career_mcp/server.py extensions/career_mcp/tests
git commit -m "feat(crawler): add fixture-tested crawl pipeline"
```

Do not include unrelated user work in either commit.

## Plan Self-Review

- Spec coverage: Task 1 covers the Stage 2 gate; Tasks 2-5 cover domain boundaries, schema, pipeline, state model, MCP tools, and offline tests; Task 6 covers documentation and regressions.
- Placeholder scan: no `TODO`, `TBD`, or deferred implementation instructions are used.
- Type consistency: `JobSnapshot`, `NormalizedJob`, `JobAdapter`, `FakeAdapter`, `CrawlerService`, and `CrawlResult` are defined before their consuming tasks.
