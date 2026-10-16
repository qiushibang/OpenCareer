# JD or Public Job Link to Mock Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Career conversation preview a pasted JD or public job URL, require explicit confirmation, persist the exact confirmed job for the current tenant, create a fresh resume match, and create one InterviewSession.

**Architecture:** Keep parsing and persistence in Career MCP. Add one guarded URL reader, extend the existing manual-JD service with a deterministic preview hash and injected repository writes, and store manual-job ownership in PostgreSQL. Reuse attended `ask_user`, the existing matching service, and the existing conversation-bound interview creation path.

**Tech Stack:** Python 3.11, FastMCP, psycopg 3, PostgreSQL 16, SQLite, pytest, OpenWorker Skills, React/Vitest regression tests.

---

### Task 1: Exact Preview Confirmation Contract

**Files:**
- Modify: `extensions/career_mcp/services/jobs.py`
- Modify: `extensions/career_mcp/database/repository.py`
- Test: `extensions/career_mcp/tests/test_jobs_service.py`

- [ ] **Step 1: Write failing tests for preview hash and changed-payload rejection**

```python
preview = service.import_manual_jd(raw_text=RAW_JD, confirmed=False)
assert len(preview["preview_hash"]) == 64

with pytest.raises(ValueError, match="preview changed"):
    service.import_manual_jd(
        raw_text=RAW_JD + "\n额外要求：熟悉评测",
        preview_hash=preview["preview_hash"],
        confirmed=True,
    )
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest extensions/career_mcp/tests/test_jobs_service.py -q`

Expected: FAIL because `preview_hash` is absent and the method does not accept it.

- [ ] **Step 3: Implement canonical preview hashing and repository-session writes**

Add a pure helper that hashes JSON containing `cleaned_text`, normalized source URL, company,
and title with sorted keys. Require the supplied hash on `confirmed=True`. Replace the direct
`connect()` block in `import_manual_jd()` with `self._repository_session(write=True)`.
Extend `_repository_session` so injected factories may receive `write=True`, while SQLite starts,
commits, and rolls back the transaction locally.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest extensions/career_mcp/tests/test_jobs_service.py extensions/career_mcp/tests/test_stage2_tools.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extensions/career_mcp/services/jobs.py \
  extensions/career_mcp/database/repository.py \
  extensions/career_mcp/tests/test_jobs_service.py
git commit -m "feat(career): bind manual JD confirmation to preview"
```

### Task 2: PostgreSQL Manual Job Ownership

**Files:**
- Create: `coworker/storage/postgres/sql/0006_manual_job_ownership.sql`
- Modify: `coworker/storage/postgres/database.py`
- Modify: `extensions/career_mcp/database/postgres_catalog_repository.py`
- Modify: `extensions/career_mcp/server.py`
- Test: `tests/test_postgres_schema.py`
- Test: `tests/test_postgres_job_service.py`
- Test: `tests/test_postgres_tenant_scope.py`

- [ ] **Step 1: Write failing schema and two-tenant tests**

Assert the migration creates `career.manual_job_owners`, enables forced RLS, creates
`career.visible_jobs`, and installs job-visibility checks for tenant tables. In an integration
test, user A creates a manual job; user B cannot get it, match it, or create an interview from it.

- [ ] **Step 2: Run the focused PostgreSQL tests and verify RED**

Run:

```bash
python -m pytest tests/test_postgres_schema.py \
  tests/test_postgres_job_service.py \
  tests/test_postgres_tenant_scope.py -q
```

Expected: FAIL because migration 0006 and manual repository methods do not exist.

- [ ] **Step 3: Add migration and repository methods**

Implement:

```text
ensure_manual_source(company_name)
find_by_source_and_hash(source_id, content_hash)
create_manual_job(..., owner_user_id)
```

Use `career.manual_job_owners` as the ownership source. Query jobs through the visibility
predicate for principal-scoped `get_job`, `search_jobs`, and match loading. Do not change public
crawler job visibility.

- [ ] **Step 4: Wire the principal into `_job_service()` and fix MCP calls**

Make the injected PostgreSQL repository session accept `write`. Change `import_manual_jd`,
`get_job`, and `search_jobs` MCP handlers to call `_job_service()` rather than constructing
`JobService()` directly. PostgreSQL errors must not fall back to SQLite.

- [ ] **Step 5: Run migration and tenant tests and verify GREEN**

Run the command from Step 2.

Expected: PASS, including cross-tenant denial.

- [ ] **Step 6: Commit**

```bash
git add coworker/storage/postgres/sql/0006_manual_job_ownership.sql \
  coworker/storage/postgres/database.py \
  extensions/career_mcp/database/postgres_catalog_repository.py \
  extensions/career_mcp/server.py \
  tests/test_postgres_schema.py tests/test_postgres_job_service.py \
  tests/test_postgres_tenant_scope.py
git commit -m "feat(storage): isolate tenant manual jobs"
```

### Task 3: Guarded Public Job URL Preview

**Files:**
- Create: `extensions/career_mcp/services/public_job_url.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `coworker/server/alpha.py`
- Test: `extensions/career_mcp/tests/test_public_job_url.py`
- Test: `extensions/career_mcp/tests/test_stage2_tools.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing URL safety and extraction tests**

Use an injected fake HTTP client to test:

```python
with pytest.raises(PublicJobUrlError, match="private"):
    service.preview("http://127.0.0.1/job")

preview = service.preview("https://careers.example/job/1")
assert preview["final_url"] == "https://careers.example/job/1"
assert "岗位职责" in preview["text"]
```

Also cover a public redirect to `169.254.169.254`, non-text content, response above 2 MiB,
login/captcha markers, and extracted text below the minimum useful length.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest extensions/career_mcp/tests/test_public_job_url.py tests/test_server.py -q`

Expected: FAIL because the service and MCP tool are absent.

- [ ] **Step 3: Implement the minimal guarded reader**

Use `coworker.web.guard.get_checked`, `httpx.Client(follow_redirects=False)`, a 20-second timeout,
and a streaming 2 MiB cap. Accept HTML, text, and JSON. Extract visible HTML text with a local,
small `HTMLParser`; do not import the private `_html_to_text` helper. Return only final URL,
content type, truncation, and text.

- [ ] **Step 4: Register and allowlist the Career tool**

Register `preview_public_job_url` with FastMCP and add exactly these Alpha tools:

```text
mcp__career__preview_public_job_url
mcp__career__import_manual_jd
```

Do not add generic `web_fetch`.

- [ ] **Step 5: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/services/public_job_url.py \
  extensions/career_mcp/server.py coworker/server/alpha.py \
  extensions/career_mcp/tests/test_public_job_url.py \
  extensions/career_mcp/tests/test_stage2_tools.py tests/test_server.py
git commit -m "feat(career): preview public job URLs safely"
```

### Task 4: Conversation Skill Orchestration

**Files:**
- Modify: `.coworker/skills/career-jd-analysis/SKILL.md`
- Modify: `.coworker/skills/mock-interview/SKILL.md`
- Test: `tests/test_skills.py`

- [ ] **Step 1: Write failing Skill-contract tests**

Assert the JD Skill requires URL preview, `confirmed=false`, `preview_hash`, and one `ask_user`
with “确认并开始面试” / “取消”. Assert the interview Skill generates a fresh match after import,
selects confirmed resumes safely, creates one session, and stops after creation.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_skills.py -q`

Expected: FAIL on the new workflow assertions.

- [ ] **Step 3: Update the two Skills**

Describe exact tool order and stop conditions. Preserve the existing branch for explicit saved
job IDs. Remove the instruction that sends users to Job Radar when no fresh match exists; for
the confirmed import branch, call `match_job_to_profile` once and use its returned snapshot.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_skills.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .coworker/skills/career-jd-analysis/SKILL.md \
  .coworker/skills/mock-interview/SKILL.md tests/test_skills.py
git commit -m "feat(career): orchestrate JD interview launch"
```

### Task 5: Regression, Alpha Build, and Real Flow Gate

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Run focused backend suites**

```bash
python -m pytest extensions/career_mcp/tests/test_jobs_service.py \
  extensions/career_mcp/tests/test_stage2_tools.py \
  extensions/career_mcp/tests/test_public_job_url.py \
  tests/test_postgres_job_service.py tests/test_postgres_tenant_scope.py \
  tests/test_skills.py tests/test_server.py -q
```

- [ ] **Step 2: Run required project Gates**

```bash
python -m coworker.server.run --help
python -m extensions.career_mcp.crawl_cli --list
cd surfaces/gui && npx tsc && cd -
bash deploy/build-frontend.sh
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
```

- [ ] **Step 3: Execute real Alpha browser flow**

Use one pasted JD and one readable public official job URL. Verify the tool trace is:

```text
preview -> ask_user -> confirmed import -> resume selection
-> fresh match -> create InterviewSession -> first question
```

Verify cancel creates zero rows and the 375x812 viewport has no overflow.

- [ ] **Step 4: Record exact evidence and commit**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record JD interview launch gate"
```
