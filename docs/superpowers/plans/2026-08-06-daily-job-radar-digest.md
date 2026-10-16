# Daily Job Radar Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete, read-only 24-hour job-radar digest and deliver it every day through OpenWorker Automation as both Markdown and a session result.

**Architecture:** `JobRepository` performs complete SQL aggregation and bounded sample selection. `CrawlerService` validates the rolling window and combines repository data; the MCP server only returns existing success/error envelopes. Career Skill and Automation consume the read-only tool without changing crawler state or OpenWorker permissions.

**Tech Stack:** Python 3.12, SQLite schema v3, FastMCP, pytest, OpenWorker workspace Skills and Automation.

---

## File Map

| File | Responsibility |
|---|---|
| `extensions/career_mcp/database/repository.py` | Aggregate job counts, windowed events, company totals, samples, and latest source health |
| `extensions/career_mcp/services/crawler.py` | Validate digest inputs, calculate UTC window, assemble response |
| `extensions/career_mcp/server.py` | Expose `get_job_radar_digest` and translate errors |
| `extensions/career_mcp/tests/test_crawler_repository.py` | Prove complete aggregation and latest-run source health |
| `extensions/career_mcp/tests/test_crawler_service.py` | Prove rolling-window and validation behavior |
| `extensions/career_mcp/tests/test_stage3_tools.py` | Prove MCP envelope and registration |
| `tests/test_mcp.py` | Prove stdio discovery exposes the new tool |
| `.coworker/skills/career-job-search/SKILL.md` | Replace mock workflow with real Career MCP workflow and daily format |
| `tests/test_skills.py` | Lock down Skill tool names, source URLs, and fact constraints |
| `docs/15_DAILY_JOB_RADAR_DIGEST_RUNBOOK.md` | Document schedule, artifact, manual run, and failure behavior |
| `artifacts/job-radar-daily/2026-08-06.md` | Real source-backed smoke artifact |

### Task 1: Repository Aggregation

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/tests/test_crawler_repository.py`

- [ ] **Step 1: Write a failing complete-aggregation test**

Insert two companies, two crawl sources, jobs, four in-window events, one
out-of-window event, and multiple source runs. Require:

```python
digest = repository.get_job_radar_digest_data(
    occurred_after="2026-08-05T01:00:00Z",
    sample_limit=2,
)

assert digest["jobs"] == {"total": 3, "active": 2, "inactive": 1}
assert digest["events"]["total"] == 4
assert digest["events"]["by_type"] == {"changed": 2, "created": 1, "missing": 1}
assert len(digest["events"]["samples"]) == 2
assert digest["events"]["by_company"][0]["total"] == 3
assert digest["sources"]["configured"] == 2
assert digest["sources"]["healthy"] == 1
assert digest["sources"]["failed"] == 1
assert digest["sources"]["pending"] == 0
```

The assertion that total is four while samples are two proves the display limit
does not truncate aggregation.

- [ ] **Step 2: Run the repository test and verify RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_crawler_repository.py::test_job_radar_digest_aggregates_full_window_and_latest_source_health \
  -q
```

Expected: fail because `get_job_radar_digest_data` does not exist.

- [ ] **Step 3: Implement the repository method**

Add:

```python
def get_job_radar_digest_data(
    self,
    *,
    occurred_after: str,
    sample_limit: int,
) -> dict:
```

Use separate structured SQL queries:

```sql
SELECT COUNT(*) AS total,
       COALESCE(SUM(status = 'active'), 0) AS active,
       COALESCE(SUM(status = 'inactive'), 0) AS inactive
FROM jobs
```

```sql
SELECT event_type, COUNT(*) AS count
FROM job_events
WHERE occurred_at >= ?
GROUP BY event_type
ORDER BY event_type
```

```sql
SELECT c.slug AS company_slug, c.name AS company_name,
       e.event_type, COUNT(*) AS count
FROM job_events e
JOIN jobs j ON j.id = e.job_id
JOIN companies c ON c.id = j.company_id
WHERE e.occurred_at >= ?
GROUP BY c.id, e.event_type
ORDER BY c.slug, e.event_type
```

Sample rows must include `j.canonical_url AS source_url`. Latest source health
must use `ROW_NUMBER() OVER (PARTITION BY cs.id ORDER BY cr.started_at DESC,
cr.id DESC)` so one query selects the latest run. A configured source without a
run has null latest-run fields and increments `pending`. Return only failed or
pending rows in `sources.items`; keep configured/healthy/failed/pending counts
based on the complete source set.

- [ ] **Step 4: Run repository tests and verify GREEN**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_crawler_repository.py -q
```

Expected: all tests pass.

### Task 2: Service And MCP Contract

**Files:**
- Modify: `extensions/career_mcp/services/crawler.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_crawler_service.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] **Step 1: Write failing service tests**

Add an injectable UTC clock to `CrawlerService` and assert:

```python
service = CrawlerService(
    config,
    clock=lambda: datetime(2026, 8, 6, 1, 0, tzinfo=timezone.utc),
)
result = service.get_job_radar_digest(hours=24, sample_limit=20)

assert result["window"] == {
    "started_at": "2026-08-05T01:00:00Z",
    "ended_at": "2026-08-06T01:00:00Z",
    "hours": 24,
}
```

Also register one `FakeAdapter` that has no persisted `crawl_sources` row and
require it to appear in `sources.items` with null run fields while incrementing
`sources.pending`.

Parametrize invalid values:

```python
("hours", 0)
("hours", 169)
("sample_limit", 0)
("sample_limit", 101)
```

Each must raise `ValueError` with a stable range message.

- [ ] **Step 2: Run service tests and verify RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_crawler_service.py \
  -k job_radar_digest -q
```

Expected: fail because the clock argument and digest method do not exist.

- [ ] **Step 3: Implement service assembly**

Extend the constructor without changing existing callers:

```python
def __init__(
    self,
    config: CareerConfig | None = None,
    *,
    adapters: Iterable[JobAdapter] = (),
    clock: Callable[[], datetime] | None = None,
) -> None:
    ...
    self._clock = clock or (lambda: datetime.now(timezone.utc))
```

Implement:

```python
def get_job_radar_digest(
    self,
    *,
    hours: int = 24,
    sample_limit: int = 20,
) -> dict:
```

Validate ranges, require an aware UTC clock value, calculate
`started_at = ended_at - timedelta(hours=hours)`, call the repository method,
merge repository source rows against `self.adapters.source_slugs()`, and prepend
the normalized `window` object. Only currently registered adapters contribute to
`configured/healthy/failed/pending`; a registered adapter without a persisted
run becomes pending.

- [ ] **Step 4: Write failing MCP tests**

Require:

```python
assert server.get_job_radar_digest(hours=0)["error"]["code"] == "INVALID_INPUT"
assert server.get_job_radar_digest()["ok"] is True
assert "window" in server.get_job_radar_digest()["data"]
```

Also require `get_job_radar_digest` in the stdio MCP discovered tool names in
`tests/test_mcp.py`.

- [ ] **Step 5: Register the read-only MCP tool**

Add the server function with existing envelope handling:

```python
def get_job_radar_digest(
    hours: int = 24,
    sample_limit: int = 20,
) -> dict:
```

Register it with:

```python
mcp.tool()(get_job_radar_digest)
```

Do not add approval metadata and do not modify OpenWorker permissions.

- [ ] **Step 6: Run service and MCP tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_crawler_service.py \
  extensions/career_mcp/tests/test_stage3_tools.py \
  tests/test_mcp.py -q
```

Expected: all tests pass and stdio discovers ten Career MCP tools.

### Task 3: Real Career Job Search Skill

**Files:**
- Modify: `.coworker/skills/career-job-search/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: Write the failing Skill contract test**

Load the workspace Skill and require all of:

```python
required = {
    "get_job_radar_digest",
    "list_sources",
    "search_jobs",
    "get_job",
    "list_recent_job_events",
    "source URL",
    "active",
    "pagination",
}
assert all(value in skill_text for value in required)
assert "mock data" not in skill_text
assert "do not fabricate" in skill_text.lower()
```

- [ ] **Step 2: Run the Skill test and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_skills.py -k career_job_search -q
```

Expected: fail because the Skill still describes `get_mock_jobs`.

- [ ] **Step 3: Replace the Skill body**

Keep the existing frontmatter. Define:

- tool-selection rules from the approved design;
- active-only default for normal search;
- offset/limit pagination until the requested result set is covered;
- `get_job` before detailed analysis;
- official source URL and job ID in every listed result;
- direct reporting of tool errors and missing fields;
- the exact daily Markdown section order;
- no fabricated counts, fields, or mock labeling.

- [ ] **Step 4: Run Skill and Persona tests**

Run:

```bash
.venv/bin/pytest tests/test_skills.py tests/test_builtin_personas.py -q
```

Expected: all tests pass.

### Task 4: Daily Automation And Real Artifact

**Files:**
- Add: `docs/15_DAILY_JOB_RADAR_DIGEST_RUNBOOK.md`
- Add: `artifacts/job-radar-daily/2026-08-06.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Restart Server before GUI**

Start with absolute state paths:

```bash
COWORKER_STATE_DIR="$PWD/.local-state" \
CAREER_DATA_DIR="$PWD/career" \
.venv/bin/openworker-server --cwd "$PWD" --port 8765
```

Then start GUI from `surfaces/gui` with the same absolute
`COWORKER_STATE_DIR`.

- [ ] **Step 2: Run a real read-only MCP smoke**

Call `get_job_radar_digest(hours=24, sample_limit=20)` through a Career
Automation/session. Verify:

- event total equals the database aggregate for the same returned window;
- samples are at most 20;
- source configured/healthy/failed/pending totals are internally consistent;
- no new `crawl_runs`, `job_events`, or `job_versions` are created.

- [ ] **Step 3: Create the daily Automation**

Use the existing trusted workspace and Career agent:

```text
title: Career Job Radar Daily Digest
cron: 0 9 * * *
timezone: Asia/Shanghai
workspace: <repo>
agent: career
```

Instructions must call only `get_job_radar_digest`, `write_file`, and optional
todo tools. Explicitly forbid Shell and crawler tools.

- [ ] **Step 4: Execute one scheduled smoke run**

Temporarily trigger the task, verify the dated artifact and session result, then
restore `0 9 * * *`. The artifact must contain the exact window, all aggregate
counts, source warnings, sample job IDs, and official source URLs.

- [ ] **Step 5: Write the runbook**

Document task ID, schedule, output path, manual trigger, source-failure
interpretation, empty-window behavior, and recovery. Record the real smoke
counts in the development log and progress compass.

### Task 5: Final Regression And Commit

**Files:**
- Verify all files above

- [ ] **Step 1: Run complete relevant backend tests**

```bash
.venv/bin/pytest \
  tests/test_automation.py \
  tests/test_automation_create.py \
  tests/test_mcp.py \
  extensions/career_mcp/tests \
  tests/test_skills.py \
  tests/test_builtin_personas.py -q
```

- [ ] **Step 2: Run GUI tests and build**

```bash
cd surfaces/gui
npm test -- --run
npm run build
```

- [ ] **Step 3: Verify database invariants**

Require 34 latest source runs succeeded, duplicate crawl identities zero, and
`PRAGMA foreign_key_check` empty. Confirm the digest smoke did not add crawler
state.

- [ ] **Step 4: Check and commit only digest files**

```bash
git diff --check
git commit --only -m "feat(career): add daily job radar digest" -- \
  extensions/career_mcp/database/repository.py \
  extensions/career_mcp/services/crawler.py \
  extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_crawler_repository.py \
  extensions/career_mcp/tests/test_crawler_service.py \
  extensions/career_mcp/tests/test_stage3_tools.py \
  tests/test_mcp.py \
  .coworker/skills/career-job-search/SKILL.md \
  tests/test_skills.py \
  docs/15_DAILY_JOB_RADAR_DIGEST_RUNBOOK.md \
  artifacts/job-radar-daily/2026-08-06.md \
  docs/11_DEVELOPMENT_LOG.md \
  docs/12_TONIGHT_PROGRESS.md
```

Existing unrelated staged and unstaged files must remain untouched.

## Execution Outcome

- Repository, Service, MCP, Skill, artifact, Automation, and runbook tasks completed.
- Real stdio discovery exposed ten Career MCP tools.
- Digest smoke wrote `artifacts/job-radar-daily/2026-08-06.md` without changing
  crawl runs, job events, or job versions.
- Final verification: backend 210 passed, GUI 110 passed, GUI production build
  passed, and `git diff --check` passed.
- Implementation variance: source health detail is exception-only to keep the
  model context bounded; aggregate health counts still cover all configured
  sources.
