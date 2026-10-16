# PostgreSQL Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the cloud PostgreSQL system of record with schemas, RLS, Blob storage, connection scoping, and a repeatable migration framework while preserving desktop SQLite behavior.

**Architecture:** A small `CloudDatabase` interface owns pooled PostgreSQL transactions and tenant context. SQL migrations create identity, catalog, career, agent, and blob schemas. Desktop construction remains unchanged unless `DATABASE_URL` is set.

**Tech Stack:** Python 3.11+, psycopg 3, PostgreSQL 16, pytest, Docker Compose.

---

### Task 1: Cloud dependencies and Compose services

**Files:**
- Modify: `pyproject.toml`
- Modify: `deploy/requirements-server.txt`
- Modify: `deploy/requirements-server.cn.txt`
- Modify: `deploy/docker-compose.ip.yml`
- Modify: `deploy/docker-compose.yml`
- Test: `tests/test_cloud_compose.py`

- [ ] Write a failing test that parses both Compose files and asserts `postgres`, `redis`, healthchecks, persistent volumes, `DATABASE_URL`, and `REDIS_URL`.
- [ ] Run `pytest -q tests/test_cloud_compose.py`; expect missing service assertions.
- [ ] Add `psycopg[binary,pool]>=3.2,<4` and `redis>=5,<6` to both cloud dependency lists and project cloud extra.
- [ ] Add PostgreSQL 16 and Redis 7 services with private-only networking, healthchecks, memory limits, volumes, and secrets from `.env`.
- [ ] Run the focused test and both `docker compose ... config` commands; expect PASS.
- [ ] Commit `feat(storage): add postgres and redis infrastructure`.

### Task 2: Versioned PostgreSQL schema

**Files:**
- Create: `coworker/storage/postgres/migrations.py`
- Create: `coworker/storage/postgres/sql/0001_initial.sql`
- Create: `tests/test_postgres_schema.py`

- [ ] Write a failing integration test using `TEST_DATABASE_URL` that runs migration twice and asserts all five schemas and required tables exist.
- [ ] Add assertions for unique job identity, append-only message sequence, Blob SHA-256, and migration ledger.
- [ ] Run `pytest -q tests/test_postgres_schema.py`; expect import failure.
- [ ] Implement an advisory-lock migration runner and idempotent SQL migration.
- [ ] Run the focused test; expect PASS on a local PostgreSQL and SKIP with an explicit reason when `TEST_DATABASE_URL` is absent.
- [ ] Commit `feat(storage): add postgres schema migrations`.

### Task 3: Tenant transaction and RLS

**Files:**
- Create: `coworker/storage/postgres/database.py`
- Modify: `coworker/server/identity.py`
- Test: `tests/test_postgres_tenant_scope.py`

- [ ] Write RED tests creating Alice and Bob rows, asserting cross-user reads and writes return no rows.
- [ ] Add a pool-reuse test proving Bob cannot inherit Alice's `app.user_id`.
- [ ] Run `pytest -q tests/test_postgres_tenant_scope.py`; expect missing `CloudDatabase`.
- [ ] Implement `CloudDatabase.transaction(principal)` using `psycopg_pool.ConnectionPool`, a transaction block, and `SELECT set_config('app.user_id', %s, true)`.
- [ ] Enable and force RLS on every user-owned table with `USING` and `WITH CHECK` policies.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(storage): enforce postgres tenant scope`.

### Task 4: Blob repository

**Files:**
- Create: `coworker/storage/blobs.py`
- Create: `coworker/storage/postgres/blob_repository.py`
- Test: `tests/test_postgres_blobs.py`

- [ ] Write RED tests for user/shared ownership, SHA-256 calculation, streaming reads, soft delete, and cross-user denial.
- [ ] Define `BlobRepository.put/open/metadata/delete` without exposing database connections.
- [ ] Implement PostgreSQL `bytea` storage with a 10 MB resume limit and chunked response iterator.
- [ ] Run `pytest -q tests/test_postgres_blobs.py`; expect PASS.
- [ ] Commit `feat(storage): add tenant-scoped blob repository`.

### Task 5: Storage selection and health

**Files:**
- Create: `coworker/storage/factory.py`
- Modify: `coworker/server/run.py`
- Modify: `coworker/server/app.py`
- Test: `tests/test_storage_factory.py`
- Test: `tests/test_server.py`

- [ ] Write RED tests proving absent `DATABASE_URL` selects local adapters and cloud configuration fails closed when PostgreSQL is unavailable.
- [ ] Implement the factory and expose sanitized PostgreSQL/Redis readiness in authenticated health output.
- [ ] Run focused tests and `python -m coworker.server.run --help`; expect PASS.
- [ ] Commit `feat(storage): select cloud storage adapters`.

### Task 6: Repeatable migration framework

**Files:**
- Create: `deploy/migrate_to_postgres.py`
- Create: `tests/test_postgres_migration.py`

- [ ] Write RED fixture tests for migration batches, source hashes, idempotent reruns, count verification, and rollback-on-error.
- [ ] Implement CLI argument validation, migration ledger, dry-run, per-domain transactions, and JSON verification report.
- [ ] Ensure secrets are never printed and `._*` files are ignored.
- [ ] Run `pytest -q tests/test_postgres_migration.py`; expect PASS.
- [ ] Commit `feat(storage): add repeatable postgres migration`.

### Task 7: Foundation regression gate

- [ ] Run focused PostgreSQL tests with `TEST_DATABASE_URL`.
- [ ] Run `pytest -q tests/test_server_identity.py tests/test_alpha_mode.py tests/test_server.py`.
- [ ] Run both Compose config commands.
- [ ] Run `git diff --check`.
- [ ] Record exact evidence in `docs/11_DEVELOPMENT_LOG.md` and `docs/12_TONIGHT_PROGRESS.md`.
- [ ] Commit `docs(storage): record postgres foundation gate`.
