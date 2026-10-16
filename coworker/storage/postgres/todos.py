"""Tenant-scoped PostgreSQL todo persistence."""

from __future__ import annotations

import json

from coworker.server.identity import Principal


class PostgresTodoRepository:
    def __init__(self, database, principal: Principal) -> None:
        self._database = database
        self._principal = principal

    def load(self, conversation_id: str) -> list[dict]:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT data
                FROM agent.todos
                WHERE user_id = %s AND conversation_id = %s
                """,
                (self._principal.user_id, conversation_id),
            ).fetchone()
        if row is None:
            return []
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        return list(value) if isinstance(value, list) else []

    def replace(self, conversation_id: str, items: list[dict]) -> None:
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
                (conversation_id, self._principal.user_id),
            )
            connection.execute(
                """
                INSERT INTO agent.todos(user_id, conversation_id, data)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (user_id, conversation_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                """,
                (
                    self._principal.user_id,
                    conversation_id,
                    json.dumps(items, ensure_ascii=False),
                ),
            )
