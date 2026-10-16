"""Cloud BYOK: per-user provider credentials and the alpha gate for them.

The cloud alpha used to block /v1/providers entirely and share one process-wide
SecretStore. These tests lock the new contract:

- every principal gets its own SecretStore file under users/<uid>/;
- one user's saved key is invisible to (and removable without affecting) another;
- provider responses never echo the key back;
- the alpha surface opens exactly /v1/providers* and /v1/settings/default-model
  while every other /v1/settings path (and the chat-completions proxy) stays 403.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server import alpha
from coworker.server import run as server_run
from coworker.server.identity import Principal
from coworker.secrets import SecretStore
from coworker.runtime.local_coordinator import LocalRuntimeCoordinator


class _PostgresRuntime:
    mode = "postgres"
    database = object()
    origin_repository = None
    coordinator = LocalRuntimeCoordinator()

    def health(self) -> dict[str, str]:
        return {"mode": "postgres", "postgres": "ready", "redis": "ready"}

    def close(self) -> None:
        pass


def test_alpha_gate_opens_exactly_the_byok_surface(monkeypatch) -> None:
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")

    assert not alpha.blocks_http("GET", "/v1/providers")
    assert not alpha.blocks_http("POST", "/v1/providers")
    assert not alpha.blocks_http("POST", "/v1/providers/verify")
    assert not alpha.blocks_http("DELETE", "/v1/providers/deepseek")
    assert not alpha.blocks_http("POST", "/v1/settings/default-model")

    # Desktop-only settings and the OpenAI-compatible proxy stay shut.
    assert alpha.blocks_http("GET", "/v1/settings")
    assert alpha.blocks_http("POST", "/v1/settings/model-key")
    assert alpha.blocks_http("POST", "/v1/settings/models/add")
    assert alpha.blocks_http("POST", "/v1/chat/completions")


def test_alpha_http_allows_byok_without_leaking_the_key(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    manager = SessionManager(workspace=tmp_path)
    client = TestClient(create_app(manager))

    assert client.get("/v1/providers").status_code == 200

    saved = client.post(
        "/v1/providers",
        json={"name": "deepseek", "fields": {"api_key": "sk-alpha-secret"}},
    )
    assert saved.status_code == 200
    assert saved.json().get("ok") is True

    listed = client.get("/v1/providers")
    assert listed.status_code == 200
    assert "sk-alpha-secret" not in listed.text

    model = client.post(
        "/v1/settings/default-model", json={"model": "deepseek:deepseek-chat"}
    )
    assert model.status_code == 200
    assert model.json().get("ok") is True
    assert "sk-alpha-secret" not in model.text

    # The rest of /v1/settings is still desktop-only.
    assert client.get("/v1/settings").status_code == 403
    assert (
        client.post("/v1/settings/model-key", json={"api_key": "sk-x"}).status_code
        == 403
    )


def test_manager_for_gives_each_user_their_own_secret_store(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        server_run, "build_storage_runtime", lambda: _PostgresRuntime()
    )

    app = server_run.build_app(None, "deepseek:deepseek-chat", "interactive")
    registry = app.state.manager

    alice_manager = registry._managers.get("alice")  # not built yet
    assert alice_manager is None  # sanity: lazy construction

    token = registry.activate(Principal("alice", "test"))
    try:
        alice = registry.secrets
        assert alice.path == tmp_path / "state" / "users" / "alice" / "secrets.json"
        result = alice_set = registry.set_provider(
            "deepseek", {"api_key": "sk-alice"}
        )
        assert result.get("ok") is True
    finally:
        registry.deactivate(token)

    token = registry.activate(Principal("bob", "test"))
    try:
        bob = registry.secrets
        assert bob.path == tmp_path / "state" / "users" / "bob" / "secrets.json"
        # Bob sees deepseek as not configured and his own store has no profile.
        assert bob.get("provider:deepseek") is None
        bob_providers = {
            p["name"]: p for p in registry.get_providers()
        }
        assert bob_providers["deepseek"]["configured"] is False
        assert "sk-alice" not in json.dumps(bob_providers)
    finally:
        registry.deactivate(token)

    token = registry.activate(Principal("alice", "test"))
    try:
        assert registry.secrets.get("provider:deepseek") is not None
        removed = registry.remove_provider("deepseek")
        assert removed.get("ok") is True
        assert registry.secrets.get("provider:deepseek") is None
    finally:
        registry.deactivate(token)

    # Removing Alice's key never touched Bob's (empty) store.
    assert bob.get("provider:deepseek") is None


def test_providers_report_credential_source(tmp_path, monkeypatch) -> None:
    """source distinguishes the user's own stored key ("store") from a server
    environment key ("env") — the cloud key-management card only manages the
    former, because deleting a personal key falls back to the server's."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-server-env")
    manager = SessionManager(workspace=tmp_path)

    providers = {p["name"]: p for p in manager.get_providers()}
    assert providers["deepseek"]["configured"] is True
    assert providers["deepseek"]["source"] == "env"

    assert manager.set_provider("deepseek", {"api_key": "sk-mine"})["ok"] is True
    providers = {p["name"]: p for p in manager.get_providers()}
    assert providers["deepseek"]["source"] == "store"

    manager.remove_provider("deepseek")
    providers = {p["name"]: p for p in manager.get_providers()}
    assert providers["deepseek"]["configured"] is True  # server key still usable
    assert providers["deepseek"]["source"] == "env"


def test_default_secret_store_unchanges_for_desktop(tmp_path) -> None:
    # No injected store → the process-wide desktop default, unchanged behavior.
    manager = SessionManager(workspace=tmp_path)
    assert isinstance(manager.secrets, SecretStore)
