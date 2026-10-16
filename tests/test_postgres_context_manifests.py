import json
from contextlib import contextmanager

from coworker.context_manifest import build_context_manifest
from coworker.server.identity import Principal
from coworker.storage.postgres.context_manifests import (
    PostgresContextManifestRepository,
)


class _Rows:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self) -> None:
        self.inserted: dict | None = None
        self.updated_usage: dict | None = None

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        if compact.startswith("INSERT INTO identity.users"):
            return _Rows([])
        if compact.startswith("INSERT INTO agent.conversations"):
            return _Rows([])
        if compact.startswith("INSERT INTO agent.context_manifests"):
            self.inserted = {
                "id": params[0],
                "user_id": params[1],
                "conversation_id": params[2],
                "turn_id": params[3],
                "manifest": json.loads(params[4]),
                "content_hash": params[5],
            }
            return _Rows([])
        if compact.startswith("UPDATE agent.context_manifests"):
            self.updated_usage = json.loads(params[0])
            return _Rows([(params[1],)])
        raise AssertionError(f"unexpected SQL: {compact}")


class _Database:
    def __init__(self) -> None:
        self.connection = _Connection()

    @contextmanager
    def transaction(self, _principal: Principal):
        yield self.connection


def test_postgres_context_manifest_create_and_usage_update() -> None:
    database = _Database()
    repository = PostgresContextManifestRepository(
        database,
        Principal("alice", "test"),
        "conversation-1",
    )
    manifest = build_context_manifest(
        conversation_id="conversation-1",
        turn_id="turn-1",
        messages=[{"role": "user", "content": "secret resume body"}],
        canonical_start=0,
        canonical_end=0,
        model="deepseek:model",
        estimated_tokens=20,
    )

    manifest_id = repository.create(manifest)
    assert database.connection.inserted is not None
    assert database.connection.inserted["id"] == manifest_id
    assert (
        database.connection.inserted["content_hash"]
        == manifest.content_hash
    )
    assert (
        "secret resume body"
        not in str(database.connection.inserted["manifest"])
    )

    assert repository.update_actual_usage(
        manifest_id,
        {
            "input": 18,
            "output": 5,
            "cache_read": 2,
            "cache_write": 0,
        },
    )
    assert database.connection.updated_usage == {
        "input": 18,
        "output": 5,
        "cache_read": 2,
        "cache_write": 0,
    }
