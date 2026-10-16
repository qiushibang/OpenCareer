# DeepSeek Static Bundle Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable DeepSeek as a production job source by safely parsing the structured recruitment dataset in its official static JavaScript bundle.

**Architecture:** The Adapter discovers the hashed same-origin bundle from the official careers HTML, decodes only quoted `JSON.parse` values, selects the verified DeepSeek Moka dataset, and emits existing `JobSnapshot` values. Existing `CrawlerService` remains responsible for persistence and state transitions.

**Tech Stack:** Python 3.12 standard library (`json`, `html.parser`, `urllib.request`), pytest, SQLite, FastMCP.

---

## File Structure

| Path | Responsibility |
|---|---|
| `extensions/career_mcp/crawler/deepseek.py` | Bundle discovery, JS string decoding, dataset validation, HTML-to-text, fetch policy, Adapter |
| `extensions/career_mcp/crawler/adapters.py` | Register DeepSeek after live acceptance |
| `extensions/career_mcp/tests/fixtures/deepseek-careers/index.html` | Minimal real official entry HTML |
| `extensions/career_mcp/tests/fixtures/deepseek-careers/main.js` | Reduced real bundle dataset |
| `extensions/career_mcp/tests/fixtures/deepseek-careers/metadata.json` | Fixture provenance and expected IDs |
| `extensions/career_mcp/tests/test_deepseek_bundle.py` | Pure parser, policy, Adapter, registry, pipeline tests |
| `extensions/career_mcp/tests/test_stage3_tools.py` | MCP source-list regression |
| `README.md` | Supported source and request boundary |
| `docs/source-notes/deepseek.md` | Final live evidence |
| `docs/11_DEVELOPMENT_LOG.md` | TDD and smoke commands |
| `docs/12_TONIGHT_PROGRESS.md` | Multi-source stage status |

### Task 1: Add Reduced Real Fixtures

**Files:**
- Create: `extensions/career_mcp/tests/fixtures/deepseek-careers/index.html`
- Create: `extensions/career_mcp/tests/fixtures/deepseek-careers/main.js`
- Create: `extensions/career_mcp/tests/fixtures/deepseek-careers/metadata.json`

- [ ] Save the exact 530-byte entry HTML that references `/static/main.264ac482b7.js`.
- [ ] Save a reduced `JSON.parse(...)` bundle containing two complete real jobs and set `total` to 2.
- [ ] Record exact live URLs, retrieval date, original bundle size, original total, reduced total, content types, and two UUIDs.
- [ ] Validate `metadata.json` with `python -m json.tool`.

### Task 2: Discover Bundle And Decode JavaScript Strings

**Files:**
- Create: `extensions/career_mcp/tests/test_deepseek_bundle.py`
- Create: `extensions/career_mcp/crawler/deepseek.py`

- [ ] Write failing tests:

```python
def test_extract_bundle_url_requires_one_same_origin_main_script():
    assert extract_bundle_url(INDEX_HTML) == (
        "https://talent.deepseek.com/static/main.264ac482b7.js"
    )


def test_extract_json_parse_values_handles_escaped_quotes():
    script = r"""var data=JSON.parse('{"text":"DeepSeek\\'s Agent"}');"""
    assert extract_json_parse_values(script) == [{"text": "DeepSeek's Agent"}]
```

- [ ] Run the test and confirm import failure because `deepseek.py` does not exist.
- [ ] Implement `DeepSeekBundleError`, `extract_bundle_url`, a quote-aware literal scanner,
  strict supported-escape decoder, and `extract_json_parse_values`.
- [ ] Add rejection tests for missing/foreign/duplicate bundle URLs and malformed/unknown escapes.
- [ ] Run focused tests until green.

### Task 3: Parse Dataset Into JobSnapshots

**Files:**
- Modify: `extensions/career_mcp/crawler/deepseek.py`
- Modify: `extensions/career_mcp/tests/test_deepseek_bundle.py`

- [ ] Write failing fixture tests:

```python
dataset = select_deepseek_dataset(MAIN_JS)
jobs = parse_deepseek_dataset(dataset, observed_at=OBSERVED_AT)
assert [job.external_job_id for job in jobs] == metadata["expected_job_ids"]
assert jobs[0].source_url.endswith(f"/job/{jobs[0].external_job_id}")
assert "团队使命" in jobs[0].description_raw
```

- [ ] Implement exact `sourceUrl` selection and validation of `total`, jobs, UUIDs,
  titles, locations, and `descriptionHtml`.
- [ ] Implement a standard-library `HTMLParser` converter preserving block boundaries.
- [ ] Add tests for duplicate/invalid UUID, wrong tenant, total mismatch, empty JD,
  and mixed recruitment type remaining `None`.
- [ ] Run parser tests until green.

### Task 4: Add Two-Request Fetch Policy And Adapter

**Files:**
- Modify: `extensions/career_mcp/crawler/deepseek.py`
- Modify: `extensions/career_mcp/tests/test_deepseek_bundle.py`

- [ ] Write failing injected-fetcher test:

```python
requested = []
adapter = DeepSeekStaticBundleAdapter(
    fetch_text=lambda url, kind: requested.append((url, kind)) or fixtures[kind],
    clock=lambda: OBSERVED_AT,
)
jobs = adapter.fetch_jobs()
assert requested == [
    ("https://talent.deepseek.com/", "entry"),
    ("https://talent.deepseek.com/static/main.264ac482b7.js", "bundle"),
]
```

- [ ] Implement `DeepSeekAccessRestricted`, `fetch_public_text`, and
  `DeepSeekStaticBundleAdapter`.
- [ ] Enforce host, path, status, redirect, MIME, body-size, login/CAPTCHA, and timeout rules.
- [ ] Add policy tests using injected `urlopen` responses; default tests remain offline.

### Task 5: Register And Drive Existing Pipeline

**Files:**
- Modify: `extensions/career_mcp/crawler/adapters.py`
- Modify: `extensions/career_mcp/tests/test_deepseek_bundle.py`
- Modify: `extensions/career_mcp/tests/test_xiaomi_api.py`
- Modify: `extensions/career_mcp/tests/test_baidu_ssr.py`
- Modify: `extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] Write a failing registry assertion:

```python
assert [a.source_slug for a in default_adapters()] == [
    "deepseek-careers",
    "xiaomi-careers",
]
```

- [ ] Register DeepSeek while keeping Baidu, MiniMax, and Zhipu disabled.
- [ ] Inject the fixture Adapter into `CrawlerService`; assert `created=2`, then
  `unchanged=2`, and a modified fixture yields `changed=1`.
- [ ] Update MCP `list_sources` expectations to expose both configured sources.

### Task 6: Live Smoke And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/source-notes/deepseek.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] Run all DeepSeek, registry, pipeline, and MCP tests.
- [ ] Run the full affected offline suite.
- [ ] Run one explicit live Adapter smoke and assert non-empty unique UUIDs within 120 seconds.
- [ ] Run a real MCP stdio `crawl_source("deepseek-careers", dry_run=True)` call.
- [ ] Register DeepSeek only if both live checks pass; otherwise remove it from the default registry and record the exact stop reason.
- [ ] Run `git diff --check`.

## Plan Self-Review

- Spec coverage: discovery, safe JS decoding, dataset selection, mapping, HTML parsing,
  fetch restrictions, failure protection, registry, pipeline, live and MCP acceptance
  each have an explicit task.
- Placeholder scan: no guessed API, browser runtime, login, cookie, token, signature, or
  unbounded network operation is required.
- Type consistency: `DeepSeekBundleError`, `DeepSeekAccessRestricted`,
  `extract_bundle_url`, `extract_json_parse_values`, `select_deepseek_dataset`,
  `parse_deepseek_dataset`, and `DeepSeekStaticBundleAdapter` are used consistently.
