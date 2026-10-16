# PostgreSQL Job Catalog and Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the shared Job Catalog and crawler history to PostgreSQL, provide exact and full-text job search with traceable resume evidence matching, and restore scheduled all-source crawling.

**Architecture:** Existing adapters and `CrawlerService` stay authoritative for fetch, normalization, transitions, and quality gates. A PostgreSQL catalog repository replaces SQLite persistence in cloud mode. The crawler writes one shared catalog and publishes cache invalidation only after commit.

**Tech Stack:** Python, PostgreSQL 16, psycopg 3, Redis 7, Playwright, pytest.

---

### Task 1: Catalog repository interface

**Files:**
- Create: `extensions/career_mcp/database/catalog_repository.py`
- Create: `extensions/career_mcp/database/postgres_catalog_repository.py`
- Modify: `extensions/career_mcp/services/jobs.py`
- Modify: `extensions/career_mcp/services/crawler.py`
- Test: `tests/test_postgres_catalog_repository.py`

- [ ] Write RED contract tests for source registration, upsert, version, event, missing/offline, dry-run, failed-run isolation, and idempotent replay.
- [ ] Define one repository interface used by Jobs and Crawler services.
- [ ] Implement PostgreSQL transactions while retaining the SQLite adapter for desktop.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(catalog): add postgres job repository`.

### Task 2: Exact filters and full-text retrieval

**Files:**
- Modify: `coworker/storage/postgres/sql/0001_initial.sql`
- Modify: `extensions/career_mcp/database/postgres_catalog_repository.py`
- Test: `tests/test_postgres_job_search.py`

- [ ] Write RED tests for exact company/location/type/status/time filters and stable cursor pagination.
- [ ] Add generated/search-vector columns and GIN indexes for title, department, description, responsibilities, and requirements.
- [ ] Add Chinese query token normalization without model calls.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(catalog): add exact and full-text job search`.

### Task 3: Traceable resume matching

**Files:**
- Modify: `extensions/career_mcp/domain/matching.py`
- Modify: `extensions/career_mcp/services/matches.py`
- Test: `tests/test_postgres_job_resume_matching.py`

- [ ] Write RED tests for exact requirement refs, job hash, resume revision, personal fact refs, stale detection, and no fabricated evidence.
- [ ] Keep deterministic filtering/ranking and use the model only for unresolved semantic relations.
- [ ] Persist every match item with source refs and calculation inputs.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(matching): persist traceable postgres matches`.

### Task 4: Crawler CLI single PostgreSQL target

**Files:**
- Modify: `extensions/career_mcp/crawl_cli.py`
- Modify: `deploy/crawler/entrypoint.sh`
- Test: `tests/test_crawl_cli_postgres.py`

- [ ] Write RED tests for one fetch per source, PostgreSQL target, raw snapshot Blob, dry-run, from-cache replay, partial failure exit code, and advisory lock.
- [ ] Replace cloud multi-SQLite fan-out with one PostgreSQL catalog transaction per source.
- [ ] Keep desktop/default SQLite CLI path for local use.
- [ ] Publish Redis invalidation only after successful commit.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(crawler): write shared postgres catalog`.

### Task 5: Catalog migration

**Files:**
- Modify: `deploy/migrate_to_postgres.py`
- Test: `tests/test_postgres_catalog_migration.py`

- [ ] Write RED tests migrating companies, sources, runs, jobs, versions, events, and snapshot files.
- [ ] Verify IDs, active count, source count, foreign keys, unique identities, and snapshot SHA-256.
- [ ] Implement idempotent migration and JSON verification report.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(catalog): migrate sqlite job history`.

### Task 6: Local fixture and all-source gate

- [ ] Run adapter fixture tests with networking disabled.
- [ ] Run `python -m extensions.career_mcp.crawl_cli --list`.
- [ ] Run cache replay against test PostgreSQL.
- [ ] Run full Career tests and `git diff --check`.
- [ ] Record evidence and commit `docs(crawler): record postgres crawler gate`.

### Task 7: Server migration rehearsal

- [ ] Build backend and crawler images after deleting `._*` files from the transfer set.
- [ ] Start PostgreSQL and Redis in an isolated Compose project or alternate port.
- [ ] Back up current volume and run migration dry-run, migration, and verification.
- [ ] Compare current 286 jobs, active count, source count, resume count, Conversation count, and Blob hashes.
- [ ] Run shadow reads without switching production.
- [ ] Stop rehearsal services if any count or hash differs.

### Task 8: Production crawler restoration

- [ ] Cut over backend/crawler `DATABASE_URL` only after rehearsal passes.
- [ ] Run light API/static source dry-runs and then committed crawls.
- [ ] Run Playwright sources separately within the 2C2G memory budget.
- [ ] Verify each latest `crawl_run`, foreign keys, duplicate identity count, and active total.
- [ ] Re-run successful sources and confirm predominantly `unchanged`.
- [ ] Enable daily 04:00 schedule with jitter and confirm next execution time.
- [ ] Verify `/_openworker/v1/health`, REST auth, WebSocket 101/1008, and current user data.
- [ ] Record failures by source without weakening quality gates.
