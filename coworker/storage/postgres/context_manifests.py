"""PostgreSQL persistence for auditable model context manifests."""

from __future__ import annotations

import json
import uuid

from coworker.context_manifest import ContextManifest
from coworker.server.identity import Principal


class PostgresContextManifestRepository:
    def __init__(
        self,
        database,
        principal: Principal,
        conversation_id: str,
    ) -> None:
        self._database = database
        self._principal = principal
        self._conversation_id = conversation_id

    def create(self, manifest: ContextManifest) -> str:
        if manifest.conversation_id != self._conversation_id:
            raise ValueError("context manifest conversation does not match")
        manifest_id = str(uuid.uuid4())
        with self._database.transaction(self._principal) as connection:
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (self._principal.user_id,),
            )
            connection.execute(
                """
                INSERT INTO agent.conversations(id, user_id, metadata)
                VALUES (%s, %s, '{}'::jsonb)
                ON CONFLICT (user_id, id) DO NOTHING
                """,
                (self._conversation_id, self._principal.user_id),
            )
            connection.execute(
                """
                INSERT INTO agent.context_manifests(
                    id, user_id, conversation_id, turn_id,
                    manifest, content_hash
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    manifest_id,
                    self._principal.user_id,
                    self._conversation_id,
                    manifest.turn_id,
                    json.dumps(manifest.as_dict(), ensure_ascii=False),
                    manifest.content_hash,
                ),
            )
        return manifest_id

    def update_actual_usage(
        self,
        manifest_id: str,
        usage: dict[str, int],
    ) -> bool:
        normalized = {
            key: int(usage.get(key, 0))
            for key in ("input", "output", "cache_read", "cache_write")
        }
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                UPDATE agent.context_manifests
                SET manifest = jsonb_set(
                    manifest,
                    '{actual_usage}',
                    %s::jsonb,
                    TRUE
                )
                WHERE id = %s
                RETURNING id
                """,
                (
                    json.dumps(normalized),
                    manifest_id,
                ),
            ).fetchone()
        return row is not None
