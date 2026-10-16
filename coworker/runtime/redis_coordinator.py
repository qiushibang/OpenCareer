"""Redis-backed coordination containing no authoritative business data."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from urllib.parse import quote, unquote

_PREFIX = "opencareer:runtime:"
_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_REPLACE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3])
  return 1
end
return 0
"""
_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class RedisRuntimeCoordinator:
    def __init__(self, client) -> None:
        self._client = client

    @staticmethod
    def _lease_key(key: str) -> str:
        return f"{_PREFIX}lease:{quote(key, safe='')}"

    def acquire_lease(
        self,
        key: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        return bool(
            self._client.set(
                self._lease_key(key),
                owner,
                nx=True,
                ex=ttl_seconds,
            )
        )

    def renew_lease(
        self,
        key: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        return bool(
            self._client.eval(
                _RENEW,
                1,
                self._lease_key(key),
                owner,
                ttl_seconds,
            )
        )

    def lease_owner(self, key: str) -> str | None:
        owner = self._client.get(self._lease_key(key))
        if owner is None:
            return None
        return (
            owner.decode("utf-8")
            if isinstance(owner, bytes)
            else str(owner)
        )

    def replace_lease(
        self,
        key: str,
        expected_owner: str,
        owner: str,
        ttl_seconds: int,
    ) -> bool:
        return bool(
            self._client.eval(
                _REPLACE,
                1,
                self._lease_key(key),
                expected_owner,
                owner,
                ttl_seconds,
            )
        )

    def release_lease(self, key: str, owner: str) -> bool:
        return bool(
            self._client.eval(
                _RELEASE,
                1,
                self._lease_key(key),
                owner,
            )
        )

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
        self._client.set(
            self._presence_key(user_id, connection_id),
            "1",
            ex=ttl_seconds,
        )

    @staticmethod
    def _presence_key(user_id: str, connection_id: str) -> str:
        return (
            f"{_PREFIX}presence:{quote(user_id, safe='')}:"
            f"{quote(connection_id, safe='')}"
        )

    def clear_presence(self, user_id: str, connection_id: str) -> None:
        self._client.delete(self._presence_key(user_id, connection_id))

    def presence(self, user_id: str) -> tuple[str, ...]:
        prefix = f"{_PREFIX}presence:{quote(user_id, safe='')}:"
        connections = []
        for raw_key in self._client.scan_iter(match=f"{prefix}*"):
            key = (
                raw_key.decode("utf-8")
                if isinstance(raw_key, bytes)
                else str(raw_key)
            )
            connections.append(unquote(key[len(prefix) :]))
        return tuple(sorted(connections))

    def allow_rate(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        redis_key = f"{_PREFIX}rate:{quote(key, safe='')}"
        count = int(self._client.incr(redis_key))
        if count == 1:
            self._client.expire(redis_key, window_seconds)
        return count <= limit

    def publish(self, channel: str, event: dict) -> None:
        self._client.publish(
            f"opencareer:event:{channel}",
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        )

    def subscribe(
        self,
        channel: str,
        callback: Callable[[dict], None],
    ) -> Callable[[], None]:
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(f"opencareer:event:{channel}")
        stopped = threading.Event()

        def consume() -> None:
            while not stopped.is_set():
                message = pubsub.get_message(timeout=0.5)
                if message and message.get("data") is not None:
                    raw = message["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    callback(json.loads(raw))
                else:
                    time.sleep(0.05)

        thread = threading.Thread(target=consume, daemon=True)
        thread.start()

        def unsubscribe() -> None:
            stopped.set()
            pubsub.close()

        return unsubscribe

    def flush_reconstructible(self) -> None:
        keys = list(self._client.scan_iter(match=f"{_PREFIX}*"))
        if keys:
            self._client.delete(*keys)
