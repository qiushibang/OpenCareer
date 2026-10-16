# DeepSeek Static Bundle Adapter Design

## Goal

Add DeepSeek as a production job source using the structured recruitment dataset
published in the static JavaScript bundle referenced by DeepSeek's official careers
site. The Adapter must not execute JavaScript, depend on browser rendering, or call
unverified Moka APIs.

## Source Contract

- Official company site: `https://www.deepseek.com/`
- Official careers site: `https://talent.deepseek.com/`
- Entry response: `HTTP 200 text/html`
- Bundle discovery: one same-origin script URL matching `/static/main.<hash>.js`
- Bundle response: `HTTP 200 text/javascript`
- Dataset selector:
  - value is passed to `JSON.parse(...)`;
  - parsed value is an object;
  - `sourceUrl` equals
    `https://app.mokahr.com/social-recruitment/high-flyer/140576#/`;
  - `jobs` is a list;
  - `total` equals `len(jobs)`.

The currently observed dataset has 32 jobs. That count is evidence, not a permanent
constant. The Adapter validates internal consistency instead of requiring 32.

## Architecture

`crawler/deepseek.py` owns four focused operations:

1. Extract one allowed static bundle URL from the official entry HTML.
2. Scan JavaScript string literals passed to `JSON.parse` without executing code.
3. Select and validate the DeepSeek recruitment dataset.
4. Convert jobs into existing `JobSnapshot` values.

`DeepSeekStaticBundleAdapter.fetch_jobs()` performs exactly two serial public GETs:
the careers entry page and its discovered same-origin bundle. It does not fetch
individual Moka detail pages because `descriptionHtml` already contains the complete
JD.

The existing `CrawlerService` remains the only owner of normalization, persistence,
versions, events, missing counts, offline transitions, and crawl-run status.

## JavaScript String Extraction

The extractor scans occurrences of `JSON.parse(` and accepts only a single- or
double-quoted JavaScript string literal. A quote-aware scanner handles escaped
delimiters and terminates at the matching quote.

The decoder supports only explicit JSON/JavaScript escapes needed by a static string:
`\\`, `\/`, `\'`, `\"`, `\b`, `\f`, `\n`, `\r`, `\t`, `\xHH`, and `\uHHHH`.
Unknown, malformed, or incomplete escapes fail parsing. The decoded text is passed to
`json.loads`; no `eval`, JavaScript runtime, regex-only greedy extraction, or model is
used.

If several `JSON.parse` values exist, the Adapter selects exactly one object with the
verified `sourceUrl` and `jobs` list. Zero or multiple matches fail the entire crawl.

## Mapping

- `external_job_id`: trimmed UUID `id`
- `title`: trimmed `title`
- `location_raw`: non-empty `locations` joined with `、`
- `description_raw`: deterministic plain text converted from `descriptionHtml`
- `source_url`:
  `https://app.mokahr.com/social-recruitment/high-flyer/140576#/job/<UUID>`
- `observed_at`: one UTC timestamp shared by every job in one crawl
- `recruitment_type`:
  - exact internship-only label: `internship`
  - exact campus-only label: `campus`
  - exact experienced/full-time-only label: `experienced`
  - mixed or absent labels: `None`

The Adapter does not infer a recruitment type from the Moka `social-recruitment`
tenant alone because the published jobs include internship and full-time options.

## HTML To Text

A standard-library `HTMLParser` subclass converts `descriptionHtml` into plain text.
Block elements and `<br>` create line boundaries; HTML entities are decoded by the
parser. Consecutive blank lines and surrounding whitespace are normalized while text
order is preserved.

The parser does not summarize, rewrite, translate, or remove semantically repeated
source content. Raw fixture data remains available for regression analysis.

## Fetch Policy

- Standard-library `urllib.request`; no new dependency.
- Explicit `OpenWorker-Career/0.1` User-Agent.
- Entry host allowlist: `talent.deepseek.com`.
- Bundle host allowlist: `talent.deepseek.com`.
- Bundle path must match `/static/main.<hash>.js`.
- Serial requests, 15-second timeout each.
- Entry response limit: 256 KB.
- Bundle response limit: 2 MB.
- Stop on redirects outside the allowlist, unexpected content type, login/CAPTCHA
  content, 401/403/429, or 5xx.
- Do not attach cookies, credentials, signatures, or browser state.

## Failure Protection

The entire Adapter call fails without returning partial jobs when any of these occur:

- entry HTML has zero or multiple eligible bundle scripts;
- bundle contains zero or multiple matching datasets;
- `sourceUrl` is not the verified DeepSeek Moka tenant;
- `total` is not a non-negative integer or differs from `len(jobs)`;
- a job is not an object;
- UUID or title is missing;
- UUID format is invalid or duplicated;
- `descriptionHtml` is missing or converts to empty text;
- locations have an unexpected type;
- generated detail URL escapes the verified tenant.

An Adapter failure is recorded by the existing crawler service as a failed run.
Because no successful snapshot set is returned, missing/offline transitions are not
applied.

## Registry

After fixture tests and one explicit live smoke pass, `default_adapters()` contains:

1. `deepseek-careers`
2. `xiaomi-careers`

The registry remains deterministic and sorted by source slug at presentation time.
Disabled Baidu, MiniMax, and Zhipu sources are not registered.

`crawl_source` retains the existing OpenWorker approval requirement. Default tests
never access the network.

## Fixtures And Testing

Fixtures:

```text
extensions/career_mcp/tests/fixtures/deepseek-careers/
├── index.html
├── main.js
└── metadata.json
```

`metadata.json` records exact URLs, retrieval date, content types, sizes, expected
dataset total, and two expected UUIDs. If the bundle is reduced for repository size,
the metadata states that explicitly and the fixture's `total` is reduced consistently.

Offline tests cover:

- same-origin hashed bundle discovery;
- rejection of foreign, missing, or duplicate scripts;
- quote-aware JavaScript string decoding;
- selection of the verified dataset;
- UUID, total, tenant, and required-field validation;
- HTML-to-text paragraph preservation;
- deterministic field mapping and recruitment-type restraint;
- injected fetcher behavior and request limits;
- registry exposure;
- `created`, `unchanged`, and `changed` pipeline transitions;
- MCP `list_sources` and unknown-source behavior.

## Live Acceptance

One explicit live smoke performs only the entry and bundle GETs. It passes when:

- both responses satisfy the fetch policy;
- at least one job is returned;
- all external IDs are unique UUIDs;
- all jobs have title, non-empty JD text, and verified source URL;
- execution completes within the MCP 120-second timeout.

If the live smoke encounters session dependence, a signature, access control, or an
unrecognized bundle contract, DeepSeek remains disabled and the project proceeds to
ByteDance.
