# Job Radar Favorites, JD, and Catalog Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add top-level All Jobs/Favorites navigation, show only the complete JD, and remove verified test Catalog rows without affecting official jobs.

**Architecture:** Reuse the existing `favorite_only` list query and expose a tenant-scoped favorite count through the existing filters response. Keep structured responsibility and requirement fields in storage for downstream analysis while removing their duplicate GUI rendering. Protect PostgreSQL integration tests with a fail-closed database-name guard and isolated teardown, then clean production test rows in one audited transaction.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, FastAPI, Python 3.11, psycopg 3, PostgreSQL 16, Docker, Caddy.

---

### Task 1: Tenant-Scoped Favorite Count

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/database/postgres_catalog_repository.py`
- Modify: `surfaces/gui/src/api.ts`
- Test: `tests/test_postgres_job_search.py`
- Test: `extensions/career_mcp/tests/test_job_tracking.py`

- [ ] **Step 1: Write failing repository tests**

Add assertions that one favorited record produces `favorite_count == 1` and a different tenant sees `0`.

```python
filters = repository.get_job_filters()
assert filters["favorite_count"] == 1
```

For SQLite, seed one `job_tracking` row with `is_favorite = 1` and assert the same key.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest -q \
  tests/test_postgres_job_search.py \
  extensions/career_mcp/tests/test_job_tracking.py
```

Expected: FAIL because `favorite_count` is absent.

- [ ] **Step 3: Implement the minimal count**

In SQLite `JobRepository.get_job_filters()`:

```python
favorite_row = self.connection.execute(
    "SELECT COUNT(*) FROM job_tracking WHERE is_favorite = 1"
).fetchone()
```

In `PostgresCatalogRepository.get_job_filters()`:

```python
favorite_row = self.connection.execute(
    """
    SELECT COUNT(*)
    FROM career.job_tracking
    WHERE is_favorite
    """
).fetchone()
```

Return:

```python
"favorite_count": int(favorite_row[0] if favorite_row else 0),
```

RLS and the request transaction's `app.user_id` keep the PostgreSQL result tenant-scoped.

Extend `CareerJobFilters`:

```typescript
favorite_count: number;
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit the focused change**

```bash
git add \
  extensions/career_mcp/database/repository.py \
  extensions/career_mcp/database/postgres_catalog_repository.py \
  surfaces/gui/src/api.ts \
  tests/test_postgres_job_search.py \
  extensions/career_mcp/tests/test_job_tracking.py
git commit -m "feat(jobs): expose favorite count"
```

### Task 2: Top Favorites Box and Single JD

**Files:**
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [ ] **Step 1: Write failing GUI tests**

Add a test that verifies both entrances and the query:

```typescript
expect(
  screen.getByRole("button", { name: "全部岗位" }),
).toHaveAttribute("aria-pressed", "true");
expect(
  screen.getByRole("button", { name: "收藏箱（1）" }),
).toBeTruthy();
expect(screen.queryByLabelText("仅看收藏")).toBeNull();

fireEvent.click(screen.getByRole("button", { name: "收藏箱（1）" }));
await waitFor(() =>
  expect(api.getCareerJobs).toHaveBeenLastCalledWith(
    expect.objectContaining({ favoriteOnly: true, offset: 0 }),
  ),
);
```

Add a detail test:

```typescript
expect(await screen.findByRole("heading", { name: "JD" })).toBeTruthy();
expect(screen.getByText("完整 JD")).toBeTruthy();
expect(screen.queryByRole("heading", { name: "职位职责" })).toBeNull();
expect(screen.queryByRole("heading", { name: "职位要求" })).toBeNull();
expect(screen.queryByRole("heading", { name: "完整 JD" })).toBeNull();
```

Update the arranged filter response with `favorite_count: 1`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/CareerJobsView.test.tsx
```

Expected: FAIL because the segmented entrances and `JD` heading do not exist.

- [ ] **Step 3: Implement the minimal GUI**

Render a tab-style segmented control above the existing filter grid:

```tsx
<div className="inline-flex rounded-lg border border-line bg-paper p-1">
  <button
    type="button"
    aria-pressed={!favoriteOnly}
    className={jobScopeClass(!favoriteOnly)}
    onClick={() => resetOffset(() => setFavoriteOnly(false))}
  >
    全部岗位
  </button>
  <button
    type="button"
    aria-pressed={favoriteOnly}
    className={jobScopeClass(favoriteOnly)}
    onClick={() => resetOffset(() => setFavoriteOnly(true))}
  >
    收藏箱（{filters?.favorite_count || 0}）
  </button>
</div>
```

Use a local `jobScopeClass(active: boolean)` function for the two stable styles. Remove the old checkbox and label.

Remove `DetailList` and both calls. Replace the complete-JD section heading:

```tsx
<h3 className="text-sm font-semibold mb-2">JD</h3>
```

Keep `detail.description_raw`, `detail.responsibilities`, and `detail.requirements` API types unchanged.

- [ ] **Step 4: Verify favorite mutation behavior**

After a successful favorite toggle, update the loaded filter count without another endpoint:

```typescript
setFilters((current) =>
  current
    ? {
        ...current,
        favorite_count: Math.max(
          0,
          current.favorite_count + (target ? 1 : -1),
        ),
      }
    : current,
);
```

Do not update the count on failed writes. Existing rollback and version-conflict behavior remains authoritative.

- [ ] **Step 5: Run GUI tests and verify GREEN**

Run:

```bash
cd surfaces/gui
npx vitest run \
  src/components/CareerJobsView.test.tsx \
  src/careerJobsApi.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit the focused change**

```bash
git add \
  surfaces/gui/src/components/CareerJobsView.tsx \
  surfaces/gui/src/components/CareerJobsView.test.tsx
git commit -m "feat(gui): add job favorites box"
```

### Task 3: Fail-Closed PostgreSQL Test Isolation

**Files:**
- Create: `tests/postgres_test_support.py`
- Create: `tests/test_postgres_test_support.py`
- Modify: `tests/test_postgres_integration.py`
- Modify: `tests/test_postgres_application_packets.py`
- Modify: `tests/test_postgres_tailored_resumes.py`

- [ ] **Step 1: Write the failing URL guard tests**

```python
def test_rejects_production_database_name():
    with pytest.raises(RuntimeError, match="refusing PostgreSQL tests"):
        validated_test_database_url(
            "postgresql://user:secret@localhost/opencareer_prod"
        )


@pytest.mark.parametrize(
    "database_name",
    ["opencareer_gate", "opencareer_gate_fresh", "feature_test"],
)
def test_accepts_isolated_database_names(database_name):
    url = f"postgresql://user:secret@localhost/{database_name}"
    assert validated_test_database_url(url) == url
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
pytest -q tests/test_postgres_test_support.py
```

Expected: FAIL because `tests.postgres_test_support` does not exist.

- [ ] **Step 3: Implement the guard**

```python
from urllib.parse import urlsplit


def validated_test_database_url(url: str) -> str:
    database_name = urlsplit(url).path.lstrip("/")
    allowed = (
        database_name in {"opencareer_gate", "opencareer_gate_fresh"}
        or database_name.endswith("_test")
    )
    if not allowed:
        raise RuntimeError(
            f"refusing PostgreSQL tests against database {database_name!r}"
        )
    return url
```

Each affected `database` fixture must call this helper before
`CloudDatabase.from_url()`. This prevents any future test run from targeting
`opencareer_prod`.

- [ ] **Step 4: Add isolated Catalog teardown**

In each affected test module, track the exact company, source, and job IDs it
creates. In fixture teardown, delete dependent test records in this order:

```sql
DELETE FROM career.tailored_resume_exports
WHERE draft_id IN (
    SELECT id FROM career.tailored_resume_drafts WHERE job_id = ANY(%s)
);
DELETE FROM career.interview_turns
WHERE session_id IN (
    SELECT id FROM career.interview_sessions WHERE job_id = ANY(%s)
);
DELETE FROM career.job_application_events WHERE job_id = ANY(%s);
DELETE FROM career.application_packets WHERE job_id = ANY(%s);
DELETE FROM career.tailored_resume_drafts WHERE job_id = ANY(%s);
DELETE FROM career.interview_sessions WHERE job_id = ANY(%s);
DELETE FROM career.job_resume_matches WHERE job_id = ANY(%s);
DELETE FROM career.job_tracking WHERE job_id = ANY(%s);
DELETE FROM catalog.job_events WHERE job_id = ANY(%s);
DELETE FROM catalog.job_versions WHERE job_id = ANY(%s);
DELETE FROM catalog.jobs WHERE id = ANY(%s);
DELETE FROM catalog.job_sources WHERE id = ANY(%s);
DELETE FROM catalog.companies WHERE id = ANY(%s);
```

The teardown must raise on failure. Do not catch or ignore cleanup errors.

- [ ] **Step 5: Run isolated PostgreSQL tests**

Run against `opencareer_gate`, never `opencareer_prod`:

```bash
TEST_DATABASE_URL="$OPENCAR_GATE_TEST_DATABASE_URL" pytest -q \
  tests/test_postgres_test_support.py \
  tests/test_postgres_integration.py \
  tests/test_postgres_application_packets.py \
  tests/test_postgres_tailored_resumes.py
```

Expected: PASS and no `API Company`, `Flow Company`, `Packet Co`, or
`Tailored Co` rows remain in the Gate database.

- [ ] **Step 6: Commit the focused change**

```bash
git add \
  tests/postgres_test_support.py \
  tests/test_postgres_test_support.py \
  tests/test_postgres_integration.py \
  tests/test_postgres_application_packets.py \
  tests/test_postgres_tailored_resumes.py
git commit -m "test(postgres): isolate catalog fixtures"
```

### Task 4: Audited Production Catalog Cleanup

**Files:**
- Create: `deploy/sql/cleanup_test_catalog_20260819.sql`
- Test: production PostgreSQL preflight and postflight queries

- [ ] **Step 1: Write a transaction that fails closed**

The SQL file must:

1. Create a temporary target table using the four approved slug patterns.
2. Assert exactly 33 jobs.
3. Assert zero references from all six career tables.
4. Assert every target Job Source has `source_type IN ('test', 'integration')`.
5. Delete target jobs, Job Sources, and Companies.
6. Assert 10,769 active jobs and zero target companies before commit.

Use `DO $$ ... RAISE EXCEPTION ... $$` for each assertion and one explicit
`BEGIN`/`COMMIT`.

- [ ] **Step 2: Validate against a restored production copy**

Restore the latest production custom dump into an isolated database, then run:

```bash
sudo -u postgres psql \
  --set=ON_ERROR_STOP=1 \
  -d opencareer_cleanup_rehearsal \
  -f cleanup_test_catalog_20260819.sql
```

Expected: all assertions pass and one transaction commits. Re-run against a
second fresh restore after deliberately adding a reference to one target Job;
expected result is a non-zero exit and all 33 target Jobs remain.

- [ ] **Step 3: Record production preflight**

Save the target Company, Source, Job IDs, reference counts, active count,
official crawl-source count, and duplicate business-key count under the release
directory. Do not include credentials.

- [ ] **Step 4: Apply once to production**

Run with `ON_ERROR_STOP=1` against `opencareer_prod`. Expected:

- 33 Jobs deleted.
- 33 Job Sources deleted.
- 33 Companies deleted.
- active Jobs: 10,769.
- official Crawl Sources unchanged.
- target references and target Companies: 0.

- [ ] **Step 5: Commit the cleanup script**

```bash
git add deploy/sql/cleanup_test_catalog_20260819.sql
git commit -m "ops(catalog): remove test job fixtures"
```

### Task 5: Regression, Browser Gate, and Alpha Release

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`
- Build output: `deploy/web/`

- [ ] **Step 1: Run focused and shared regression**

```bash
pytest -q \
  tests/test_postgres_job_search.py \
  tests/test_postgres_test_support.py \
  extensions/career_mcp/tests/test_job_tracking.py

cd surfaces/gui
npx vitest run \
  src/components/CareerJobsView.test.tsx \
  src/careerJobsApi.test.ts
npx tsc
cd ../..

python -m compileall \
  coworker \
  extensions/career_mcp \
  deploy
bash deploy/build-frontend.sh
git diff --check
```

Expected: all tests and checks pass. Existing npm audit and bundle-size warnings
are recorded but not changed in this scope.

- [ ] **Step 2: Start or deploy the tested build**

Build the backend with the China requirements path, stage the Alpha frontend,
and preserve the current backend container, static frontend, PostgreSQL restore
point, and exact-Origin configuration.

- [ ] **Step 3: Run desktop browser Gate**

Verify:

- Top buttons are visible and stable.
- Favorites displays the server count.
- Clicking Favorites sends `favorite_only=true`.
- Favoriting and unfavoriting update the count and list.
- Detail contains only one `JD` heading.
- Company dropdown has no four test company names.
- Console and failed network requests are empty.

- [ ] **Step 4: Run 375x812 browser Gate**

Verify no horizontal overflow, clipped controls, text overlap, or inaccessible
favorite action.

- [ ] **Step 5: Verify production runtime**

Check public and direct health, PostgreSQL/Redis readiness, backend and Caddy
restart counts, new frontend bundle, and logs for traceback/database/Redis
errors.

- [ ] **Step 6: Update evidence**

Append exact commands, test counts, production SQL counts, bundle name, image
ID, browser results, rollback assets, and residual risks to both documentation
files.

- [ ] **Step 7: Commit documentation**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record job radar cleanup gate"
```
