# Xiaohongshu Social Adapter Design

## Goal

Read every public Xiaohongshu social-recruitment job without implementing or
persisting the site's dynamic request signature.

## Architecture

A pure parser maps the official list response to `JobSnapshot`. The browser
transport opens the official page in a fresh context and uses its own Next
button so the first-party application generates each signed request.

Because live ordering drifts between pages, the transport performs at most
three complete passes. The Adapter unions stable IDs and returns only when the
unique count exactly equals the official total.

## Failure Policy

Totals, page counts and page numbers must remain stable. Duplicate IDs with
different content, incomplete duties or qualifications, unexpected hosts,
timeouts, CAPTCHA/access controls, more than 1,000 jobs or an incomplete
three-pass union fail the complete crawl.

## Security

No `x-s`, `x-t`, Cookie or storage state is read, generated, exported, saved or
reused. The Adapter does not log in or submit an application.

## Acceptance

- Offline parser, drift-union, thread, pipeline and registry tests pass.
- Live returns 875 unique complete JDs.
- MCP dry run returns `created=875` below 120 seconds.
