from contextlib import contextmanager

from coworker.server.identity import Principal
from coworker.storage.postgres.database import CloudDatabase


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.transactions = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def execute(self, sql: str, params: object = None):
        self.calls.append((sql, params))


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    @contextmanager
    def connection(self):
        yield self._connection


def test_tenant_transaction_sets_the_principal_locally() -> None:
    connection = _Connection()
    database = CloudDatabase(pool=_Pool(connection))

    with database.transaction(Principal("alice", "test")) as current:
        assert current is connection

    assert connection.transactions == 1
    assert connection.calls == [
        (
            "SELECT set_config('app.user_id', %s, true)",
            ("alice",),
        )
    ]


def test_tenant_transaction_rejects_an_invalid_user_id() -> None:
    database = CloudDatabase(pool=_Pool(_Connection()))

    try:
        with database.transaction(Principal("../alice", "test")):
            pass
    except ValueError as exc:
        assert str(exc) == "invalid OpenCareer user id"
    else:
        raise AssertionError("invalid user id was accepted")


def test_shared_transaction_does_not_set_a_user_context() -> None:
    connection = _Connection()
    database = CloudDatabase(pool=_Pool(connection))

    with database.shared_transaction() as current:
        assert current is connection

    assert connection.transactions == 1
    assert connection.calls == []
