# Moonshot Social Adapter Design

## Goal

Register the official Moonshot/Kimi experienced-hiring source and emit all
public jobs as `JobSnapshot` values without decrypting Moka API responses or
persisting browser state.

## Selected Approach

Use a fresh Playwright context to load each public Moka result page and extract
the rendered job cards. Direct API parsing is rejected because Moka returns an
encrypted application payload. Static/manual-only approaches are rejected
because the official page already provides a complete, fast, public listing.

## Components

`crawler/moonshot.py` owns three units:

1. `parse_moonshot_card()` validates a fixture-shaped mapping and creates a
   `JobSnapshot`.
2. `fetch_moonshot_pages()` loads the official site in a fresh context, reads
   pagination metadata and returns plain mappings. It never returns browser
   objects or state.
3. `MoonshotSocialAdapter.fetch_jobs()` runs browser work in a dedicated thread,
   validates page counts and unique UUIDs, then invokes the pure parser.

The existing `CrawlerService` continues to own normalization, persistence,
state transitions and dry-run behavior.

## Data Contract

Each extracted mapping contains `href`, `title`, `published_at`, `metadata` and
`description`. `href` must contain one UUID. `metadata` contains:

- index 0: recruitment type, currently `全职`;
- index 1: optional category;
- index 2: optional location.

Missing category or location remains unknown. The Adapter does not infer
locations from the title or description.

The canonical detail URL is:

```text
https://app.mokahr.com/apply/moonshot/148506#/job/<UUID>
```

## Completeness And Failure Policy

The first page determines the public page count from numeric `data-page`
buttons. Page count must be between 1 and 20. Every non-final page must contain
30 cards; the final page must contain 1-30 cards. The result must not exceed 600
jobs.

Duplicate UUIDs, changed duplicate content, missing UUID/title/description,
unexpected recruitment type, missing pagination, login/CAPTCHA, timeout or
unexpected host fail the entire crawl. Partial results are never returned.

## Security

The production transport creates a new browser and context for every crawl,
uses no supplied storage state, and closes all pages and contexts. It does not
inspect, export or persist cookies. It does not call Moka's encrypted API
directly and does not implement response decryption.

## Tests

Offline tests cover card parsing, optional metadata, invalid UUIDs, pagination,
duplicates, thread isolation, the crawler pipeline and default registry.
Live acceptance requires 91 unique jobs, four pages and completion below the
MCP 120-second timeout.
