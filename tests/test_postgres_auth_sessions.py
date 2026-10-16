from __future__ import annotations

from contextlib import contextmanager

from coworker.server.auth import IdentityClaims
from coworker.storage.postgres.auth_sessions import PostgresAuthSessionStore


class _Result:
    def __init__(self, row=None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.identity_user_id: str | None = None
        self.profile = ("alice@example.com", "Alice")

    def execute(self, sql: str, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if compact.startswith("SELECT user_id FROM identity.external_identities"):
            return _Result(
                (self.identity_user_id,) if self.identity_user_id else None
            )
        if compact.startswith("INSERT INTO identity.users"):
            self.identity_user_id = params[0]
        if compact.startswith("SELECT s.user_id"):
            return _Result(
                (
                    self.identity_user_id,
                    self.profile[0],
                    self.profile[1],
                )
            )
        return _Result()


class _Database:
    def __init__(self) -> None:
        self.connection = _Connection()

    @contextmanager
    def shared_transaction(self):
        yield self.connection


def test_postgres_auth_session_maps_identity_and_never_stores_raw_token() -> None:
    database = _Database()
    store = PostgresAuthSessionStore(database)
    claims = IdentityClaims(
        issuer="https://tenant.authing.cn/oidc",
        subject="authing-user-1",
        email="alice@example.com",
        email_verified=True,
        display_name="Alice",
    )

    issued = store.issue(claims, ttl_seconds=3600)
    resolved = store.resolve(issued.raw_token)

    assert issued.session.principal.user_id.startswith("usr_")
    assert issued.session.principal == resolved.principal
    assert resolved.email == "alice@example.com"
    assert resolved.display_name == "Alice"

    session_insert = next(
        call
        for call in database.connection.calls
        if call[0].startswith("INSERT INTO identity.auth_sessions")
    )
    stored_hash = session_insert[1][1]
    assert stored_hash != issued.raw_token
    assert len(stored_hash) == 64
    assert issued.raw_token not in repr(database.connection.calls)

    store.revoke(issued.raw_token)
    revoke = database.connection.calls[-1]
    assert revoke[0].startswith("UPDATE identity.auth_sessions")
    assert revoke[1] == (stored_hash,)


def test_postgres_auth_session_uses_a_postgres_safe_advisory_lock_key() -> None:
    database = _Database()
    store = PostgresAuthSessionStore(database)

    store.issue(
        IdentityClaims(
            issuer="https://tenant.authing.cn/oidc",
            subject="authing-user-1",
        ),
        ttl_seconds=3600,
    )

    advisory_lock = database.connection.calls[0]
    assert advisory_lock[0].startswith("SELECT pg_advisory_xact_lock(%s)")
    assert isinstance(advisory_lock[1][0], int)
