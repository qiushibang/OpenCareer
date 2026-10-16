# Stage 7 Overnight Job Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the three accepted production sources into a reliable, searchable, observable job radar that can be demonstrated and operated repeatedly.

**Architecture:** Keep the existing `Adapter -> JobSnapshot -> CrawlerService -> JobRepository -> MCP` boundary. Extend only Career domain values, repository queries, MCP responses, workspace Skills, and OpenWorker's existing Automation configuration; do not modify TurnEngine, permissions, provider routing, or core conversation management.

**Tech Stack:** Python 3.12, SQLite schema v2, FastMCP, pytest, OpenWorker workspace Skills and Automation, React GUI smoke tests.

---

## Current Truth

- Production adapters: `xiaomi-careers`, `deepseek-careers`, `bytedance-seed-campus`.
- Persisted crawler data: Xiaomi 2,522 active jobs and one successful crawl.
- DeepSeek 32 jobs and ByteDance Seed 85 jobs passed live and GUI dry runs but are not persisted.
- Current complete regression: Career/backend 96 passed; GUI 109 passed.
- Known functional gaps:
  - a failed crawl may be wrapped as MCP `ok=true` with `status=failed`;
  - dry-run failure drops the underlying reason;
  - search has no `changed_after`, defaults to all statuses, and sorts by first seen only;
  - event query has no time/type/company filters and omits `changed_fields`;
  - source listing omits last success/failure and observed count;
  - `career-job-search` still describes the old mock-only workflow;
  - there is no all-source orchestration tool;
  - Git identity is not configured, so commits remain blocked unless the user supplies an identity.

## Overnight Gates

| Gate | Timebox | Deliverable | Continue only when |
|---|---:|---|---|
| G0 Baseline | 20 min | Clean test baseline and database inventory | Existing tests pass; no unexpected process or database drift |
| G1 Failure contract | 60 min | Failed crawl returns actionable MCP error | Offline tests cover live and dry-run failure without state damage |
| G2 Three-source persistence | 45 min | 2,639 crawler jobs persisted | DeepSeek 32 + ByteDance 85 written; repeat runs are unchanged |
| G3 Search | 90 min | Product-level job search | A-009 filters and default active/recent ordering pass |
| G4 Events and source health | 75 min | Changes and source status are queryable | Filters, changed fields, last run/error/count are returned |
| G5 All-source run | 60 min | One approval-gated sequential tool | One source failure does not prevent other sources from finishing |
| G6 Agent brief | 60 min | Real job radar Skill and Markdown brief | GUI uses MCP facts and writes a traceable artifact |
| G7 Soak and demo | 75 min | Repeat-run evidence and runbook | No duplicate jobs, false changes, or unexpected offline transitions |
| Stretch | remaining | Automation feasibility and UX polish | Only after G0-G7 pass |

## Task 0: Freeze Baseline And Inventory

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Record `git status --short`, baseline commit, Python/Node versions, running Server/GUI PIDs, and current source/job/run/event counts.
- [ ] Run:

```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q
cd surfaces/gui && npm test -- --run
git diff --check
```

- [ ] Stop G0 if a previously passing test fails. Diagnose that regression before changing behavior.
- [ ] Confirm no Git identity is configured with `git config --get user.name` and `git config --get user.email`. Do not invent identity values or modify global Git configuration.

## Task 1: Make Crawl Failures Actionable

**Files:**
- Modify: `extensions/career_mcp/domain/crawler.py`
- Modify: `extensions/career_mcp/services/crawler.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_crawler_service.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] Add a failing service test:

```python
result = CrawlerService(config, adapters=[FailingAdapter()]).crawl_registered_source(
    "failing", dry_run=True
)
assert result.status == "failed"
assert result.error_summary == "fixture failure"
```

- [ ] Run the focused test and confirm it fails because `CrawlResult` has no `error_summary`.
- [ ] Add `error_summary: str | None = None` to `CrawlResult`; preserve the sanitized Adapter exception for both persisted and dry-run failures.
- [ ] Add a failing MCP test requiring:

```python
assert result["ok"] is False
assert result["error"]["code"] == "CRAWL_FAILED"
assert result["error"]["retryable"] is True
```

- [ ] Change `crawl_source` so `failed` becomes an error envelope while `dry_run` and `succeeded` remain successful envelopes.
- [ ] Verify failed crawls do not add missing counts, job events, or versions.
- [ ] Run all crawler and MCP tests before continuing.

## Task 2: Persist DeepSeek And ByteDance Safely

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Run GUI/MCP dry runs for `deepseek-careers` and `bytedance-seed-campus`; require `created=32` and `created=85`.
- [ ] Through the existing approval cards, run `crawl_source(..., dry_run=false)` for DeepSeek and ByteDance. Do not bypass approval even with broad execution permission.
- [ ] Verify SQLite invariants:

```sql
SELECT cs.slug, COUNT(j.id), SUM(j.status='active')
FROM crawl_sources cs
LEFT JOIN jobs j ON j.crawl_source_id = cs.id
GROUP BY cs.id
ORDER BY cs.slug;
```

Expected crawler totals: ByteDance 85, DeepSeek 32, Xiaomi 2,522.

- [ ] Run a second successful crawl for DeepSeek and ByteDance; require `unchanged=32` and `unchanged=85`, with no new versions or events.
- [ ] Stop G2 on any count mismatch, duplicate ID, failed run, or unexpected changed/missing/offline transition.

## Task 3: Complete Search Contract

**Files:**
- Modify: `extensions/career_mcp/domain/models.py`
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/services/jobs.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_jobs_service.py`
- Modify: `extensions/career_mcp/tests/test_stage2_tools.py`

- [ ] Write failing tests for:
  - omitted `statuses` returns only active jobs;
  - `changed_after` excludes older changes;
  - company, city, recruitment type, first-seen, and changed-after filters compose;
  - ordering is `last_changed_at DESC, first_seen_at DESC, id ASC`;
  - limit remains 1-100 and offset remains non-negative.
- [ ] Add `changed_after: str | None` to `JobSearchFilters`.
- [ ] Normalize omitted/empty statuses to `["active"]` in `JobService`, without changing explicit status queries.
- [ ] Add `j.last_changed_at >= ?` and the required ordering to the structured SQL query.
- [ ] Keep offset pagination; do not add cursor pagination tonight.
- [ ] Run A-009 as an integration test: Beijing + internship + recent window returns only matching active jobs.

## Task 4: Add Event Filters And Source Health

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/services/crawler.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`
- Modify: `extensions/career_mcp/tests/test_crawler_repository.py`

- [ ] Write failing event tests for `event_types`, `company_slugs`, `occurred_after`, and `limit`.
- [ ] Return `changed_fields` by decoding `changed_fields_json`; retain job ID, company, title, event type, summary, and occurrence time.
- [ ] Reject unsupported event types and invalid limits with `INVALID_INPUT`.
- [ ] Write a failing `list_sources` test requiring each source to include:

```json
{
  "last_run_status": "succeeded",
  "last_run_at": "2026-08-05T...",
  "last_observed_count": 85,
  "last_error": null
}
```

- [ ] Implement one latest-run query per source using a SQL subquery or window expression; avoid N+1 Python queries.
- [ ] Use readable source names: Xiaomi Careers, DeepSeek Careers, ByteDance Seed Campus.
- [ ] Verify configured-but-never-run sources return null run fields rather than guessed success.

## Task 5: Add Approval-Gated All-Source Orchestration

**Files:**
- Modify: `extensions/career_mcp/services/crawler.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_crawler_service.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`
- Modify: `tests/test_mcp.py`

- [ ] Add a failing service test with one successful, one failing, and one successful FakeAdapter.
- [ ] Implement `crawl_all_sources(dry_run: bool = True)` as deterministic sequential orchestration over sorted enabled adapters.
- [ ] Return one result per source and an aggregate transition count. Catch source-level failures so later sources still run.
- [ ] Register the MCP tool without changing OpenWorker's permission engine. Confirm it receives the same approval treatment as `crawl_source`.
- [ ] Keep a 110-second aggregate acceptance budget. If live three-source execution exceeds it, retain per-source operation and disable the aggregate production path.
- [ ] Never use concurrent browser/API requests merely to reduce elapsed time.

## Task 6: Replace Mock Search Skill With Real Workflow

**Files:**
- Modify: `.coworker/skills/career-job-search/SKILL.md`
- Modify: `tests/test_skills.py`
- Add: `artifacts/three-source-job-radar-brief.md`

- [ ] Write a failing Skill test requiring the instructions to mention `search_jobs`, `get_job`, `list_recent_job_events`, source URLs, active default, pagination, and no fabricated fields.
- [ ] Replace the mock-only instructions with this workflow:
  1. use `list_sources` for source health questions;
  2. use `search_jobs` for filters and pagination;
  3. use `get_job` before detailed analysis;
  4. use `list_recent_job_events` for new/changed/offline questions;
  5. report tool errors and missing fields directly;
  6. write a Markdown brief only through normal file approval.
- [ ] Define one compact brief format: query, filters, generated time, source health, selected jobs, source URLs, and recent changes.
- [ ] In GUI, request Beijing AI/Agent jobs across all sources and write `artifacts/three-source-job-radar-brief.md`.
- [ ] Verify every listed job ID and URL exists in Career MCP output.

## Task 7: Soak Test, Demo, And Operational Runbook

**Files:**
- Add: `docs/13_JOB_RADAR_RUNBOOK.md`
- Modify: `README.md`
- Modify: `docs/07_TEST_AND_ACCEPTANCE.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Run all three sources again and capture transitions, elapsed times, and crawl-run records.
- [ ] Assert database invariants:
  - crawler job total is 2,639 unless a verified live source count changed;
  - every crawler job has source URL, external ID, first seen, last seen, and content hash;
  - no duplicate `(crawl_source_id, external_job_id)`;
  - failed runs did not create missing/offline events.
- [ ] Run the full Career/backend and GUI test suites plus GUI build.
- [ ] Document startup order, browser-extra installation, dry run, approved write run, search examples, event examples, source failure recovery, and database backup location.
- [ ] Execute the manual demo from `docs/07_TEST_AND_ACCEPTANCE.md`: source status -> search -> detail -> events -> Markdown artifact.
- [ ] Leave Server and GUI healthy and report their URLs and PIDs.

## Stretch Task: Automation Feasibility Only

**Files:**
- Modify only if supported: `docs/13_JOB_RADAR_RUNBOOK.md`

- [ ] Verify whether OpenWorker Automation can grant scoped standing approval to Career MCP read tools and `crawl_all_sources`.
- [ ] If the current permission model supports it without bypassing safety, create a daily Asia/Shanghai job-radar automation using the existing Automation UI/API.
- [ ] If MCP standing approval is unsupported, do not modify core permissions. Document a manual approved crawl followed by an automated/read-only digest as the supported workflow.
- [ ] Do not begin resume import, profile matching, application packets, a new frontend, or another company Adapter tonight.

## Final Acceptance

- Three official source datasets are persisted and repeat crawls are idempotent.
- Crawl failures are visible as MCP errors with sanitized reasons.
- Search satisfies keyword/company/city/type/status/first-seen/changed-after behavior.
- Events support time/type/company filters and include changed fields.
- Source status includes latest run outcome, count, and error.
- Career Agent produces one source-backed three-source brief through GUI.
- Full tests and `git diff --check` pass.
- All evidence is recorded in the development log and progress compass.

## Plan Self-Review

- Scope is one subsystem: Stage 7 job-radar usability and operations.
- Every behavioral change starts with a failing test and has a focused verification command.
- P1 resume/application work remains behind the documented seven-day stability gate.
- No step bypasses workspace trust, tool approval, login, CAPTCHA, signature, or source access controls.
- Existing dirty worktree and missing Git identity are preserved; no reset, cleanup, or fabricated commits are allowed.
