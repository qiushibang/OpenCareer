---
name: career-job-search
description: Search Career MCP jobs and produce traceable job briefs.
---
Use Career MCP as the only source of job facts. Do not fabricate counts, job
fields, company details, or requirements.

## Tool Selection

- For combined filters, business lines, function subcategories or explicit daily subscription intent, load `career-catalog-query` and use the new catalog schema/query tools. Keep `search_jobs` for legacy simple requests.

- Use `get_job_radar_digest` for a daily summary or a complete rolling-window
  view of job events and source health.
- Use `list_sources` for source inventory questions.
- Use `search_jobs` for filtered job discovery. Unless the user explicitly asks
  for inactive jobs, keep the default `active` status.
- Follow `search_jobs` pagination with its limit and offset until the requested
  result set is covered; do not imply the first page is the full result.
- Use `get_job` before detailed JD analysis.
- Use `list_recent_job_events` only for a small chronological event listing,
  not for complete aggregate counts.

Every listed job must include its returned job ID and official source URL.
Report missing fields and tool errors directly. Never infer an internal business
unit from a title or replace an official source URL with a search result.

## Fit Triage (when a confirmed resume exists)

When the user has at least one confirmed resume and asks which results fit,
triage the listed jobs into three coarse tags — 对口 / 疑似对口 / 缺口明显 —
judged conversationally from title, requirements keywords, and location against
the confirmed resume. One short evidence line per tagged job; no numeric
scores. This is a coarse first pass only: recommend `career-job-fit` for a
structured verdict on any single job, and do not auto-batch deep evaluations
across the list (token cost). Untagged plain listings stay the default when the
user just wants to browse.

## Daily Markdown

For a saved daily digest, call
`get_job_radar_digest(hours=24, sample_limit=20)` and write:

```text
# Job Radar Daily - YYYY-MM-DD
## Window
## Source Health
## Event Summary
## Company Breakdown
## Recent Job Samples
## Warnings
```

Use the exact returned window and aggregate counts. Event samples must include
job ID, company, title, event type, occurrence time, and source URL. List failed
or pending sources under Warnings. If there are no events, state that the window
is empty without inventing activity.

Write daily files under `artifacts/job-radar-daily/` through the normal
workspace file flow.
