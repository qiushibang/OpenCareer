"""Discover and apply versioned PostgreSQL schema migrations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_MIGRATION_NAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
_LOCK_KEY = 0x4F50454E434152


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    sha256: str


def discover_migrations() -> tuple[Migration, ...]:
    root = Path(__file__).with_name("sql")
    migrations: list[Migration] = []
    for path in sorted(root.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            continue
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                sql=sql,
                sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise RuntimeError("PostgreSQL migration versions must be unique")
    return tuple(migrations)


def apply_migrations(
    connection,
    *,
    migrations: tuple[Migration, ...] | None = None,
) -> tuple[int, ...]:
    """Apply pending migrations inside the caller's transaction."""

    connection.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
    connection.execute("CREATE SCHEMA IF NOT EXISTS opencareer_meta")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS opencareer_meta.schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    rows = connection.execute(
        "SELECT version, sha256 "
        "FROM opencareer_meta.schema_migrations ORDER BY version"
    ).fetchall()
    applied = {int(version): str(sha256) for version, sha256 in rows}
    selected = migrations if migrations is not None else discover_migrations()
    completed: list[int] = []
    for migration in selected:
        recorded = applied.get(migration.version)
        if recorded is not None:
            if recorded != migration.sha256:
                raise RuntimeError(
                    f"PostgreSQL migration {migration.version} checksum changed"
                )
            continue
        connection.execute(migration.sql)
        connection.execute(
            """
            INSERT INTO opencareer_meta.schema_migrations(
                version, name, sha256
            ) VALUES (%s, %s, %s)
            """,
            (migration.version, migration.name, migration.sha256),
        )
        completed.append(migration.version)
    return tuple(completed)
