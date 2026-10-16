from contextlib import contextmanager

from coworker.server.identity import Principal
from coworker.storage.postgres.session_skills import (
    PostgresSessionSkillState,
)


class _Rows:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple]:
        return self.rows


class _Store:
    def __init__(self) -> None:
        self.conversations: set[tuple[str, str]] = set()
        self.hashes: dict[tuple[str, str, str], str] = {}


class _Connection:
    def __init__(self, store: _Store, user_id: str) -> None:
        self.store = store
        self.user_id = user_id

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        if compact.startswith("SELECT skill_name, content_sha256"):
            rows = [
                (name, content_hash)
                for (user_id, conversation_id, name), content_hash
                in self.store.hashes.items()
                if user_id == self.user_id
                and conversation_id == params[0]
            ]
            return _Rows(rows)
        if compact.startswith("SELECT content_sha256"):
            value = self.store.hashes.get(
                (self.user_id, params[0], params[1])
            )
            return _Rows([(value,)] if value is not None else [])
        if compact.startswith("INSERT INTO identity.users"):
            return _Rows([])
        if compact.startswith("INSERT INTO agent.conversations"):
            conversation_id, user_id = params
            self.store.conversations.add((user_id, conversation_id))
            return _Rows([])
        if compact.startswith("INSERT INTO agent.session_skills"):
            user_id, conversation_id, name, _, content_hash = params
            assert (user_id, conversation_id) in self.store.conversations
            self.store.hashes[(user_id, conversation_id, name)] = content_hash
            return _Rows([])
        raise AssertionError(f"unexpected SQL: {compact}")


class _Database:
    def __init__(self) -> None:
        self.store = _Store()

    @contextmanager
    def transaction(self, principal: Principal):
        yield _Connection(self.store, principal.user_id)


def test_postgres_session_skill_state_is_durable_and_tenant_scoped() -> None:
    database = _Database()
    alice = PostgresSessionSkillState(
        database,
        Principal("alice", "test"),
        "conversation-1",
    )
    bob = PostgresSessionSkillState(
        database,
        Principal("bob", "test"),
        "conversation-1",
    )

    assert alice.loaded_hash("interview") is None
    alice.mark_loaded(
        "interview",
        version="2",
        content_sha256="a" * 64,
    )

    assert alice.loaded_hash("interview") == "a" * 64
    assert alice.loaded_hashes() == {"interview": "a" * 64}
    assert bob.loaded_hash("interview") is None
    assert bob.loaded_hashes() == {}
