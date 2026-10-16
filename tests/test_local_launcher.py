"""Public command-line contract for the isolated local distribution."""
from pathlib import Path
import os
import subprocess
import sys
import socket

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_local_model_clients_ignore_inherited_provider_endpoints(tmp_path, monkeypatch):
    from start_local import local_environment
    from coworker.providers.registry import build_provider_client
    from coworker.secrets import SecretStore

    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9999/capture")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9999/capture")
    monkeypatch.setenv("OPENAI_ORG_ID", "inherited-organization")
    env = local_environment(tmp_path, 1422, 8767)
    with monkeypatch.context() as isolated:
        for name in list(os.environ):
            isolated.delenv(name)
        for name, value in env.items():
            isolated.setenv(name, value)
        secrets = SecretStore(tmp_path / "secrets.json")
        secrets.put("provider:openai", {"api_key": "local-fixture-not-a-real-key"})
        captured = []

        def reject_request(_client, request, **kwargs):
            captured.append(str(request.url))
            # Mock only the external HTTP boundary, before any real network call.
            return httpx.Response(401, json={"error": {"message": "fixture", "type": "authentication_error"}}, request=request)

        isolated.setattr(httpx.Client, "send", reject_request)
        for name, expected in (("openai", "https://api.openai.com/v1/responses"),
                               ("anthropic", "https://api.anthropic.com/v1/messages")):
            provider = build_provider_client(name, {"api_key": "local-fixture-not-a-real-key"}, secrets)
            with pytest.raises(Exception, match="fixture"):
                provider.complete(model="fixture-model", messages=[{"role": "user", "content": "fixture"}])
            assert captured[-1] == expected
        assert "OPENAI_ORG_ID" not in os.environ


def test_local_launcher_explains_setup_without_touching_a_server():
    result = subprocess.run(
        [sys.executable, str(ROOT / "start_local.py"), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "--data-dir" in result.stdout
    assert "--no-browser" in result.stdout
    assert "--host" not in result.stdout


def test_local_launcher_refuses_an_occupied_port_without_stopping_its_owner(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run(
            [sys.executable, str(ROOT / "start_local.py"), "--port", str(port),
             "--data-dir", str(tmp_path / "unused"), "--no-browser", "--skip-install"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "already in use" in result.stderr
        assert not (tmp_path / "unused").exists()
        assert listener.fileno() >= 0
