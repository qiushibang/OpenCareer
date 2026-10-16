"""Durable per-conversation Skill content state."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .skills.base import Skill


class SessionSkillState(Protocol):
    def loaded_hash(self, name: str) -> str | None: ...

    def loaded_hashes(self) -> dict[str, str]: ...

    def mark_loaded(
        self,
        name: str,
        *,
        version: str | None,
        content_sha256: str,
    ) -> None: ...


def skill_content_sha256(skill: Skill) -> str:
    canonical = json.dumps(
        {
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions,
            "allowed_tools": skill.allowed_tools,
            "preload_skills": skill.preload_skills,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
