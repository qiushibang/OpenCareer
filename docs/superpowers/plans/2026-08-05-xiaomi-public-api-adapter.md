# Xiaomi Public API Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Xiaomi as the first real official job source using its public recruitment JSON API.

**Architecture:** A focused `XiaomiPublicApiAdapter` fetches and parses public JSON pages into existing `JobSnapshot` values. Existing `CrawlerService` owns persistence and state transitions; existing MCP approval protects execution.

**Tech Stack:** Python 3.12, standard-library `json` and `urllib.request`, pytest, SQLite, FastMCP.

---

## File Structure

| Path | Responsibility |
|---|---|
| `extensions/career_mcp/crawler/xiaomi.py` | JSON parsing, response policy, serial pagination, adapter |
| `extensions/career_mcp/crawler/adapters.py` | Enable Xiaomi in the explicit production registry |
| `extensions/career_mcp/tests/fixtures/xiaomi-careers/listing_page_1.json` | Real public page-1 response |
| `extensions/career_mcp/tests/fixtures/xiaomi-careers/metadata.json` | Fixture provenance and expected IDs |
| `extensions/career_mcp/tests/test_xiaomi_api.py` | Parser, policy, adapter, registry, and pipeline tests |
| `extensions/career_mcp/tests/test_stage3_tools.py` | MCP source-list and crawl integration regression |
| `README.md` | Supported source and approval boundary |
| `docs/source-notes/xiaomi.md` | Verified contract and live-smoke result |
| `docs/11_DEVELOPMENT_LOG.md` | Commands and evidence |
| `docs/12_TONIGHT_PROGRESS.md` | Stage 4 status |

### Task 1: Add A Real Minimal Fixture

**Files:**
- Create: `extensions/career_mcp/tests/fixtures/xiaomi-careers/listing_page_1.json`
- Create: `extensions/career_mcp/tests/fixtures/xiaomi-careers/metadata.json`

- [ ] Capture page 1 once with no cookies or credentials.
- [ ] Keep at least two complete real job records and the original pagination envelope.
- [ ] Record exact URL, date, content type, authentication, expected `jobId` values,
  and whether the fixture was reduced.
- [ ] Validate both JSON files with `python -m json.tool`.

### Task 2: Parse Xiaomi JSON

**Files:**
- Create: `extensions/career_mcp/crawler/xiaomi.py`
- Create: `extensions/career_mcp/tests/test_xiaomi_api.py`

- [ ] Write failing tests that call:

```python
page = parse_xiaomi_listing(payload, observed_at="2026-08-05T00:00:00Z")
assert page.jobs[0].external_job_id == "7621150010131237158"
assert page.jobs[0].source_url.endswith("/7621150010131400998/detail")
```

- [ ] Run the test and verify import failure.
- [ ] Implement `XiaomiApiError`, `XiaomiListingPage`, and
  `parse_xiaomi_listing(payload, observed_at)`.
- [ ] Add failing tests for duplicate IDs, API `code != 0`, missing title, invalid URL,
  and unsupported `data.list`.
- [ ] Implement only the validation needed to pass those tests.

### Task 3: Add Bounded Public Fetch And Pagination

**Files:**
- Modify: `extensions/career_mcp/crawler/xiaomi.py`
- Modify: `extensions/career_mcp/tests/test_xiaomi_api.py`

- [ ] Write failing tests for an injected page fetcher, page sequence `1..pageTotal`,
  one timestamp per crawl, and the 300-page bound.
- [ ] Implement:

```python
class XiaomiPublicApiAdapter:
    source_slug = "xiaomi-careers"

    def __init__(
        self,
        fetch_page: Callable[[int], Mapping[str, object]] | None = None,
    ) -> None: ...

    def fetch_jobs(self) -> list[JobSnapshot]: ...
```

- [ ] Implement `fetch_public_page(page_num)` with host, timeout, size, status,
  content-type, login/captcha, and JSON checks.
- [ ] Verify all adapter tests pass without network access.

### Task 4: Register Xiaomi And Drive The Pipeline

**Files:**
- Modify: `extensions/career_mcp/crawler/adapters.py`
- Modify: `extensions/career_mcp/tests/test_xiaomi_api.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] Write a failing test asserting:

```python
assert [adapter.source_slug for adapter in default_adapters()] == ["xiaomi-careers"]
```

- [ ] Enable `XiaomiPublicApiAdapter` and keep Baidu/MiniMax disabled.
- [ ] Inject the fixture adapter into `CrawlerService` and assert two `created`
  transitions, persisted source URLs, and stable external IDs.
- [ ] Verify `list_sources` exposes Xiaomi as configured and `crawl_source` still
  returns the existing MCP envelope.

### Task 5: Verify And Document

**Files:**
- Modify: `README.md`
- Modify: `docs/source-notes/xiaomi.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_xiaomi_api.py \
  extensions/career_mcp/tests/test_stage3_tools.py \
  extensions/career_mcp/tests/test_crawler_service.py -q
```

- [ ] Run the complete affected offline suite:

```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests \
  tests/test_skills.py tests/test_builtin_personas.py -q
```

- [ ] Run one explicit page-1 live smoke. Do not paginate.
- [ ] Record the smoke result and run `git diff --check`.

## Plan Self-Review

- Spec coverage: fixture, parsing, identity, public fetch limits, pagination,
  registry, pipeline, MCP approval, smoke, and documentation each have a task.
- Placeholder scan: no guessed endpoint, token, signature, or detail API is required.
- Type consistency: `XiaomiListingPage`, `XiaomiPublicApiAdapter`,
  `parse_xiaomi_listing`, and `fetch_public_page` use the same names throughout.
