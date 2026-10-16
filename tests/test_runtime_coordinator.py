import fnmatch
import json

from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from coworker.runtime.redis_coordinator import RedisRuntimeCoordinator
from coworker.server.app import _acquire_turn_lease


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str | int] = {}
        self.published: list[tuple[str, str]] = []

    def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def eval(self, script, _keys, key, owner, *args):
        if self.values.get(key) != owner:
            return 0
        if "'set'" in script:
            self.values[key] = args[0]
            return 1
        if "del" in script:
            self.values.pop(key, None)
        return 1

    def scan_iter(self, *, match):
        return [
            key
            for key in self.values
            if fnmatch.fnmatch(key, match)
        ]

    def incr(self, key):
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    def expire(self, key, seconds):
        return key in self.values

    def publish(self, channel, payload):
        self.published.append((channel, payload))

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


def test_local_runtime_coordinator_leases_expire_and_recover() -> None:
    now = [100.0]
    coordinator = LocalRuntimeCoordinator(clock=lambda: now[0])

    assert coordinator.acquire_lease("session-1", "worker-a", 10)
    assert not coordinator.acquire_lease("session-1", "worker-b", 10)
    assert coordinator.renew_lease("session-1", "worker-a", 10)
    assert not coordinator.release_lease("session-1", "worker-b")
    assert coordinator.release_lease("session-1", "worker-a")
    assert coordinator.acquire_lease("session-1", "worker-b", 10)

    now[0] = 111.0
    assert coordinator.acquire_lease("session-1", "worker-a", 10)

    coordinator.flush_reconstructible()
    assert coordinator.acquire_lease("session-1", "worker-a", 10)


def test_local_turn_lease_reclaims_only_an_orphaned_connection() -> None:
    coordinator = LocalRuntimeCoordinator()
    coordinator.set_presence("alice", "connection-old", 60)
    assert coordinator.acquire_lease("session-1", "connection-old", 300)

    assert not _acquire_turn_lease(
        coordinator,
        key="session-1",
        user_id="alice",
        owner="connection-new",
        ttl_seconds=300,
    )

    coordinator.clear_presence("alice", "connection-old")
    assert _acquire_turn_lease(
        coordinator,
        key="session-1",
        user_id="alice",
        owner="connection-new",
        ttl_seconds=300,
    )
    assert not coordinator.release_lease("session-1", "connection-old")


def test_local_runtime_coordinator_crawler_presence_and_rate_limits() -> None:
    now = [100.0]
    coordinator = LocalRuntimeCoordinator(clock=lambda: now[0])

    assert coordinator.acquire_crawler_lock("tencent", "crawler-a", 30)
    assert not coordinator.acquire_crawler_lock(
        "tencent",
        "crawler-b",
        30,
    )

    coordinator.set_presence("alice", "connection-1", 10)
    assert coordinator.presence("alice") == ("connection-1",)
    coordinator.clear_presence("alice", "connection-1")
    assert coordinator.presence("alice") == ()
    coordinator.set_presence("alice", "connection-1", 10)
    now[0] = 111.0
    assert coordinator.presence("alice") == ()

    assert coordinator.allow_rate("alice:chat", 2, 60)
    assert coordinator.allow_rate("alice:chat", 2, 60)
    assert not coordinator.allow_rate("alice:chat", 2, 60)
    now[0] = 172.0
    assert coordinator.allow_rate("alice:chat", 2, 60)


def test_local_runtime_coordinator_publishes_ephemeral_events() -> None:
    coordinator = LocalRuntimeCoordinator()
    received: list[dict] = []
    unsubscribe = coordinator.subscribe("session-events", received.append)

    coordinator.publish("session-events", {"type": "updated"})
    unsubscribe()
    coordinator.publish("session-events", {"type": "ignored"})

    assert received == [{"type": "updated"}]


def test_redis_runtime_coordinator_uses_only_reconstructible_keys() -> None:
    redis = _Redis()
    coordinator = RedisRuntimeCoordinator(redis)

    assert coordinator.acquire_lease("session-1", "worker-a", 10)
    assert not coordinator.acquire_lease("session-1", "worker-b", 10)
    assert coordinator.renew_lease("session-1", "worker-a", 10)
    assert not coordinator.release_lease("session-1", "worker-b")
    assert coordinator.release_lease("session-1", "worker-a")
    assert coordinator.acquire_lease("session-1", "worker-b", 10)
    assert coordinator.acquire_crawler_lock("tencent", "crawler-a", 30)

    coordinator.set_presence("alice", "connection-1", 10)
    assert coordinator.presence("alice") == ("connection-1",)
    coordinator.clear_presence("alice", "connection-1")
    assert coordinator.presence("alice") == ()
    assert coordinator.allow_rate("alice:chat", 1, 60)
    assert not coordinator.allow_rate("alice:chat", 1, 60)

    coordinator.publish("session-events", {"type": "updated"})
    channel, payload = redis.published[0]
    assert channel == "opencareer:event:session-events"
    assert json.loads(payload) == {"type": "updated"}

    redis.values["unrelated:durable"] = "keep"
    coordinator.flush_reconstructible()
    assert redis.values == {"unrelated:durable": "keep"}
    assert coordinator.acquire_lease("session-1", "worker-b", 10)


def test_redis_turn_lease_reclaims_only_an_orphaned_connection() -> None:
    redis = _Redis()
    coordinator = RedisRuntimeCoordinator(redis)
    coordinator.set_presence("alice", "connection-old", 60)
    assert coordinator.acquire_lease("session-1", "connection-old", 300)

    assert not _acquire_turn_lease(
        coordinator,
        key="session-1",
        user_id="alice",
        owner="connection-new",
        ttl_seconds=300,
    )

    coordinator.clear_presence("alice", "connection-old")
    assert _acquire_turn_lease(
        coordinator,
        key="session-1",
        user_id="alice",
        owner="connection-new",
        ttl_seconds=300,
    )
    assert not coordinator.release_lease("session-1", "connection-old")
