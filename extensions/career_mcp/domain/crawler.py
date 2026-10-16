"""Crawler domain values independent of adapters and SQLite."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDescriptor:
    source_slug: str
    source_name: str
    company_slug: str
    company_name: str
    scope_key: str
    adapter_type: str
    base_url: str | None


@dataclass(frozen=True)
class JobSnapshot:
    external_job_id: str
    title: str
    description_raw: str
    source_url: str
    observed_at: str
    location_raw: str | None = None
    recruitment_type: str | None = None


@dataclass(frozen=True)
class NormalizedJob:
    identity: str
    external_job_id: str
    title: str
    description_raw: str
    source_url: str
    observed_at: str
    locations: list[str]
    recruitment_type: str | None
    content_hash: str


@dataclass(frozen=True)
class CrawlResult:
    source_slug: str
    run_id: str
    status: str
    transitions: dict[str, int]
    error_summary: str | None = None


@dataclass(frozen=True)
class CrawlBatchResult:
    results: list[CrawlResult]
    transitions: dict[str, int]
    completed: int
    failed: int
    total_sources: int
    has_more: bool
    next_cursor: str | None
