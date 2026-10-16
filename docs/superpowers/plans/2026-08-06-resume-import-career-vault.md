# Resume Import And Career Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import text, PDF, and DOCX resumes into a staged preview, confirm five fact sections independently, and persist one masked, versioned local candidate profile.

**Architecture:** A small authenticated OpenWorker endpoint delegates file staging to `ResumeService`; deterministic local parsers save content-addressed originals and extracted text. Career Agent performs semantic extraction through the existing model router, while Career MCP validates proposals, computes conflicts, confirms sections transactionally, and exposes masked profile reads.

**Tech Stack:** Python 3.12, FastAPI, SQLite schema v4, FastMCP, pypdf, python-docx, React/TypeScript, pytest, Vitest.

---

## File Map

| File | Responsibility |
|---|---|
| `extensions/career_mcp/config.py` | Resolve Career DB and private resume directories |
| `extensions/career_mcp/domain/resume.py` | Resume section constants, normalization, validation, and masking |
| `extensions/career_mcp/database/migrations.py` | Schema v4 Career Vault tables |
| `extensions/career_mcp/database/resume_repository.py` | Resume imports, previews, facts, versions, deletion |
| `extensions/career_mcp/services/resumes.py` | File extraction, staging, preview, confirmation, profile API |
| `extensions/career_mcp/server.py` | Register six Career resume MCP tools |
| `coworker/server/manager.py` | Thin dynamic delegation to ResumeService |
| `coworker/server/app.py` | Authenticated `/v1/career/resumes/stage` endpoint |
| `surfaces/gui/src/api.ts` | Resume staging API client |
| `surfaces/gui/src/components/Composer.tsx` | Career resume upload/paste action and prepared prompt |
| `.coworker/skills/career-resume-import/SKILL.md` | Safe extraction and section-confirmation workflow |
| `.coworker/skills/career-application-packet/SKILL.md` | Require confirmed Career Vault facts |
| `extensions/career_mcp/tests/` | Offline domain, parser, repository, service, and MCP tests |
| `tests/test_server.py` | Upload endpoint authentication and validation |
| `tests/test_skills.py` | Resume Skill contract |
| `surfaces/gui/src/components/Composer.resume.test.tsx` | Resume upload UI behavior |
| `docs/16_RESUME_IMPORT_RUNBOOK.md` | Private storage, usage, deletion, and recovery |

## Task 1: Schema v4 And Private Configuration

**Files:**
- Modify: `extensions/career_mcp/config.py`
- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/tests/test_crawler_repository.py`

- [ ] Write a failing migration test that starts at schema v3, inserts existing
  jobs and crawl runs, migrates to v4, and requires:

```python
assert schema_version(connection) == 4
assert {
    "resume_imports",
    "candidate_profile",
    "candidate_facts",
    "profile_versions",
    "resume_previews",
} <= tables
assert existing_jobs_after == existing_jobs_before
```

- [ ] Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_crawler_repository.py \
  -k version_four -q
```

Expected: RED because schema version is 3.

- [ ] Set `SCHEMA_VERSION = 4` and add the five tables from the approved spec.
  Add `upload_token`, `expires_at`, and `preview_token` unique constraints.
  Use foreign keys with `ON DELETE CASCADE` for profile-owned data.

- [ ] Add:

```python
@property
def private_resume_dir(self) -> Path:
    value = os.environ.get("CAREER_PRIVATE_DIR", "").strip()
    root = Path(value).expanduser() if value else state_dir() / "career-private"
    return root.resolve() / "resumes"

@property
def staged_resume_dir(self) -> Path:
    return self.private_resume_dir.parent / "staged"
```

- [ ] Run the complete migration tests and `PRAGMA foreign_key_check`.

## Task 2: Local Text, PDF, And DOCX Extraction

**Files:**
- Create: `extensions/career_mcp/domain/resume.py`
- Create: `extensions/career_mcp/tests/test_resume_parsing.py`
- Modify: `extensions/career_mcp/pyproject.toml`

- [ ] Add synthetic text, PDF, and DOCX fixtures generated in tests. Require all
  three to contain the same normalized candidate facts.

- [ ] Add failing tests for:
  - text under 20 characters;
  - text over 200,000 characters;
  - PDF over 20 pages;
  - encrypted PDF;
  - PDF with no extractable text;
  - damaged DOCX;
  - unsupported suffix;
  - filename path components being ignored.

- [ ] Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_resume_parsing.py -q
```

Expected: RED because resume parsing functions do not exist.

- [ ] Add `python-docx>=1.1,<2` to Career MCP dependencies.

- [ ] Implement pure functions:

```python
normalize_resume_text(text: str) -> str
extract_resume_text(
    *,
    filename: str,
    mime: str,
    raw_bytes: bytes | None = None,
    text: str | None = None,
) -> ExtractedResume
validate_resume_proposal(proposal: dict) -> dict
mask_candidate_profile(profile: dict) -> dict
```

Use `pypdf.PdfReader` and `docx.Document(io.BytesIO(raw_bytes))`. Read DOCX
paragraphs and table cells only; do not extract ZIP members to disk.

- [ ] Run parser tests and dependency import smoke.

## Task 3: Resume Repository And Versioned Confirmation

**Files:**
- Create: `extensions/career_mcp/database/resume_repository.py`
- Create: `extensions/career_mcp/tests/test_resume_repository.py`

- [ ] Write failing repository tests for:
  - identical content hash reuses one original/import;
  - upload token lookup and expiry;
  - preview creation does not create candidate facts;
  - confirming `basic` creates version 1;
  - confirming `education` creates version 2 and retains `basic`;
  - correcting a selected section replaces the proposal;
  - a conflicting unselected section does not overwrite current facts;
  - profile versions remain immutable;
  - discard refuses a confirmed referenced import;
  - full delete cascades all Career Vault rows.

- [ ] Run repository tests and verify RED.

- [ ] Implement `ResumeRepository` with explicit transaction boundaries owned by
  the service. Store section values as canonical JSON with sorted keys. Replace
  selected sections atomically.

- [ ] Run repository tests and verify GREEN.

## Task 4: Resume Service

**Files:**
- Create: `extensions/career_mcp/services/resumes.py`
- Create: `extensions/career_mcp/tests/test_resume_service.py`

- [ ] Write failing service tests for:
  - staging text/PDF/DOCX saves content-addressed private originals;
  - duplicate bytes reuse the original;
  - returned stage response omits extracted text and private path;
  - `get_resume_import_text` returns text only for a valid non-expired token;
  - preview validation rejects unknown fields and invalid dates;
  - conflicts are section-level;
  - default profile read masks name, phone, email, and address;
  - `include_sensitive=True` returns confirmed clear text;
  - exact deletion confirmation phrase is required;
  - errors never contain full resume text or private paths.

- [ ] Implement:

```python
stage_resume(...)
get_resume_import_text(upload_token: str)
preview_resume_import(upload_token: str, proposal: dict)
confirm_resume_sections(
    preview_token: str,
    sections: list[str],
    corrections: dict | None = None,
)
get_candidate_profile(include_sensitive: bool = False)
discard_resume_import(preview_token: str)
delete_candidate_profile(confirm_text: str)
```

Use `secrets.token_urlsafe(32)`, SHA-256 content addressing, 24-hour UTC expiry,
atomic temporary-file rename, and repository transactions.

- [ ] Run service tests and verify GREEN.

## Task 5: Career MCP Tools And Skills

**Files:**
- Modify: `extensions/career_mcp/server.py`
- Create: `extensions/career_mcp/tests/test_resume_tools.py`
- Create: `.coworker/skills/career-resume-import/SKILL.md`
- Modify: `.coworker/skills/career-application-packet/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] Write failing MCP tests requiring six tools and stable error envelopes:

```text
get_resume_import_text
preview_resume_import
confirm_resume_sections
get_candidate_profile
discard_resume_import
delete_candidate_profile
```

- [ ] Register thin MCP wrappers. Convert `ValueError` to `INVALID_INPUT`,
  token lookup/expiry to the approved stable codes, and SQLite failures to
  retryable `PERSISTENCE_ERROR`. Do not include private data in errors.

- [ ] Write a failing Skill test requiring the extraction, preview, explicit
  section confirmation, masking, and confirmed-facts-only rules.

- [ ] Create `career-resume-import` and update `career-application-packet`.

- [ ] Run MCP and Skill tests. Real stdio discovery must report 16 Career tools.

## Task 6: Authenticated Local Staging Endpoint

**Files:**
- Modify: `coworker/server/manager.py`
- Modify: `coworker/server/app.py`
- Modify: `tests/test_server.py`

- [ ] Write failing REST tests:
  - missing/invalid OpenWorker token returns 401;
  - valid text upload returns metadata and token;
  - valid base64 PDF/DOCX delegates to ResumeService;
  - invalid base64, MIME, extension, and >10MB payload return safe errors;
  - response never contains extracted text or private path.

- [ ] Add `SessionManager.stage_resume_upload(body)` with a local import:

```python
from extensions.career_mcp.services.resumes import ResumeService
```

Instantiate only inside the method so generic OpenWorker startup does not
require the Career extension.

- [ ] Register:

```python
@app.post("/v1/career/resumes/stage")
def stage_resume(body: dict) -> dict[str, Any]:
    return manager.stage_resume_upload(body or {})
```

The existing API token middleware and origin gate remain unchanged.

- [ ] Run focused server and security tests.

## Task 7: Minimal GUI Resume Action

**Files:**
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/components/Composer.tsx`
- Create: `surfaces/gui/src/components/Composer.resume.test.tsx`

- [ ] Write failing Vitest tests proving:
  - Career sessions show `Import resume`;
  - the picker accepts `.pdf,.docx`;
  - pasted text can be staged;
  - successful staging sends a prompt containing only upload token, filename,
    format, and Skill name;
  - file bytes and extracted text are absent from the prompt;
  - upload errors are visible and do not send a message.

- [ ] Add `stageResume()` to `api.ts`.

- [ ] Add a restrained Career-only menu action in Composer. Reuse existing file
  size notices and conversation flow; do not add a dashboard.

- [ ] Run GUI tests and verify GREEN.

## Task 8: Real Synthetic Smoke, Privacy Audit, And Runbook

**Files:**
- Create: `docs/16_RESUME_IMPORT_RUNBOOK.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Restart Server before GUI using:

```bash
COWORKER_STATE_DIR="$PWD/.local-state" \
CAREER_DATA_DIR="$PWD/career" \
.venv/bin/openworker-server --cwd "$PWD" --port 8765
```

- [ ] Generate a synthetic resume with no real personal data in text, PDF, and
  DOCX. Complete:
  upload -> get text -> preview -> confirm `basic` -> masked profile query ->
  confirm remaining sections -> sensitive query -> full delete.

- [ ] Verify:
  - all three formats normalize to equivalent text;
  - no facts exist before confirmation;
  - versions increase monotonically;
  - ordinary profile result is masked;
  - deletion removes DB rows and private originals;
  - application-packet Skill refuses staged facts;
  - no log or Git diff contains the synthetic full resume text.

- [ ] Run:

```bash
.venv/bin/pytest \
  tests/test_server.py \
  tests/test_mcp.py \
  extensions/career_mcp/tests \
  tests/test_skills.py \
  tests/test_builtin_personas.py -q
cd surfaces/gui && npm test -- --run && npm run build
git diff --check
```

- [ ] Document private paths, supported formats, confirmation workflow, masking,
  deletion, backups, and unsupported scanned PDF behavior.

- [ ] Commit only resume-import files with:

```bash
git commit --only -m "feat(career): add confirmed resume import" -- \
  extensions/career_mcp/config.py \
  extensions/career_mcp/domain/resume.py \
  extensions/career_mcp/database/migrations.py \
  extensions/career_mcp/database/resume_repository.py \
  extensions/career_mcp/services/resumes.py \
  extensions/career_mcp/server.py \
  extensions/career_mcp/pyproject.toml \
  extensions/career_mcp/tests/test_resume_parsing.py \
  extensions/career_mcp/tests/test_resume_repository.py \
  extensions/career_mcp/tests/test_resume_service.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  coworker/server/manager.py \
  coworker/server/app.py \
  tests/test_server.py \
  tests/test_skills.py \
  .coworker/skills/career-resume-import/SKILL.md \
  .coworker/skills/career-application-packet/SKILL.md \
  surfaces/gui/src/api.ts \
  surfaces/gui/src/components/Composer.tsx \
  surfaces/gui/src/components/Composer.resume.test.tsx \
  docs/16_RESUME_IMPORT_RUNBOOK.md \
  docs/11_DEVELOPMENT_LOG.md \
  docs/12_TONIGHT_PROGRESS.md
```

Existing unrelated staged and unstaged changes remain untouched.

## Execution Outcome

- Schema v4, local text/PDF/DOCX parsing, versioned repository, resume service,
  six MCP tools, two Skills, authenticated staging endpoint, and Career-only GUI
  actions completed.
- Synthetic HTTP + real stdio MCP smoke confirmed versions 1 and 2, masked
  reads, 16 tools, and full deletion with zero private files remaining.
- Final verification: Career 185 passed, OpenWorker/Automation/MCP/Skill 93
  passed, GUI 113 passed, GUI production build passed, and `git diff --check`
  passed.
- Both existing Automations were paused during private-data smoke and restored
  to their original schedules afterward.
