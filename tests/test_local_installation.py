"""Opt-in real-process acceptance. Never uses real credentials or production URLs.

Run OPENCAR_TEST_LOCAL_INSTALL=1 python -m pytest tests/test_local_installation.py -q.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.environ.get("OPENCAR_TEST_LOCAL_INSTALL") != "1", reason="opt-in real localhost installation"
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(url: str, body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        response = build_opener(ProxyHandler({})).open(req, timeout=3)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read().decode()


@contextmanager
def running(tmp_path: Path, port: int, backend_port: int, *, root: Path = ROOT,
            install: bool = False, python: str = sys.executable, job_source: str = "shared"):
    log_path = tmp_path / "launcher.log"
    with log_path.open("w") as log:
        # Deliberately hostile inherited settings: launcher must isolate all of them.
        env = {**os.environ, "DATABASE_URL": "postgresql://invalid.invalid/unreachable",
               "REDIS_URL": "redis://invalid.invalid", "OPENCAR_AUTH_ISSUER": "https://invalid.invalid",
               "OPENCAR_USER_TOKENS": "wrong:inherited", "COWORKER_API_TOKEN": "inherited-do-not-use"}
        process = subprocess.Popen(
            [python, str(root / "start_local.py"), *([] if install else ["--skip-install"]), "--no-browser", "--no-job-sync",
             "--port", str(port), "--backend-port", str(backend_port),
             "--job-source", job_source,
             "--data-dir", str(tmp_path / "data")], stdout=log, stderr=log, env=env,
        )
        try:
            deadline = time.monotonic() + (240 if install else 120)
            while time.monotonic() < deadline:
                assert process.poll() is None, log_path.read_text()
                try:
                    code, health = request(f"http://127.0.0.1:{port}/_openworker/v1/health")
                    if code == 200 and json.loads(health).get("model"):
                        break
                except (URLError, OSError, ValueError):
                    pass
                time.sleep(0.2)
            else:
                pytest.fail("Local startup timed out: " + log_path.read_text())
            yield
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def test_local_installation_is_isolated_guarded_and_persistent(tmp_path):
    from websockets.sync.client import connect
    from websockets.exceptions import InvalidStatus

    port, backend_port = free_port(), free_port()
    base = f"http://127.0.0.1:{port}"
    api = base + "/_openworker"
    with running(tmp_path, port, backend_port):
        assert request(base)[0] == 200
        assert json.loads(request(api + "/v1/auth/session")[1])["configured"] is False
        assert request(f"http://127.0.0.1:{backend_port}/v1/providers")[0] == 401
        assert request(f"http://127.0.0.1:{backend_port}/v1/career/jobs/sync")[0] == 401
        assert request(api + "/v1/career/jobs/sync", {}, headers={"Origin": "https://evil.example"})[0] == 403
        assert request(api + "/v1/providers", headers={"Origin": "https://evil.example"})[0] == 403
        assert request(api + "/v1/providers", headers={"Host": f"evil.example:{port}"})[0] == 403
        assert request(api + "/v1/providers", headers={"Origin": "null"})[0] == 403
        assert request(api + "/v1/settings")[0] == 403  # desktop-only surface stays unavailable
        code, body = request(api + "/v1/providers", {"name": "deepseek", "fields": {"api_key": "local-fixture-not-a-real-key"}})
        assert code == 200 and json.loads(body)["ok"] is True
        with connect(f"ws://127.0.0.1:{port}/_openworker/ws/events", origin=base, subprotocols=["openworker"], open_timeout=10) as ws:
            assert ws.subprotocol == "openworker"
        with pytest.raises(InvalidStatus):
            connect(f"ws://127.0.0.1:{port}/_openworker/ws/events", origin="https://evil.example", subprotocols=["openworker"], open_timeout=10)
    with running(tmp_path, port, backend_port):
        code, providers = request(api + "/v1/providers")
        assert code == 200
        assert "local-fixture-not-a-real-key" not in providers
        entries = json.loads(providers)
        assert next(p for p in entries if p["name"] == "deepseek")["configured"] is True
