"""Deterministic parsing for manually pasted job descriptions."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from .models import ManualJDPreview

_LABELS = {
    "company_name": ("公司", "公司名称"),
    "title": ("职位", "岗位", "招聘岗位"),
    "location_raw": ("工作地点", "地点", "城市"),
}
_SECTION_KIND = {
    "岗位职责": "responsibilities",
    "职责": "responsibilities",
    "你将负责": "responsibilities",
    "任职要求": "requirements",
    "岗位要求": "requirements",
    "我们希望你": "requirements",
}


def clean_manual_jd(raw_text: str) -> str:
    """Normalize whitespace without deleting substantive JD content."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
    result: list[str] = []
    for line in lines:
        if line or (result and result[-1]):
            result.append(line)
    while result and not result[-1]:
        result.pop()
    return "\n".join(result)


def manual_content_hash(cleaned_text: str) -> str:
    return hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()


def company_slug(company_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
    if normalized:
        return normalized
    return "manual-company-" + hashlib.sha256(
        company_name.encode("utf-8")
    ).hexdigest()[:12]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _label_value(line: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.+)$", line)
        if match:
            return match.group(1).strip() or None
    return None


def _items(lines: list[str]) -> list[str]:
    return [
        re.sub(r"^(?:[-*•]|\d+[.)、])\s*", "", line).strip()
        for line in lines
        if re.sub(r"^(?:[-*•]|\d+[.)、])\s*", "", line).strip()
    ]


def parse_manual_jd(cleaned_text: str) -> ManualJDPreview:
    lines = [line for line in cleaned_text.splitlines() if line]
    values: dict[str, str | None] = {key: None for key in _LABELS}
    sections: dict[str, list[str]] = {"responsibilities": [], "requirements": []}
    current_section: str | None = None

    for line in lines:
        section = next(
            (kind for heading, kind in _SECTION_KIND.items() if line.rstrip("：:") == heading),
            None,
        )
        if section:
            current_section = section
            continue
        matched = False
        for field, labels in _LABELS.items():
            value = _label_value(line, labels)
            if value is not None:
                values[field] = value
                current_section = None
                matched = True
                break
        if not matched and current_section:
            sections[current_section].append(line)

    if values["title"] is None and lines and not any(
        _label_value(lines[0], labels) is not None for labels in _LABELS.values()
    ) and lines[0].rstrip("：:") not in _SECTION_KIND:
        values["title"] = lines[0]

    location = values["location_raw"]
    locations = [location] if location else []
    type_map = (("实习", "internship"), ("校招", "campus"), ("社招", "experienced"))
    recruitment_type = next(
        (value for marker, value in type_map if marker in cleaned_text), None
    )
    responsibilities = _items(sections["responsibilities"])
    requirements = _items(sections["requirements"])
    missing = [
        field
        for field, value in (
            ("title", values["title"]),
            ("company_name", values["company_name"]),
            ("location", location),
            ("recruitment_type", recruitment_type),
            ("responsibilities", responsibilities),
            ("requirements", requirements),
        )
        if not value
    ]
    return ManualJDPreview(
        raw_text=cleaned_text,
        cleaned_text=cleaned_text,
        company_name=values["company_name"],
        title=values["title"],
        location_raw=location,
        locations=locations,
        recruitment_type=recruitment_type,
        responsibilities=responsibilities,
        requirements=requirements,
        missing_fields=missing,
    )
