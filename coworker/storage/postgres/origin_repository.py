"""PostgreSQL-backed exact browser Origins."""

from __future__ import annotations

from .database import CloudDatabase


class PostgresOriginRepository:
    def __init__(self, database: CloudDatabase) -> None:
        self._database = database

    def enabled_origins(self) -> tuple[str, ...]:
        with self._database.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT origin
                FROM identity.deployment_origins
                WHERE enabled = TRUE
                ORDER BY origin
                """
            ).fetchall()
        return tuple(str(row[0]) for row in rows)
