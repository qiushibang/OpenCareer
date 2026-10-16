"""Public-cloud security boundaries; never execute programs or contact the network."""

import pytest
from contextlib import ExitStack
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app, alpha


@pytest.mark.parametrize("method,path", [
    ("POST", "/v1/skills"), ("PATCH", "/v1/skills/mock-interview"),
    ("DELETE", "/v1/skills/mock-interview"), ("POST", "/v1/skills/upload"),
    ("POST", "/v1/skills/upload/confirm"), ("GET", "/v1/web-search"),
    ("GET", "/v1/sessions/other/artifacts/read"),
    ("POST", "/v1/messaging/dm-route"), ("GET", "/future-admin-control"),
])
def test_cloud_unknown_and_desktop_routes_are_denied(tmp_path, monkeypatch, method, path):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    assert client.request(method, path, json={}).status_code == 403


def test_cloud_agent_cannot_request_arbitrary_web_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    manager = SessionManager(workspace=tmp_path)
    engine = manager.get_engine("diagnostic", agent="career")
    assert "shell" not in engine.registry.names()
    assert "write_file" not in engine.registry.names()
    assert "mcp__career__preview_public_job_url" not in alpha.conversation_tools()


@pytest.mark.parametrize("name,fields", [
    ("aiden", {"aiden_path": "/diagnostic/not-executed"}),
    ("ollama", {"base_url": "http://127.0.0.1:18768"}),
    ("bedrock", {}), ("vertex", {}),
    ("openai", {"api_key": "diagnostic", "base_url": "http://127.0.0.1:18768"}),
    ("openai", {"api_key": "diagnostic", "base_url": "https://attacker.example/v1"}),
    ("openai", {"api_key": "diagnostic", "base_url": "https://api.openai.com/v1?secret=1"}),
])
def test_cloud_provider_save_and_verify_refuse_unsafe_settings(tmp_path, monkeypatch, name, fields):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    def unexpected(*args, **kwargs):
        pytest.fail("security refusal must happen before network or program execution")
    monkeypatch.setattr("httpx.get", unexpected)
    monkeypatch.setattr("coworker.providers.aiden_provider.subprocess.run", unexpected)
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    for path in ("/v1/providers", "/v1/providers/verify"):
        response = client.post(path, json={"name": name, "fields": fields})
        assert response.status_code == 403


def test_cloud_historical_provider_profile_is_revalidated(monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    from coworker.providers.registry import build_provider_client
    with pytest.raises(ValueError):
        build_provider_client("openai", {"api_key": "diagnostic", "base_url": "http://127.0.0.1"}, None)


def test_cloud_official_model_endpoint_and_desktop_compatibility(monkeypatch):
    from coworker.server.cloud_security import validate_provider
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    validate_provider("deepseek", {"base_url": "https://api.deepseek.com/v1"})
    validate_provider("anthropic", {})
    monkeypatch.delenv("OPENCAR_ALPHA_TEST")
    validate_provider("aiden", {"aiden_path": "/desktop-only"})


def test_cloud_budget_enforces_and_releases_capacity():
    from coworker.server.cloud_security import CloudBudget
    budget = CloudBudget()
    assert all(budget.acquire("socket", "alice") for _ in range(8))
    assert not budget.acquire("socket", "alice")
    budget.release("socket", "alice")
    assert budget.acquire("socket", "alice")
    assert all(budget.acquire("turn", user) for user in ("alice", "alice", "bob", "bob"))
    assert not budget.acquire("turn", "charlie")
    budget.release("turn", "bob")
    assert budget.acquire("turn", "charlie")
    assert budget.acquire("body", "alice")
    assert budget.acquire("body", "alice")
    assert not budget.acquire("body", "alice")
    assert budget.acquire("body", "bob")
    assert budget.acquire("body", "charlie")
    assert not budget.acquire("body", "dana")
    budget.release("body", "alice")
    assert budget.acquire("body", "dana")
    assert budget.acquire("anonymous_body", "anonymous")
    assert budget.acquire("anonymous_body", "anonymous")
    assert not budget.acquire("anonymous_body", "anonymous")
    # Anonymous slow uploads cannot consume authenticated request-body slots.
    budget.release("body", "bob")
    assert budget.acquire("body", "erin")
    with pytest.raises(ValueError):
        budget.acquire("unknown", "alice")
    assert all(budget.allow_request("alice", write=True) for _ in range(30))
    assert not budget.allow_request("alice", write=True)
    assert budget.allow_request("alice", write=False)
    assert budget.allow_request("bob", write=True)


def test_cloud_request_body_and_skill_workspace_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_ALPHA_WORKSPACE", str(tmp_path))
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    assert client.get("/v1/skills", params={"workspace": "/etc"}).status_code == 403
    assert client.get("/v1/sessions/test/skills", params={"workspace": "/etc"}).status_code == 403
    assert client.post("/v1/sessions/test/skills", json={"workspace": "/etc", "skill": "test", "enabled": True}).status_code == 403
    assert client.post("/v1/sessions/test/skills", json={"skill": "unknown-skill", "enabled": True}).status_code == 403
    assert [row["id"] for row in client.get("/v1/personas").json()["personas"]] == ["career"]
    assert client.post("/v1/providers", content=b"{}", headers={"Content-Length": str(17 * 1024 * 1024)}).status_code == 413
    response = client.post("/v1/providers", json={"name": "deepseek", "fields": {"api_key": "test-not-a-real-key"}})
    assert response.status_code == 200


def test_cloud_socket_limit_is_enforced_and_capacity_is_returned(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    with ExitStack() as stack:
        for _ in range(8):
            stack.enter_context(client.websocket_connect("/ws/events"))
        with pytest.raises(WebSocketDisconnect) as refusal:
            with client.websocket_connect("/ws/events"):
                pass
        assert refusal.value.code == 1013
    with client.websocket_connect("/ws/events"):
        pass


def test_cloud_chunked_body_and_event_flood_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    assert client.post("/v1/providers", content=iter([b"x" * (17 * 1024 * 1024)])).status_code == 413
    with client.websocket_connect("/ws/events") as ws:
        for _ in range(31):
            ws.send_text("diagnostic")
        with pytest.raises(WebSocketDisconnect) as refusal:
            ws.receive_text()
        assert refusal.value.code == 1008


def test_cloud_authentication_precedes_request_body_buffering(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("COWORKER_API_TOKEN", "diagnostic-only")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    # Even an oversized declaration cannot make an unauthenticated request reach body parsing.
    response = client.post("/v1/providers", content=b"{}", headers={"Content-Length": str(17 * 1024 * 1024)})
    assert response.status_code == 401
