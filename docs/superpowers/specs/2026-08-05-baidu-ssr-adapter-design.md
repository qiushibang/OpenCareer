# Baidu SSR Adapter Design

## Goal

Add the first real Career job source using only public, unauthenticated pages from Baidu's official recruitment site. The adapter must produce deterministic `JobSnapshot` values for the existing Stage 3 pipeline without modifying OpenWorker's agent loop, MCP client, or permission system.

## Evidence And Scope

The source investigation is recorded in `docs/source-notes/baidu.md`. The official social-recruitment page is `https://talent.baidu.com/jobs/social`. Its SSR HTML contains `window.__INITIAL_DATA__`, including a job list, detailed job content, page fields, and UUID-shaped `jobId` values.

Stage 4 covers one source only: `baidu-careers`. It does not add browser automation, authentication, CAPTCHA handling, XHR reverse engineering, scheduling, or other company adapters.

## Adapter Boundary

Create `BaiduSsrHtmlAdapter` under `extensions/career_mcp/crawler/`. It implements the existing `JobAdapter` protocol:

```python
class JobAdapter(Protocol):
    source_slug: str

    def fetch_jobs(self) -> list[JobSnapshot]: ...
```

The adapter has two independent concerns:

1. A public page fetch function with a fixed timeout, a bounded response body, one request at a time, and a clear project User-Agent.
2. Pure SSR parsing functions that receive HTML and return `JobSnapshot` values.

Tests inject fixture HTML into the parsing functions. Default tests never call the network. The adapter does not open SQLite, invoke MCP, generate files, or call an Agent.

## Public Request Policy

The first online adapter run requests only the official social-recruitment page. It does not submit forms, send cookies, reuse tokens, follow login flows, or inspect private endpoints.

Stop the run and return an `AccessRestricted` or degraded adapter error when any of the following occurs:

- HTTP 401, 403, 429, or 5xx;
- login redirect or login-response body;
- CAPTCHA content;
- a non-HTML response;
- response body exceeds the configured limit;
- missing `window.__INITIAL_DATA__`;
- malformed embedded state or no valid jobs.

The initial source is manually run through the existing approval-gated `crawl_source` tool. It has no scheduler. The recommended operating frequency is no more than once every 6 to 12 hours.

## SSR Extraction

The parser locates the `window.__INITIAL_DATA__` assignment and extracts its balanced JSON object using a quote-aware brace scanner. It does not use a greedy regular expression and does not execute page JavaScript.

For each entry in `listData.listDetailData`, the parser:

- requires non-empty `jobId`, `name`, and a source URL;
- uses `jobId` as `external_job_id`;
- preserves `postId`, displayed job code, `publishDate`, and `updateDate` only in fixture-level assertions until the crawler domain explicitly supports raw metadata;
- uses page-provided detail data when it unambiguously matches the list `jobId`;
- otherwise uses the list entry's available descriptive fields;
- constructs `description_raw` deterministically from title, organization, location, responsibilities, requirements, and recruitment fields;
- keeps the original official page URL as `source_url`.

`location_raw` is sourced from `workPlace`. The initial recruitment-type mapping is deterministic and checks `recruitType`, then `projectType`, then `postType`: texts containing internship markers map to `internship`; campus markers map to `campus`; social/employment markers map to `experienced`; all other values map to `None` rather than being guessed.

## Fixture And Test Design

Create:

```text
extensions/career_mcp/tests/fixtures/baidu-careers/
├── social_page.html
└── metadata.json
```

`metadata.json` records the official URL, retrieval date, content type, and expected job IDs. Fixture content is limited to public job information and contains no credentials or user data.

Tests cover:

1. extracting a valid `window.__INITIAL_DATA__` object;
2. parsing the expected jobs and stable `jobId`;
3. deterministic description and recruitment-type mapping;
4. absent/malformed state producing a clear parser error;
5. duplicate `jobId` rejection;
6. adapter failure converting to a failed crawl run without absence processing;
7. a fixture-only end-to-end crawl creating source, job, version, and event records.

An optional online smoke test, marked `live`, is excluded from default test runs. It performs one public GET only and is never a prerequisite for CI.

## MCP Registration

Register `BaiduSsrHtmlAdapter` only in the default production adapter registry after fixture tests pass. Then:

- `list_sources` reports `baidu-careers` as configured;
- `crawl_source(source_slug="baidu-careers", dry_run=true)` remains non-persistent;
- `crawl_source(..., dry_run=false)` continues to use the existing OpenWorker MCP approval card.

The MCP tool itself is not changed. It already defaults to approval for the trusted workspace MCP server.

## Acceptance

Stage 4 passes when:

1. the source note and local fixtures exist;
2. all parser and fixture tests pass with no network access;
3. a fake fetcher integration test verifies the adapter drives the Stage 3 pipeline;
4. `crawl_source` resolves `baidu-careers` from the production registry;
5. an optional one-request live smoke, if run, encounters no access restriction and its result is recorded separately.

If the live smoke hits a restriction, record it in the source note, leave fixture tests intact, disable the production registration, and do not retry by bypassing controls.

## Non-Goals

- Automated pagination before the public page contract is reconfirmed.
- Public XHR/API usage without independently observing the request.
- Login, cookies, CAPTCHA, signatures, or access-control workarounds.
- Other company adapters.
- Any change to OpenWorker's core engine, providers, permission handling, or MCP client.
