"""Binary object metadata and repository interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from coworker.server.identity import Principal


@dataclass(frozen=True)
class BlobMetadata:
    id: str
    scope: str
    user_id: str | None
    kind: str
    media_type: str
    original_name: str | None
    size_bytes: int
    sha256: str


class BlobRepository(Protocol):
    def put(
        self,
        principal: Principal,
        *,
        content: bytes,
        kind: str,
        media_type: str,
        original_name: str | None = None,
    ) -> BlobMetadata: ...

    def iter_content(
        self,
        principal: Principal,
        blob_id: str,
        *,
        chunk_size: int = 64 * 1024,
    ) -> Iterable[bytes]: ...

    def delete(self, principal: Principal, blob_id: str) -> bool: ...
