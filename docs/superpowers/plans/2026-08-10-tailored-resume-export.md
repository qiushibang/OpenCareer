# Tailored Resume DOCX/PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a traceable, user-confirmed tailored-resume workflow that exports one selected confirmed resume as an ATS-friendly DOCX/PDF pair without exposing private contact data to the model.

**Architecture:** Schema v8 persists versioned tailored-resume drafts and export metadata. A pure Domain validator binds every proposed bullet to one authoritative resume fact, a transactional Draft Service enforces fresh snapshots and CAS confirmation, and an Export Service renders one frozen version to DOCX before converting that same file to PDF and publishing the pair as one directory. Career MCP may prepare and submit proposals, while only authenticated HTTP/GUI actions may confirm and export.

**Tech Stack:** Python 3.12, SQLite, FastAPI, FastMCP, `python-docx`, LibreOffice `soffice`, `pypdf`, React 18, TypeScript, Vitest, pytest, Playwright

---

## File Map

**Create**

- `extensions/career_mcp/domain/tailored_resumes.py`: pure source-bundle and proposal validation.
- `extensions/career_mcp/database/tailored_resume_repository.py`: draft/export SQL and row mapping.
- `extensions/career_mcp/services/tailored_resumes.py`: prepare, submit, decision, confirm, freshness, CAS.
- `extensions/career_mcp/services/tailored_resume_exports.py`: ATS DOCX renderer, fixed LibreOffice conversion, validation, atomic publication.
- `extensions/career_mcp/tests/test_tailored_resumes.py`: pure Domain tests.
- `extensions/career_mcp/tests/test_tailored_resume_service.py`: draft transaction, freshness, CAS and confirmation tests.
- `extensions/career_mcp/tests/test_tailored_resume_exports.py`: DOCX/PDF and publication tests.
- `.coworker/skills/career-tailored-resume/SKILL.md`: Agent proposal workflow and hard fact boundaries.
- `surfaces/gui/src/careerTailoredResume.ts`: opaque-ID Agent prompt builder.
- `surfaces/gui/src/careerTailoredResume.test.ts`: prompt privacy regression.
- `surfaces/gui/src/components/CareerTailoredResumePanel.tsx`: draft review, decisions, confirm, export, downloads.
- `surfaces/gui/src/components/CareerTailoredResumePanel.test.tsx`: GUI behavior and conflict tests.

**Modify**

- `extensions/career_mcp/database/migrations.py`: schema v8 tables and indexes using transactional `execute()`.
- `extensions/career_mcp/tests/test_migrations.py`: v8 schema and failure/retry tests.
- `extensions/career_mcp/server.py`: prepare/submit MCP factories, wrappers and registration.
- `extensions/career_mcp/tests/test_resume_tools.py`: tailored-resume MCP wrapper tests.
- `tests/test_mcp.py`: discovery of the two new tools.
- `tests/test_skills.py`: tailored-resume Skill policy assertions.
- `coworker/server/app.py`: draft HTTP, confirm/export, authenticated downloads and stable errors.
- `tests/test_career_jobs_api.py`: HTTP contract, CAS, confirmation and download tests.
- `surfaces/gui/src/api.ts`: tailored draft/export types and API clients.
- `surfaces/gui/src/careerJobsApi.test.ts`: tailored-resume request tests.
- `surfaces/gui/src/components/CareerJobMatchPanel.tsx`: single-fresh-result entry and embedded draft panel.
- `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`: entry/payload and panel integration.
- `surfaces/gui/src/App.tsx`: route tailored-resume opaque IDs into a new Career conversation.
- `.gitignore`: explicitly ignore `artifacts/tailored-resumes/`.
- `docs/11_DEVELOPMENT_LOG.md`: Gate evidence, test counts and real acceptance.
- `docs/12_TONIGHT_PROGRESS.md`: stage status and next OCR gate.

## Shared Contracts

Use these exact internal values throughout the plan:

```python
TAILORED_SECTIONS = ("education", "experience", "project", "skill")
DRAFT_STATUSES = ("draft", "review", "confirmed", "exported", "stale")
ITEM_DECISIONS = ("pending", "confirmed", "omitted")
TEMPLATE_ID = "ats_single_column_zh_v1"
```

Proposal input:

```json
{
  "section": "project",
  "source_path": "project[0].highlights[0]",
  "source_text": "使用 Python 构建检索服务",
  "proposed_text": "使用 Python 构建检索服务，支持核心业务检索流程",
  "linked_requirement": "熟悉 Python",
  "evidence_status": "direct",
  "order": 0,
  "entry_path": "project[0]",
  "field": "highlights[0]",
  "editable": true,
  "required": false
}
```

`prepare` first persists every displayable confirmed resume fact as a baseline
`source` item with `proposed_text=source_text` and `decision="confirmed"`.
Agent proposals update only an editable direct/related subset and never
replace that baseline. Every item has deterministic `id`, `entry_path`,
`field`, `editable`, and `required`; an accepted Agent rewrite changes only
that item to `decision="pending"`.

Stable service errors:

```text
INVALID_INPUT
JOB_NOT_FOUND
RESUME_NOT_FOUND
SNAPSHOT_MISMATCH
STALE_DRAFT
VERSION_CONFLICT
PROPOSAL_VALIDATION_FAILED
CONFIRMATION_REQUIRED
PDF_CONVERTER_UNAVAILABLE
PAGE_LIMIT_EXCEEDED
PERSISTENCE_ERROR
```

### Task 1: Schema v8 and Pure Proposal Validation

**Files:**

- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/tests/test_migrations.py`
- Create: `extensions/career_mcp/domain/tailored_resumes.py`
- Create: `extensions/career_mcp/tests/test_tailored_resumes.py`

- [ ] **Step 1: Write schema v8 RED tests**

Append:

```python
def test_schema_v8_adds_tailored_resume_tables(tmp_path: Path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)

    assert schema_version(connection) == 8
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "tailored_resume_drafts",
        "tailored_resume_exports",
    } <= tables
    assert {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(tailored_resume_drafts)"
        )
    } == {
        "id",
        "job_id",
        "resume_import_id",
        "snapshot_id",
        "job_content_hash",
        "resume_revision_at",
        "template_id",
        "status",
        "items_json",
        "version",
        "created_at",
        "updated_at",
        "confirmed_at",
        "exported_at",
    }
    connection.close()


def test_schema_v8_failure_is_atomic_and_retryable(
    tmp_path: Path,
    monkeypatch,
):
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 7)
    migrate(connection)
    connection.execute(
        "CREATE TABLE tailored_resume_exports(id TEXT PRIMARY KEY)"
    )
    connection.commit()
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 8)

    with pytest.raises(sqlite3.OperationalError):
        migrate(connection)

    assert schema_version(connection) == 7
    assert connection.execute(
        """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'table' AND name = 'tailored_resume_drafts'
        """
    ).fetchone()[0] == 0

    connection.execute("DROP TABLE tailored_resume_exports")
    connection.commit()
    migrate(connection)
    assert schema_version(connection) == 8
    connection.close()
```

- [ ] **Step 2: Write pure Domain RED tests**

Create:

```python
import copy

import pytest

from extensions.career_mcp.domain.tailored_resumes import (
    TailoredResumeValidationError,
    build_baseline_items,
    build_source_facts,
    normalize_proposal_items,
)


SOURCE_FACTS = [
    {
        "section": "project",
        "path": "project[0].highlights[0]",
        "text": "使用 Python 构建检索服务，吞吐提升 20%",
        "terms": ["python"],
        "entry_path": "project[0]",
        "field": "highlights[0]",
        "editable": True,
        "required": False,
    },
    {
        "section": "skill",
        "path": "skill[0].name",
        "text": "Python",
        "terms": ["python"],
        "entry_path": "skill[0]",
        "field": "name",
        "editable": False,
        "required": True,
    },
]
REQUIREMENTS = [
    {
        "requirement": "熟悉 Python",
        "status": "direct",
        "evidence_paths": ["project[0].highlights[0]"],
    },
    {
        "requirement": "具有 Kubernetes 经验",
        "status": "none",
        "evidence_paths": [],
    },
]


def proposal(**overrides):
    value = {
        "section": "project",
        "source_path": "project[0].highlights[0]",
        "source_text": "使用 Python 构建检索服务，吞吐提升 20%",
        "proposed_text": "使用 Python 构建检索服务，吞吐提升 20%",
        "linked_requirement": "熟悉 Python",
        "evidence_status": "direct",
        "order": 0,
    }
    value.update(overrides)
    return value


def test_normalize_proposals_binds_authoritative_source():
    items = normalize_proposal_items(
        [proposal()],
        source_facts=SOURCE_FACTS,
        requirements=REQUIREMENTS,
    )

    assert items[0]["decision"] == "pending"
    assert items[0]["source_text"] == SOURCE_FACTS[0]["text"]
    assert items[0]["id"].startswith("item-")


def test_build_baseline_preserves_all_confirmed_source_facts():
    items = build_baseline_items(SOURCE_FACTS)

    assert len(items) == len(SOURCE_FACTS)
    assert all(item["evidence_status"] == "source" for item in items)
    assert all(item["decision"] == "confirmed" for item in items)
    assert items[0]["entry_path"] == "project[0]"
    assert items[1]["required"] is True


def test_build_source_facts_preserves_entry_structure():
    facts = build_source_facts(
        {
            "experience": [
                {
                    "company": "示例公司",
                    "title": "算法工程师",
                    "start_date": "2024-01",
                    "highlights": ["使用 Python 构建检索服务"],
                }
            ]
        }
    )

    company = next(item for item in facts if item["field"] == "company")
    highlight = next(
        item for item in facts if item["field"] == "highlights[0]"
    )
    assert company["entry_path"] == "experience[0]"
    assert company["required"] is True
    assert company["editable"] is False
    assert highlight["editable"] is True


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"source_path": "experience[0].summary"}, "SOURCE_NOT_FOUND"),
        ({"source_text": "伪造原文"}, "SOURCE_MISMATCH"),
        (
            {
                "section": "skill",
                "source_path": "skill[0].name",
                "source_text": "Python",
                "proposed_text": "Python 与 Go",
            },
            "NON_EDITABLE_SOURCE",
        ),
        ({"proposed_text": "吞吐提升 30%"}, "NEW_NUMBER"),
        ({"proposed_text": "使用 Kubernetes 构建服务"}, "NEW_SKILL"),
        (
            {
                "linked_requirement": "具有 Kubernetes 经验",
                "evidence_status": "none",
            },
            "INVALID_EVIDENCE_BINDING",
        ),
        ({"proposed_text": "联系 secret@example.com"}, "SENSITIVE_CONTENT"),
        ({"proposed_text": "100% 匹配岗位"}, "FORBIDDEN_CONCLUSION"),
    ],
)
def test_normalize_proposals_rejects_boundary_violations(changes, code):
    with pytest.raises(TailoredResumeValidationError) as error:
        normalize_proposal_items(
            [proposal(**changes)],
            source_facts=SOURCE_FACTS,
            requirements=REQUIREMENTS,
        )

    assert code in {item["code"] for item in error.value.violations}


def test_normalize_proposals_rejects_duplicate_source_path():
    with pytest.raises(TailoredResumeValidationError) as error:
        normalize_proposal_items(
            [proposal(), copy.deepcopy(proposal(order=1))],
            source_facts=SOURCE_FACTS,
            requirements=REQUIREMENTS,
        )

    assert "DUPLICATE_SOURCE" in {
        item["code"] for item in error.value.violations
    }
```

- [ ] **Step 3: Run RED tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_migrations.py::test_schema_v8_adds_tailored_resume_tables \
  extensions/career_mcp/tests/test_migrations.py::test_schema_v8_failure_is_atomic_and_retryable \
  extensions/career_mcp/tests/test_tailored_resumes.py
```

Expected: collection fails because `domain.tailored_resumes` does not exist and
schema remains v7.

- [ ] **Step 4: Implement schema v8 with transactional statements**

Set `SCHEMA_VERSION = 8`. Add after v7:

```python
if version < 8 <= SCHEMA_VERSION:
    statements = (
        """
        CREATE TABLE tailored_resume_drafts (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            resume_import_id TEXT NOT NULL REFERENCES resume_imports(id),
            snapshot_id TEXT NOT NULL REFERENCES job_resume_matches(id),
            job_content_hash TEXT NOT NULL,
            resume_revision_at TEXT NOT NULL,
            template_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN (
                'draft', 'review', 'confirmed', 'exported', 'stale'
            )),
            items_json TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            exported_at TEXT
        )
        """,
        """
        CREATE INDEX tailored_resume_drafts_lookup
        ON tailored_resume_drafts(
            job_id, resume_import_id, updated_at DESC, id DESC
        )
        """,
        """
        CREATE TABLE tailored_resume_exports (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES tailored_resume_drafts(id),
            draft_version INTEGER NOT NULL,
            directory_path TEXT NOT NULL,
            docx_path TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            docx_sha256 TEXT NOT NULL,
            pdf_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(draft_id, draft_version)
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (8, utc_now_iso()),
    )
```

Do not use `executescript()` for v8.

- [ ] **Step 5: Implement pure validation**

Create `tailored_resumes.py` with this public interface:

```python
from __future__ import annotations

import hashlib
import re
import unicodedata

from .matching import extract_terms
from .privacy import contains_sensitive_value

TAILORED_SECTIONS = ("education", "experience", "project", "skill")
DRAFT_STATUSES = ("draft", "review", "confirmed", "exported", "stale")
ITEM_DECISIONS = ("pending", "confirmed", "omitted")
TEMPLATE_ID = "ats_single_column_zh_v1"

_NUMBER = re.compile(
    r"(?:\d+(?:\.\d+)?%?|\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2})?)"
)
_URL = re.compile(r"https?://|www\\.", re.IGNORECASE)
_FORBIDDEN = (
    re.compile(r"匹配率|录用概率|100%\\s*匹配"),
    re.compile(r"(?:符合|不符合|满足|不满足).{0,8}(?:要求|资格)"),
)


class TailoredResumeValidationError(ValueError):
    def __init__(self, violations: list[dict[str, str]]) -> None:
        super().__init__("tailored resume proposal validation failed")
        self.violations = violations


def build_source_facts(sections: dict) -> list[dict]:
    facts: list[dict] = []
    for section in TAILORED_SECTIONS:
        entries = sections.get(section)
        if not isinstance(entries, list):
            continue
        for entry_index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            entry_path = f"{section}[{entry_index}]"
            _append_source_fields(
                facts,
                section=section,
                entry_path=entry_path,
                path=entry_path,
                value=entry,
            )
    return facts


def _append_source_fields(
    facts: list[dict],
    *,
    section: str,
    entry_path: str,
    path: str,
    value: object,
) -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _append_source_fields(
                facts,
                section=section,
                entry_path=entry_path,
                path=f"{path}[{index}]",
                value=item,
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _append_source_fields(
                facts,
                section=section,
                entry_path=entry_path,
                path=f"{path}.{key}",
                value=item,
            )
        return
    if not isinstance(value, str) or not value.strip():
        return
    text = value.strip()
    if contains_sensitive_value(text):
        return
    field = path.removeprefix(f"{entry_path}.")
    editable = bool(
        re.search(
            r"(?:^|\\.)(?:summary|description|evidence)$|"
            r"(?:^|\\.)highlights\\[\\d+\\]$",
            field,
        )
    )
    required = field in {
        "school",
        "institution",
        "degree",
        "company",
        "title",
        "name",
        "start_date",
        "end_date",
    }
    facts.append(
        {
            "section": section,
            "path": path,
            "text": text,
            "terms": extract_terms(text),
            "entry_path": entry_path,
            "field": field,
            "editable": editable,
            "required": required,
        }
    )


def build_baseline_items(source_facts: list[dict]) -> list[dict]:
    result = []
    for index, source in enumerate(source_facts):
        source_path = str(source["path"])
        source_text = str(source["text"]).strip()
        result.append(
            {
                "id": "item-" + hashlib.sha256(
                    source_path.encode("utf-8")
                ).hexdigest()[:16],
                "section": source["section"],
                "source_path": source_path,
                "source_text": source_text,
                "proposed_text": source_text,
                "linked_requirement": None,
                "evidence_status": "source",
                "decision": "confirmed",
                "order": index,
                "entry_path": source["entry_path"],
                "field": source["field"],
                "editable": bool(source["editable"]),
                "required": bool(source["required"]),
            }
        )
    return result


def normalize_proposal_items(
    items: object,
    *,
    source_facts: list[dict],
    requirements: list[dict],
) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise TailoredResumeValidationError(
            [_violation("INVALID_ITEMS", "items must be a non-empty list")]
        )
    sources = {str(item["path"]): item for item in source_facts}
    requirement_map = {
        str(item["requirement"]): item for item in requirements
    }
    normalized = []
    seen_paths: set[str] = set()
    violations: list[dict[str, str]] = []
    for index, raw in enumerate(items):
        path = f"items[{index}]"
        if not isinstance(raw, dict):
            violations.append(_violation("INVALID_ITEM", path))
            continue
        source_path = _text(raw.get("source_path"))
        source = sources.get(source_path)
        if source is None:
            violations.append(_violation("SOURCE_NOT_FOUND", path))
            continue
        if source_path in seen_paths:
            violations.append(_violation("DUPLICATE_SOURCE", path))
        seen_paths.add(source_path)
        source_text = _text(raw.get("source_text"))
        proposed = _text(raw.get("proposed_text"))
        requirement_text = _text(raw.get("linked_requirement"))
        requirement = requirement_map.get(requirement_text)
        if _normalized(source_text) != _normalized(source["text"]):
            violations.append(_violation("SOURCE_MISMATCH", path))
        if (
            raw.get("section") not in TAILORED_SECTIONS
            or raw.get("section") != source["section"]
            or not proposed
            or len(proposed) > 500
        ):
            violations.append(_violation("INVALID_ITEM", path))
        if not source.get("editable"):
            violations.append(_violation("NON_EDITABLE_SOURCE", path))
        if (
            requirement is None
            or requirement.get("status") not in {"direct", "related"}
            or raw.get("evidence_status") != requirement.get("status")
            or source_path not in requirement.get("evidence_paths", [])
        ):
            violations.append(
                _violation("INVALID_EVIDENCE_BINDING", path)
            )
        if not _tokens(proposed, _NUMBER) <= _tokens(source["text"], _NUMBER):
            violations.append(_violation("NEW_NUMBER", path))
        if _URL.search(proposed) and not _URL.search(str(source["text"])):
            violations.append(_violation("NEW_URL", path))
        if not set(extract_terms(proposed)) <= set(source.get("terms", [])):
            violations.append(_violation("NEW_SKILL", path))
        if contains_sensitive_value(proposed):
            violations.append(_violation("SENSITIVE_CONTENT", path))
        if any(pattern.search(proposed) for pattern in _FORBIDDEN):
            violations.append(_violation("FORBIDDEN_CONCLUSION", path))
        normalized.append(
            {
                "id": "item-" + hashlib.sha256(
                    source_path.encode("utf-8")
                ).hexdigest()[:16],
                "section": source["section"],
                "source_path": source_path,
                "source_text": str(source["text"]).strip(),
                "proposed_text": proposed,
                "linked_requirement": requirement_text,
                "evidence_status": raw.get("evidence_status"),
                "decision": "pending",
                "order": index,
                "entry_path": source["entry_path"],
                "field": source["field"],
                "editable": True,
                "required": bool(source["required"]),
            }
        )
    if violations:
        raise TailoredResumeValidationError(violations)
    return normalized
```

Add private `_text`, `_normalized`, `_tokens`, and `_violation` helpers. `_tokens`
must use `unicodedata.normalize("NFKC", value)` and return the exact regex matches.

- [ ] **Step 6: Run Task 1 tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_tailored_resumes.py
```

Expected: all pass and every existing schema assertion expects v8.

- [ ] **Step 7: Commit Task 1**

```bash
git add \
  extensions/career_mcp/database/migrations.py \
  extensions/career_mcp/domain/tailored_resumes.py \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_tailored_resumes.py
git commit -m "feat(career): add tailored resume draft schema"
```

### Task 2: Draft Repository and Prepare/Submit Service

**Files:**

- Create: `extensions/career_mcp/database/tailored_resume_repository.py`
- Create: `extensions/career_mcp/services/tailored_resumes.py`
- Create: `extensions/career_mcp/tests/test_tailored_resume_service.py`

- [ ] **Step 1: Write prepare/submit RED tests**

Use the existing `_seed()` fixture from `test_match_service.py`:

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from extensions.career_mcp.services.tailored_resumes import (
    TailoredResumeService,
    TailoredResumeServiceError,
)
from extensions.career_mcp.tests.test_match_service import NOW, _seed


def seeded_service(tmp_path):
    config, _, matches, job_id, resume_id = _seed(tmp_path)
    matched = matches.analyze(job_id, [resume_id])
    snapshot_id = matched["results"][0]["snapshot_id"]
    service = TailoredResumeService(config, clock=lambda: NOW)
    return service, config, job_id, resume_id, snapshot_id


def test_prepare_returns_masked_authoritative_source_bundle(tmp_path):
    service, _, job_id, resume_id, snapshot_id = seeded_service(tmp_path)

    result = service.prepare(job_id, resume_id, snapshot_id)

    assert result["status"] == "draft"
    assert result["version"] == 1
    assert result["source_facts"]
    assert len(result["items"]) == len(result["source_facts"])
    assert all(
        item["evidence_status"] == "source"
        and item["decision"] == "confirmed"
        for item in result["items"]
    )
    serialized = str(result)
    assert "phone" not in serialized.casefold()
    assert "email" not in serialized.casefold()
    assert "private_path" not in serialized
    assert "upload_token" not in serialized


def test_submit_proposals_uses_cas_and_enters_review(tmp_path):
    service, _, job_id, resume_id, snapshot_id = seeded_service(tmp_path)
    draft = service.prepare(job_id, resume_id, snapshot_id)
    requirement = next(
        item
        for item in draft["requirements"]
        if item["status"] in {"direct", "related"}
        and item["evidence_paths"]
    )
    source = next(
        item
        for item in draft["source_facts"]
        if item["editable"]
        and item["path"] in requirement["evidence_paths"]
    )

    updated = service.submit_proposals(
        draft["id"],
        expected_version=1,
        items=[
            {
                "section": source["section"],
                "source_path": source["path"],
                "source_text": source["text"],
                "proposed_text": source["text"],
                "linked_requirement": requirement["requirement"],
                "evidence_status": requirement["status"],
                "order": 0,
            }
        ],
    )

    assert updated["status"] == "review"
    assert updated["version"] == 2
    rewritten = next(
        item
        for item in updated["items"]
        if item["source_path"] == source["path"]
    )
    assert rewritten["decision"] == "pending"
    assert len(updated["items"]) == len(draft["items"])


def test_submit_rejects_stale_version(tmp_path):
    service, _, job_id, resume_id, snapshot_id = seeded_service(tmp_path)
    draft = service.prepare(job_id, resume_id, snapshot_id)
    service.submit_proposals(
        draft["id"],
        expected_version=1,
        items=_valid_items(draft),
    )

    with pytest.raises(TailoredResumeServiceError) as error:
        service.submit_proposals(
            draft["id"],
            expected_version=1,
            items=_valid_items(draft),
        )

    assert error.value.code == "VERSION_CONFLICT"


def test_prepare_rejects_snapshot_for_another_resume(tmp_path):
    service, _, job_id, _, _ = seeded_service(tmp_path)

    with pytest.raises(TailoredResumeServiceError) as error:
        service.prepare(job_id, "missing-resume", "missing-snapshot")

    assert error.value.code in {"RESUME_NOT_FOUND", "SNAPSHOT_MISMATCH"}
```

Add `_valid_items(draft)` in the test file by selecting the first requirement
whose `evidence_paths` contains a source path.

- [ ] **Step 2: Run RED tests**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_tailored_resume_service.py
```

Expected: collection fails because repository and service modules do not exist.

- [ ] **Step 3: Implement Repository**

Create a repository with these methods:

```python
class TailoredResumeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        migrate(connection)

    def get(self, draft_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM tailored_resume_drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        return self._draft(row) if row else None

    def latest(self, job_id: str, resume_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT * FROM tailored_resume_drafts
            WHERE job_id = ? AND resume_import_id = ?
            ORDER BY updated_at DESC, rowid DESC
            LIMIT 1
            """,
            (job_id, resume_id),
        ).fetchone()
        return self._draft(row) if row else None

    def get_export(self, draft_id: str, version: int) -> dict | None:
        row = self.connection.execute(
            """
            SELECT * FROM tailored_resume_exports
            WHERE draft_id = ? AND draft_version = ?
            """,
            (draft_id, version),
        ).fetchone()
        return dict(row) if row else None

    def create(
        self,
        *,
        draft_id: str,
        job_id: str,
        resume_id: str,
        snapshot_id: str,
        job_content_hash: str,
        resume_revision_at: str,
        items: list[dict],
        now: str,
    ) -> dict:
        self.connection.execute(
            """
            INSERT INTO tailored_resume_drafts(
                id, job_id, resume_import_id, snapshot_id,
                job_content_hash, resume_revision_at, template_id,
                status, items_json, version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, 1, ?, ?)
            """,
            (
                draft_id,
                job_id,
                resume_id,
                snapshot_id,
                job_content_hash,
                resume_revision_at,
                TEMPLATE_ID,
                self._json(items),
                now,
                now,
            ),
        )
        return self.get(draft_id)

    def update_if_version(
        self,
        draft_id: str,
        expected_version: int,
        *,
        status: str,
        items: list[dict],
        now: str,
        confirmed_at: str | None = None,
        exported_at: str | None = None,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE tailored_resume_drafts
            SET status = ?, items_json = ?, version = version + 1,
                updated_at = ?,
                confirmed_at = COALESCE(?, confirmed_at),
                exported_at = COALESCE(?, exported_at)
            WHERE id = ? AND version = ?
            """,
            (
                status,
                self._json(items),
                now,
                confirmed_at,
                exported_at,
                draft_id,
                expected_version,
            ),
        )
        return cursor.rowcount == 1
```

Row mapping must parse `items_json`, expose `resume_id`, and convert `version`
to int. Sort latest by `updated_at DESC, rowid DESC`.

- [ ] **Step 4: Implement prepare and submit**

`TailoredResumeService.prepare()` must:

1. Normalize three IDs.
2. Call `MatchService.analyze(job_id, [resume_id],
   expected_snapshot_ids=[snapshot_id])`.
3. Read the selected resume with `ResumeRepository.get_resume_match_input`.
4. Use `build_source_facts(resume["sections"])` to preserve section,
   entry path, field, editability and required structure.
5. Build and persist the complete baseline with
   `build_baseline_items(source_facts)` before returning the draft.
6. Return each source with
   `{section, path, text, terms, entry_path, field, editable, required}`.
7. Convert match requirements to
   `{requirement, status, evidence_paths}`.
8. Reuse a non-stale `draft/review/confirmed` row with identical identity, or
   insert a new UUID row.

Public signatures:

```python
class TailoredResumeServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        violations: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.violations = list(violations or [])


```

Implement `prepare(job_id, resume_id, snapshot_id) -> dict` and
`submit_proposals(draft_id, *, expected_version, items) -> dict` on
`TailoredResumeService`.

`submit_proposals()` must initialize repositories before
`BEGIN IMMEDIATE`, read the draft, re-run freshness validation, call
`normalize_proposal_items`, merge the returned subset into baseline items by
deterministic item ID, and update from `draft` to `review` with CAS. It must
preserve every baseline item not named by a proposal and reject a proposal for
an unknown or non-editable path.
Map Domain violations to `PROPOSAL_VALIDATION_FAILED` and preserve the
structured violations.

- [ ] **Step 5: Add concurrent CAS RED/GREEN**

Add:

```python
def test_two_proposal_writers_allow_only_one_version(tmp_path):
    service, config, job_id, resume_id, snapshot_id = seeded_service(tmp_path)
    draft = service.prepare(job_id, resume_id, snapshot_id)
    barrier = Barrier(2)

    def submit():
        local = TailoredResumeService(config, clock=lambda: NOW)
        barrier.wait()
        try:
            return local.submit_proposals(
                draft["id"],
                expected_version=1,
                items=_valid_items(draft),
            )["version"]
        except TailoredResumeServiceError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))

    assert sorted(map(str, results)) == ["2", "VERSION_CONFLICT"]
```

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_tailored_resumes.py \
  extensions/career_mcp/tests/test_tailored_resume_service.py
```

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  extensions/career_mcp/database/tailored_resume_repository.py \
  extensions/career_mcp/services/tailored_resumes.py \
  extensions/career_mcp/tests/test_tailored_resume_service.py
git commit -m "feat(career): persist tailored resume drafts"
```

### Task 3: User Decisions, Confirmation and HTTP Draft Contract

**Files:**

- Modify: `extensions/career_mcp/services/tailored_resumes.py`
- Modify: `extensions/career_mcp/tests/test_tailored_resume_service.py`
- Modify: `coworker/server/app.py`
- Modify: `tests/test_career_jobs_api.py`

- [ ] **Step 1: Write decision and confirmation RED tests**

Append:

```python
def reviewed_draft(tmp_path):
    service, config, job_id, resume_id, snapshot_id = seeded_service(tmp_path)
    draft = service.prepare(job_id, resume_id, snapshot_id)
    reviewed = service.submit_proposals(
        draft["id"],
        expected_version=draft["version"],
        items=_valid_items(draft),
    )
    return service, config, reviewed


def test_user_edit_returns_item_to_pending(tmp_path):
    service, _, draft = reviewed_draft(tmp_path)
    item = draft["items"][0]

    confirmed = service.update_items(
        draft["id"],
        expected_version=draft["version"],
        changes=[{"id": item["id"], "decision": "confirmed"}],
    )
    edited = service.update_items(
        draft["id"],
        expected_version=confirmed["version"],
        changes=[
            {
                "id": item["id"],
                "proposed_text": item["source_text"],
                "decision": "confirmed",
            }
        ],
    )

    assert edited["items"][0]["decision"] == "pending"
    assert edited["status"] == "review"


def test_confirm_requires_every_item_decided(tmp_path):
    service, _, draft = reviewed_draft(tmp_path)

    with pytest.raises(TailoredResumeServiceError) as error:
        service.confirm(
            draft["id"],
            expected_version=draft["version"],
        )

    assert error.value.code == "CONFIRMATION_REQUIRED"


def test_confirm_freezes_at_least_one_confirmed_item(tmp_path):
    service, _, draft = reviewed_draft(tmp_path)
    decided = service.update_items(
        draft["id"],
        expected_version=draft["version"],
        changes=[
            {"id": draft["items"][0]["id"], "decision": "confirmed"}
        ],
    )

    confirmed = service.confirm(
        draft["id"],
        expected_version=decided["version"],
    )

    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_at"] is not None
```

Also test a required/non-editable source item cannot be edited or omitted,
confirming a `draft` before Agent submission returns
`CONFIRMATION_REQUIRED`, stale job hash returns `STALE_DRAFT`, and editing an
exported draft creates a new draft ID with version 1.

- [ ] **Step 2: Run RED tests**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_tailored_resume_service.py \
  -k 'user_edit or confirm or stale or exported'
```

Expected: FAIL because `update_items()` and `confirm()` do not exist.

- [ ] **Step 3: Implement decision and confirmation methods**

Add `get(draft_id) -> dict`, `list_for_job(job_id) -> list[dict]`,
`update_items(draft_id, *, expected_version, changes) -> dict`, and
`confirm(draft_id, *, expected_version) -> dict`.

For every write:

- validate `expected_version` as non-negative int excluding bool;
- initialize Repository/migration before `BEGIN IMMEDIATE`;
- re-read authoritative job, resume and snapshot identity;
- reject `stale` or `exported` mutation;
- apply changes by item ID only;
- reject edits or `omitted` decisions for `required=true` or
  `editable=false` source items;
- permit a non-required `source` item to be omitted, but reject direct text
  edits until Agent has produced a direct/related proposal for that item;
- when `proposed_text` changes, rebuild one proposal through
  `normalize_proposal_items` and force `decision="pending"`;
- accept only `confirmed/omitted` decision values from GUI;
- confirm only a `review` draft with no pending item and at least one
  confirmed item;
- read result before commit and rollback every exception.

- [ ] **Step 4: Write HTTP RED tests**

Add to `tests/test_career_jobs_api.py` using a monkeypatched fake service:

```python
def test_tailored_resume_http_updates_confirms_and_lists(
    tmp_path,
    monkeypatch,
):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)
    service = SimpleNamespace(
        list_for_job=lambda value: [{"id": "draft-1"}],
        get=lambda value: {"id": value, "version": 2},
        update_items=lambda value, **kwargs: {
            "id": value,
            "version": 3,
            "status": "review",
        },
        confirm=lambda value, **kwargs: {
            "id": value,
            "version": 4,
            "status": "confirmed",
        },
    )
    monkeypatch.setattr(
        app_module,
        "career_tailored_resume_service",
        lambda: service,
    )

    listed = client.get(
        f"/v1/career/jobs/{job_id}/tailored-resumes"
    )
    detail = client.get("/v1/career/tailored-resumes/draft-1")
    updated = client.patch(
        "/v1/career/tailored-resumes/draft-1",
        json={
            "expected_version": 2,
            "changes": [{"id": "item-1", "decision": "confirmed"}],
        },
    )
    confirmed = client.post(
        "/v1/career/tailored-resumes/draft-1/confirm",
        json={"expected_version": 3},
    )

    assert listed.status_code == 200
    assert detail.json()["draft"]["version"] == 2
    assert updated.json()["draft"]["version"] == 3
    assert confirmed.json()["draft"]["status"] == "confirmed"
```

Import `coworker.server.app` as `app_module` in the test. Add these module-level
factories so tests and future surfaces can replace only the domain dependency:

```python
def career_tailored_resume_service():
    from extensions.career_mcp.services.tailored_resumes import (
        TailoredResumeService,
    )
    return TailoredResumeService()


def career_tailored_export_service():
    from extensions.career_mcp.services.tailored_resume_exports import (
        TailoredResumeExportService,
    )
    return TailoredResumeExportService()
```

Do not add a global exception handler.

- [ ] **Step 5: Implement HTTP routes and stable error mapping**

Add routes with direct Service delegation:

```python
@app.get("/v1/career/jobs/{job_id}/tailored-resumes")
def tailored_resume_list(job_id: str):
    try:
        return {
            "ok": True,
            "drafts": career_tailored_resume_service().list_for_job(job_id),
        }
    except Exception as exc:
        return career_tailored_resume_error(exc)

@app.get("/v1/career/tailored-resumes/{draft_id}")
def tailored_resume_get(draft_id: str):
    try:
        return {
            "ok": True,
            "draft": career_tailored_resume_service().get(draft_id),
        }
    except Exception as exc:
        return career_tailored_resume_error(exc)

@app.patch("/v1/career/tailored-resumes/{draft_id}")
def tailored_resume_patch(
    draft_id: str,
    body: Any = Body(None),
):
    try:
        payload = body if isinstance(body, dict) else body
        return {
            "ok": True,
            "draft": career_tailored_resume_service().update_items(
                draft_id,
                expected_version=(
                    payload.get("expected_version")
                    if isinstance(payload, dict)
                    else None
                ),
                changes=(
                    payload.get("changes")
                    if isinstance(payload, dict)
                    else payload
                ),
            ),
        }
    except Exception as exc:
        return career_tailored_resume_error(exc)

@app.post("/v1/career/tailored-resumes/{draft_id}/confirm")
def tailored_resume_confirm(
    draft_id: str,
    body: Any = Body(None),
):
    try:
        payload = body if isinstance(body, dict) else {}
        return {
            "ok": True,
            "draft": career_tailored_resume_service().confirm(
                draft_id,
                expected_version=payload.get("expected_version"),
            ),
        }
    except Exception as exc:
        return career_tailored_resume_error(exc)
```

Map `INVALID_INPUT/PROPOSAL_VALIDATION_FAILED` to 400,
`JOB_NOT_FOUND/RESUME_NOT_FOUND` to 404,
`SNAPSHOT_MISMATCH/STALE_DRAFT/VERSION_CONFLICT/CONFIRMATION_REQUIRED` to
409, and unknown persistence failures to 409. Return:

```json
{
  "ok": false,
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "草稿已在其他入口更新，请刷新后重试。"
  }
}
```

Non-object JSON, including `null`, must reach Service validation and return
`400 INVALID_INPUT`, not FastAPI 422.

- [ ] **Step 6: Run Task 3 tests and commit**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_tailored_resume_service.py \
  tests/test_career_jobs_api.py -k 'tailored or tracking'
```

Expected: all pass.

```bash
git add \
  extensions/career_mcp/services/tailored_resumes.py \
  extensions/career_mcp/tests/test_tailored_resume_service.py \
  coworker/server/app.py \
  tests/test_career_jobs_api.py
git commit -m "feat(career): confirm tailored resume drafts"
```

### Task 4: ATS DOCX/PDF Export and Atomic Publication

**Files:**

- Create: `extensions/career_mcp/services/tailored_resume_exports.py`
- Create: `extensions/career_mcp/tests/test_tailored_resume_exports.py`
- Modify: `extensions/career_mcp/database/tailored_resume_repository.py`
- Modify: `coworker/server/app.py`
- Modify: `tests/test_career_jobs_api.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write exporter RED tests**

Create a fake converter that writes a minimal two-page-or-fewer PDF with
`pypdf.PdfWriter` so default tests never require the installed LibreOffice:

```python
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader, PdfWriter
import pytest

from extensions.career_mcp.services.tailored_resume_exports import (
    TailoredResumeExportService,
    TailoredResumeExportServiceError,
)


def fake_converter(docx_path: Path, output_dir: Path) -> Path:
    output = output_dir / f"{docx_path.stem}.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with output.open("wb") as handle:
        writer.write(handle)
    return output


def fake_pdf_validator(
    pdf_path: Path,
    required_text: list[str],
) -> int:
    assert pdf_path.is_file()
    assert required_text
    return 1


def test_export_creates_one_docx_pdf_pair(tmp_path):
    service, workspace, draft = _confirmed_export_service(
        tmp_path,
        converter=fake_converter,
        pdf_validator=fake_pdf_validator,
    )

    result = service.export(
        draft["id"],
        expected_version=draft["version"],
    )

    directory = workspace / result["directory_path"]
    assert sorted(path.name for path in directory.iterdir()) == [
        "resume.docx",
        "resume.pdf",
    ]
    document = Document(directory / "resume.docx")
    text = "\n".join(
        paragraph.text for paragraph in document.paragraphs
    )
    assert draft["job_title"] in text
    assert draft["items"][0]["proposed_text"] in text
    assert len(PdfReader(directory / "resume.pdf").pages) == 1
    assert len(result["docx_sha256"]) == 64
    assert len(result["pdf_sha256"]) == 64


def test_export_rejects_unconfirmed_draft_without_files(tmp_path):
    service, workspace, draft = _review_export_service(tmp_path)

    with pytest.raises(TailoredResumeExportServiceError) as error:
        service.export(draft["id"], expected_version=draft["version"])

    assert error.value.code == "CONFIRMATION_REQUIRED"
    assert not (workspace / "artifacts" / "tailored-resumes").exists()


def test_export_rejects_three_page_pdf_without_publication(tmp_path):
    def three_pages(docx_path, output_dir):
        output = output_dir / f"{docx_path.stem}.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=595, height=842)
        with output.open("wb") as handle:
            writer.write(handle)
        return output

    service, workspace, draft = _confirmed_export_service(
        tmp_path,
        converter=three_pages,
        pdf_validator=lambda path, required: 3,
    )

    with pytest.raises(TailoredResumeExportServiceError) as error:
        service.export(draft["id"], expected_version=draft["version"])

    assert error.value.code == "PAGE_LIMIT_EXCEEDED"
    assert not list(
        (workspace / "artifacts").glob("tailored-resumes/*")
    )
```

Add tests for converter missing, timeout, malformed PDF, same-version
idempotency, symlinked output root, pre-existing conflicting target,
metadata insert failure, commit failure and orphan quarantine.

`TailoredResumeExportService` accepts `converter` and `pdf_validator` only as
constructor dependencies for tests. Production factories never expose those
arguments through HTTP or MCP. The production PDF validator uses `pypdf` to
require 1–2 readable pages and, when text extraction is available, verifies all
required strings. If Chinese text extraction is empty, provenance is still
anchored by conversion from the already validated DOCX and the real
LibreOffice smoke/visual gate below.

- [ ] **Step 2: Run RED tests**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_tailored_resume_exports.py
```

Expected: collection fails because export service does not exist.

- [ ] **Step 3: Implement fixed ATS DOCX renderer**

Create:

```python
def render_ats_docx(model: dict) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.7)
    section.right_margin = Cm(1.7)
    normal = document.styles["Normal"]
    normal.font.name = "Arial Unicode MS"
    normal.font.size = Pt(10.5)
    _set_east_asia_font(normal, "Arial Unicode MS")

    name = document.add_paragraph()
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = name.add_run(model["name"])
    run.bold = True
    run.font.size = Pt(18)
    _set_east_asia_font(run, "Arial Unicode MS")

    contact = document.add_paragraph(
        " · ".join(model["contact_lines"])
    )
    contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(f"目标岗位：{model['job_title']}")

    for section_name in (
        "education",
        "experience",
        "project",
        "skill",
    ):
        entries = model["sections"].get(section_name, [])
        if not entries:
            continue
        _add_heading(document, SECTION_LABELS[section_name])
        for entry in entries:
            heading = document.add_paragraph()
            heading.paragraph_format.space_after = Pt(1)
            heading_run = heading.add_run(entry["heading"])
            heading_run.bold = True
            if entry.get("meta"):
                heading.add_run(f"  {entry['meta']}")
            for bullet in entry["bullets"]:
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.paragraph_format.space_after = Pt(3)
                paragraph.add_run(bullet)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
```

Set `w:eastAsia` through `qn("w:eastAsia")`. Do not render source paths,
snapshot IDs or internal statuses into the resume.

Before rendering, build the model by grouping confirmed non-omitted items by
`section` and `entry_path`, then map fields without concatenating unrelated
entries:

- education heading: `school/institution`; meta:
  `degree + major + start_date–end_date`;
- experience heading: `company + title`; meta:
  `location + start_date–end_date`;
- project heading: `name/title`; meta: `role + start_date–end_date`;
- skill heading: `name`; meta: `level`; optional evidence becomes bullets;
- editable summary/description/highlights become bullets under their own entry.

Missing fields are omitted, never replaced with guessed text. Add a renderer
test with two experience entries and assert each company/title remains adjacent
to only its own bullets.

- [ ] **Step 4: Implement fixed LibreOffice converter**

Production converter:

```python
def convert_docx_to_pdf(
    docx_path: Path,
    output_dir: Path,
    *,
    executable: Path | None = None,
    timeout_seconds: int = 30,
) -> Path:
    soffice = executable or discover_soffice()
    if soffice is None:
        raise TailoredResumeExportServiceError(
            "PDF_CONVERTER_UNAVAILABLE",
            "未找到 LibreOffice，暂时无法生成 PDF。",
        )
    profile = output_dir / ".libreoffice-profile"
    profile.mkdir()
    command = [
        str(soffice),
        "--headless",
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(docx_path),
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TailoredResumeExportServiceError(
            "PERSISTENCE_ERROR",
            "PDF 转换超时，请精简内容后重试。",
        ) from exc
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.is_file():
        raise TailoredResumeExportServiceError(
            "PERSISTENCE_ERROR",
            "PDF 转换失败，请检查本地 LibreOffice。",
        )
    return pdf_path
```

`discover_soffice()` may inspect only:

```text
/opt/homebrew/bin/soffice
/usr/local/bin/soffice
/Applications/LibreOffice.app/Contents/MacOS/soffice
PATH resolved with shutil.which("soffice")
```

The API must not accept an executable or arguments.

- [ ] **Step 5: Implement export transaction and compensation**

`TailoredResumeExportService.export(draft_id, expected_version)` must:

1. Validate IDs/version.
2. Read confirmed draft and exact selected resume.
3. Build local render model with basic name/phone/email and only confirmed
   items.
4. Create a random sibling temp directory under
   `artifacts/tailored-resumes`.
5. Write `resume.docx`, fsync, convert `resume.pdf`, validate page count,
   compute hashes.
6. Initialize Repository, `BEGIN IMMEDIATE`, recheck draft version/freshness.
7. Rename the complete temp directory to deterministic final directory.
8. Insert export metadata and CAS mark draft exported.
9. Fsync the final parent directory, then commit and return metadata.
10. On DB error after rename, rollback and remove final directory; if removal
    fails rename it `.orphan-<uuid>`.

Repository additions:

```python
def insert_export(self, record: dict) -> None:
    self.connection.execute(
        """
        INSERT INTO tailored_resume_exports(
            id, draft_id, draft_version, directory_path,
            docx_path, pdf_path, docx_sha256, pdf_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["id"],
            record["draft_id"],
            record["draft_version"],
            record["directory_path"],
            record["docx_path"],
            record["pdf_path"],
            record["docx_sha256"],
            record["pdf_sha256"],
            record["created_at"],
        ),
    )

def mark_exported_if_version(
    self,
    draft_id: str,
    expected_version: int,
    *,
    now: str,
) -> bool:
    cursor = self.connection.execute(
        """
        UPDATE tailored_resume_drafts
        SET status = 'exported', version = version + 1,
            updated_at = ?, exported_at = ?
        WHERE id = ? AND version = ? AND status = 'confirmed'
        """,
        (now, now, draft_id, expected_version),
    )
    return cursor.rowcount == 1
```

`tailored_resume_exports.draft_version` stores the confirmed content version
passed as `expected_version`. The draft row increments once when its status
changes to exported; that later row version is not the content version.

Before normal export, delete `.orphan-*` directories. Never return their
paths.

- [ ] **Step 6: Add HTTP export/download RED tests and implementation**

Add:

```python
def test_tailored_resume_export_and_download_are_authenticated(
    tmp_path,
    monkeypatch,
):
    client, _ = _client_with_jobs(tmp_path, monkeypatch)
    fake = SimpleNamespace(
        export=lambda draft_id, expected_version: {
            "id": "export-1",
            "draft_id": draft_id,
            "draft_version": expected_version,
            "docx_sha256": "a" * 64,
            "pdf_sha256": "b" * 64,
        },
        read=lambda export_id, kind: {
            "bytes": b"content",
            "filename": f"resume.{kind}",
            "media_type": (
                "application/pdf"
                if kind == "pdf"
                else "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        },
    )
    monkeypatch.setattr(app_module, "career_tailored_export_service", lambda: fake)

    created = client.post(
        "/v1/career/tailored-resumes/draft-1/export",
        json={"expected_version": 4},
    )
    docx = client.get(
        "/v1/career/tailored-resume-exports/export-1/docx"
    )
    pdf = client.get(
        "/v1/career/tailored-resume-exports/export-1/pdf"
    )

    assert created.status_code == 200
    assert docx.headers["content-disposition"].startswith("attachment;")
    assert pdf.headers["content-type"] == "application/pdf"
```

Add the three routes from the spec. Resolve paths only through export ID in
Repository; reject kind outside `{docx,pdf}`. Reuse `_content_disposition`.

- [ ] **Step 7: Explicitly ignore private exports**

Append:

```gitignore
# Tailored resumes contain private contact information.
artifacts/tailored-resumes/
```

- [ ] **Step 8: Run Task 4 tests and real converter smoke**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_tailored_resume_exports.py \
  tests/test_career_jobs_api.py -k tailored

.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from extensions.career_mcp.services.tailored_resume_exports import (
    convert_docx_to_pdf,
    render_ats_docx,
)

model = {
    "name": "测试候选人",
    "contact_lines": ["test@example.com", "138****0000"],
    "job_title": "大模型工程师",
    "sections": {
        "education": [{"text": "示例大学 · 计算机科学"}],
        "experience": [],
        "project": [{"text": "使用 Python 构建检索服务"}],
        "skill": [{"text": "Python"}],
    },
}
with TemporaryDirectory() as raw:
    root = Path(raw)
    docx = root / "resume.docx"
    docx.write_bytes(render_ats_docx(model))
    pdf = convert_docx_to_pdf(docx, root)
    print(docx.stat().st_size, pdf.stat().st_size)
PY
```

Expected: tests pass and smoke prints two positive byte sizes.

- [ ] **Step 9: Commit Task 4**

```bash
git add \
  .gitignore \
  extensions/career_mcp/database/tailored_resume_repository.py \
  extensions/career_mcp/services/tailored_resume_exports.py \
  extensions/career_mcp/tests/test_tailored_resume_exports.py \
  coworker/server/app.py \
  tests/test_career_jobs_api.py
git commit -m "feat(career): export confirmed resumes as docx and pdf"
```

### Task 5: Career MCP and Tailored Resume Skill

**Files:**

- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_resume_tools.py`
- Modify: `tests/test_mcp.py`
- Create: `.coworker/skills/career-tailored-resume/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: Invoke `skill-creator` before creating the new Skill**

The implementation agent must read and follow the installed
`skill-creator/SKILL.md` because this task creates a new workspace Skill. Keep
the Skill project-local under `.coworker/skills/`; do not install a global
Skill.

- [ ] **Step 2: Write MCP wrapper RED tests**

Add:

```python
def test_tailored_resume_mcp_tools_use_shared_service(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        prepare=lambda job_id, resume_id, snapshot_id: (
            calls.append(("prepare", job_id, resume_id, snapshot_id))
            or {"id": "draft-1", "version": 1}
        ),
        submit_proposals=lambda draft_id, **kwargs: (
            calls.append(("submit", draft_id, kwargs))
            or {"id": draft_id, "version": 2}
        ),
    )
    monkeypatch.setattr(server, "_tailored_resume_service", lambda: fake)

    prepared = server.prepare_tailored_resume(
        "job-1",
        "resume-1",
        "snapshot-1",
    )
    submitted = server.submit_tailored_resume_proposals(
        "draft-1",
        1,
        [{"source_path": "project[0]"}],
    )

    assert prepared["data"]["version"] == 1
    assert submitted["data"]["version"] == 2
    assert calls == [
        ("prepare", "job-1", "resume-1", "snapshot-1"),
        (
            "submit",
            "draft-1",
            {
                "expected_version": 1,
                "items": [{"source_path": "project[0]"}],
            },
        ),
    ]
```

Add stable `PROPOSAL_VALIDATION_FAILED` violations and `VERSION_CONFLICT`
error tests.

- [ ] **Step 3: Implement and register MCP tools**

Add:

```python
def _tailored_resume_service() -> TailoredResumeService:
    return TailoredResumeService()


def prepare_tailored_resume(
    job_id: str,
    resume_id: str,
    snapshot_id: str,
) -> dict:
    try:
        return _ok(
            _tailored_resume_service().prepare(
                job_id,
                resume_id,
                snapshot_id,
            )
        )
    except TailoredResumeServiceError as exc:
        response = _error(exc.code, str(exc))
        if exc.violations:
            response["error"]["violations"] = exc.violations
        return response


def submit_tailored_resume_proposals(
    draft_id: str,
    expected_version: int,
    items: list[dict],
) -> dict:
    try:
        return _ok(
            _tailored_resume_service().submit_proposals(
                draft_id,
                expected_version=expected_version,
                items=items,
            )
        )
    except TailoredResumeServiceError as exc:
        response = _error(exc.code, str(exc))
        if exc.violations:
            response["error"]["violations"] = exc.violations
        return response
```

Register both with `mcp.tool()`. Do not expose confirm/export through MCP.

- [ ] **Step 4: Create the Skill with hard boundaries**

The Skill must require this exact sequence:

```text
1. Call prepare_tailored_resume with exactly one resume and one snapshot.
2. Use only editable source_facts that occur in a returned direct/related
   requirement's evidence_paths.
3. Emit at most one proposal per unique source_path. Do not resend baseline
   source items and do not propose non-editable structure fields.
4. Preserve every number, date, URL and explicit skill exactly; omission is
   allowed, invention is not.
5. Call submit_tailored_resume_proposals with returned draft ID/version.
6. Stop and tell the user to review every item in 岗位雷达.
```

The Skill must explicitly prohibit:

- `get_candidate_profile(include_sensitive=true)`;
- phone/email/contact requests;
- `write_file` or Shell under `artifacts/tailored-resumes`;
- calling HTTP confirm/export;
- binding `none` requirements;
- combining multiple resumes;
- claiming that a proposal is already verified or ready to submit.

- [ ] **Step 5: Update discovery and Skill tests**

Assert:

```python
assert {
    "prepare_tailored_resume",
    "submit_tailored_resume_proposals",
} <= discovered_tool_names
```

`tests/test_skills.py` must assert the Skill contains both tool names,
`include_sensitive=false`, `逐条确认`, and prohibitions for `write_file`,
Shell, confirm and export.

- [ ] **Step 6: Run and commit**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_resume_tools.py -k tailored \
  tests/test_mcp.py -k career \
  tests/test_skills.py -k tailored
```

Expected: all pass and stdio discovery includes the two tools.

```bash
git add \
  .coworker/skills/career-tailored-resume/SKILL.md \
  extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py \
  tests/test_skills.py
git commit -m "feat(career): stage tailored resume proposals through mcp"
```

### Task 6: Job Radar Review and Download GUI

**Files:**

- Create: `surfaces/gui/src/careerTailoredResume.ts`
- Create: `surfaces/gui/src/careerTailoredResume.test.ts`
- Create: `surfaces/gui/src/components/CareerTailoredResumePanel.tsx`
- Create: `surfaces/gui/src/components/CareerTailoredResumePanel.test.tsx`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/careerJobsApi.test.ts`
- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.tsx`
- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: Write prompt and API client RED tests**

Prompt helper:

```typescript
export interface TailoredResumePromptPayload {
  jobId: string;
  resumeId: string;
  snapshotId: string;
}

export function careerTailoredResumePrompt(
  payload: TailoredResumePromptPayload,
): string {
  return [
    "请使用 career-tailored-resume Skill 生成定制简历改写建议。",
    `job_id=${payload.jobId}`,
    `resume_id=${payload.resumeId}`,
    `match_snapshot_id=${payload.snapshotId}`,
    "只提交带来源路径的建议，不要确认或导出，不要请求敏感联系方式。",
  ].join("\n");
}
```

Test that the prompt contains only opaque IDs and does not contain resume text,
phone, email, `include_sensitive=true`, file path or upload token.

API test:

```typescript
it("updates, confirms and exports a tailored resume draft", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    json: async () => ({ ok: true }),
  });
  vi.stubGlobal("fetch", fetchMock);

  await updateCareerTailoredResume("draft/1", {
    expected_version: 2,
    changes: [{ id: "item-1", decision: "confirmed" }],
  });
  await confirmCareerTailoredResume("draft/1", 3);
  await exportCareerTailoredResume("draft/1", 4);

  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH" });
  expect(String(fetchMock.mock.calls[1][0])).toContain("/confirm");
  expect(String(fetchMock.mock.calls[2][0])).toContain("/export");
});
```

- [ ] **Step 2: Add frontend types and API functions**

Add:

```typescript
export type TailoredResumeDecision =
  | "pending"
  | "confirmed"
  | "omitted";

export interface CareerTailoredResumeItem {
  id: string;
  section: "education" | "experience" | "project" | "skill";
  source_path: string;
  source_text: string;
  proposed_text: string;
  linked_requirement: string | null;
  evidence_status: "source" | "direct" | "related";
  decision: TailoredResumeDecision;
  order: number;
  entry_path: string;
  field: string;
  editable: boolean;
  required: boolean;
}

export interface CareerTailoredResumeDraft {
  id: string;
  job_id: string;
  resume_id: string;
  snapshot_id: string;
  resume_name: string;
  job_title: string;
  status: "draft" | "review" | "confirmed" | "exported" | "stale";
  version: number;
  items: CareerTailoredResumeItem[];
  confirmed_at?: string | null;
  exported_at?: string | null;
  export?: CareerTailoredResumeExport;
}

export interface CareerTailoredResumeExport {
  id: string;
  draft_version: number;
  docx_sha256: string;
  pdf_sha256: string;
  created_at: string;
}
```

Implement list/get/PATCH/confirm/export clients and download URL helpers using
`encodeURIComponent`. All fetches use the existing authenticated fetch wrapper
or `authHeaders`; do not construct an unauthenticated browser URL.

- [ ] **Step 3: Write panel RED tests**

Test:

```typescript
it("shows source and proposal and blocks export while pending", async () => {
  arrangeDraft({ status: "review", decision: "pending" });
  render(<CareerTailoredResumePanel jobId="job-1" />);

  expect(await screen.findByText("原事实")).toBeTruthy();
  expect(screen.getByText("建议措辞")).toBeTruthy();
  expect(screen.getByText("project[0].highlights[0]")).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "确认并导出" }),
  ).toBeDisabled();
  expect(screen.getByText("待确认 1 条")).toBeTruthy();
});


it("edits return to pending and conflicts refresh", async () => {
  arrangeDraft({ status: "review", decision: "confirmed", version: 2 });
  api.updateCareerTailoredResume.mockResolvedValueOnce({
    ok: false,
    error: { code: "VERSION_CONFLICT", message: "conflict" },
  });
  render(<CareerTailoredResumePanel jobId="job-1" />);

  fireEvent.change(await screen.findByLabelText("建议措辞"), {
    target: { value: "新的证据内措辞" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

  expect(
    await screen.findByText(
      "草稿已在其他入口更新，请确认最新内容后重试。",
    ),
  ).toBeTruthy();
  expect(api.getCareerTailoredResume).toHaveBeenCalledTimes(2);
});
```

Also cover confirm/omit for editable items, locked required source items,
stale block, export success, DOCX/PDF links, repeated-click disabling and
Chinese labels.

- [ ] **Step 4: Implement panel**

The panel must:

- fetch latest drafts for `jobId`;
- show a refresh button while Agent proposal is not yet present;
- render one card per item with source, proposal, path, requirement and status;
- label unchanged `source` items as “原样保留”; disable edit/omit controls for
  required or non-editable structure fields;
- save one item with current `expected_version`;
- force edited text to pending visually before response;
- on `VERSION_CONFLICT`, reload exact draft and never auto-overwrite;
- confirm only after Agent submission when all items are decided and at least
  one item is confirmed;
- export only after confirmed response;
- use authenticated blob download functions for DOCX/PDF;
- never render proposal as HTML.

- [ ] **Step 5: Integrate the entry into match panel**

Only show the entry when:

```typescript
const tailoredCandidate =
  !stale && results.length === 1 ? results[0] : null;
```

Call:

```typescript
onGenerateTailoredResume?.({
  jobId: job.id,
  resumeId: tailoredCandidate.resume.id,
  snapshotId: tailoredCandidate.snapshot_id,
});
```

Keep “生成申请准备包” unchanged. Embed
`<CareerTailoredResumePanel jobId={job.id} />` below match results so returning
to the job exposes the latest persisted draft.

In `App.tsx`, mirror the existing application-packet flow:

```typescript
const openTailoredResumeComposer = (
  payload: TailoredResumePromptPayload,
) => {
  startNewSession("career");
  setComposerPrefill(careerTailoredResumePrompt(payload));
};
```

Do not auto-send.

- [ ] **Step 6: Run GUI tests and build**

```bash
cd surfaces/gui
npm test -- --run \
  src/careerTailoredResume.test.ts \
  src/careerJobsApi.test.ts \
  src/components/CareerTailoredResumePanel.test.tsx \
  src/components/CareerJobMatchPanel.test.tsx \
  src/uiChineseAudit.test.ts
npm run build
```

Expected: all pass; only existing mixed-import and chunk-size warnings remain.

- [ ] **Step 7: Commit Task 6**

```bash
git add \
  surfaces/gui/src/App.tsx \
  surfaces/gui/src/api.ts \
  surfaces/gui/src/careerJobsApi.test.ts \
  surfaces/gui/src/careerTailoredResume.ts \
  surfaces/gui/src/careerTailoredResume.test.ts \
  surfaces/gui/src/components/CareerJobMatchPanel.tsx \
  surfaces/gui/src/components/CareerJobMatchPanel.test.tsx \
  surfaces/gui/src/components/CareerTailoredResumePanel.tsx \
  surfaces/gui/src/components/CareerTailoredResumePanel.test.tsx
git commit -m "feat(gui): review and export tailored resumes"
```

### Task 7: Full Gate, Real Browser Acceptance and Adversarial Review

**Files:**

- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

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

Expected: all pass; only the existing Starlette/httpx deprecation warning is
accepted.

- [ ] **Step 2: Run the complete GUI gate**

```bash
cd surfaces/gui
npm test -- --run
npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 3: Verify schema, FK and MCP discovery**

```bash
CAREER_DATA_DIR="$PWD/career" .venv/bin/python - <<'PY'
import asyncio
from extensions.career_mcp.database.migrations import connect, schema_version
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.server import mcp

config = CareerConfig.from_env()
with connect(config.database_path) as connection:
    print("schema", schema_version(connection))
    print("fk", connection.execute("PRAGMA foreign_key_check").fetchall())

async def main():
    names = {tool.name for tool in await mcp.list_tools()}
    required = {
        "prepare_tailored_resume",
        "submit_tailored_resume_proposals",
    }
    print("missing", sorted(required - names))

asyncio.run(main())
PY
```

Expected: schema 8, no FK errors and no missing tools.

- [ ] **Step 4: Run isolated end-to-end acceptance**

Start a separate Server with:

```bash
ACCEPTANCE_DIR="$(mktemp -d)"
CAREER_DATA_DIR="$ACCEPTANCE_DIR/career" \
COWORKER_STATE_DIR="$ACCEPTANCE_DIR/state" \
.venv/bin/openworker-server --cwd "$PWD" --port 8875
```

Seed one synthetic Chinese resume containing no real personal data and import
one copied real-job fixture into that isolated database. Use the real Aiden
Career Agent through the normal Skill/MCP flow to prepare and submit proposals.
In Playwright:

1. open the isolated GUI/Server pair;
2. open the job and one fresh match;
3. verify source/proposal/path/requirement are visible;
4. confirm or omit every item;
5. export and download both files;
6. assert no console/page/network errors;
7. verify edit-after-confirm returns to pending;
8. restore/delete the isolated directory.

The production `career/career.sqlite3` must have identical counts before and
after this acceptance.

- [ ] **Step 5: Render and inspect the actual artifacts**

Use LibreOffice to render DOCX and PDFium or existing PDF renderer to PNG.
Inspect:

- Chinese glyphs render correctly;
- no overlap or clipped text;
- body font is readable;
- one or two pages only;
- all confirmed bullets appear once;
- omitted/pending bullets do not appear;
- name/contact appear in files but not in MCP transcript or draft JSON.

Store screenshots under `artifacts/acceptance/` only if they contain synthetic
data. Never save real user contact details in tracked artifacts.

- [ ] **Step 6: Run two independent adversarial reviews**

Backend review scope:

- cross-resume path and snapshot swapping;
- new number/date/URL/skill injection;
- masked basic/contact leakage;
- stale job/resume and concurrent CAS;
- v8 DDL failure/retry;
- converter timeout/corruption;
- filesystem/DB compensation and orphan isolation;
- symlink and conflicting target directory.

GUI review scope:

- Agent cannot confirm/export;
- pending/locked-source/stale gating;
- conflict refresh and edit-to-pending;
- proposal displayed as text, not HTML;
- authenticated downloads;
- single-result entry only;
- no IDs or internal status values shown as user labels.

Any Critical or Major finding requires a new failing test, minimal fix and
rerun of Steps 1–5.

- [ ] **Step 7: Final static checks**

```bash
.venv/bin/python -m py_compile \
  extensions/career_mcp/domain/tailored_resumes.py \
  extensions/career_mcp/database/tailored_resume_repository.py \
  extensions/career_mcp/services/tailored_resumes.py \
  extensions/career_mcp/services/tailored_resume_exports.py \
  extensions/career_mcp/server.py \
  coworker/server/app.py
git diff --check
```

Expected: no output.

- [ ] **Step 8: Update stage documentation**

Append exact:

- schema version and migration failure evidence;
- final backend/GUI test counts;
- DOCX/PDF hashes, page count and synthetic acceptance paths;
- confirmation and stale/CAS evidence;
- MCP tool count;
- adversarial findings and fixes;
- accepted warnings;
- next task `OCR`.

Update the tailored-resume row in `docs/12_TONIGHT_PROGRESS.md` to `通过`
only after both adversarial rechecks report `major_remaining:false`.

- [ ] **Step 9: Commit documentation**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record tailored resume export acceptance"
```

## Completion Audit

Before declaring this stage complete, prove each requirement with current-state
evidence:

- exactly one selected resume per draft;
- fresh snapshot and current revision required;
- model receives no private contact data;
- every proposal binds one authoritative source path;
- user edits run the same validator and return to pending;
- every included item is explicitly confirmed;
- Agent has no confirm/export tool;
- DOCX and PDF derive from one frozen version;
- PDF is one or two pages;
- pair publication cannot leave a downloadable half-result;
- downloads are authenticated and path-safe;
- schema v8 and FK checks pass;
- full backend/GUI/build gates pass;
- two adversarial rechecks have no Critical/Major.

Do not start OCR until every item above is proven.
