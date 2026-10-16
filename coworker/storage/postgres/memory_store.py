"""Tenant-scoped PostgreSQL durable memory."""

from __future__ import annotations

from typing import Optional

from coworker.memory import MemoryItem, MemoryStore, Scope
from coworker.server.identity import Principal


class PostgresMemoryStore(MemoryStore):
    def __init__(self, database, principal: Principal) -> None:
        self._database = database
        self._principal = principal

    def add(
        self,
        content: str,
        *,
        scope: Scope = Scope.WORKSPACE,
        key: Optional[str] = None,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> MemoryItem:
        normalized_scope = Scope(scope)
        with self._database.transaction(self._principal) as connection:
            self._ensure_parent(connection, session_id)
            row = connection.execute(
                """
                INSERT INTO agent.memories(
                    user_id, scope, key, content, workspace, conversation_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING
                    id, scope, content, key, workspace,
                    conversation_id, created_at
                """,
                (
                    self._principal.user_id,
                    normalized_scope.value,
                    key,
                    content,
                    workspace,
                    session_id,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to persist memory")
        return _memory_item(row)

    def get(self, item_id: int) -> Optional[MemoryItem]:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT
                    id, scope, content, key, workspace,
                    conversation_id, created_at
                FROM agent.memories
                WHERE user_id = %s AND id = %s AND status = 'active'
                """,
                (self._principal.user_id, item_id),
            ).fetchone()
        return _memory_item(row) if row is not None else None

    def list(
        self,
        *,
        scope: Optional[Scope] = None,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[MemoryItem]:
        query = """
            SELECT
                id, scope, content, key, workspace,
                conversation_id, created_at
            FROM agent.memories
            WHERE user_id = %s AND status = 'active'
        """
        params: list[object] = [self._principal.user_id]
        if scope is not None:
            query += " AND scope = %s"
            params.append(Scope(scope).value)
        if workspace is not None:
            query += " AND workspace = %s"
            params.append(workspace)
        if session_id is not None:
            query += " AND conversation_id = %s"
            params.append(session_id)
        query += " ORDER BY id"
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [_memory_item(row) for row in rows]

    def update(self, item_id: int, content: str) -> Optional[MemoryItem]:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                UPDATE agent.memories
                SET content = %s, version = version + 1, updated_at = now()
                WHERE user_id = %s AND id = %s AND status = 'active'
                RETURNING
                    id, scope, content, key, workspace,
                    conversation_id, created_at
                """,
                (content, self._principal.user_id, item_id),
            ).fetchone()
        return _memory_item(row) if row is not None else None

    def delete(self, item_id: int) -> bool:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                DELETE FROM agent.memories
                WHERE user_id = %s AND id = %s
                RETURNING id
                """,
                (self._principal.user_id, item_id),
            ).fetchone()
        return row is not None

    def _ensure_parent(self, connection, session_id: str | None) -> None:
        connection.execute(
            """
            INSERT INTO identity.users(id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (self._principal.user_id,),
        )
        if session_id is not None:
            connection.execute(
                """
                INSERT INTO agent.conversations(id, user_id, metadata)
                VALUES (%s, %s, '{}'::jsonb)
                ON CONFLICT (user_id, id) DO NOTHING
                """,
                (session_id, self._principal.user_id),
            )


def _memory_item(row) -> MemoryItem:
    return MemoryItem(
        id=int(row[0]),
        scope=Scope(row[1]),
        content=str(row[2]),
        key=row[3],
        workspace=row[4],
        session_id=row[5],
        created_at=str(row[6]) if row[6] is not None else None,
    )
