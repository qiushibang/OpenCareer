# ADR 0001: PostgreSQL Is the Cloud System of Record

- Status: Accepted
- Date: 2026-08-18

## Context

The current cloud Alpha persists related state across SQLite databases, JSONL conversations, JSON
files, private filesystem directories, and process memory. That layout is appropriate for the
desktop product but makes multi-user isolation, complete backup, cross-record auditing, and
horizontal runtime expansion difficult.

Redis can improve coordination and latency, but eviction and asynchronous persistence make it
unsuitable as the only copy of resumes, conversations, job history, approvals, or interview data.

## Decision

PostgreSQL will be the authoritative cloud store for all durable OpenCareer data:

- shared jobs, versions, events, crawl runs, and source snapshots;
- users, conversations, messages, compactions, context manifests, memories, approvals, and tasks;
- resumes, confirmed facts, applications, matches, interviews, evaluations, and generated files;
- binary content stored as integrity-checked `bytea` Blob records during the Alpha stage.

User-owned tables carry `user_id` and use PostgreSQL row-level security. Shared Job Catalog tables
are readable by authenticated users and writable only by the crawler role.

Redis is an optional Runtime State adapter for caches, rate limits, leases, distributed locks,
presence, and event fan-out. No workflow requires Redis data to recover durable business state.

Desktop mode keeps the existing SQLite and filesystem adapters. Callers use storage interfaces so
the domain and Agent loop do not branch on database type.

## Consequences

- Cloud backup and restore cover structured and binary data through PostgreSQL.
- Canonical messages remain queryable after Compaction.
- PostgreSQL and Redis add deployment dependencies and require health, migration, backup, and
  rollback gates.
- Storing Blobs in PostgreSQL is operationally simple for Alpha but increases database size. A
  future object-store adapter may replace Blob bytes without changing Blob ownership or references.
- The production cutover must follow identity and isolation tests; a failed migration leaves the
  existing SQLite volumes authoritative.
