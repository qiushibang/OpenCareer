"""In-process runtime coordination for desktop and tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import RLock


class LocalRuntimeCoordinator:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._leases: dict[str, tuple[str, float]] = {}
        self._presence: dict[tuple[str, str], float] = {}
        self._rates: dict[str, tuple[float, int]] = {}
        self._subscribers: dict[str, list[Callable[[dict], None]]] = {}
        self._lock = RLock()

    def acquire_lease(
        self,
        key: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        now = self._clock()
        with self._lock:
            current = self._leases.get(key)
            if current is not None and current[1] > now:
                return current[0] == owner
            self._leases[key] = (owner, now + ttl_seconds)
            return True

    def renew_lease(
        self,
        key: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        now = self._clock()
        with self._lock:
            current = self._leases.get(key)
            if (
                current is None
                or current[0] != owner
                or current[1] <= now
            ):
                return False
            self._leases[key] = (owner, now + ttl_seconds)
            return True

    def lease_owner(self, key: str) -> str | None:
        now = self._clock()
        with self._lock:
            current = self._leases.get(key)
            if current is None:
                return None
            if current[1] <= now:
                self._leases.pop(key, None)
                return None
            return current[0]

    def replace_lease(
        self,
        key: str,
        expected_owner: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        now = self._clock()
        with self._lock:
            current = self._leases.get(key)
            if (
                current is None
                or current[0] != expected_owner
                or current[1] <= now
            ):
                return False
            self._leases[key] = (owner, now + ttl_seconds)
            return True

    def release_lease(self, key: str, owner: str) -> bool:
        with self._lock:
            current = self._leases.get(key)
            if current is None or current[0] != owner:
                return False
            self._leases.pop(key, None)
            return True

    def acquire_crawler_lock(
        self,
        source_id: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        return self.acquire_lease(
            f"crawler:{source_id}",
            owner,
            ttl_seconds,
        )

    def set_presence(
        self,
        user_id: str,
        connection_id: str,
        ttl_seconds: int,
    ) -> None:
        with self._lock:
            self._presence[(user_id, connection_id)] = (
                self._clock() + ttl_seconds
            )

    def clear_presence(self, user_id: str, connection_id: str) -> None:
        with self._lock:
            self._presence.pop((user_id, connection_id), None)

    def presence(self, user_id: str) -> tuple[str, ...]:
        now = self._clock()
        with self._lock:
            expired = [
                key
                for key, deadline in self._presence.items()
                if deadline <= now
            ]
            for key in expired:
                self._presence.pop(key, None)
            return tuple(
                sorted(
                    connection_id
                    for (owner, connection_id) in self._presence
                    if owner == user_id
                )
            )

    def allow_rate(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        now = self._clock()
        with self._lock:
            started, count = self._rates.get(key, (now, 0))
            if now - started >= window_seconds:
                started, count = now, 0
            count += 1
            self._rates[key] = (started, count)
            return count <= limit

    def publish(self, channel: str, event: dict) -> None:
        with self._lock:
            callbacks = tuple(self._subscribers.get(channel, ()))
        for callback in callbacks:
            callback(dict(event))

    def subscribe(
        self,
        channel: str,
        callback: Callable[[dict], None],
    ) -> Callable[[], None]:
        with self._lock:
            self._subscribers.setdefault(channel, []).append(callback)

        def unsubscribe() -> None:
            with self._lock:
                callbacks = self._subscribers.get(channel, [])
                if callback in callbacks:
                    callbacks.remove(callback)

        return unsubscribe

    def flush_reconstructible(self) -> None:
        with self._lock:
            self._leases.clear()
            self._presence.clear()
            self._rates.clear()
