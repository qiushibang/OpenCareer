from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from coworker.server.identity import Principal
from coworker.sessions import SessionRecord
from coworker.storage.postgres.conversations import (
    PostgresConversationRepository,
)


class _Rows:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return self._rows


class _Store:
    def __init__(self) -> None:
        self.conversations: dict[tuple[str, str], dict] = {}
        self.messages: dict[tuple[str, str], list[dict]] = {}
        self.workspaces: dict[str, list[str]] = {}
        self.compactions: dict[tuple[str, str], list[tuple]] = {}


class _Connection:
    def __init__(self, store: _Store, user_id: str) -> None:
        self.store = store
        self.user_id = user_id

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        if compact.startswith("INSERT INTO identity.users"):
            return _Rows([])
        if compact.startswith("INSERT INTO agent.workspaces"):
            user_id, path = params
            workspaces = self.store.workspaces.setdefault(user_id, [])
            if path in workspaces:
                workspaces.remove(path)
            workspaces.append(path)
            return _Rows([])
        if compact.startswith("SELECT path FROM agent.workspaces"):
            limit = params[0]
            paths = reversed(self.store.workspaces.get(self.user_id, []))
            return _Rows([(path,) for path in list(paths)[:limit]])
        if compact.startswith(
            "SELECT id, metadata FROM agent.conversations"
        ):
            rows = [
                (conversation_id, metadata)
                for (user_id, conversation_id), metadata
                in self.store.conversations.items()
                if user_id == self.user_id
            ]
            return _Rows(rows)
        if compact.startswith("SELECT metadata FROM agent.conversations"):
            metadata = self.store.conversations.get((self.user_id, params[0]))
            return _Rows([(metadata,)] if metadata is not None else [])
        if compact.startswith("INSERT INTO agent.conversations"):
            conversation_id, user_id, raw_metadata = params
            self.store.conversations.setdefault(
                (user_id, conversation_id),
                json.loads(raw_metadata),
            )
            self.store.messages.setdefault((user_id, conversation_id), [])
            return _Rows([])
        if compact.startswith(
            "SELECT sequence, content FROM agent.messages"
        ):
            rows = self.store.messages.get((self.user_id, params[0]), [])
            return _Rows(
                [(index + 1, message) for index, message in enumerate(rows)]
            )
        if compact.startswith(
            "SELECT version, boundary_sequence, source_hash, state "
            "FROM agent.compactions"
        ):
            rows = self.store.compactions.get(
                (self.user_id, params[0]),
                [],
            )
            return _Rows([rows[-1]] if rows else [])
        if compact.startswith("INSERT INTO agent.messages"):
            _, user_id, conversation_id, sequence, raw_content = params
            messages = self.store.messages[(user_id, conversation_id)]
            assert sequence == len(messages) + 1
            messages.append(json.loads(raw_content))
            return _Rows([])
        if compact.startswith("INSERT INTO agent.compactions"):
            (
                _,
                user_id,
                conversation_id,
                version,
                boundary,
                _,
                _,
                source_hash,
                raw_state,
            ) = params
            self.store.compactions.setdefault(
                (user_id, conversation_id),
                [],
            ).append(
                (
                    version,
                    boundary,
                    source_hash,
                    json.loads(raw_state),
                )
            )
            return _Rows([])
        if compact.startswith("UPDATE agent.conversations SET metadata"):
            raw_metadata, conversation_id = params
            self.store.conversations[(self.user_id, conversation_id)] = (
                json.loads(raw_metadata)
            )
            return _Rows([])
        if compact.startswith("DELETE FROM agent.messages"):
            self.store.messages.pop((self.user_id, params[0]), None)
            return _Rows([])
        if compact.startswith("DELETE FROM agent.conversations"):
            removed = self.store.conversations.pop(
                (self.user_id, params[0]),
                None,
            )
            return _Rows([(params[0],)] if removed is not None else [])
        raise AssertionError(f"unexpected SQL: {compact}")


class _Database:
    def __init__(self) -> None:
        self.store = _Store()

    @contextmanager
    def transaction(self, principal: Principal):
        yield _Connection(self.store, principal.user_id)


def _record(
    messages: list[dict],
    *,
    compaction: dict | None = None,
) -> SessionRecord:
    return SessionRecord(
        session_id="conversation-1",
        workspace="/workspace",
        model="deepseek:model",
        mode="interactive",
        messages=messages,
        title="Interview",
        agent="career",
        compaction=compaction or {},
    )


def test_postgres_conversation_messages_are_append_only_and_idempotent() -> None:
    database = _Database()
    repository = PostgresConversationRepository(
        database,
        Principal("alice", "test"),
    )
    first = {"role": "user", "content": "one"}
    second = {"role": "assistant", "content": "two"}

    repository.save(_record([first, second]))
    repository.save(_record([first, second]))
    repository.save(
        _record([first, second, {"role": "user", "content": "three"}])
    )

    loaded = repository.load("conversation-1")
    assert loaded is not None
    assert loaded.messages == [
        first,
        second,
        {"role": "user", "content": "three"},
    ]
    assert loaded.title == "Interview"
    assert loaded.agent == "career"


def test_postgres_conversation_rejects_canonical_history_rewrites() -> None:
    database = _Database()
    repository = PostgresConversationRepository(
        database,
        Principal("alice", "test"),
    )
    repository.save(_record([{"role": "user", "content": "original"}]))

    with pytest.raises(RuntimeError, match="append-only"):
        repository.save(_record([{"role": "user", "content": "changed"}]))


def test_postgres_conversation_is_scoped_to_the_principal() -> None:
    database = _Database()
    alice = PostgresConversationRepository(
        database,
        Principal("alice", "test"),
    )
    bob = PostgresConversationRepository(
        database,
        Principal("bob", "test"),
    )

    alice.save(_record([{"role": "user", "content": "private"}]))

    assert bob.load("conversation-1") is None


def test_postgres_conversation_list_and_archive_use_metadata() -> None:
    database = _Database()
    repository = PostgresConversationRepository(
        database,
        Principal("alice", "test"),
    )
    repository.save(_record([{"role": "user", "content": "one"}]))

    assert repository.set_flags("conversation-1", archived=True)
    listed = repository.list()

    assert len(listed) == 1
    assert listed[0].session_id == "conversation-1"
    assert listed[0].message_count == 1
    assert listed[0].archived is True
    assert listed[0].messages == []


def test_postgres_conversation_supports_existing_manager_metadata_calls() -> None:
    database = _Database()
    repository = PostgresConversationRepository(
        database,
        Principal("alice", "test"),
    )
    repository.save(_record([]))

    repository.touch_workspace("/first")
    repository.touch_workspace("/second")
    assert repository.recent_workspaces(limit=1) == ["/second"]

    assert repository.rename("conversation-1", "  Manual   title  ")
    assert not repository.set_auto_title("conversation-1", "Ignored")
    assert repository.title_state("conversation-1") == {
        "renamed": True,
        "auto_title": None,
    }
    assert repository.set_origin("conversation-1", "lark", "Hiring")
    repository.set_extra_roots(
        "conversation-1",
        [{"path": "/shared", "writable": False, "label": "Shared"}],
    )

    loaded = repository.load("conversation-1")
    assert loaded is not None
    assert loaded.title == "Manual title"
    assert loaded.origin == "lark"
    assert loaded.origin_label == "Hiring"
    assert loaded.extra_roots == [
        {"path": "/shared", "writable": False, "label": "Shared"}
    ]

    assert repository.delete("conversation-1")
    assert repository.load("conversation-1") is None


def test_postgres_compactions_are_versioned_without_deleting_messages() -> None:
    database = _Database()
    repository = PostgresConversationRepository(
        database,
        Principal("alice", "test"),
    )
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    first = {
        "boundary_index": 1,
        "summary_text": "first summary",
        "working_state": "",
        "user_messages": ["one"],
    }
    second = {
        "boundary_index": 2,
        "summary_text": "second summary",
        "working_state": "",
        "user_messages": ["one", "three"],
    }

    repository.save(_record(messages, compaction=first))
    repository.save(_record(messages, compaction=second))
    repository.save(_record(messages, compaction=second))

    versions = database.store.compactions[("alice", "conversation-1")]
    loaded = repository.load("conversation-1")
    assert [version for version, _, _, _ in versions] == [1, 2]
    assert loaded is not None
    assert loaded.compaction == second
    assert loaded.messages == messages
