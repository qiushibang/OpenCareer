# PostgreSQL Job Radar Query Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce public Job Radar list and filter P95 latency to 500 ms or less while preserving the existing API contract and tenant visibility.

**Architecture:** Denormalize the authoritative manual-job owner onto
`catalog.jobs` with a database trigger, use that key in the security-barrier
view and write guard, remove the duplicate repository predicate, and map a
lightweight list projection separately from full Job detail. Aggregate shared
facets from one materialized visible set and add one partial feed index;
introduce no cache unless measured SQL-only performance misses the target.

**Tech Stack:** Python 3.12, PostgreSQL 16, psycopg 3, FastAPI, pytest.

---

### Task 1: Lock the Lightweight List SQL Contract

**Files:**
- Create: `tests/test_postgres_job_radar_performance.py`
- Modify: `extensions/career_mcp/database/postgres_catalog_repository.py`

- [ ] **Step 1: Write the failing repository test**

Create a fake connection that returns an exact count and one 14-column summary
row. Assert:

```python
jobs, total = repository.search_jobs(
    JobSearchFilters(statuses=["active"], limit=20, offset=0)
)

sql = "\n".join(call[0] for call in connection.calls)
assert "career.job_visible_to_user" not in sql
assert "j.description_raw" not in connection.calls[1][0]
assert "j.responsibilities" not in connection.calls[1][0]
assert "j.requirements" not in connection.calls[1][0]
assert total == 29612
assert jobs[0]["id"] == "job-1"
assert "description_raw" not in jobs[0]
assert jobs[0]["tracking"]["is_favorite"] is False
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_postgres_job_radar_performance.py::test_job_feed_uses_lightweight_visible_projection \
  -q
```

Expected: FAIL because the current SQL repeats the visibility function and
selects JD-sized columns.

- [ ] **Step 3: Implement the minimal repository change**

In `search_jobs()`:

```python
clauses = []
```

Continue to query `career.visible_jobs`; do not append a second
`career.job_visible_to_user()` predicate.

Change only the page projection to:

```sql
SELECT
    j.id, c.slug, c.name, j.title, j.location_raw,
    j.locations, j.recruitment_type, j.status,
    j.canonical_url, j.first_seen_at, j.last_seen_at,
    j.last_changed_at, tracking.data, tracking.version
```

Add `_job_summary_row()` for that shape. Keep `_job_row()` and `get_job()`
unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_postgres_job_radar_performance.py \
  tests/test_postgres_job_search.py \
  tests/test_career_jobs_api.py -q
```

Expected: PASS with the existing response contract unchanged.

### Task 2: Optimize the Equivalent Visibility View

**Files:**
- Create: `coworker/storage/postgres/sql/0008_job_radar_query_performance.sql`
- Modify: `tests/test_postgres_job_radar_performance.py`

- [ ] **Step 1: Write the failing migration contract test**

Assert migration `0008` exists and contains:

```python
assert "CREATE OR REPLACE VIEW career.visible_jobs" in sql
assert "visibility_user_id" in sql
assert "sync_manual_job_visibility" in sql
assert "FROM career.manual_job_owners owner" in sql
assert "career.job_visible_to_user(" not in view_body
assert "CREATE INDEX IF NOT EXISTS jobs_active_feed" in sql
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_postgres_job_radar_performance.py::test_migration_8_optimizes_visibility_and_feed_index \
  -q
```

Expected: FAIL because migration `0008` does not exist.

- [ ] **Step 3: Add migration 0008**

Backfill and maintain a non-RLS visibility key:

```sql
ALTER TABLE catalog.jobs
ADD COLUMN IF NOT EXISTS visibility_user_id TEXT
REFERENCES identity.users(id);

UPDATE catalog.jobs jobs
SET visibility_user_id = owner.user_id
FROM career.manual_job_owners owner
WHERE owner.job_id = jobs.id;

CREATE OR REPLACE VIEW career.visible_jobs
WITH (security_barrier = true)
AS
SELECT jobs.*
FROM catalog.jobs jobs
WHERE jobs.visibility_user_id IS NULL
   OR jobs.visibility_user_id = current_setting('app.user_id', true);

CREATE INDEX IF NOT EXISTS jobs_active_feed
ON catalog.jobs(first_seen_at DESC, id ASC)
WHERE status = 'active';
```

Add a trigger on `career.manual_job_owners` to keep the key synchronized, and
update `career.job_visible_to_user()` to use the same key. This is required
because querying the forced-RLS owner table directly from the view causes
another tenant's owner row to disappear and incorrectly treats that job as
shared.

### Task 2.5: Consolidate Filter Facets

- [ ] Add a RED test requiring two database calls for `get_job_filters()`.
- [ ] Compute company, location, recruitment type, and status counts from one
  materialized visible-job CTE.
- [ ] Keep the tenant-specific favorite count as a separate RLS query.
- [ ] Preserve the existing response shape and sort order.

- [ ] **Step 4: Verify migration discovery and unit tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_postgres_job_radar_performance.py \
  tests/test_storage_factory.py -q
```

Expected: PASS and migration discovery ends at version 8.

### Task 3: Prove Tenant Isolation on Real PostgreSQL

**Files:**
- Modify: `tests/test_postgres_job_radar_performance.py`

- [ ] **Step 1: Add the PostgreSQL integration regression test**

With `TEST_DATABASE_URL`, migrate an isolated database and create:

```text
shared job with no manual_job_owners row
Alice manual job with (alice, manual-job) ownership
Bob principal
```

Assert:

```python
assert shared_job in alice_ids
assert shared_job in bob_ids
assert manual_job in alice_ids
assert manual_job not in bob_ids
```

Also run migration twice and assert the second call applies no versions. This
test preserves the existing security behavior while Task 2's migration
contract test provides the required RED for the implementation change.

- [ ] **Step 2: Run the real integration test after migration 8**

Run:

```bash
TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  .venv/bin/python -m pytest \
  tests/test_postgres_job_radar_performance.py -q
```

Expected: PASS with shared visibility and manual-job isolation unchanged.

### Task 4: Production-Shaped Performance Gate

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Restore the latest production dump to an isolated database**

Restore backup `20260821T032119Z` into a temporary database and apply
migration 8. Do not point the public backend at this database.

- [ ] **Step 2: Compare query plans**

Run `EXPLAIN (ANALYZE, BUFFERS)` for:

```text
exact active count
first 20 active jobs
company facets
location facets
```

Require:

- no repository-level `career.job_visible_to_user()` predicate;
- no JD-sized columns in the list projection;
- no tenant visibility regression;
- active count equal to the source backup.

- [ ] **Step 3: Apply the cache decision**

If both endpoint-equivalent SQL paths fit within a 500 ms database budget, do
not add caching. If filters exceed 500 ms, stop and write a separate cache
design rather than adding an unreviewed cache in this change.

### Task 5: Backup, Deploy, and Measure Public P95

**Files:**
- Modify: `docs/source-notes/bytedance.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Run project Gates**

```bash
.venv/bin/python -m pytest \
  tests/test_postgres_job_radar_performance.py \
  tests/test_postgres_job_search.py \
  tests/test_postgres_tenant_scope.py \
  tests/test_career_jobs_api.py -q
.venv/bin/python -m coworker.server.run --help
.venv/bin/python -m extensions.career_mcp.crawl_cli --list
git diff --check
```

- [ ] **Step 2: Create a pre-migration production backup**

Use `docs/18_BACKUP_AND_ROLLBACK_RUNBOOK.md`. Verify the server and offsite
checksums before applying migration 8.

- [ ] **Step 3: Perform a blue-green backend switch**

Build a uniquely tagged image, preserve the current image/container/volume,
start the candidate on the existing host-network endpoint, and fail closed on
migration or health failure.

- [ ] **Step 4: Run security and correctness Gates**

Verify:

```text
PostgreSQL ready
Redis ready
WebSocket openworker subprotocol accepted
active count unchanged except audited crawler changes
active external-job duplicates = 0
Bob cannot read Alice's manual job
```

- [ ] **Step 5: Measure public endpoint P95**

After one warm-up request, collect at least 10 samples for:

```text
/_openworker/v1/career/jobs?limit=20
/_openworker/v1/career/jobs/filters
```

Sort each sample set and report P50, P95, and maximum. Both P95 values must be
500 ms or less. Otherwise roll back or stop for an explicitly reviewed cache
design.

- [ ] **Step 6: Record evidence and commit**

Record exact plans, timings, counts, image IDs, backup path, and any remaining
risk. Stage only files from this optimization and commit with:

```bash
git commit -m "perf(career): optimize PostgreSQL job radar queries"
```
