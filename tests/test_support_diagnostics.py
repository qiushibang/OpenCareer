"""User-visible support diagnostics through real HTTP boundaries."""

import re

from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.providers import ProviderClient, ModelCapabilities
from contextlib import contextmanager
from coworker.storage.postgres.database import CloudDatabase
from extensions.support.diagnostics import DiagnosticStore


def test_http_failure_has_a_private_safe_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture,bob:bob-fixture")
    app = create_app(SessionManager(workspace=tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-OpenWorker-Token": "alice-fixture", "X-Request-ID": "forged-private-text"}
    response = client.get("/v1/missing-fixture?api_key=private-fixture", headers=headers)
    assert response.status_code >= 400
    request_id = response.headers.get("X-Request-ID", "")
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    diagnostic = client.get(f"/v1/support/diagnostics/{request_id}", headers=headers)
    assert diagnostic.status_code == 200
    assert diagnostic.json()["diagnostic"]["request_id"] == request_id
    assert diagnostic.json()["diagnostic"]["release"] == "unknown"
    assert "private-fixture" not in diagnostic.text
    assert "forged-private-text" not in diagnostic.text
    assert client.get(f"/v1/support/diagnostics/{request_id}",
                      headers={"X-OpenWorker-Token": "bob-fixture"}).status_code == 404


def test_unhandled_failure_is_generic_and_diagnostic_survives(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    app = create_app(SessionManager(workspace=tmp_path))

    @app.get("/v1/failure-fixture")
    def failure():
        raise ValueError("api_key=private-key and fictional-resume-body")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/v1/failure-fixture", headers={"X-OpenWorker-Token": "alice-fixture"})
    assert response.status_code == 500
    assert "private-key" not in response.text
    assert "fictional-resume-body" not in response.text
    request_id = response.headers["X-Request-ID"]
    diagnostic = client.get(f"/v1/support/diagnostics/{request_id}",
                            headers={"X-OpenWorker-Token": "alice-fixture"})
    assert diagnostic.json()["diagnostic"]["kind"] == "http_server_error"


def test_browser_diagnostic_upload_is_authenticated_and_content_free(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    path = "/v1/support/diagnostics"
    assert client.post(path, json={"kind": "page_crash"}).status_code == 401
    headers = {"X-OpenWorker-Token": "alice-fixture"}
    response = client.post(path, json={"kind": "page_crash", "page": "conversation"}, headers=headers)
    assert response.status_code == 201
    assert re.fullmatch(r"[0-9a-f]{32}", response.json()["request_id"])
    assert client.post(path, json={"kind": "page_crash", "body": "fictional-private"}, headers=headers).status_code == 422
    assert client.post(path, content=b" " * 8193, headers=headers).status_code == 413


def test_websocket_provider_failure_has_safe_correlated_diagnostic(tmp_path, monkeypatch):
    class FailingProvider(ProviderClient):
        def complete(self, **kwargs):
            raise ValueError("api_key=private-provider-key resume=fictional-private")

        def capabilities(self, model):
            return ModelCapabilities()

    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    client = TestClient(create_app(SessionManager(workspace=tmp_path, provider=FailingProvider())))
    with client.websocket_connect("/ws/session/support-fixture", subprotocols=["openworker", "alice-fixture"]) as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.send_json({"type": "user_message", "text": "fictional greeting"})
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event["type"] == "turn_done":
                break
        failure = next(event for event in events if event["type"] == "error")
        assert "private-provider-key" not in str(failure)
        assert "fictional-private" not in str(failure)
        request_id = failure["data"]["request_id"]
        response = client.get(f"/v1/support/diagnostics/{request_id}", headers={"X-OpenWorker-Token": "alice-fixture"})
        assert response.json()["diagnostic"]["kind"] == "provider_error"


def test_diagnostic_database_failure_does_not_replace_business_response(tmp_path, monkeypatch):
    class OfflinePool:
        @contextmanager
        def connection(self):
            raise ConnectionError("private-database-password")
            yield

    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    store = DiagnosticStore(database=CloudDatabase(pool=OfflinePool()))
    client = TestClient(create_app(SessionManager(workspace=tmp_path), diagnostic_store=store))
    response = client.get("/v1/missing-fixture", headers={"X-OpenWorker-Token": "alice-fixture"})
    assert response.status_code == 404
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
    assert "private-database-password" not in response.text


def test_diagnostic_capacity_keeps_newest_faults_within_same_second(tmp_path, monkeypatch):
    import uuid
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "0")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    counter = 0
    def decreasing_uuid():
        nonlocal counter
        counter += 1
        return uuid.UUID(int=2**120 - counter)
    monkeypatch.setattr("uuid.uuid4", decreasing_uuid)
    monkeypatch.setattr("time.time", lambda: 1789700000)
    headers = {"X-OpenWorker-Token": "alice-fixture"}
    ids = [client.get("/v1/missing-fixture", headers=headers).headers["X-Request-ID"] for _ in range(1001)]
    assert client.get(f"/v1/support/diagnostics/{ids[-1]}", headers=headers).status_code == 200
    assert client.get(f"/v1/support/diagnostics/{ids[0]}", headers=headers).status_code == 404


def test_unavailable_local_support_storage_does_not_prevent_business_startup(tmp_path):
    manager = SessionManager(workspace=tmp_path)
    support_path = manager.audit_store.db_path.parent / "support.db"
    support_path.write_bytes(b"fictional-corrupt-storage")
    client = TestClient(create_app(manager), raise_server_exceptions=False)
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/support/feedback").status_code == 503
