from contextlib import contextmanager

from coworker.storage.postgres.database import CloudDatabase
from coworker.storage.postgres.origin_repository import (
    PostgresOriginRepository,
)


class _Result:
    def fetchall(self) -> list[tuple[str]]:
        return [
            ("https://alpha.example.com",),
            ("https://friend.example.com:8443",),
        ]


class _Connection:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, sql: str) -> _Result:
        self.calls.append(sql)
        return _Result()


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    @contextmanager
    def connection(self):
        yield self._connection


def test_postgres_origin_repository_lists_only_enabled_origins() -> None:
    connection = _Connection()
    database = CloudDatabase(pool=_Pool(connection))
    repository = PostgresOriginRepository(database)

    assert repository.enabled_origins() == (
        "https://alpha.example.com",
        "https://friend.example.com:8443",
    )
    assert len(connection.calls) == 1
    assert "identity.deployment_origins" in connection.calls[0]
    assert "enabled = TRUE" in connection.calls[0]
