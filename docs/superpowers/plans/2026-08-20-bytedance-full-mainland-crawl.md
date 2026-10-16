# ByteDance Full Mainland Crawl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl all publicly listed mainland China ByteDance social and campus jobs through bounded, resumable cycles that update the production Catalog only after a complete validated cycle.

**Architecture:** Keep page transport and parsing independent from persistence. Add a resumable cycle store for shard cursors and staged snapshots, a bounded runner that performs at most 20 pages per call, and an atomic commit path that reuses the existing crawler transition rules. Use only requests emitted by ByteDance public pages and partition capped scopes with public filter metadata.

**Tech Stack:** Python 3.11, Playwright Chromium, FastMCP, PostgreSQL 16, SQLite, pytest, Docker crawler container.

---

### Task 1: Mainland Scope and Page Parsing

**Files:**
- Modify: `extensions/career_mcp/crawler/bytedance.py`
- Test: `extensions/career_mcp/tests/test_bytedance_browser.py`
- Create: `extensions/career_mcp/tests/fixtures/bytedance-mainland/social_page.json`
- Create: `extensions/career_mcp/tests/fixtures/bytedance-mainland/campus_page.json`
- Create: `extensions/career_mcp/tests/fixtures/bytedance-mainland/filter_metadata.json`

- [ ] **Step 1: Write failing parser tests**

Define tests for social portal, campus portal, internship mapping, mainland city filtering,
non-mainland exclusion, and missing-city rejection. Test the response matcher requires HTTPS,
official host, POST, 200, exact portal, filters, limit, and offset.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest extensions/career_mcp/tests/test_bytedance_browser.py -q`

Expected: FAIL because full-scope descriptors, shard filters, and parser entry points are absent.

- [ ] **Step 3: Add immutable scope and shard models**

Implement focused dataclasses:

```python
@dataclass(frozen=True)
class ByteDanceScope:
    source_slug: str
    portal_type: str
    recruitment_scope: str

@dataclass(frozen=True)
class ByteDanceShard:
    scope: ByteDanceScope
    location_code: str | None
    category_code: str | None
```

Add `BYTEDANCE_MAINLAND_SOCIAL` and `BYTEDANCE_MAINLAND_CAMPUS`. Keep old project classes
unchanged until migration Gate.

- [ ] **Step 4: Implement pure page parsing**

Parse one response into `ByteDanceListingPage`, preserving full description and requirement text.
Return filter metadata separately. Reject ambiguous city and unsupported recruitment types rather
than silently dropping records.

- [ ] **Step 5: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/crawler/bytedance.py \
  extensions/career_mcp/tests/test_bytedance_browser.py \
  extensions/career_mcp/tests/fixtures/bytedance-mainland
git commit -m "feat(crawler): parse ByteDance mainland scopes"
```

### Task 2: Resumable Cycle Schema

**Files:**
- Modify: `extensions/career_mcp/database/migrations.py`
- Create: `coworker/storage/postgres/sql/0007_crawl_cycles.sql`
- Modify: `coworker/storage/postgres/database.py`
- Test: `extensions/career_mcp/tests/test_crawler_repository.py`
- Test: `tests/test_postgres_schema.py`

- [ ] **Step 1: Write failing migration tests**

Assert SQLite and PostgreSQL expose:

```text
crawl_cycles
crawl_cycle_shards
crawl_cycle_jobs
```

Assert one running cycle per source, shard primary key `(cycle_id, shard_key)`, and staged job
primary key `(cycle_id, external_job_id)`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest extensions/career_mcp/tests/test_crawler_repository.py \
  tests/test_postgres_schema.py -q
```

Expected: FAIL because the tables are absent.

- [ ] **Step 3: Add schema migrations**

Use JSONB in PostgreSQL and canonical JSON text in SQLite. Add status checks for `running`,
`degraded`, `failed`, and `committed`. Add timestamps and error summary. Do not change
`catalog.jobs` or existing `crawl_runs` semantics.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extensions/career_mcp/database/migrations.py \
  coworker/storage/postgres/sql/0007_crawl_cycles.sql \
  coworker/storage/postgres/database.py \
  extensions/career_mcp/tests/test_crawler_repository.py \
  tests/test_postgres_schema.py
git commit -m "feat(storage): add resumable crawl cycles"
```

### Task 3: Cycle Repository Contract

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/database/postgres_catalog_repository.py`
- Test: `extensions/career_mcp/tests/test_crawler_repository.py`
- Test: `tests/test_postgres_catalog_repository.py`

- [ ] **Step 1: Write failing repository contract tests**

Cover create-or-resume cycle, lock collision, shard offset checkpoint, idempotent staged upsert,
same-ID/different-hash conflict, degraded status, and committed status.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest extensions/career_mcp/tests/test_crawler_repository.py \
  tests/test_postgres_catalog_repository.py -q
```

Expected: FAIL because cycle repository methods are absent.

- [ ] **Step 3: Implement the common repository surface**

Add:

```text
get_or_create_crawl_cycle(source_id)
list_cycle_shards(cycle_id)
checkpoint_cycle_shard(...)
stage_cycle_job(...)
list_cycle_jobs(cycle_id)
complete_cycle(cycle_id, status, error_summary=None)
```

PostgreSQL acquires a transaction-scoped advisory lock derived from source slug. SQLite remains
single-process and relies on its write transaction.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extensions/career_mcp/database/repository.py \
  extensions/career_mcp/database/postgres_catalog_repository.py \
  extensions/career_mcp/tests/test_crawler_repository.py \
  tests/test_postgres_catalog_repository.py
git commit -m "feat(crawler): persist crawl cycle checkpoints"
```

### Task 4: Bounded Cycle Runner and Atomic Commit

**Files:**
- Create: `extensions/career_mcp/services/resumable_crawler.py`
- Modify: `extensions/career_mcp/services/crawler.py`
- Test: `extensions/career_mcp/tests/test_resumable_crawler.py`
- Test: `extensions/career_mcp/tests/test_crawler_service.py`

- [ ] **Step 1: Write failing runner tests**

Use fixture transports to cover:

- stop after 20 pages and resume exact offset;
- replayed page is idempotent;
- cross-shard duplicate with same hash is accepted;
- same ID with different hash degrades;
- second pass converges after ordering drift;
- third pass still drifting degrades;
- running/degraded/failed cycles never call `mark_absent`;
- committed cycle calls the existing transition pipeline once.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest extensions/career_mcp/tests/test_resumable_crawler.py \
  extensions/career_mcp/tests/test_crawler_service.py -q
```

Expected: FAIL because `ResumableCrawlerService` is absent.

- [ ] **Step 3: Implement one bounded batch**

Process at most `max_pages=20`. Persist each accepted page and its next offset in one transaction.
Return cycle ID, processed pages, observed unique count, status, and `has_more`. Never return staged
jobs to the normal `CrawlerService.crawl()` path.

- [ ] **Step 4: Implement convergence and atomic commit**

After all shards complete, perform boundary validation passes up to three. On convergence, load
staged snapshots and call a new `CrawlerService.commit_complete_snapshot()` that contains the
existing transition loop and missing logic. Commit transitions, successful `crawl_run`, and cycle
status in one transaction.

- [ ] **Step 5: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/services/resumable_crawler.py \
  extensions/career_mcp/services/crawler.py \
  extensions/career_mcp/tests/test_resumable_crawler.py \
  extensions/career_mcp/tests/test_crawler_service.py
git commit -m "feat(crawler): commit complete resumable cycles"
```

### Task 5: First-Party Playwright Transport and Source Registration

**Files:**
- Modify: `extensions/career_mcp/crawler/bytedance.py`
- Modify: `extensions/career_mcp/crawler/adapters.py`
- Modify: `extensions/career_mcp/server.py`
- Test: `extensions/career_mcp/tests/test_bytedance_browser.py`
- Test: `extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] **Step 1: Write failing transport and registry tests**

Assert the transport opens only official social/campus pages, blocks images/media/fonts, captures
only exact first-party POST 200 responses, and never exposes `_signature`. Assert both new source
slugs are registered without removing old project sources.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest extensions/career_mcp/tests/test_bytedance_browser.py \
  extensions/career_mcp/tests/test_stage3_tools.py -q
```

Expected: FAIL because the new transport and resumable tool routing are absent.

- [ ] **Step 3: Implement the transport**

Use one fresh browser/context per bounded batch. Build public page URLs from verified public filter
metadata, wait for exact matching responses, and close all resources in `finally`. Return response
JSON only; do not persist request headers, cookies, or signature query values.

- [ ] **Step 4: Register resumable sources and route tools**

Register the two full scopes as resumable adapters. Keep old projects enabled until production
coverage migration. Make `crawl_source` return bounded progress for resumable adapters and the
existing result for atomic adapters.

- [ ] **Step 5: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/crawler/bytedance.py \
  extensions/career_mcp/crawler/adapters.py extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_bytedance_browser.py \
  extensions/career_mcp/tests/test_stage3_tools.py
git commit -m "feat(crawler): register ByteDance mainland cycles"
```

### Task 6: Daily Runner Resume Semantics

**Files:**
- Modify: `extensions/career_mcp/crawl_cli.py`
- Modify: `deploy/crawler/entrypoint.sh`
- Modify: `extensions/career_mcp/services/crawler.py`
- Test: `tests/test_crawl_cli_postgres.py`
- Test: `extensions/career_mcp/tests/test_crawler_service.py`

- [ ] **Step 1: Write failing CLI and global cursor tests**

Assert a resumable source remains the current `crawl_all_sources` item while `has_more=true`.
Assert process restart resumes from PostgreSQL without a local cursor. Assert social failure does
not erase campus progress.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/test_crawl_cli_postgres.py \
  extensions/career_mcp/tests/test_crawler_service.py -q
```

Expected: FAIL because global cursor currently advances after every source call.

- [ ] **Step 3: Implement bounded daily looping**

Add a CLI command that runs one ByteDance batch or loops until a configured wall-clock budget.
The container invokes it before or as part of the existing source schedule. Exit nonzero only for
infrastructure failure; a degraded cycle emits a structured result and leaves evidence intact.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extensions/career_mcp/crawl_cli.py deploy/crawler/entrypoint.sh \
  extensions/career_mcp/services/crawler.py \
  tests/test_crawl_cli_postgres.py \
  extensions/career_mcp/tests/test_crawler_service.py
git commit -m "feat(deploy): resume ByteDance crawl cycles"
```

### Task 7: Regression and Production Coverage Gate

**Files:**
- Modify: `docs/source-notes/bytedance.md`
- Modify: `docs/13_SOURCE_COVERAGE_MATRIX.md`
- Modify: `docs/14_CRAWL_ALL_SOURCES_RUNBOOK.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Run offline crawler regression**

```bash
python -m pytest extensions/career_mcp/tests/test_bytedance_browser.py \
  extensions/career_mcp/tests/test_resumable_crawler.py \
  extensions/career_mcp/tests/test_crawler_service.py \
  tests/test_crawl_cli_postgres.py tests/test_postgres_catalog_repository.py -q
python -m extensions.career_mcp.crawl_cli --list
```

- [ ] **Step 2: Run required project Gates**

```bash
python -m coworker.server.run --help
cd surfaces/gui && npx tsc && cd -
bash deploy/build-frontend.sh
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
```

- [ ] **Step 3: Run isolated live dry cycles**

Run social and campus against an isolated PostgreSQL database until each cycle reaches committed
or degraded. Record each public shard count, unique staged count, excluded non-mainland count,
passes, duration, and final transitions. Do not claim full coverage if any shard remains capped.

- [ ] **Step 4: Run controlled production cycles**

Back up production, deploy the migration and runner, complete both cycles, and verify:

```text
duplicate (crawl_source_id, external_job_id) = 0
non-committed cycles changed missing_count = 0
second complete cycle = unchanged except documented live changes
```

Only after coverage comparison succeeds, disable the two old project sources.

- [ ] **Step 5: Update evidence and commit**

Update the source note and coverage matrix with measured facts, not estimates.

```bash
git add docs/source-notes/bytedance.md docs/13_SOURCE_COVERAGE_MATRIX.md \
  docs/14_CRAWL_ALL_SOURCES_RUNBOOK.md docs/11_DEVELOPMENT_LOG.md \
  docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record ByteDance mainland crawl gate"
```
