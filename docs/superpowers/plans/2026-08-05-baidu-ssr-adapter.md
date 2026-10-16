# Baidu SSR Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fixture-tested, public SSR HTML adapter for Baidu official recruitment jobs and register it with the existing approval-gated Career MCP crawl flow.

**Architecture:** `BaiduSsrHtmlAdapter` owns one public HTML GET and transforms SSR state into existing `JobSnapshot` values. Pure functions extract and parse `window.__INITIAL_DATA__`; the existing `CrawlerService` owns every database transition. The default adapter registry contains Baidu only after parser and fetch-policy tests pass.

**Tech Stack:** Python 3.12, standard-library `urllib.request`, `json`, dataclasses, pytest, SQLite, FastMCP.

---

## File Structure

| Path | Responsibility |
|---|---|
| `docs/source-notes/baidu.md` | Official-source evidence, request boundary, and live-smoke record |
| `extensions/career_mcp/crawler/baidu.py` | Public HTML fetch policy, SSR extraction, parsing, and `BaiduSsrHtmlAdapter` |
| `extensions/career_mcp/crawler/adapters.py` | Explicit default adapter construction and registry source enumeration |
| `extensions/career_mcp/services/crawler.py` | Default registry injection and configured-source listing |
| `extensions/career_mcp/server.py` | Use the configured crawler service while retaining the existing MCP approval gate |
| `extensions/career_mcp/tests/fixtures/baidu-careers/social_page.html` | One public SSR HTML response |
| `extensions/career_mcp/tests/fixtures/baidu-careers/metadata.json` | Fixture provenance and expected stable job IDs |
| `extensions/career_mcp/tests/test_baidu_ssr.py` | Pure parser, fetch-policy, adapter, and fixture pipeline tests |
| `extensions/career_mcp/tests/test_stage3_tools.py` | Default-registry and `crawl_source` MCP envelope tests |
| `README.md` | Baidu source scope, manual approval, and no-login limitations |
| `docs/11_DEVELOPMENT_LOG.md` | Commands, fixture provenance, and optional live-smoke result |
| `docs/12_TONIGHT_PROGRESS.md` | Stage 4 acceptance state |

### Task 1: Capture And Describe One Public Fixture

**Files:**
- Create: `extensions/career_mcp/tests/fixtures/baidu-careers/social_page.html`
- Create: `extensions/career_mcp/tests/fixtures/baidu-careers/metadata.json`
- Modify: `docs/source-notes/baidu.md`

- [ ] **Step 1: Make one normal public request to the official social page**

Use a single request with no cookies, no login, no form submission, and no retry:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from urllib.request import Request, urlopen

url = "https://talent.baidu.com/jobs/social"
request = Request(url, headers={"User-Agent": "OpenWorker-Career/0.1 (+local fixture capture)"})
with urlopen(request, timeout=15) as response:
    body = response.read(2_000_000)
    content_type = response.headers.get_content_type()
    status = response.status
if status != 200 or content_type != "text/html":
    raise SystemExit(f"fixture capture stopped: status={status}, content_type={content_type}")
Path("extensions/career_mcp/tests/fixtures/baidu-careers").mkdir(parents=True, exist_ok=True)
Path("extensions/career_mcp/tests/fixtures/baidu-careers/social_page.html").write_bytes(body)
PY
```

Expected: exactly one public HTML page captured. Stop without saving a fixture when the response is a login page, CAPTCHA, 401, 403, 429, 5xx, non-HTML, or exceeds 2 MB.

- [ ] **Step 2: Create fixture metadata**

Create `extensions/career_mcp/tests/fixtures/baidu-careers/metadata.json`:

```json
{
  "source_id": "baidu-careers",
  "source_url": "https://talent.baidu.com/jobs/social",
  "retrieved_at": "2026-08-05",
  "content_type": "text/html",
  "authentication": "none",
  "expected_job_ids": []
}
```

Extract the actual `jobId` values from the captured SSR state and replace the empty array with the sorted first two values. Do not add cookies, tokens, user data, or request headers beyond the declared User-Agent.

- [ ] **Step 3: Record fixture provenance**

Append the capture date, URL, response type, body size, and any access restriction to `docs/source-notes/baidu.md`. Do not record response headers that could contain session identifiers.

- [ ] **Step 4: Verify fixture is local and parseable**

Run:

```bash
test -s extensions/career_mcp/tests/fixtures/baidu-careers/social_page.html
.venv/bin/python -m json.tool \
  extensions/career_mcp/tests/fixtures/baidu-careers/metadata.json >/dev/null
```

Expected: both commands exit `0`; no test requests the network.

### Task 2: Implement Test-First SSR State Extraction

**Files:**
- Create: `extensions/career_mcp/crawler/baidu.py`
- Create: `extensions/career_mcp/tests/test_baidu_ssr.py`

- [ ] **Step 1: Write failing extraction tests**

```python
import pytest

from extensions.career_mcp.crawler.baidu import BaiduSsrParseError, extract_initial_data


def test_extract_initial_data_handles_braces_inside_json_strings():
    html = (
        '<script>window.__INITIAL_DATA__ = '
        '{"listDetailData":[{"jobId":"job-1","name":"Role {A}"}]};</script>'
    )

    state = extract_initial_data(html)

    assert state["listDetailData"][0]["jobId"] == "job-1"


def test_extract_initial_data_rejects_missing_assignment():
    with pytest.raises(BaiduSsrParseError, match="INITIAL_DATA"):
        extract_initial_data("<html><body>no state</body></html>")
```

- [ ] **Step 2: Run the extraction tests to confirm failure**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py -q
```

Expected: import error because `baidu.py` does not exist.

- [ ] **Step 3: Implement the quote-aware scanner**

Add the following public API to `extensions/career_mcp/crawler/baidu.py`:

```python
class BaiduSsrParseError(ValueError):
    pass


def extract_initial_data(html: str) -> dict:
    marker = "window.__INITIAL_DATA__"
    start = html.find(marker)
    if start < 0:
        raise BaiduSsrParseError("window.__INITIAL_DATA__ was not found")
    brace = html.find("{", start)
    if brace < 0:
        raise BaiduSsrParseError("window.__INITIAL_DATA__ has no JSON object")
    depth = 0
    quoted = False
    escaped = False
    for index in range(brace, len(html)):
        char = html[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[brace : index + 1])
                except json.JSONDecodeError as exc:
                    raise BaiduSsrParseError("window.__INITIAL_DATA__ is invalid JSON") from exc
    raise BaiduSsrParseError("window.__INITIAL_DATA__ JSON is incomplete")
```

Import `json` and do not execute JavaScript or use a greedy regex.

- [ ] **Step 4: Run the extraction tests**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py -q
```

Expected: `2 passed`.

### Task 3: Parse Fixture Data Into Stable JobSnapshots

**Files:**
- Modify: `extensions/career_mcp/crawler/baidu.py`
- Modify: `extensions/career_mcp/tests/test_baidu_ssr.py`

- [ ] **Step 1: Write failing fixture parser tests**

```python
import json
from pathlib import Path

from extensions.career_mcp.crawler.baidu import parse_baidu_social_html

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baidu-careers"


def test_parse_baidu_fixture_uses_metadata_job_ids():
    metadata = json.loads((FIXTURE_DIR / "metadata.json").read_text(encoding="utf-8"))
    html = (FIXTURE_DIR / "social_page.html").read_text(encoding="utf-8")

    jobs = parse_baidu_social_html(html, metadata["source_url"])

    assert [job.external_job_id for job in jobs][:2] == metadata["expected_job_ids"]
    assert all(job.title and job.description_raw and job.source_url for job in jobs)


def test_parse_baidu_social_html_rejects_duplicate_job_ids():
    html = (
        '<script>window.__INITIAL_DATA__ = {"listDetailData":['
        '{"jobId":"same","name":"A","workPlace":"北京"},'
        '{"jobId":"same","name":"B","workPlace":"上海"}]};</script>'
    )

    with pytest.raises(BaiduSsrParseError, match="duplicate jobId"):
        parse_baidu_social_html(html, "https://talent.baidu.com/jobs/social")
```

- [ ] **Step 2: Run parser tests to confirm failure**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py -q
```

Expected: import error for `parse_baidu_social_html`.

- [ ] **Step 3: Implement deterministic mapping**

Implement:

```python
def recruitment_type(value: str) -> str | None:
    normalized = value.lower()
    if "实习" in value or "intern" in normalized:
        return "internship"
    if "校招" in value or "校园" in value or "campus" in normalized:
        return "campus"
    if "社招" in value or "社会招聘" in value or "social" in normalized:
        return "experienced"
    return None
```

`parse_baidu_social_html(html, source_url)` must:

1. call `extract_initial_data`;
2. require `listData.listDetailData` to be a list;
3. require each accepted entry to have non-empty string `jobId` and `name`;
4. reject a repeated `jobId`;
5. use `workPlace` as `location_raw`;
6. derive recruitment type by checking `recruitType`, then `projectType`, then `postType`;
7. build `description_raw` from non-empty labeled values in this exact order: `name`, `orgName`, `workPlace`, `workContent`, `serviceCondition`, `education`, `workYears`;
8. return `JobSnapshot` with `observed_at=utc_now_iso()` and the supplied official page URL.

Do not invent responsibilities, requirements, detail URLs, or metadata fields unsupported by the fixture.

- [ ] **Step 4: Run parser and existing normalization tests**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py \
  extensions/career_mcp/tests/test_crawler_normalize.py -q
```

Expected: all tests pass offline.

### Task 4: Add Public Fetch Policy And BaiduSsrHtmlAdapter

**Files:**
- Modify: `extensions/career_mcp/crawler/baidu.py`
- Modify: `extensions/career_mcp/tests/test_baidu_ssr.py`

- [ ] **Step 1: Write failing adapter tests with injected fetchers**

```python
from extensions.career_mcp.crawler.baidu import AccessRestricted, BaiduSsrHtmlAdapter


def test_adapter_uses_injected_public_html_fetcher():
    html = (
        '<script>window.__INITIAL_DATA__ = {"listDetailData":['
        '{"jobId":"job-1","name":"测试职位","workPlace":"北京","postType":"社会招聘"}'
        "]};</script>"
    )
    adapter = BaiduSsrHtmlAdapter(fetch_html=lambda _: html)

    jobs = adapter.fetch_jobs()

    assert adapter.source_slug == "baidu-careers"
    assert jobs[0].external_job_id == "job-1"
    assert jobs[0].recruitment_type == "experienced"


def test_adapter_propagates_access_restriction():
    def restricted(_: str) -> str:
        raise AccessRestricted("HTTP 403")

    with pytest.raises(AccessRestricted, match="HTTP 403"):
        BaiduSsrHtmlAdapter(fetch_html=restricted).fetch_jobs()
```

- [ ] **Step 2: Run adapter tests to confirm failure**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py -q
```

Expected: import error for `BaiduSsrHtmlAdapter`.

- [ ] **Step 3: Implement the adapter and default fetcher**

Implement:

```python
class AccessRestricted(RuntimeError):
    pass


class BaiduSsrHtmlAdapter:
    source_slug = "baidu-careers"
    social_url = "https://talent.baidu.com/jobs/social"

    def __init__(self, fetch_html: Callable[[str], str] | None = None) -> None:
        self._fetch_html = fetch_html or fetch_public_html

    def fetch_jobs(self) -> list[JobSnapshot]:
        return parse_baidu_social_html(self._fetch_html(self.social_url), self.social_url)
```

`fetch_public_html(url)` uses `urllib.request.Request` with `User-Agent: OpenWorker-Career/0.1 (+local job research)`, `urlopen(..., timeout=15)`, a 2 MB response limit, and no cookies. Raise `AccessRestricted` for statuses 401/403/429/500/502/503/504, a final URL containing `login`, content types other than `text/html`, and bodies containing `captcha` or `need-login` case-insensitively.

- [ ] **Step 4: Run adapter tests**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py -q
```

Expected: all tests pass without network access.

### Task 5: Register The Source And Exercise The Existing Crawl Pipeline

**Files:**
- Modify: `extensions/career_mcp/crawler/adapters.py`
- Modify: `extensions/career_mcp/services/crawler.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`
- Modify: `extensions/career_mcp/tests/test_baidu_ssr.py`

- [ ] **Step 1: Write failing registry and pipeline tests**

```python
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.services.crawler import CrawlerService


def test_default_registry_contains_only_baidu_adapter():
    assert [adapter.source_slug for adapter in default_adapters()] == ["baidu-careers"]


def test_fixture_adapter_drives_created_job_through_pipeline(tmp_path):
    html = (
        '<script>window.__INITIAL_DATA__ = {"listDetailData":['
        '{"jobId":"job-1","name":"测试职位","workPlace":"北京","postType":"社会招聘"}'
        "]};</script>"
    )
    adapter = BaiduSsrHtmlAdapter(fetch_html=lambda _: html)
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"), adapters=[adapter])

    result = service.crawl_registered_source("baidu-careers")

    assert result.transitions == {"created": 1}
```

- [ ] **Step 2: Run registry tests to confirm failure**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py \
  extensions/career_mcp/tests/test_stage3_tools.py -q
```

Expected: import error for `default_adapters` or source-not-found result from the current default registry.

- [ ] **Step 3: Implement default source registration**

Add:

```python
def default_adapters() -> list[JobAdapter]:
    from .baidu import BaiduSsrHtmlAdapter
    return [BaiduSsrHtmlAdapter()]
```

Add `AdapterRegistry.source_slugs()` returning sorted configured source slugs. Change `CrawlerService` to use `default_adapters()` only when `adapters is None`; an explicitly supplied empty iterable remains empty for isolation tests. Add `CrawlerService.configured_source_slugs()` for `list_sources`.

Change `server.py` to build its `CrawlerService` through one helper:

```python
def _crawler_service() -> CrawlerService:
    return CrawlerService(adapters=default_adapters())
```

Use that helper in `list_sources`, `list_recent_job_events`, and `crawl_source`. `crawl_source` remains unchanged in risk behavior because the trusted workspace MCP config still has `requires_approval=true`.

- [ ] **Step 4: Run fixture pipeline and MCP tests**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py \
  extensions/career_mcp/tests/test_stage3_tools.py \
  extensions/career_mcp/tests/test_crawler_service.py -q
```

Expected: all tests pass with no network calls.

### Task 6: Run Optional Single-Request Smoke And Close Stage 4

**Files:**
- Modify: `docs/source-notes/baidu.md`
- Modify: `README.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Add a live smoke test marker**

Add this test to `extensions/career_mcp/tests/test_baidu_ssr.py`:

```python
@pytest.mark.live
def test_baidu_social_page_is_public_when_explicitly_requested():
    jobs = BaiduSsrHtmlAdapter().fetch_jobs()
    assert jobs
```

Register the `live` marker in the repository pytest configuration. Default test commands must not select it.

- [ ] **Step 2: Run the default offline suite**

Run:

```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests \
  tests/test_skills.py tests/test_builtin_personas.py -q -m "not live"
git diff --check
```

Expected: all selected offline tests pass and `git diff --check` emits no output.

- [ ] **Step 3: Run the optional smoke once**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_baidu_ssr.py -q -m live
```

Expected: one public GET succeeds and returns one or more jobs. If it raises `AccessRestricted`, record the exact restriction class in `docs/source-notes/baidu.md`, remove Baidu from `default_adapters()`, and do not retry with login, cookies, CAPTCHAs, signatures, or alternative private endpoints.

- [ ] **Step 4: Update documentation and create focused commits**

Document the selected SSR route, fixture metadata, smoke result, approval behavior, and remaining source limitations. Mark Stage 4 as passed only when fixture tests and the optional smoke meet the acceptance criteria; otherwise mark the source disabled and retain manual JD as the fallback.

```bash
git add docs/source-notes/baidu.md docs/superpowers/specs/2026-08-05-baidu-ssr-adapter-design.md \
  extensions/career_mcp/tests/fixtures/baidu-careers
git commit -m "test(crawler): add baidu SSR fixtures"
```

```bash
git add extensions/career_mcp/crawler extensions/career_mcp/services/crawler.py \
  extensions/career_mcp/server.py extensions/career_mcp/tests README.md \
  docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "feat(crawler): add baidu SSR adapter"
```

Do not include unrelated user work in either commit. If local Git author identity remains unset, record the commit block without modifying global Git configuration.

## Plan Self-Review

- Spec coverage: Tasks 1-2 cover official fixture provenance and quote-safe SSR extraction; Tasks 3-4 cover deterministic parsing and public request limits; Task 5 covers registry, Stage 3 integration, MCP approval preservation; Task 6 covers offline regression, optional smoke, documentation, and commit isolation.
- Placeholder scan: no implementation step relies on unspecified APIs, guessed XHR routes, login state, or private credentials.
- Type consistency: `BaiduSsrHtmlAdapter`, `AccessRestricted`, `extract_initial_data`, `parse_baidu_social_html`, `default_adapters`, `CrawlerService.crawl_registered_source`, and `JobSnapshot` use the exact names defined in the tasks.
