"""Public command-line contract for the isolated local distribution."""
from pathlib import Path
import os
import importlib
import subprocess
import sys
import socket
from argparse import Namespace

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_generated_mcp_runs_this_checkout_and_only_migrates_exact_legacy_config(tmp_path):
    import json
    from start_local import prepare_workspace
    prepare_workspace(tmp_path / "user", Path(sys.executable))
    path = tmp_path / "user" / "workspace" / ".coworker" / "mcp.json"
    config = json.loads(path.read_text())
    server = config["mcpServers"]["career"]
    assert Path(server["cwd"]).resolve() == ROOT
    server.pop("cwd")
    path.write_text(json.dumps(config))
    prepare_workspace(tmp_path / "user", Path(sys.executable))
    assert json.loads(path.read_text())["mcpServers"]["career"]["cwd"] == str(ROOT)
    config["mcpServers"]["career"]["args"] = ["unapproved-command"]
    path.write_text(json.dumps(config))
    with pytest.raises(RuntimeError, match="MCP 配置已被修改"):
        prepare_workspace(tmp_path / "user", Path(sys.executable))


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

        def block_network(*args, **kwargs):
            raise AssertionError("Unexpected network access: transport must be intercepted")

        isolated.setattr(socket, "getaddrinfo", block_network)
        isolated.setattr(socket.socket, "connect", block_network)
        # Newer provider SDKs use httpx2; support both without allowing a real request.
        transports = [httpx]
        try:
            transports.append(importlib.import_module("httpx2"))
        except ImportError:
            pass
        for transport in transports:
            def reject_request(_client, request, response_type=transport.Response, **kwargs):
                captured.append(str(request.url))
                return response_type(401, json={"error": {"message": "fixture", "type": "authentication_error"}}, request=request)

            isolated.setattr(transport.Client, "send", reject_request)
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


@pytest.mark.parametrize("disabled", [False, True])
def test_launcher_owns_and_stops_its_background_job_worker(tmp_path, monkeypatch, disabled):
    import start_local
    commands, stopped = [], []
    class Child:
        def __init__(self, command, **kwargs):
            self.command = command
            commands.append(command)
        def poll(self):
            return None
    monkeypatch.setattr(start_local.shutil, "which", lambda _: "/fixture/node")
    monkeypatch.setattr(start_local, "prepare_workspace", lambda *args: None)
    monkeypatch.setattr(start_local.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_local.subprocess, "Popen", Child)
    monkeypatch.setattr(start_local, "wait_ready", lambda *args: None)
    monkeypatch.setattr(start_local, "stop_process", lambda child: stopped.append(child.command))
    def interrupt(_seconds):
        raise KeyboardInterrupt
    monkeypatch.setattr(start_local.time, "sleep", interrupt)
    args = Namespace(data_dir=tmp_path, port=1422, backend_port=8767, skip_install=True,
                     no_browser=True, no_job_sync=disabled)
    with pytest.raises(KeyboardInterrupt):
        start_local.run_local(args)
    workers = [c for c in commands if "extensions.career_mcp.local_jobs" in c]
    assert len(workers) == (0 if disabled else 1)
    assert len(stopped) == len(commands)
    if workers:
        assert stopped[0] == workers[0]
