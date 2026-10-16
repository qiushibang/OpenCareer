"""Deterministic parsing for job location labels."""

from __future__ import annotations

import re
from collections.abc import Iterable

_LOCATION_SEPARATOR = re.compile(r"[、，,；;/]+")


def split_job_locations(values: Iterable[str]) -> list[str]:
    """Split composite labels, normalize simple city names, and preserve order."""
    locations: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        for part in _LOCATION_SEPARATOR.split(str(raw_value)):
            value = part.strip()
            if not value:
                continue
            if " " not in value and value.endswith("市") and len(value) > 1:
                value = value[:-1]
            if value not in seen:
                seen.add(value)
                locations.append(value)
    return locations
