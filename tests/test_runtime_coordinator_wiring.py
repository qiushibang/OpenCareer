from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from coworker.server import SessionManager, create_app


class _Provider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        return AssistantTurn(text="done", finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


class _RecordingCoordinator(LocalRuntimeCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.released: list[tuple[str, str]] = []

    def release_lease(self, key: str, owner: str) -> bool:
        self.released.append((key, owner))
        return super().release_lease(key, owner)


def _manager(tmp_path, coordinator: LocalRuntimeCoordinator) -> SessionManager:
    return SessionManager(
        data_dir=tmp_path,
        provider=_Provider(),
        runtime_coordinator=coordinator,
    )


def test_event_websocket_registers_and_clears_presence(tmp_path) -> None:
    coordinator = LocalRuntimeCoordinator()
    client = TestClient(create_app(_manager(tmp_path, coordinator)))

    with client.websocket_connect("/ws/events"):
        assert len(coordinator.presence("local")) == 1

    assert coordinator.presence("local") == ()


def test_session_websocket_rejects_turn_owned_by_another_worker(
    tmp_path,
) -> None:
    coordinator = LocalRuntimeCoordinator()
    coordinator.set_presence("local", "other-worker", 60)
    assert coordinator.acquire_lease(
        "session-turn:local:shared",
        "other-worker",
        300,
    )
    client = TestClient(create_app(_manager(tmp_path, coordinator)))

    with client.websocket_connect("/ws/session/shared?agent=chat") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "user_message", "text": "hello"})
        rejected = websocket.receive_json()

    assert rejected["type"] == "input_rejected"
    assert "already running" in rejected["data"]["error"]


def test_session_websocket_reclaims_turn_owned_by_disconnected_worker(
    tmp_path,
) -> None:
    coordinator = LocalRuntimeCoordinator()
    assert coordinator.acquire_lease(
        "session-turn:local:shared",
        "disconnected-worker",
        300,
    )
    client = TestClient(create_app(_manager(tmp_path, coordinator)))

    with client.websocket_connect("/ws/session/shared?agent=chat") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "user_message", "text": "hello"})
        assert websocket.receive_json()["type"] == "turn_start"


def test_session_websocket_releases_turn_lease_when_done(tmp_path) -> None:
    coordinator = _RecordingCoordinator()
    client = TestClient(create_app(_manager(tmp_path, coordinator)))

    with client.websocket_connect("/ws/session/one?agent=chat") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "user_message", "text": "hello"})
        while websocket.receive_json()["type"] != "turn_done":
            pass

    assert len(coordinator.released) == 1
    assert coordinator.released[0][0] == "session-turn:local:one"
