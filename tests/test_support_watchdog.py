"""Operator CLI fault simulation at external HTTP/system boundaries."""
import json
import pytest
from types import SimpleNamespace
from urllib.error import URLError
from extensions.support.watchdog import main


def test_watchdog_reports_fixed_categories_without_private_exception_text(tmp_path, monkeypatch, capsys):
    def offline(*args, **kwargs):
        raise URLError("api_key=fictional-private-watchdog-secret")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", offline)
    monkeypatch.setattr("shutil.disk_usage", lambda path: SimpleNamespace(total=100, free=5))
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='{"restart_count":2,"started_at":"new-fixture"}'))
    memory = tmp_path / "meminfo"
    memory.write_text("MemTotal: 100 kB\nMemAvailable: 5 kB\n")
    state = tmp_path / "state.json"
    state.write_text('{"restart_count":1,"started_at":"old-fixture"}')
    result = main(["--dry-run", "--state-file", str(state)], environ={
        "OPENCAR_WATCHDOG_MEMINFO_PATH": str(memory), "OPENCAR_WATCHDOG_DISK_PATH": str(tmp_path),
        "OPENCAR_WATCHDOG_CONTAINER": "fixture-backend",
    })
    assert result == 0
    output = capsys.readouterr().out
    assert "fictional-private-watchdog-secret" not in output
    assert json.loads(output)["observed"] == {"health_down": 1, "unexpected_restart": 1, "disk_pressure": 95, "memory_pressure": 95}
    assert state.read_text() == '{"restart_count":1,"started_at":"old-fixture"}'

@pytest.mark.parametrize("target", ["http://[broken/v1/health", "http://localhost:broken/v1/health", "http://localhost:99999/v1/health"])
def test_invalid_health_target_is_rejected_without_exception_or_network(tmp_path, capsys, target):
    assert main(["--dry-run", "--state-file", str(tmp_path / "state.json")], environ={"OPENCAR_WATCHDOG_HEALTH_URL": target}) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "invalid_watchdog_health_target"}
