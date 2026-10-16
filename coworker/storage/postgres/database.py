"""Pooled PostgreSQL transactions with explicit tenant context."""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

from coworker.server.identity import Principal

from .migrations import apply_migrations

_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CloudDatabase:
    def __init__(self, *, pool) -> None:
        self.pool = pool

    @classmethod
    def from_url(
        cls,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
    ) -> "CloudDatabase":
        from psycopg_pool import ConnectionPool

        return cls(
            pool=ConnectionPool(
                database_url,
                min_size=min_size,
                max_size=max_size,
                open=True,
            )
        )

    @contextmanager
    def transaction(self, principal: Principal) -> Iterator[object]:
        if _USER_ID.fullmatch(principal.user_id) is None:
            raise ValueError("invalid OpenCareer user id")
        with self.pool.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('app.user_id', %s, true)",
                    (principal.user_id,),
                )
                yield connection

    @contextmanager
    def shared_transaction(self) -> Iterator[object]:
        with self.pool.connection() as connection:
            with connection.transaction():
                yield connection

    def migrate(self) -> tuple[int, ...]:
        with self.pool.connection() as connection:
            with connection.transaction():
                return apply_migrations(connection)

    def check(self) -> None:
        with self.pool.connection() as connection:
            connection.execute("SELECT 1")

    def close(self) -> None:
        self.pool.close()
