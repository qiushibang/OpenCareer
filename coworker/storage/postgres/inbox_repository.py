"""PostgreSQL-backed durable Inbox with first-responder-wins resolution."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from typing import Any, Optional

from coworker.inbox import (
    STATE_PENDING,
    STATE_RESOLVED,
    VIS_INBOX,
    InboxItem,
    InboxStore,
)
from coworker.server.identity import Principal


class PostgresInboxRepository(InboxStore):
    def __init__(self, database, principal: Principal) -> None:
        self._database = database
        self._principal = principal
        self._waiters: dict[str, asyncio.Event] = {}

    def add(
        self,
        session_id: str,
        kind: str,
        title: str,
        *,
        body: str = "",
        inbox: str = "default",
        visibility: str = VIS_INBOX,
        data: Optional[dict[str, Any]] = None,
        options=None,
        allow_text: bool = True,
        multi: bool = False,
        tool_call_id: Optional[str] = None,
    ) -> InboxItem:
        item = InboxItem(
            id=uuid.uuid4().hex,
            session_id=session_id,
            kind=kind,
            title=title,
            body=body,
            inbox=inbox,
            visibility=visibility,
            data=dict(data or {}),
            options=list(options or []),
            allow_text=bool(allow_text),
            multi=bool(multi),
            tool_call_id=tool_call_id,
        )
        with self._database.transaction(self._principal) as connection:
            self._ensure_parent(connection, session_id)
            inserted = connection.execute(
                """
                INSERT INTO agent.inbox_items(
                    id, user_id, conversation_id, tool_call_id,
                    state, data, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (
                    user_id, conversation_id, tool_call_id
                ) DO NOTHING
                RETURNING id
                """,
                (
                    item.id,
                    self._principal.user_id,
                    session_id,
                    tool_call_id,
                    item.state,
                    json.dumps(asdict(item), ensure_ascii=False),
                    item.created_at,
                ),
            ).fetchone()
        if inserted is not None:
            return item
        if tool_call_id is not None:
            existing = self.for_tool_call(session_id, tool_call_id)
            if existing is not None:
                return existing
        raise RuntimeError("failed to persist Inbox item")

    def for_tool_call(
        self,
        session_id: str,
        tool_call_id: str,
    ) -> Optional[InboxItem]:
        items = self._query(
            session_id=session_id,
            tool_call_id=tool_call_id,
        )
        return items[0] if items else None

    def get(self, item_id: str) -> Optional[InboxItem]:
        items = self._query(item_id=item_id)
        return items[0] if items else None

    def list(
        self,
        *,
        session_id: Optional[str] = None,
        state: Optional[str] = None,
        inbox: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> list[InboxItem]:
        return self._query(
            session_id=session_id,
            state=state,
            inbox=inbox,
            visibility=visibility,
        )

    def pending(self, session_id: Optional[str] = None) -> list[InboxItem]:
        return self.list(session_id=session_id, state=STATE_PENDING)

    def resolve(self, item_id: str, resolution: str) -> bool:
        resolution_id = str(uuid.uuid4())
        with self._database.transaction(self._principal) as connection:
            won = connection.execute(
                """
                UPDATE agent.inbox_items
                SET state = 'resolved', resolved_at = now()
                WHERE user_id = %s AND id = %s AND state = 'pending'
                RETURNING id
                """,
                (self._principal.user_id, item_id),
            ).fetchone()
            if won is None:
                return False
            connection.execute(
                """
                INSERT INTO agent.inbox_resolutions(
                    id, user_id, inbox_item_id, resolution
                ) VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    resolution_id,
                    self._principal.user_id,
                    item_id,
                    json.dumps({"value": resolution}, ensure_ascii=False),
                ),
            )
        waiter = self._waiters.get(item_id)
        if waiter is not None:
            waiter.set()
        return True

    def resolve_session(
        self,
        session_id: str,
        resolution: str = "session deleted",
    ) -> int:
        return sum(
            self.resolve(item.id, resolution)
            for item in self.pending(session_id)
        )

    async def wait(self, item_id: str) -> str:
        while True:
            item = self.get(item_id)
            if item is None:
                return ""
            if item.state == STATE_RESOLVED:
                return item.resolution or ""
            event = self._waiters.setdefault(item_id, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout=0.25)
            except TimeoutError:
                continue

    def reconcile_on_resume(self, session_id: str) -> dict:
        return {
            "pending": [
                asdict(item)
                for item in self.list(
                    session_id=session_id,
                    state=STATE_PENDING,
                )
            ],
            "recap": [
                asdict(item)
                for item in self.list(
                    session_id=session_id,
                    state=STATE_RESOLVED,
                )
            ],
        }

    def _query(
        self,
        *,
        item_id: str | None = None,
        session_id: str | None = None,
        tool_call_id: str | None = None,
        state: str | None = None,
        inbox: str | None = None,
        visibility: str | None = None,
    ) -> list[InboxItem]:
        query = """
            SELECT
                i.id, i.conversation_id, i.state, i.data,
                i.created_at, i.resolved_at, r.resolution
            FROM agent.inbox_items i
            LEFT JOIN agent.inbox_resolutions r
              ON r.user_id = i.user_id AND r.inbox_item_id = i.id
            WHERE i.user_id = %s
        """
        params: list[object] = [self._principal.user_id]
        for clause, value in (
            ("i.id = %s", item_id),
            ("i.conversation_id = %s", session_id),
            ("i.tool_call_id = %s", tool_call_id),
            ("i.state = %s", state),
            ("i.data->>'inbox' = %s", inbox),
            ("i.data->>'visibility' = %s", visibility),
        ):
            if value is not None:
                query += f" AND {clause}"
                params.append(value)
        query += " ORDER BY i.created_at"
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [_inbox_item(row) for row in rows]

    def _ensure_parent(self, connection, session_id: str) -> None:
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
            (session_id, self._principal.user_id),
        )


def _inbox_item(row) -> InboxItem:
    data = row[3]
    if isinstance(data, str):
        data = json.loads(data)
    payload = dict(data or {})
    resolution = row[6]
    if isinstance(resolution, str):
        resolution = json.loads(resolution)
    payload.update(
        {
            "id": str(row[0]),
            "session_id": str(row[1]),
            "state": str(row[2]),
            "created_at": str(row[4]),
            "resolved_at": (
                str(row[5]) if row[5] is not None else None
            ),
            "resolution": (
                resolution.get("value")
                if isinstance(resolution, dict)
                else None
            ),
        }
    )
    return InboxItem(**payload)
