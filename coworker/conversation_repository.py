"""Persistence contract shared by local and cloud conversations."""

from __future__ import annotations

from typing import Protocol

from .sessions import SessionRecord


class ConversationRepository(Protocol):
    def save(self, record: SessionRecord) -> None: ...

    def load(self, session_id: str) -> SessionRecord | None: ...

    def list(
        self,
        *,
        workspace: str | None = None,
    ) -> list[SessionRecord]: ...

    def set_flags(
        self,
        session_id: str,
        *,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> bool: ...

    def touch_workspace(self, path: str) -> None: ...

    def recent_workspaces(self, limit: int = 20) -> list[str]: ...

    def rename(self, session_id: str, title: str) -> bool: ...

    def set_auto_title(self, session_id: str, title: str) -> bool: ...

    def title_state(self, session_id: str) -> dict | None: ...

    def set_origin(
        self,
        session_id: str,
        origin: str,
        origin_label: str = "",
    ) -> bool: ...

    def set_extra_roots(
        self,
        session_id: str,
        extra_roots: list[dict],
    ) -> None: ...

    def delete(self, session_id: str) -> bool: ...
