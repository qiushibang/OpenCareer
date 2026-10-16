# Xiaomi Public API Adapter Design

## Goal

Add Xiaomi as the first enabled production job source using the public JSON request
observed on Xiaomi's official recruitment page. The adapter must return complete,
traceable `JobSnapshot` values without login, browser automation, private tokens, or
model-based extraction.

## Source Contract

- Official discovery page: `https://hr.xiaomi.com/website/opportunities.html`
- Public listing endpoint:
  `https://hr.xiaomi.com/website/api/agent/searchJobPage`
- Request parameters: `keyword`, `cityZhNames`, `pageSize=100`, and `pageNum`
- Successful response: `HTTP 200 application/json`, `code=0`
- Pagination: `data.pageNum`, `data.pageSize`, `data.pageTotal`, and `data.total`
- Job fields: `title`, `cityZhNames`, `levelOneDeptName`, `description`,
  `requirement`, `publishTime`, `type`, `url`, `jobId`, and `jobPostId`

`jobId` is the stable `external_job_id`. `jobPostId` and `url` remain source
metadata. The listing response already contains responsibilities and requirements,
so the adapter does not fetch detail pages.

## Architecture

`crawler/xiaomi.py` owns three responsibilities:

1. Parse one validated JSON page into `JobSnapshot` values.
2. Fetch one public JSON page under explicit timeout, size, and response checks.
3. Iterate pagination serially with a bounded page count.

The adapter does not persist data, generate events, call an Agent, or operate the
GUI. Existing `CrawlerService` remains responsible for normalization, versions,
events, missing counts, offline transitions, and crawl runs.

`default_adapters()` enables only Xiaomi. Baidu remains disabled because its latest
live SSR contract failed validation. MiniMax remains disabled because its listing
request depends on a short-lived signature.

## Mapping

- `external_job_id`: string form of `jobId`
- `title`: trimmed `title`
- `location_raw`: non-empty `cityZhNames` joined with `、`
- `recruitment_type`: `type=1` experienced, `type=2` campus,
  `type=3` internship; unknown values remain `None`
- `description_raw`: labeled, non-empty fields in this order:
  department, responsibilities, requirements, publish date, job code
- `source_url`: validated absolute HTTPS `url`
- `observed_at`: one UTC timestamp supplied by the adapter for the page

Missing or duplicate `jobId`, missing title, invalid detail URL, malformed envelope,
or inconsistent pagination fails the entire source run. It must never be converted
into an empty successful result, because that could falsely mark jobs offline.

## Fetch Policy

- Standard-library `urllib.request`; no new dependency.
- Explicit `OpenWorker-Career/0.1` User-Agent.
- Domain allowlist limited to `hr.xiaomi.com`.
- One request at a time, 15-second timeout, 2 MB page limit.
- Verified page size of 100 jobs and maximum 300 pages as a defensive bound.
- Stop on login/captcha content, redirects outside the allowed host, non-JSON,
  401/403/429, or 5xx responses.
- Do not attach cookies, credentials, signatures, or browser state.

Default tests never access the network. A live smoke is explicit and limited to page
1. Production crawling remains behind OpenWorker's existing MCP tool approval.

## Testing

The local fixture records a real page-1 response and provenance metadata. Tests cover:

- successful envelope and deterministic field mapping;
- `jobId` versus `jobPostId`;
- duplicate and missing IDs;
- malformed envelopes and API errors;
- response policy and injected fetcher behavior;
- serial pagination;
- default registry and Stage 3 pipeline integration;
- MCP `list_sources` and approval-gated `crawl_source`.

## Acceptance

Stage 4 passes when offline tests prove the fixture can create Xiaomi jobs through
the existing pipeline, the default registry lists `xiaomi-careers`, all affected
regressions pass, and one explicit page-1 live smoke returns at least one valid job.
