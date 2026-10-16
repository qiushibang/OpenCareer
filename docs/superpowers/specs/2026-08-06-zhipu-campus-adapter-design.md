# Zhipu Campus Adapter Design

## Goal

Enable the complete official Zhipu campus source while keeping the incomplete
social source disabled.

## Architecture

The existing Moka rendered-DOM transport is parameterized by entry URL and
extracts each page atomically to avoid React rerender drift. A Zhipu-specific
parser maps the tenant's variable metadata as team, employment type, optional
category and optional location.

Campus and social remain separate scopes under one canonical company. Only
`zhipu-campus` is registered because all 19 jobs contain complete JDs. Social
is rejected because 3 of 145 official jobs explicitly have no description.

## Security And Failure Policy

Every crawl uses a fresh context and never persists browser state. Pagination,
UUID, metadata shape and description failures reject the full source.

## Acceptance

Campus returns 19 unique jobs, no overlap with social, and MCP dry run returns
`created=19` below 120 seconds.
