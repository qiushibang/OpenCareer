"""Select local or cloud storage without changing desktop defaults."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from coworker.runtime.redis_coordinator import RedisRuntimeCoordinator

from .postgres.database import CloudDatabase
from .postgres.origin_repository import PostgresOriginRepository


@dataclass
class StorageRuntime:
    mode: str
    database: Any = None
    redis: Any = None
    origin_repository: PostgresOriginRepository | None = None
    coordinator: Any = None

    def health(self) -> dict[str, str]:
        configured = self.mode == "postgres"
        return {
            "mode": self.mode,
            "postgres": "ready" if configured else "not_configured",
            "redis": "ready" if configured else "not_configured",
        }

    def close(self) -> None:
        if self.redis is not None:
            self.redis.close()
        if self.database is not None:
            self.database.close()


def _database_from_url(database_url: str) -> CloudDatabase:
    return CloudDatabase.from_url(database_url)


def _redis_from_url(redis_url: str):
    import redis

    return redis.Redis.from_url(redis_url)


def build_storage_runtime(
    *,
    environ: Mapping[str, str] | None = None,
    database_factory: Callable[[str], Any] = _database_from_url,
    redis_factory: Callable[[str], Any] = _redis_from_url,
) -> StorageRuntime:
    values = os.environ if environ is None else environ
    database_url = values.get("DATABASE_URL", "").strip()
    redis_url = values.get("REDIS_URL", "").strip()
    if not database_url and not redis_url:
        return StorageRuntime(
            mode="local",
            coordinator=LocalRuntimeCoordinator(),
        )
    if not database_url or not redis_url:
        raise RuntimeError(
            "DATABASE_URL and REDIS_URL must be configured together"
        )

    database = None
    redis_client = None
    try:
        database = database_factory(database_url)
        database.check()
        database.migrate()
        redis_client = redis_factory(redis_url)
        if redis_client.ping() is not True:
            raise RuntimeError("Redis ping failed")
    except Exception as exc:
        if redis_client is not None:
            redis_client.close()
        if database is not None:
            database.close()
        raise RuntimeError("cloud storage initialization failed") from exc

    return StorageRuntime(
        mode="postgres",
        database=database,
        redis=redis_client,
        origin_repository=PostgresOriginRepository(database),
        coordinator=RedisRuntimeCoordinator(redis_client),
    )
