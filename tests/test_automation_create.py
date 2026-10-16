"""Tests for the GUI-driven `create_automation` path (the "New automation" / template flow).

No network and no LLM: this exercises validation + that a valid create lands in the task store
with a freshly provisioned scratch workspace.
"""

from __future__ import annotations

from pathlib import Path

from coworker.server.manager import SessionManager


def _manager(tmp_path, monkeypatch) -> SessionManager:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(data_dir=tmp_path / "data")
    manager.set_scratch_base(str(tmp_path / "scratch"))
    return manager


def test_create_automation_success(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    out = manager.create_automation(
        {
            "title": "Morning news briefing",
            "instructions": "Search the web and write a 5-bullet briefing.",
            "cron": "0 8 * * *",
        }
    )
    assert out["ok"] is True
    task = out["task"]
    assert task["title"] == "Morning news briefing"
    assert task["schedule"] == "Every day at ~8:00 AM"
    # it really landed in the store and is bound to a fresh scratch workspace
    saved = manager.task_store.get(task["id"])
    assert saved is not None
    assert saved.agent == "cowork"
    assert Path(saved.workspace).is_dir()


def test_create_automation_invalid_cron(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    out = manager.create_automation(
        {
            "title": "Bad",
            "instructions": "do something",
            "cron": "not-a-cron",
        }
    )
    assert out["ok"] is False
    assert "invalid cron" in out["error"]
    assert manager.task_store.list() == []


def test_create_automation_missing_instructions(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    out = manager.create_automation(
        {
            "title": "No instructions",
            "instructions": "  ",
            "cron": "0 8 * * *",
        }
    )
    assert out["ok"] is False
    assert "instructions" in out["error"]
    assert manager.task_store.list() == []


def test_create_automation_requires_schedule(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    out = manager.create_automation(
        {"title": "No schedule", "instructions": "do something"}
    )
    assert out["ok"] is False
    assert manager.task_store.list() == []


def test_create_automation_can_bind_trusted_workspace_and_agent(
    tmp_path,
    monkeypatch,
):
    manager = _manager(tmp_path, monkeypatch)
    workspace = tmp_path / "career"
    workspace.mkdir()
    manager.workspace_trust.set_trusted(workspace, True)

    out = manager.create_automation(
        {
            "title": "Career radar",
            "instructions": "Run the next Career source.",
            "cron": "0 * * * *",
            "workspace": str(workspace),
            "agent": "career",
        }
    )

    assert out["ok"] is True
    saved = manager.task_store.get(out["task"]["id"])
    assert saved.workspace == str(workspace.resolve())
    assert saved.agent == "career"


def test_create_automation_rejects_untrusted_workspace(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    workspace = tmp_path / "untrusted"
    workspace.mkdir()

    out = manager.create_automation(
        {
            "title": "Career radar",
            "instructions": "Run the next Career source.",
            "cron": "0 * * * *",
            "workspace": str(workspace),
            "agent": "career",
        }
    )

    assert out == {"ok": False, "error": "workspace must be trusted"}
    assert manager.task_store.list() == []
