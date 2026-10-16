"""Interface for reconstructible process coordination."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class RuntimeCoordinator(Protocol):
    def acquire_lease(
        self,
        key: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool: ...

    def renew_lease(
        self,
        key: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool: ...

    def lease_owner(self, key: str) -> str | None: ...

    def replace_lease(
        self,
        key: str,
        expected_owner: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool: ...

    def release_lease(self, key: str, owner: str) -> bool: ...

    def acquire_crawler_lock(
        self,
        source_id: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool: ...

    def set_presence(
        self,
        user_id: str,
        connection_id: str,
        ttl_seconds: int,
    ) -> None: ...

    def clear_presence(self, user_id: str, connection_id: str) -> None: ...

    def presence(self, user_id: str) -> tuple[str, ...]: ...

    def allow_rate(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> bool: ...

    def publish(self, channel: str, event: dict) -> None: ...

    def subscribe(
        self,
        channel: str,
        callback: Callable[[dict], None],
    ) -> Callable[[], None]: ...

    def flush_reconstructible(self) -> None: ...
