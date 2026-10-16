import asyncio
import json
from contextlib import contextmanager

from coworker.server.identity import Principal
from coworker.storage.postgres.inbox_repository import (
    PostgresInboxRepository,
)


class _Rows:
    def __init__(self, rows: list[tuple] = ()) -> None:
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _State:
    def __init__(self) -> None:
        self.conversations: set[tuple[str, str]] = set()
        self.items: dict[tuple[str, str], dict] = {}
        self.resolutions: dict[tuple[str, str], str] = {}


class _Connection:
    def __init__(self, state: _State, user_id: str) -> None:
        self.state = state
        self.user_id = user_id

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        if compact.startswith("INSERT INTO identity.users"):
            return _Rows()
        if compact.startswith("INSERT INTO agent.conversations"):
            conversation_id, user_id = params
            self.state.conversations.add((user_id, conversation_id))
            return _Rows()
        if compact.startswith("INSERT INTO agent.inbox_items"):
            item_id, user_id, conversation_id, tool_call_id, state, data, created_at = params
            for item in self.state.items.values():
                if (
                    tool_call_id is not None
                    and item["user_id"] == user_id
                    and item["conversation_id"] == conversation_id
                    and item["tool_call_id"] == tool_call_id
                ):
                    return _Rows()
            item = {
                "id": item_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "tool_call_id": tool_call_id,
                "state": state,
                "data": json.loads(data),
                "created_at": created_at,
                "resolved_at": None,
            }
            self.state.items[(user_id, item_id)] = item
            return _Rows([(item_id,)])
        if compact.startswith("SELECT i.id, i.conversation_id"):
            rows = [
                item
                for item in self.state.items.values()
                if item["user_id"] == params[0]
            ]
            index = 1
            if "i.id = %s" in compact:
                rows = [item for item in rows if item["id"] == params[index]]
                index += 1
            if "i.conversation_id = %s" in compact:
                rows = [
                    item
                    for item in rows
                    if item["conversation_id"] == params[index]
                ]
                index += 1
            if "i.tool_call_id = %s" in compact:
                rows = [
                    item
                    for item in rows
                    if item["tool_call_id"] == params[index]
                ]
                index += 1
            if "i.state = %s" in compact:
                rows = [item for item in rows if item["state"] == params[index]]
            return _Rows([self._tuple(item) for item in rows])
        if compact.startswith("UPDATE agent.inbox_items"):
            user_id, item_id = params
            item = self.state.items.get((user_id, item_id))
            if item is None or item["state"] != "pending":
                return _Rows()
            item["state"] = "resolved"
            item["resolved_at"] = "2026-08-18T01:00:00+00:00"
            return _Rows([(item_id,)])
        if compact.startswith("INSERT INTO agent.inbox_resolutions"):
            _, user_id, item_id, resolution = params
            self.state.resolutions[(user_id, item_id)] = json.loads(resolution)
            return _Rows()
        raise AssertionError(f"unexpected SQL: {compact}")

    def _tuple(self, item: dict) -> tuple:
        return (
            item["id"],
            item["conversation_id"],
            item["state"],
            item["data"],
            item["created_at"],
            item["resolved_at"],
            self.state.resolutions.get((item["user_id"], item["id"])),
        )


class _Database:
    def __init__(self) -> None:
        self.state = _State()

    @contextmanager
    def transaction(self, principal: Principal):
        yield _Connection(self.state, principal.user_id)


def test_postgres_inbox_is_idempotent_and_first_responder_wins() -> None:
    database = _Database()
    first = PostgresInboxRepository(database, Principal("alice", "test"))
    second = PostgresInboxRepository(database, Principal("alice", "test"))

    item = first.add_approval(
        "conversation-1",
        "Approve?",
        tool_call_id="call-1",
    )
    duplicate = second.add_approval(
        "conversation-1",
        "Approve again?",
        tool_call_id="call-1",
    )

    assert duplicate.id == item.id
    assert first.resolve(item.id, "allow")
    assert not second.resolve(item.id, "deny")
    resolved = second.get(item.id)
    assert resolved is not None
    assert resolved.state == "resolved"
    assert resolved.resolution == "allow"
    assert asyncio.run(second.wait(item.id)) == "allow"


def test_postgres_inbox_is_tenant_scoped() -> None:
    database = _Database()
    alice = PostgresInboxRepository(database, Principal("alice", "test"))
    bob = PostgresInboxRepository(database, Principal("bob", "test"))

    item = alice.add_question("conversation-1", "Question?")

    assert bob.get(item.id) is None
    assert bob.pending("conversation-1") == []
