# Agent Context and Exact Origin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the complete cloud Agent context in PostgreSQL, use Redis only for reconstructible runtime coordination, and serve HTTP/WebSocket through one database-backed exact Origin policy.

**Architecture:** Existing stores gain PostgreSQL adapters behind their current interfaces. Canonical messages remain append-only; compactions, memories, loaded skills, and context manifests are separate records. Redis implements a `RuntimeCoordinator`, never a repository.

**Tech Stack:** Python, psycopg 3, Redis 7, FastAPI/Starlette, pytest.

---

### Task 1: PostgreSQL Conversation repository

**Files:**
- Create: `coworker/conversation_repository.py`
- Create: `coworker/storage/postgres/conversations.py`
- Modify: `coworker/conversations.py`
- Test: `tests/test_postgres_conversations.py`

- [ ] Write RED tests for append-only sequence, metadata updates, exact reload, duplicate append idempotency, archive, and tenant isolation.
- [ ] Define a narrow repository interface matching `ConversationStore` caller needs.
- [ ] Implement the PostgreSQL adapter with `(conversation_id, sequence)` uniqueness and JSONB messages.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(context): persist cloud conversations in postgres`.

### Task 2: Compaction persistence

**Files:**
- Modify: `coworker/compaction.py`
- Modify: `coworker/server/manager.py`
- Modify: `coworker/storage/postgres/conversations.py`
- Test: `tests/test_postgres_compaction.py`

- [ ] Write RED tests proving canonical messages survive repeated compaction and latest valid boundary restores the outbound view.
- [ ] Persist each compaction version, source hash, boundary sequence, summary, and omitted count.
- [ ] Preserve existing local `SessionRecord.compaction` behavior for desktop.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(context): persist versioned compactions`.

### Task 3: PostgreSQL Memory, Todo, Inbox, and Automation adapters

**Files:**
- Create: `coworker/storage/postgres/memory_store.py`
- Create: `coworker/storage/postgres/inbox_repository.py`
- Create: `coworker/storage/postgres/automation_store.py`
- Modify: `coworker/tools/todo.py`
- Modify: `coworker/server/manager.py`
- Test: `tests/test_postgres_agent_state.py`

- [ ] Write RED tests for Memory scopes, Todo replacement, Inbox first-responder-wins, durable approval resume, Automation scheduling, and tenant isolation.
- [ ] Implement adapters without changing local SQLite/JSON behavior.
- [ ] Ensure Inbox resolution uses one conditional `UPDATE ... WHERE state='pending'`.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(context): persist durable agent state`.

### Task 4: Session Skill state

**Files:**
- Create: `coworker/session_skills.py`
- Modify: `coworker/agent.py`
- Modify: `coworker/server/app.py`
- Test: `tests/test_session_skills.py`

- [ ] Write RED tests that first use loads a Skill, unchanged hash skips reload, changed hash reloads, and users cannot see each other's loaded Skills.
- [ ] Store name, version, content SHA-256, and loaded timestamp.
- [ ] Replace unconditional WebSocket Skill prompt rewriting with repository-backed load decisions.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `perf(context): reuse unchanged session skills`.

### Task 5: Context Manifest

**Files:**
- Create: `coworker/context_manifest.py`
- Create: `coworker/storage/postgres/context_manifests.py`
- Modify: `coworker/agent.py`
- Modify: `coworker/engine.py`
- Test: `tests/test_context_manifest.py`

- [ ] Write RED tests for message range, compaction ID, memory IDs, Skill hashes, Career refs, model, token counts, content hash, and secret exclusion.
- [ ] Build manifests from identifiers and hashes rather than duplicate Prompt text.
- [ ] Persist estimated usage before provider call and update actual usage after completion.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(context): record model context manifests`.

### Task 6: Redis RuntimeCoordinator

**Files:**
- Create: `coworker/runtime/base.py`
- Create: `coworker/runtime/redis_coordinator.py`
- Create: `coworker/runtime/local_coordinator.py`
- Test: `tests/test_runtime_coordinator.py`

- [ ] Write RED tests for lease acquisition/renewal, crawler lock, presence, rate limits, pub/sub notification, and Redis flush recovery.
- [ ] Implement local and Redis adapters; keep durable state out of Redis.
- [ ] Wire coordinator selection through the storage factory.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(runtime): add redis coordination`.

### Task 7: Exact Origin policy

**Files:**
- Create: `coworker/server/origins.py`
- Modify: `coworker/server/app.py`
- Modify: `tests/test_alpha_mode.py`
- Create: `tests/test_origin_policy.py`

- [ ] Write RED table tests for scheme, host, port, IDNA normalization, path/query/fragment rejection, wildcard rejection, malicious suffix rejection, and database outage fail-closed behavior.
- [ ] Implement local and PostgreSQL Origin adapters with emergency exact environment entries.
- [ ] Make HTTP CORS and WebSocket validation call the same `OriginPolicy.allows`.
- [ ] Run focused tests; expect PASS without relaxing existing token checks.
- [ ] Commit `feat(security): centralize exact origin policy`.

### Task 8: Context migration and regression

**Files:**
- Modify: `deploy/migrate_to_postgres.py`
- Test: `tests/test_postgres_context_migration.py`

- [ ] Add fixture migration tests for SQLite session index, JSONL messages, compaction, memories, Inbox JSON, routing JSON, mentions, and automations.
- [ ] Verify reruns preserve message sequences and file hashes.
- [ ] Run all context, identity, Alpha, and server tests.
- [ ] Run `git diff --check`.
- [ ] Record evidence and commit `docs(context): record postgres context gate`.
