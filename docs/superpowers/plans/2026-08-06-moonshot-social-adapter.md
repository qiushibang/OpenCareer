# Moonshot Social Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add all public Moonshot/Kimi social-recruitment jobs through the official rendered Moka page.

**Architecture:** A pure parser converts fixture-shaped DOM records into `JobSnapshot`. A fresh Playwright context extracts all public pages, while the Adapter runs browser work in a dedicated thread for FastMCP compatibility.

**Tech Stack:** Python 3.12, Playwright, pytest, existing Career crawler pipeline.

---

### Task 1: Pure Card Parser

**Files:**
- Create: `extensions/career_mcp/tests/fixtures/moonshot-social/page_1.json`
- Create: `extensions/career_mcp/tests/test_moonshot_browser.py`
- Create: `extensions/career_mcp/crawler/moonshot.py`

- [ ] Add a fixture with one complete-location card and one missing-location card.
- [ ] Write a failing test that imports `parse_moonshot_card()` and asserts UUID,
  title, official detail URL, category/location text and complete description.
- [ ] Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_moonshot_browser.py -q
```

Expected: collection fails because `crawler.moonshot` does not exist.

- [ ] Implement immutable raw page/card types and:

```python
def parse_moonshot_card(
    raw: Mapping[str, object],
    *,
    observed_at: str,
) -> JobSnapshot:
    ...
```

- [ ] Add failures for malformed UUID, missing full description, recruitment
  type other than `全职`, and metadata longer than three fields.
- [ ] Run the focused parser tests; expected result: all pass.

### Task 2: Browser Pagination

**Files:**
- Modify: `extensions/career_mcp/tests/test_moonshot_browser.py`
- Modify: `extensions/career_mcp/crawler/moonshot.py`

- [ ] Write a failing test with an injected page fetcher returning
  `30 + 30 + 1` jobs and assert all 61 unique IDs are returned.
- [ ] Add failing tests for non-final short pages, empty final pages, changed
  page counts and duplicate UUIDs.
- [ ] Implement:

```python
class MoonshotSocialAdapter:
    source_slug = "moonshot-social"

    def fetch_jobs(self) -> list[JobSnapshot]:
        ...
```

- [ ] Keep browser extraction behind an injected callable so default tests
  remain offline.
- [ ] Run the focused tests; expected result: all pass.

### Task 3: Production DOM Transport

**Files:**
- Modify: `extensions/career_mcp/tests/test_moonshot_browser.py`
- Modify: `extensions/career_mcp/crawler/moonshot.py`

- [ ] Write a failing test that patches the synchronous transport and asserts
  the Adapter executes it outside the running asyncio thread.
- [ ] Implement a fresh Playwright browser/context, official-host checks,
  30-second page timeout and selectors for:
  - `a[href*="/job/"]` containing `div[class*="card-content"]`;
  - `span[class^="title-"]`;
  - `span[class^="published-at-"]`;
  - `div[class^="info-"] div.no-adaptive-tooltip`;
  - `div[class^="job-description-"]`;
  - `ul[class^="sd-Pagination-ul"] button[data-page]`.
- [ ] Open each numbered page as a new tab so the hash route is applied on
  initial load, then close it before the next page.
- [ ] Do not read or persist Cookie/storage state.
- [ ] Run the focused tests; expected result: all pass.

### Task 4: Pipeline And Registry

**Files:**
- Modify: `extensions/career_mcp/tests/test_moonshot_browser.py`
- Modify: `extensions/career_mcp/crawler/adapters.py`

- [ ] Write failing tests for a fixture crawl producing `created=2` and for
  `moonshot-social` appearing in `default_adapters()`.
- [ ] Add `MoonshotSocialAdapter()` to the production registry.
- [ ] Run focused and full Career tests.

### Task 5: Live And MCP Acceptance

**Files:**
- Modify: `docs/source-notes/moonshot-kimi.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Run one live Adapter smoke; require 91 unique UUIDs and less than 110
  seconds.
- [ ] Restart the local server and run MCP `crawl_source` with
  `source_slug=moonshot-social,dry_run=true`; require `created=91` and less than
  120 seconds.
- [ ] Run:

```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q
cd surfaces/gui && npm test -- --run
git diff --check
```

- [ ] Commit only Moonshot source files and their direct registry/docs changes.
