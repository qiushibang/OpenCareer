# PostgreSQL Job Radar Query Performance Design

## Goal

Reduce the public Alpha Job Radar list and filter endpoint P95 latency to
500 milliseconds or less without changing the API response contract, frontend
interaction, tenant visibility rules, Origin validation, or token handling.

## Measured Baseline

Production measurements on 2026-08-21:

- Active jobs: 29,612.
- Total PostgreSQL database size: 343 MB.
- `GET /v1/career/jobs?limit=20`: approximately 2.1 seconds.
- `GET /v1/career/jobs/filters`: approximately 2.4 seconds.
- The server was not CPU- or memory-saturated during measurement.

`EXPLAIN (ANALYZE, BUFFERS)` showed:

- The list count scanned all visible jobs and took approximately 832 ms.
- The list page scanned and sorted all visible jobs and took approximately
  641 ms.
- Company and location facets each scanned all visible jobs and took
  approximately 490-503 ms.
- `career.job_visible_to_user()` was evaluated by the security-barrier view and
  then repeated explicitly by the repository list query.

The frontend requests filters and the first list page concurrently. Once the
list arrives, it requests the selected job detail. The list loading state is
therefore dominated by the list endpoint, while complete first-detail
readiness includes another request.

## Scope

This change will:

1. Make shared crawled jobs cheaply visible to every authenticated tenant while
   preserving owner-only visibility for manual jobs.
2. Remove the duplicate visibility predicate from Job Radar list SQL.
3. Stop selecting JD-sized fields for list rows.
4. Add an index for the active feed ordering used by the first page.
5. Optimize filter aggregation through the same visibility path.
6. Add a short-lived filter cache only if the SQL-only implementation does not
   meet the production P95 target.

This change will not:

- Change pagination semantics or API response fields.
- Replace exact counts with estimates.
- Migrate PostgreSQL to Supabase or another provider.
- Add a new frontend loading model.
- Relax RLS, manual-job ownership, Origin, token, or Alpha restrictions.

## Visibility Model

The authoritative rule remains:

- A job with no row in `career.manual_job_owners` is shared and visible to all
  authenticated users.
- A job with an ownership row is visible only when that row matches the current
  `(user_id, job_id)`.

Migration `0008` adds `catalog.jobs.visibility_user_id` as a denormalized
visibility key maintained from `career.manual_job_owners` by a database
trigger. The security-barrier view and `career.job_visible_to_user()` both use
that key directly. This preserves legacy shared jobs regardless of source type
and keeps write guards and list reads on the same rule.

The owner table itself cannot be queried directly from the view: its forced RLS
would hide Alice's ownership row from Bob, causing `NOT EXISTS` to incorrectly
classify Alice's manual job as shared. The denormalized key avoids that
cross-RLS anti-join while the owner table remains the authoritative relation.

Repository list and filter queries must rely on `career.visible_jobs` and must
not add a second visibility-function predicate.

## List Query

The list query keeps exact `COUNT(*)`, offset pagination, ordering, tracking,
and all existing filters.

The page projection will include only fields required by
`CareerJobSummary`:

- ID and company identity.
- Title, locations, recruitment type, and status.
- Canonical URL and timestamps.
- Per-user tracking data and version.

It will not select `description_raw`, `responsibilities`, or `requirements`.
The detail endpoint remains the only path that reads the complete JD.

`PostgresCatalogRepository` will use a dedicated summary row mapper so the
detail mapper and detail response remain unchanged.

## Indexes

Migration `0008` will add:

```sql
CREATE INDEX IF NOT EXISTS jobs_active_feed
ON catalog.jobs(first_seen_at DESC, id ASC)
WHERE status = 'active';
```

The migration will also ensure manual ownership lookup has an index beginning
with `job_id`. Migration `0006` already provides `UNIQUE (job_id)` and
`PRIMARY KEY (user_id, job_id)`, so `0008` does not add a redundant ownership
index.

Indexes are additive and use `IF NOT EXISTS`. Production rollout will apply the
migration before replacing the backend. The 30,000-row table is small enough
for the non-concurrent migration inside the existing migration transaction,
but deployment still records lock duration and aborts if migration or health
checks fail.

## Filter Query

Companies, locations, recruitment types, and statuses continue to return exact
counts. They are computed from one materialized visible-job CTE, reducing four
full table reads to one database query. The tenant-specific favorite count
remains a separate RLS-protected query. The response structure and ordering do
not change.

After SQL optimization, the filter endpoint will be sampled independently. A
30-60 second cache may be added only if its P95 remains above 500 ms. Any cache
must:

- Cache shared facets separately from the current user's favorite count.
- Include tenant identity in user-specific cache keys.
- Expire automatically.
- Never cache Job detail, resume, tracking note, or application state.

## Tests

TDD coverage will prove:

1. The list query does not contain an explicit
   `career.job_visible_to_user()` predicate.
2. The list projection does not select JD-sized fields.
3. Summary rows preserve the current API response contract.
4. Shared crawled jobs remain visible to Alice and Bob.
5. Alice's manual job is invisible to Bob.
6. Migration `0008` is idempotent and creates the active feed index.
7. Existing search, favorite, application-status, and filter behavior remains
   unchanged.

The real PostgreSQL Gate will re-run tenant isolation tests and compare result
counts before and after migration.

## Performance Gate

Before deployment:

- Run focused repository, job API, migration, and tenant tests.
- Run `EXPLAIN (ANALYZE, BUFFERS)` against a production-shaped PostgreSQL
  database.
- Confirm the list no longer evaluates visibility twice and no longer carries
  JD-sized rows through the feed query.

After deployment:

- Sample each public endpoint at least 10 times after one warm-up request.
- Require P95 at or below 500 ms for:
  - `/v1/career/jobs?limit=20`
  - `/v1/career/jobs/filters`
- Confirm active total remains 29,612 unless a concurrently completed official
  crawl produces an audited count change.
- Confirm active external-job duplicates remain zero.
- Confirm cross-tenant manual-job reads return zero.

## Rollout and Rollback

The rollout uses the existing backup and blue-green container procedure:

1. Record current image, health, counts, and query plans.
2. Back up PostgreSQL before migration.
3. Build and smoke-test a uniquely tagged image.
4. Apply migration and start the new backend.
5. Run REST, WebSocket, tenant-isolation, count, and latency Gates.

Any security, count, migration, health, or response-contract failure stops the
release. The old container and image remain available. Migration `0008` is
additive except for the view definition; rollback restores the previous view
definition before restarting the old image.
