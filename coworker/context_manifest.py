"""Auditable model-context metadata without duplicating prompt content."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable

_USAGE_KEYS = ("input", "output", "cache_read", "cache_write")


@dataclass(frozen=True)
class ContextManifest:
    conversation_id: str
    turn_id: str
    canonical_start: int
    canonical_end: int
    compaction_id: str | None
    memory_ids: tuple[str, ...]
    skill_hashes: dict[str, str]
    career_refs: tuple[str, ...]
    model: str
    estimated_tokens: int
    actual_usage: dict[str, int] | None
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "canonical_range": {
                "start": self.canonical_start,
                "end": self.canonical_end,
            },
            "compaction_id": self.compaction_id,
            "memory_ids": list(self.memory_ids),
            "skill_hashes": dict(self.skill_hashes),
            "career_refs": list(self.career_refs),
            "model": self.model,
            "estimated_tokens": self.estimated_tokens,
            "actual_usage": (
                dict(self.actual_usage)
                if self.actual_usage is not None
                else None
            ),
            "content_hash": self.content_hash,
        }

    def with_actual_usage(
        self,
        usage: dict[str, int],
    ) -> "ContextManifest":
        normalized = {
            key: int(usage.get(key, 0))
            for key in _USAGE_KEYS
        }
        return replace(self, actual_usage=normalized)


def build_context_manifest(
    *,
    conversation_id: str,
    turn_id: str,
    messages: list[dict[str, Any]],
    canonical_start: int,
    canonical_end: int,
    model: str,
    estimated_tokens: int,
    compaction_id: str | None = None,
    memory_ids: tuple[str, ...] = (),
    skill_hashes: dict[str, str] | None = None,
    career_refs: tuple[str, ...] = (),
) -> ContextManifest:
    serialized = json.dumps(
        messages,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return ContextManifest(
        conversation_id=conversation_id,
        turn_id=turn_id,
        canonical_start=canonical_start,
        canonical_end=canonical_end,
        compaction_id=compaction_id,
        memory_ids=tuple(memory_ids),
        skill_hashes=dict(skill_hashes or {}),
        career_refs=tuple(career_refs),
        model=model,
        estimated_tokens=int(estimated_tokens),
        actual_usage=None,
        content_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    )


class ModelContextRecorder:
    def __init__(
        self,
        repository,
        *,
        conversation_id: str,
        memory_ids: Callable[[], tuple[str, ...]] = tuple,
        skill_hashes: Callable[[], dict[str, str]] = dict,
        career_refs: Callable[[], tuple[str, ...]] = tuple,
    ) -> None:
        self._repository = repository
        self._conversation_id = conversation_id
        self._memory_ids = memory_ids
        self._skill_hashes = skill_hashes
        self._career_refs = career_refs

    def begin(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        canonical_start: int,
        canonical_end: int,
        compaction_id: str | None,
        estimated_tokens: int,
    ) -> str:
        manifest = build_context_manifest(
            conversation_id=self._conversation_id,
            turn_id=str(uuid.uuid4()),
            messages=messages,
            canonical_start=canonical_start,
            canonical_end=canonical_end,
            compaction_id=compaction_id,
            memory_ids=self._memory_ids(),
            skill_hashes=self._skill_hashes(),
            career_refs=self._career_refs(),
            model=model,
            estimated_tokens=estimated_tokens,
        )
        return self._repository.create(manifest)

    def complete(
        self,
        manifest_id: str,
        usage: dict[str, int],
    ) -> None:
        if not self._repository.update_actual_usage(manifest_id, usage):
            raise RuntimeError("context manifest usage update was not persisted")
