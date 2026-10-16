# Daily Job Radar Digest Design

## Goal

Turn persisted crawler data into one complete, source-backed daily summary. Every
day at 09:00 Asia/Shanghai, Career Agent reports the previous 24 hours of job
changes in its Automation session and writes an auditable Markdown artifact.

## Current Problem

The crawler and Automation can complete all 34 sources, but the user still has
to inspect source runs and job events manually. `list_recent_job_events` returns
at most 100 rows, so asking an Agent to summarize it can silently omit events.
The current `career-job-search` Skill also still describes the obsolete mock
workflow.

The first complete Automation cycle produced 416 events. A daily summary must
aggregate all matching events before applying any display limit.

## Scope

This feature includes:

- one read-only `get_job_radar_digest` Career MCP tool;
- deterministic database aggregation over a rolling time window;
- latest health for all configured sources;
- a real-data `career-job-search` Skill;
- one daily OpenWorker Automation;
- Markdown and Automation-session output.

This feature does not:

- run a crawler;
- modify jobs, events, sources, or crawl runs;
- add a GUI page;
- change OpenWorker permissions or standing approvals;
- start resume, profile-matching, or application-packet work.

## MCP Contract

Tool:

```text
get_job_radar_digest(hours: int = 24, sample_limit: int = 20)
```

Validation:

- `hours` must be between 1 and 168.
- `sample_limit` must be between 1 and 100.
- Invalid values return the existing `INVALID_INPUT` envelope.
- SQLite failures return the existing retryable `PERSISTENCE_ERROR` envelope.

Successful data:

```json
{
  "window": {
    "started_at": "2026-08-05T01:00:00Z",
    "ended_at": "2026-08-06T01:00:00Z",
    "hours": 24
  },
  "jobs": {
    "total": 10067,
    "active": 10013,
    "inactive": 54
  },
  "events": {
    "total": 416,
    "by_type": {
      "created": 53,
      "changed": 340,
      "missing": 23
    },
    "by_company": [
      {
        "company_slug": "meituan",
        "company_name": "美团",
        "total": 324,
        "created": 13,
        "changed": 305,
        "missing": 6
      }
    ],
    "samples": [
      {
        "job_id": "job-id",
        "company_slug": "meituan",
        "company_name": "美团",
        "title": "岗位标题",
        "event_type": "changed",
        "summary": "岗位内容发生变化",
        "occurred_at": "2026-08-06T05:42:51Z",
        "source_url": "https://hr.meituan.com/..."
      }
    ]
  },
  "sources": {
    "configured": 34,
    "healthy": 34,
    "failed": 0,
    "pending": 0,
    "items": [
      {
        "source_slug": "example-failed-source",
        "source_name": "示例失败来源",
        "last_run_status": "failed",
        "last_run_at": "2026-08-06T05:42:50Z",
        "last_observed_count": 0,
        "last_error": "safe error summary"
      }
    ]
  }
}
```

`events.total`, `events.by_type`, and `events.by_company` are calculated from
all events in the window. `sample_limit` applies only to `events.samples`.
Missing event types are omitted from `by_type`; consumers treat them as zero.
Configured sources without a crawl run increment `sources.pending`; their
latest-run fields are null, and they count as neither healthy nor failed.
`sources.items` contains only failed or pending sources. Healthy sources are
represented by the complete aggregate count; use `list_sources` when every
healthy source row is required. This keeps the daily model context bounded.

## Architecture

The repository owns SQL aggregation and returns plain dictionaries. It uses:

- one aggregate query for total jobs by status;
- one aggregate query for event counts by type;
- one aggregate query for event counts by company and type;
- one bounded query for recent event samples;
- one window-function query for the latest run of every configured source,
  followed by exception-only response projection.

`CrawlerService.get_job_radar_digest()` validates inputs, calculates the UTC
window from an injectable clock, and combines repository results. The MCP server
only translates service validation and SQLite errors into existing envelopes.

No model participates in counting, filtering, source-health classification, or
URL selection.

## Skill Workflow

`career-job-search` must instruct Career Agent to:

1. use `get_job_radar_digest` for daily or time-window summaries;
2. use `list_sources` for source inventory questions;
3. use `search_jobs` for filtered discovery and pagination;
4. use `get_job` before detailed JD analysis;
5. use `list_recent_job_events` only for a small recent-event listing;
6. include returned job IDs and official source URLs;
7. report missing fields and tool errors directly;
8. never label real data as mock or fabricate counts.

Daily Markdown sections:

```text
# Job Radar Daily — YYYY-MM-DD
## Window
## Source Health
## Event Summary
## Company Breakdown
## Recent Job Samples
## Warnings
```

The artifact path is:

```text
artifacts/job-radar-daily/YYYY-MM-DD.md
```

## Automation

Create one enabled Automation:

```text
title: Career Job Radar Daily Digest
cron: 0 9 * * *
timezone: Asia/Shanghai
workspace: repository root
agent: career
```

Each run calls `get_job_radar_digest(hours=24, sample_limit=20)`, writes the
dated Markdown artifact, and repeats the same counts in the session result.
It must not call `crawl_source`, `crawl_all_sources`, or Shell.

The digest tool is read-only. File output continues through OpenWorker's normal
workspace file tool; no standing approval or permission bypass is added.

## Error Handling

- A source whose latest run failed appears in `sources.items`, increments
  `sources.failed`, and is listed under Markdown warnings.
- No events in the window is a successful empty digest, not an error.
- A failed source does not invalidate event counts from successful sources.
- Tool errors prevent artifact creation; the Automation session reports the
  error rather than writing a partial or fabricated digest.

## Testing

Offline tests must prove:

- events outside the rolling window are excluded;
- aggregate totals include more events than `sample_limit`;
- company/type counts compose correctly;
- latest source run wins, including a failed latest run;
- invalid `hours` and `sample_limit` return `INVALID_INPUT`;
- the Skill names all required tools and forbids fabricated or mock labeling;
- a real Automation run mounts Career MCP, calls the read-only digest tool,
  writes the dated artifact, and leaves crawler state unchanged.

Final regression includes Career/backend tests, GUI tests, production GUI build,
and `git diff --check`.
