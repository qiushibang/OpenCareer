# Stage 2 Closeout And Stage 3 Crawler Design

## Scope And Gate

This work has two ordered parts:

1. Finish the remaining visible Stage 2 acceptance evidence.
2. Implement the Stage 3 crawler framework only after Stage 2 is accepted.

Stage 3 does not include an online request, an official-company adapter, login, CAPTCHA handling, or any attempt to bypass site controls. Those remain Stage 4 work.

## Stage 2 Acceptance

Use a fresh trusted Career GUI session and one fixed, unique test JD. The session must retain the project workspace and expose Career MCP tools through the existing OpenWorker permission flow.

The acceptance sequence is:

1. Call `import_manual_jd(confirmed=false)` and verify the returned preview.
2. Call the same tool with `confirmed=true` and verify `created=true`.
3. Call `get_job` with the returned job id and verify one Version 1 and one `created` event.
4. Call `search_jobs` with the test title, Beijing, and internship filters and verify the job is returned.
5. Confirm the same JD again and verify the same job id with `duplicate=true`, without another version or event.
6. Generate a Markdown brief that identifies the source data as Career MCP output and approve its OpenWorker file-write request.

The GUI result, server tool-call log, test command output, and artifact path are recorded in the development log. A model response based on reading source code, or an unapproved Shell request, is not acceptance evidence.

## Stage 3 Architecture

The crawler framework has four explicit boundaries:

| Unit | Responsibility | Must not do |
|---|---|---|
| Adapter | Fetch or provide source-specific raw job snapshots | Persist data, call MCP, call an Agent, or modify GUI |
| Normalizer | Convert an adapter snapshot to a deterministic canonical candidate | Access the network or SQLite |
| Pipeline | Compare candidates with stored jobs and choose state transitions | Parse source-specific HTML |
| Repository | Persist sources, crawl runs, jobs, versions, and events transactionally | Invoke adapters or MCP |

The initial adapter is a `FakeAdapter` used only by fixture tests. Its input is fixed local data, so default tests are fully offline.

## State Model

A run processes exactly one configured source. A candidate identity is derived deterministically from source id and source job key. A content hash is derived from its normalized content.

| Prior state / observation | Result |
|---|---|
| No stored identity / candidate found | `created`, Version 1 |
| Active stored job / same content hash | `unchanged`, update `last_seen_at` only |
| Active stored job / changed content hash | `changed`, append Version and Event |
| Active stored job / not observed while run succeeds | increment missing count and emit `missing` |
| Missing count reaches configured threshold | mark inactive and emit `offline` |
| Inactive stored job / candidate found | mark active and emit `reopened`; append a version only when content changed |
| Adapter failure | mark run failed; do not increment missing count or mark jobs offline |

The first implementation uses a local threshold supplied by source configuration. It defaults to two successful absent runs. There is no scheduler or background worker in Stage 3.

## Data And Interfaces

New domain types are immutable dataclasses:

- `JobSnapshot`: raw adapter output with source job key, title, raw description, source URL, and observed timestamp.
- `NormalizedJob`: deterministic fields required by the pipeline, including identity and content hash.
- `CrawlResult`: source id, run id, terminal status, and transition counts.

The adapter protocol exposes one `fetch_jobs()` method returning `list[JobSnapshot]`. The crawler service accepts an adapter and repository through constructor injection, enabling fixture-only tests.

The Career MCP server exposes read-only `list_sources` and `list_recent_job_events` in Stage 3. `crawl_source(source_id, dry_run=false)` is registered as a write-risk tool and remains subject to the existing OpenWorker approval card. A dry run computes transitions without persistence.

## Schema Changes

Add migrations rather than modifying migration 1:

- `crawl_sources`: source identity, enabled state, missing threshold, and timestamps.
- `crawl_runs`: start/end timestamps, terminal status, error summary, and observed count.
- source linkage and missing-count fields needed by jobs.
- raw snapshot metadata sufficient to trace a normalized job back to a source observation.

Existing manual JD behavior and its tables remain compatible. Manual jobs are not processed by crawler absence logic.

## Error Handling

Adapter errors are captured as a failed crawl run with a concise, non-secret error summary. The pipeline exits before absence processing. Invalid snapshots are counted and recorded in the run summary; a run with no valid snapshots is not considered successful for offline detection.

All database changes for a successful source run occur in a transaction. A dry run opens no write transaction.

## Tests

Tests use temporary SQLite directories and local fixture data only:

- unit tests for normalization, identity, content hashing, and transition decisions;
- repository tests for migrations, source/run persistence, and no duplicate versions;
- service integration tests using `FakeAdapter` for created, unchanged, changed, missing, offline, reopened, and adapter failure;
- MCP envelope tests for source listing, event listing, and dry run;
- existing OpenWorker MCP, Persona, and Skill regression tests.

No browser work is needed for Stage 3. GUI remains covered by the Stage 2 closeout sequence.

## Non-Goals

- Real company adapters or source discovery.
- Network access in test runs.
- Scheduling, queues, Redis, Celery, or cloud deployment.
- Semantic model extraction for routine normalization.
- A new Agent loop, MCP client, permission system, or GUI framework.
