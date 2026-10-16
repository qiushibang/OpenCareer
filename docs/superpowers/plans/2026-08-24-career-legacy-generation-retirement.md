# Career Legacy Generation Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove script matching, Application Packet, tailored-resume draft, and DOCX/PDF generation from the runtime while preserving AI resume coaching, direct-source mock interviews, and recoverable historical data.

**Architecture:** Mock interviews will build a fact-reference blueprint directly from one visible job and one confirmed resume. Legacy records are first exported by a read-only archive command, then removed only by a separate retirement command that verifies the archive manifest; destructive cleanup is never part of application startup.

**Tech Stack:** Python 3.12, FastAPI, SQLite, PostgreSQL 16/psycopg, React 18, TypeScript, Vitest, pytest, Docker Compose.

---

### Task 1: Build Interview Blueprints From Direct Sources

**Files:**
- Modify: `extensions/career_mcp/domain/interviews.py`
- Modify: `extensions/career_mcp/services/interviews.py`
- Modify: `extensions/career_mcp/database/interview_repository.py`
- Modify: `coworker/storage/postgres/career.py`
- Modify: `coworker/storage/postgres/interviews.py`
- Test: `extensions/career_mcp/tests/test_interviews.py`
- Test: `extensions/career_mcp/tests/test_interview_service.py`
- Test: `extensions/career_mcp/tests/test_interview_repository.py`

- [ ] **Step 1: Write failing direct-source blueprint tests**

Add tests that call:

```python
blueprint = build_blueprint(
    job=job,
    resume_id="resume-1",
    difficulty="standard",
    duration_minutes=15,
    resume_sections=sections,
)
```

Assert `snapshot_id`, `snapshot_status`, `evidence_status`,
`candidate_strengths`, and `candidate_risks` are absent while stable
`requirement-*` and resume fact refs are present.

- [ ] **Step 2: Run the focused domain tests and verify RED**

Run:

```bash
python -m pytest \
  extensions/career_mcp/tests/test_interviews.py \
  -q
```

Expected: fail because `build_blueprint` still requires a match result and
snapshot ID.

- [ ] **Step 3: Implement the direct-source blueprint**

Change the public contract to:

```python
def build_blueprint(
    job: dict,
    *,
    resume_id: str,
    difficulty: str,
    duration_minutes: int,
    resume_sections: dict,
) -> dict:
```

Create refs from raw JD requirements and confirmed resume fact paths. Keep the
existing question/evaluation validators, but remove matching conclusions from
new blueprints.

- [ ] **Step 4: Write failing InterviewService tests**

Construct `InterviewService` with `job_loader` and `resume_loader`, then call:

```python
created = service.create(
    job_id,
    resume_id,
    conversation_id="career-session-1",
    difficulty="standard",
    duration_minutes=15,
)
```

Assert no match service is accepted or called and the saved session has no
`snapshot_id`.

- [ ] **Step 5: Run the focused service tests and verify RED**

Run:

```bash
python -m pytest \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  -q
```

Expected: fail because the service and repository still require
`snapshot_id`.

- [ ] **Step 6: Implement direct job/resume loading and persistence**

Inject:

```python
job_loader: Callable[[str], dict | None] | None = None
resume_loader: Callable[[str], dict | None] | None = None
```

Remove `MatchService`, `MatchServiceError`, and `snapshot_id` from new session
creation. Update local/PostgreSQL readers and repositories so historical
blueprints remain readable.

- [ ] **Step 7: Run focused tests and commit**

Run the tests from Steps 2 and 5. Expected: pass.

Commit:

```bash
git add extensions/career_mcp/domain/interviews.py \
  extensions/career_mcp/services/interviews.py \
  extensions/career_mcp/database/interview_repository.py \
  coworker/storage/postgres/career.py \
  coworker/storage/postgres/interviews.py \
  extensions/career_mcp/tests/test_interviews.py \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_repository.py
git commit -m "refactor(career): build interviews from direct facts"
```

### Task 2: Remove Snapshot IDs From Interview Interfaces

**Files:**
- Modify: `extensions/career_mcp/server.py`
- Modify: `coworker/server/app.py`
- Modify: `.coworker/skills/mock-interview/SKILL.md`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/careerInterview.ts`
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Test: `extensions/career_mcp/tests/test_interview_tools.py`
- Test: `tests/test_career_interview_api.py`
- Test: `surfaces/gui/src/careerInterview.test.ts`
- Test: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [ ] **Step 1: Write failing API and GUI contract tests**

Assert the MCP/HTTP create call accepts only:

```json
{
  "job_id": "job-1",
  "resume_id": "resume-1",
  "difficulty": "standard",
  "duration_minutes": 15
}
```

Assert the job view lists confirmed resumes and starts the interview without
calling match endpoints.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python -m pytest \
  extensions/career_mcp/tests/test_interview_tools.py \
  tests/test_career_interview_api.py -q
cd surfaces/gui && npm test -- --run \
  src/careerInterview.test.ts \
  src/components/CareerJobsView.test.tsx
```

Expected: fail on required snapshot arguments and match API calls.

- [ ] **Step 3: Implement the minimal interface changes**

Use:

```typescript
export interface InterviewLaunchPayload {
  jobId: string;
  resumeId: string;
  position: string;
  durationMinutes: 10 | 15 | 20;
  difficulty: "simple" | "standard" | "deep";
}
```

Remove `snapshot_id` from create requests and session types. Update
`mock-interview` creation workflow to call `create_interview_session`
immediately after selecting a confirmed resume.

- [ ] **Step 4: Run focused tests and commit**

Expected: all Step 2 tests pass.

Commit only the files listed in this task with:

```bash
git commit -m "refactor(career): start interviews without match snapshots"
```

### Task 3: Remove Legacy Runtime Surfaces

**Files:**
- Delete: `extensions/career_mcp/services/matches.py`
- Delete: `extensions/career_mcp/database/match_repository.py`
- Delete: `extensions/career_mcp/domain/matching.py`
- Delete: `extensions/career_mcp/services/application_packets.py`
- Delete: `extensions/career_mcp/domain/application_packets.py`
- Delete: `extensions/career_mcp/services/tailored_resumes.py`
- Delete: `extensions/career_mcp/services/tailored_resume_exports.py`
- Delete: `extensions/career_mcp/domain/tailored_resumes.py`
- Delete: `extensions/career_mcp/database/tailored_resume_repository.py`
- Delete: `coworker/storage/postgres/application_packets.py`
- Delete: `coworker/storage/postgres/tailored_resumes.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `coworker/server/app.py`
- Modify: `coworker/server/alpha.py`
- Modify: `coworker/storage/postgres/career.py`
- Modify: `coworker/storage/postgres/resume_service.py`
- Delete: `.coworker/skills/career-application-packet/SKILL.md`
- Test: `extensions/career_mcp/tests/test_resume_tools.py`
- Test: `tests/test_mcp.py`
- Test: `tests/test_server.py`
- Test: `tests/test_skills.py`

- [ ] **Step 1: Write failing absence tests**

Assert old HTTP paths return `404`, old MCP names are absent, and Alpha tools
exclude:

```python
{
    "mcp__career__list_job_match_candidates",
    "mcp__career__match_job_to_profile",
    "mcp__career__create_application_packet",
    "mcp__career__validate_application_packet",
    "mcp__career__prepare_tailored_resume",
    "mcp__career__submit_tailored_resume_proposals",
}
```

- [ ] **Step 2: Run absence tests and verify RED**

Run:

```bash
python -m pytest \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py tests/test_server.py tests/test_skills.py -q
```

Expected: fail because old tools and routes remain registered.

- [ ] **Step 3: Remove registrations, factories, imports, and modules**

Delete only code owned by the retired capabilities. Preserve Career Vault,
OCR, normal PDF attachments, `get_confirmed_resume`, and interview artifacts.
Update resume deletion so it no longer addresses removed tables.

- [ ] **Step 4: Delete obsolete tests and run residual-reference audit**

Remove tests dedicated exclusively to deleted behavior. Run:

```bash
rg -n "MatchService|match_job_to_profile|application_packet|tailored_resume" \
  extensions/career_mcp coworker surfaces/gui/src .coworker/skills tests \
  --glob '!**/sql/000*.sql'
```

Expected: no runtime references; historical migrations and approved documents
may remain.

- [ ] **Step 5: Run focused tests and commit**

Expected: all retained tests pass.

Commit:

```bash
git commit -m "refactor(career): remove legacy generation runtime"
```

### Task 4: Add Read-Only Legacy Archive

**Files:**
- Create: `deploy/archive_legacy_career.py`
- Create: `tests/test_archive_legacy_career.py`
- Modify: `docs/18_BACKUP_AND_ROLLBACK_RUNBOOK.md`

- [ ] **Step 1: Write failing archive tests**

Create SQLite fixtures with legacy rows/files and assert:

```python
manifest = archive_sqlite(source_db, output_dir)
assert manifest["tables"]["job_resume_matches"]["count"] == 1
assert manifest["blobs"][0]["sha256"] == expected_sha256
```

Also assert non-empty destination, missing referenced files, and tampered
content fail without changing the source database.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/test_archive_legacy_career.py -q
```

Expected: import failure because the archive module does not exist.

- [ ] **Step 3: Implement deterministic archive output**

Write `manifest.json`, normalized JSONL table exports, copied Blob/file
content, and `SHA256SUMS`. Use structured SQLite/PostgreSQL queries; never
parse SQL text or log row contents.

- [ ] **Step 4: Add PostgreSQL adapter tests**

Use the repository's PostgreSQL test fixture when `TEST_DATABASE_URL` exists.
Verify tenant rows and old Blob kinds are fully represented.

- [ ] **Step 5: Run tests and commit**

Commit:

```bash
git add deploy/archive_legacy_career.py \
  tests/test_archive_legacy_career.py \
  docs/18_BACKUP_AND_ROLLBACK_RUNBOOK.md
git commit -m "feat(deploy): archive retired career data"
```

### Task 5: Add Explicit Retirement Command

**Files:**
- Create: `deploy/retire_legacy_career.py`
- Create: `deploy/sql/retire_legacy_career.sql`
- Create: `tests/test_retire_legacy_career.py`
- Modify: `extensions/career_mcp/database/interview_repository.py`
- Modify: `coworker/storage/postgres/interviews.py`

- [ ] **Step 1: Write failing guard tests**

Assert missing, malformed, mismatched, or tampered manifests cause a non-zero
result and leave all tables/files unchanged.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/test_retire_legacy_career.py -q
```

Expected: import failure because the retirement module does not exist.

- [ ] **Step 3: Implement transactional SQLite retirement**

Verify the archive, rebuild `interview_sessions` without `snapshot_id`, drop
legacy tables in dependency order, run `foreign_key_check` and
`integrity_check`, commit, then remove only archived generated files.

- [ ] **Step 4: Implement transactional PostgreSQL retirement**

The SQL must drop old triggers/tables and delete only unreferenced Blob rows
whose kind is one of:

```python
{
    "application_packet",
    "tailored_resume_docx",
    "tailored_resume_pdf",
}
```

Record an idempotent completion marker in `opencareer_meta.data_migrations`.

- [ ] **Step 5: Run SQLite and PostgreSQL tests**

Run:

```bash
python -m pytest tests/test_retire_legacy_career.py -q
```

Expected: SQLite tests pass. PostgreSQL cases pass when
`TEST_DATABASE_URL` is configured, otherwise report their exact skip count.

- [ ] **Step 6: Commit**

```bash
git add deploy/retire_legacy_career.py \
  deploy/sql/retire_legacy_career.sql \
  tests/test_retire_legacy_career.py \
  extensions/career_mcp/database/interview_repository.py \
  coworker/storage/postgres/interviews.py
git commit -m "feat(deploy): retire archived career generation data"
```

### Task 6: Remove Image Dependencies and Update Current Documentation

**Files:**
- Modify: `deploy/Dockerfile`
- Modify: `tests/test_cloud_compose.py`
- Modify: `docs/README.md`
- Modify: `docs/05_DATA_MODEL_AND_MCP_TOOLS.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Write the failing image dependency test**

Assert the backend Dockerfile excludes `libreoffice-writer` and
`fonts-noto-cjk`, while retaining Chromium and server requirements.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python -m pytest tests/test_cloud_compose.py -q
```

Expected: fail because the two retired packages are installed.

- [ ] **Step 3: Remove packages and update authoritative docs**

Describe AI-only coaching, direct-source interviews, the explicit archive and
retirement commands, and the retained PDF/DOCX import boundary.

- [ ] **Step 4: Run the focused test and commit**

```bash
git commit -m "chore(deploy): remove tailored resume export runtime"
```

### Task 7: Full Regression and Residual Audit

**Files:**
- Modify only files required by failures caused by Tasks 1-6.

- [ ] **Step 1: Run backend and frontend suites**

```bash
python -m pytest extensions/career_mcp/tests tests -q
cd surfaces/gui && npm test -- --run
cd surfaces/gui && npx tsc
```

- [ ] **Step 2: Run production and CLI Gates**

```bash
bash deploy/build-frontend.sh
python -m coworker.server.run --help
python -m extensions.career_mcp.crawl_cli --list
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
```

Use temporary non-sensitive environment values and `--no-env-resolution`
only if the domain compose check otherwise requires the untracked
`deploy/.env`.

- [ ] **Step 3: Audit retained and removed PDF/DOCX paths**

Run:

```bash
rg -n "application_packet|tailored_resume|MatchService|job_resume_matches|soffice|libreoffice" \
  extensions/career_mcp coworker deploy surfaces/gui/src .coworker/skills tests \
  --glob '!**/sql/000*.sql'
rg -n "resume_original|application/pdf|officedocument|rapidocr|pypdf" \
  extensions/career_mcp coworker surfaces/gui/src
git diff --check
```

Expected: the first command finds only archive/retirement code and explicit
absence tests; the second confirms retained import, OCR, preview, and normal
attachment paths.

- [ ] **Step 4: Record exact results**

Append commands, pass/skip counts, unavailable PostgreSQL coverage, and
remaining deployment risk to `docs/11_DEVELOPMENT_LOG.md` and
`docs/12_TONIGHT_PROGRESS.md`.

- [ ] **Step 5: Commit verification fixes and evidence**

```bash
git commit -m "test(career): verify legacy generation retirement"
```
