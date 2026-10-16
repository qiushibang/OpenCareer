# ByteDance Stale Tail Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically reconcile at most 20 ByteDance jobs missed by a complete third listing pass through fail-closed official detail-page verification.

**Architecture:** Keep detail-page transport and text classification in the ByteDance Adapter, staging mutations in both Repository implementations, and orchestration in `ResumableCrawlerService`. The runner may commit only after every stale ID is classified and the repository reports an exact atomic reconciliation.

**Tech Stack:** Python 3.12, Playwright Chromium, SQLite, PostgreSQL 16, pytest.

---

### Task 1: Detail Classification and Transport

**Files:**
- Modify: `extensions/career_mcp/crawler/bytedance.py`
- Test: `extensions/career_mcp/tests/test_bytedance_browser.py`

- [x] **Step 1: Write failing parser and adapter tests**

Add tests proving:

```python
assert classify_bytedance_detail_text("该职位已下线") == "offline"
assert classify_bytedance_detail_text("职位描述\n...\n职位要求\n...") == "active"
assert classify_bytedance_detail_text("登录") == "unknown"
```

Inject a `verify_details` callable into `ByteDanceMainlandAdapter` and assert
`verify_stale_jobs()` passes its scope and snapshots unchanged.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  extensions/career_mcp/tests/test_bytedance_browser.py -q
```

Expected: FAIL because the classifier and adapter method do not exist.

- [x] **Step 3: Implement the pure classifier and bounded transport**

Add:

```python
def classify_bytedance_detail_text(text: str) -> str:
    if "该职位已下线" in text:
        return "offline"
    if "职位描述" in text and "职位要求" in text:
        return "active"
    return "unknown"
```

Implement `verify_mainland_job_details(scope, snapshots)` with one fresh Playwright
browser/context/page, numeric ID validation, exact official URLs, heavy-resource blocking,
official-host validation and fail-closed unknown handling.

- [x] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 2: Atomic Staging Reconciliation

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/database/postgres_catalog_repository.py`
- Test: `extensions/career_mcp/tests/test_crawler_repository.py`
- Test: `tests/test_postgres_catalog_repository.py`

- [x] **Step 1: Write failing repository tests**

Create one cycle with six stale jobs. Call:

```python
repository.reconcile_cycle_tail(
    cycle_id,
    active_ids={"active-1", "active-2"},
    offline_ids={"offline-1", "offline-2", "offline-3", "offline-4"},
    pass_number=3,
    observed_at="2026-08-21T00:00:00Z",
)
```

Assert active rows have `last_pass=3`, offline rows are absent, and overlapping or missing IDs
raise without partial writes.

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  extensions/career_mcp/tests/test_crawler_repository.py \
  tests/test_postgres_catalog_repository.py -q
```

Expected: FAIL because `reconcile_cycle_tail` does not exist.

- [x] **Step 3: Implement equivalent SQLite and PostgreSQL methods**

Both methods must:

```text
reject overlapping ID sets
update only rows with last_pass < pass_number
delete only rows with last_pass < pass_number
compare affected row counts exactly
raise on any mismatch so the surrounding transaction rolls back
```

- [x] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 3: Runner Tail Gate

**Files:**
- Modify: `extensions/career_mcp/services/resumable_crawler.py`
- Test: `extensions/career_mcp/tests/test_resumable_crawler.py`

- [x] **Step 1: Write failing runner tests**

Cover:

```text
third pass with 2 active + 4 offline stale jobs commits
unknown detail result degrades and writes no Catalog jobs
21 stale jobs degrade without calling verify_stale_jobs
already converged cycle does not call verify_stale_jobs
```

- [x] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  extensions/career_mcp/tests/test_resumable_crawler.py -q
```

Expected: FAIL because the runner degrades before detail verification.

- [x] **Step 3: Implement the fail-closed tail gate**

At third-pass non-convergence:

```python
stale = [row for row in cycle_jobs if int(row["last_pass"]) < pass_number]
```

Require `1 <= len(stale) <= 20`, call the Adapter verifier, require an exact ID/result mapping,
apply repository reconciliation, reload and recheck convergence. Include active/offline counts in
the successful result. Any exception or unknown result completes the cycle as degraded.

- [x] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 4: Real Gate and Documentation

**Files:**
- Modify: `docs/source-notes/bytedance.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [x] **Step 1: Run the six-ID real detail Gate**

Use the two previously confirmed active IDs and four offline IDs:

```text
active: 7506869832030390535, 7506870288618850567
offline: 7352891772735506725, 7523152599735798023,
         7644767618747189557, 7646317548203968821
```

Assert the automated verifier returns exactly 2 active and 4 offline without modifying the
already committed cycle.

- [x] **Step 2: Run focused and project Gates**

```bash
.venv/bin/python -m pytest \
  extensions/career_mcp/tests/test_bytedance_browser.py \
  extensions/career_mcp/tests/test_resumable_crawler.py \
  extensions/career_mcp/tests/test_crawler_repository.py \
  tests/test_postgres_catalog_repository.py -q
.venv/bin/python -m coworker.server.run --help
.venv/bin/python -m extensions.career_mcp.crawl_cli --list
git diff --check
```

- [x] **Step 3: Record measured evidence**

Document exact automated classifications, tests, remaining production deployment boundary, and
confirm that no online Alpha database was modified.

- [x] **Step 4: Commit**

Stage only the tail-verification implementation, focused tests, specification, plan and source
evidence:

```bash
git commit -m "feat(crawler): verify ByteDance stale job tails"
```
