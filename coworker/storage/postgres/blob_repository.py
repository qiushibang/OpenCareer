"""PostgreSQL-backed private Blob storage."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from uuid import UUID, uuid4

from coworker.server.identity import Principal
from coworker.storage.blobs import BlobMetadata

_MAX_RESUME_BYTES = 10 * 1024 * 1024


class PostgresBlobRepository:
    def __init__(self, database) -> None:
        self.database = database

    def put(
        self,
        principal: Principal,
        *,
        content: bytes,
        kind: str,
        media_type: str,
        original_name: str | None = None,
    ) -> BlobMetadata:
        if kind == "resume_original" and len(content) > _MAX_RESUME_BYTES:
            raise ValueError("resume Blob exceeds 10 MB")
        blob_id = str(uuid4())
        digest = hashlib.sha256(content).hexdigest()
        metadata = BlobMetadata(
            id=blob_id,
            scope="user",
            user_id=principal.user_id,
            kind=kind,
            media_type=media_type,
            original_name=original_name,
            size_bytes=len(content),
            sha256=digest,
        )
        with self.database.transaction(principal) as connection:
            connection.execute(
                """
                INSERT INTO blob.objects(
                    id, scope, user_id, kind, media_type, original_name,
                    size_bytes, sha256, content
                ) VALUES (%s, 'user', %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    blob_id,
                    principal.user_id,
                    kind,
                    media_type,
                    original_name,
                    len(content),
                    digest,
                    content,
                ),
            )
        return metadata

    def iter_content(
        self,
        principal: Principal,
        blob_id: str,
        *,
        chunk_size: int = 64 * 1024,
    ) -> Iterator[bytes]:
        normalized = str(UUID(blob_id))
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        with self.database.transaction(principal) as connection:
            row = connection.execute(
                """
                SELECT content
                FROM blob.objects
                WHERE id = %s AND deleted_at IS NULL
                """,
                (normalized,),
            ).fetchone()
            if row is None:
                raise KeyError("Blob not found")
            content = bytes(row[0])
            for offset in range(0, len(content), chunk_size):
                yield content[offset : offset + chunk_size]

    def delete(self, principal: Principal, blob_id: str) -> bool:
        normalized = str(UUID(blob_id))
        with self.database.transaction(principal) as connection:
            result = connection.execute(
                """
                UPDATE blob.objects
                SET deleted_at = now()
                WHERE id = %s AND deleted_at IS NULL
                """,
                (normalized,),
            )
            return result.rowcount == 1
