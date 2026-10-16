# Tailored Resume PostgreSQL and Blob Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist cloud tailored-resume drafts and DOCX/PDF exports in tenant-scoped PostgreSQL and Blob storage while preserving the desktop SQLite/file workflow.

**Architecture:** Keep the existing `TailoredResumeService` and `TailoredResumeExportService` domain state machines. Inject tenant-scoped repository sessions in cloud mode; render DOCX/PDF in a private temporary directory, validate them, then atomically persist export metadata and both user Blobs in one PostgreSQL transaction. Desktop construction remains unchanged.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostgreSQL 16 RLS, `BYTEA` Blob storage, python-docx, pypdf, pytest.

---

### Task 1: Tailored storage schema and tenant integrity

**Files:**
- Create: `coworker/storage/postgres/sql/0005_tailored_resume_exports.sql`
- Modify: `tests/test_postgres_schema.py`

- [ ] Add a RED schema test expecting migration version 5, `career.tailored_resume_exports`, two Blob IDs, and composite tenant foreign keys from draft to resume/match and export to draft/Blobs.
- [ ] Run `.venv/bin/pytest -q tests/test_postgres_schema.py`; expect failure because migration 5 does not exist.
- [ ] Add migration 5. Preserve `career.tailored_resume_drafts.data` as the serialized domain record, add `(user_id, id)` uniqueness, replace the snapshot reference with `(user_id, snapshot_id)`, and create `career.tailored_resume_exports` with `docx_blob_id` and `pdf_blob_id`.
- [ ] Run the focused schema test; expect PASS.

### Task 2: PostgreSQL draft repository and service injection

**Files:**
- Create: `coworker/storage/postgres/tailored_resumes.py`
- Modify: `extensions/career_mcp/services/tailored_resumes.py`
- Create: `tests/test_postgres_tailored_resumes.py`

- [ ] Write a real PostgreSQL RED test that seeds one shared Job plus tenant Resume/Match, calls `prepare()` twice, and asserts one draft with version 1.
- [ ] Add RED assertions for proposal CAS, confirmation, stale detection, list/get recovery, and Alice/Bob isolation.
- [ ] Run the focused test; expect failure because `PostgresTailoredResumeRepository` and repository injection do not exist.
- [ ] Implement `PostgresTailoredResumeRepository` with `get`, `latest`, `list_for_job`, `create`, `update_if_version`, `get_export`, `get_export_for_version`, `latest_export`, `insert_export`, and `mark_exported_if_version`.
- [ ] Add an optional `repository_session` and injected Job/Resume/Match readers to `TailoredResumeService`. Use the existing SQLite transaction path when injection is absent.
- [ ] Run the focused PostgreSQL test and existing `test_tailored_resume_service.py`; expect PASS.

### Task 3: Atomic DOCX/PDF Blob export

**Files:**
- Modify: `coworker/storage/postgres/tailored_resumes.py`
- Modify: `extensions/career_mcp/services/tailored_resume_exports.py`
- Modify: `tests/test_postgres_tailored_resumes.py`

- [ ] Add RED tests that confirm a draft, export through a fake PDF converter, and assert one export row plus two user Blobs with matching SHA-256 values.
- [ ] Add RED tests for same-version idempotency, Blob tampering, missing Blob, cross-tenant read denial, and transaction rollback leaving no partial Blob/export row.
- [ ] Run the focused tests; expect failure because export still publishes only workspace files.
- [ ] Add optional cloud repository/principal boundaries to `TailoredResumeExportService`. Keep rendering and PDF validation in a private temporary directory, then call one repository method that inserts both Blobs, the export row, and marks the draft exported in a single transaction.
- [ ] Read cloud exports from Blob bytes and verify stored metadata SHA-256 before returning download content.
- [ ] Run PostgreSQL and existing desktop export tests; expect PASS.

### Task 4: Request-scoped FastAPI and MCP factories

**Files:**
- Modify: `coworker/server/app.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `tests/test_career_jobs_api.py`
- Modify: `tests/test_postgres_resume_service.py`

- [ ] Add RED tests proving all tailored REST routes pass `request.state.principal`, cloud MCP uses the same Principal as Match/Resume, and desktop factories remain local.
- [ ] Run the focused tests; expect cloud factories to expose SQLite services.
- [ ] Change FastAPI tailored factories to accept `Request` and construct PostgreSQL services only when `storage_runtime.mode == "postgres"`.
- [ ] Change Career MCP `_tailored_resume_service()` to use `_cloud_storage()` and `_match_service()` with the same Principal. Keep export out of MCP discovery as required by the existing safety boundary.
- [ ] Run focused HTTP/MCP tests; expect PASS.

### Task 5: Legacy migration and regression gates

**Files:**
- Modify: `deploy/migrate_to_postgres.py`
- Modify: `tests/test_postgres_migration.py`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Add RED migration fixtures for `tailored_resume_exports` and real DOCX/PDF source files; require idempotent metadata and SHA-identical Blob migration.
- [ ] Extend Career migration to map draft IDs and write export Blobs plus `career.tailored_resume_exports`; never silently mark an export migrated when either file is absent or hash-mismatched.
- [ ] Run real PostgreSQL migration twice and assert the second report has `reused=true`.
- [ ] Run the Tailored/PostgreSQL/Career regression set, backend `--help`, Crawler `--list`, TypeScript, alpha build, Python compile, and `git diff --check`.
- [ ] Record exact commands, pass counts, Docker availability, and remaining deployment risk in both progress documents.
