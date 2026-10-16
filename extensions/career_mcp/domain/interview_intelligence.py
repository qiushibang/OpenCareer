"""Deterministic, privacy-bounded inputs for mock interviews."""

from __future__ import annotations

import re
import unicodedata

from .privacy import contains_sensitive_value

ROLE_TRACKS = ("algorithm", "engineering", "product", "general")
MAX_EVIDENCE_CARDS = 16
MAX_EVIDENCE_CHARS = 300

COMMON_DIMENSIONS = (
    "context",
    "personal_contribution",
    "result",
    "evidence",
    "tradeoff",
    "failure",
    "reflection",
)
TRACK_DIMENSIONS = {
    "algorithm": (
        "data",
        "model_choice",
        "training",
        "inference",
        "experiment",
        "evaluation",
        "error_analysis",
        "optimization",
    ),
    "engineering": (
        "architecture",
        "implementation",
        "interface",
        "data_structure",
        "concurrency",
        "consistency",
        "performance",
        "reliability",
        "observability",
        "security",
    ),
    "product": (
        "user_problem",
        "strategy",
        "feature_design",
        "workflow",
        "evaluation",
        "metrics",
        "experiment",
        "iteration",
        "prioritization",
        "business_tradeoff",
    ),
    "general": (),
}

_GROUP_PATH = re.compile(r"^((?:project|experience)\[\d+\])")
_EVIDENCE_SECTIONS = ("education", "experience", "project", "skill")
_SENSITIVE_KEY_MARKERS = (
    "phone",
    "mobile",
    "telephone",
    "email",
    "e-mail",
    "birth",
    "contact",
    "wechat",
    "手机",
    "电话",
    "邮箱",
    "出生",
    "联系方式",
    "微信",
)


def _normalized(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", value).casefold(),
    ).strip()


def _group_path(path: str) -> str:
    match = _GROUP_PATH.match(path)
    return match.group(1) if match else path.split(".", 1)[0]


def build_evidence_cards(
    sections: dict,
) -> list[dict]:
    """Select bounded confirmed-resume excerpts for interview grounding."""
    ranked: list[tuple[int, str, dict]] = []
    for entry in _fact_entries(sections):
        path = str(entry["path"])
        rank = 0 if entry["section"] in {"project", "experience"} else 1
        ranked.append((rank, path, entry))

    cards: list[dict] = []
    seen: set[str] = set()
    for _, path, entry in sorted(ranked, key=lambda item: item[:2]):
        if path in seen:
            continue
        seen.add(path)
        cards.append(
            {
                "fact_path": path,
                "section": str(entry["section"]),
                "group_path": _group_path(path),
                "excerpt": " ".join(str(entry["excerpt"]).split())[
                    :MAX_EVIDENCE_CHARS
                ],
            }
        )
        if len(cards) == MAX_EVIDENCE_CARDS:
            break
    return cards


def _dimensions(role_tracks: list[str]) -> list[str]:
    if any(track not in ROLE_TRACKS for track in role_tracks):
        raise ValueError("unknown interview role track")
    values = list(COMMON_DIMENSIONS)
    selected_tracks = (
        ("algorithm", "engineering", "product")
        if role_tracks == ["general"]
        else role_tracks
    )
    for track in selected_tracks:
        values.extend(TRACK_DIMENSIONS[track])
    return list(dict.fromkeys(values))


def _max_depth(difficulty: str, *, core: bool) -> int:
    if difficulty == "simple":
        return 1
    if difficulty == "standard":
        return 3 if core else 2
    if difficulty == "deep":
        return 4 if core else 3
    raise ValueError("unknown interview difficulty")


def build_probe_plan(
    *,
    role_tracks: list[str],
    requirements: list[dict],
    evidence_cards: list[dict],
    difficulty: str,
    question_budget: int,
) -> list[dict]:
    """Prioritize resume projects, JD gaps, scenarios, and reflection."""
    if question_budget <= 0:
        raise ValueError("question budget must be positive")
    dimensions = _dimensions(role_tracks)
    groups: dict[str, list[dict]] = {}
    for card in evidence_cards:
        groups.setdefault(str(card["group_path"]), []).append(card)

    candidates: list[dict] = []
    for group_path, cards in groups.items():
        candidates.append(
            {
                "target_id": group_path,
                "target_type": (
                    "resume_project"
                    if group_path.startswith("project[")
                    else "resume_work"
                ),
                "priority": 100,
                "refs": [card["fact_path"] for card in cards],
                "dimensions": list(dimensions),
            }
        )

    for requirement in requirements:
        candidates.append(
            {
                "target_id": requirement["requirement_id"],
                "target_type": "job_requirement",
                "priority": 80,
                "refs": [requirement["requirement_id"]],
                "dimensions": list(dimensions),
            }
        )

    if requirements:
        anchor_ref = requirements[0]["requirement_id"]
        candidates.extend(
            [
                {
                    "target_id": "role-scenario",
                    "target_type": "role_scenario",
                    "priority": 40,
                    "refs": [anchor_ref],
                    "dimensions": list(dimensions),
                },
                {
                    "target_id": "reflection",
                    "target_type": "reflection",
                    "priority": 20,
                    "refs": [anchor_ref],
                    "dimensions": list(COMMON_DIMENSIONS),
                },
            ]
        )

    candidates.sort(
        key=lambda item: (-item["priority"], item["target_id"])
    )
    for index, candidate in enumerate(candidates):
        candidate["max_depth"] = _max_depth(
            difficulty,
            core=index == 0,
        )
    return candidates[:question_budget]


def _fact_entries(sections: dict) -> list[dict]:
    entries: list[dict] = []
    basic = sections.get("basic")
    if isinstance(basic, dict):
        summary = basic.get("summary")
        if isinstance(summary, str) and summary.strip():
            entries.append(
                {
                    "section": "basic",
                    "path": "basic.summary",
                    "excerpt": summary.strip(),
                }
            )
    for section in _EVIDENCE_SECTIONS:
        _append_fact_entries(
            entries,
            section,
            section,
            sections.get(section),
        )
    return entries


def _append_fact_entries(
    entries: list[dict],
    section: str,
    path: str,
    value: object,
) -> None:
    if isinstance(value, str):
        if value.strip() and not contains_sensitive_value(value):
            entries.append(
                {
                    "section": section,
                    "path": path,
                    "excerpt": value.strip(),
                }
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _append_fact_entries(
                entries,
                section,
                f"{path}[{index}]",
                item,
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = unicodedata.normalize("NFKC", key).casefold()
            if any(
                marker in normalized
                for marker in _SENSITIVE_KEY_MARKERS
            ):
                continue
            _append_fact_entries(
                entries,
                section,
                f"{path}.{key}",
                item,
            )
