# Alibaba Token Foundry Adapter Design

## Goal

Expose all public Token Foundry social-recruitment jobs while preserving
Alibaba's first-party anonymous CSRF flow and existing Career crawler boundaries.

## Architecture

`AlibabaScope` describes one official Alibaba business site. The production
transport opens the official position page in a fresh Playwright context,
captures the page-generated `/position/search` request, and paginates through
that same context with `pageSize=500`. It never exports or persists cookies or
CSRF values.

`parse_alibaba_page()` validates the public JSON and maps numeric IDs, complete
descriptions, requirements, categories and locations to `JobSnapshot`.
`AlibabaCareersAdapter` validates stable totals, sequential pages, uniqueness
and exact observed counts. The shared implementation does not imply that other
Alibaba business scopes are enabled; each scope requires separate live,
performance and overlap acceptance.

## Failure Policy

Unexpected hosts, missing first-party requests, HTTP errors, totals above the
scope limit, empty premature pages, duplicate IDs, incomplete JDs and the
110-second budget fail the complete crawl. Partial data is never returned.

## Acceptance

- Offline parser, pagination, thread, pipeline and registry tests pass.
- Live Token Foundry returns 61 unique complete JDs.
- MCP dry run returns `created=61` below 120 seconds.
