"""Career domain values kept independent of MCP and SQLite."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManualJDInput:
    raw_text: str
    source_url: str | None = None
    company_name: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class ManualJDPreview:
    raw_text: str
    cleaned_text: str
    company_name: str | None
    title: str | None
    location_raw: str | None
    locations: list[str]
    recruitment_type: str | None
    responsibilities: list[str]
    requirements: list[str]
    missing_fields: list[str]


@dataclass(frozen=True)
class JobSearchFilters:
    query: str | None = None
    company_slugs: list[str] | None = None
    locations: list[str] | None = None
    recruitment_types: list[str] | None = None
    statuses: list[str] | None = None
    first_seen_after: str | None = None
    favorite_only: bool = False
    application_status: str | None = None
    limit: int = 20
    offset: int = 0
