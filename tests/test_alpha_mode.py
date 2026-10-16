from __future__ import annotations

import aisuite as ai
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server import alpha


def test_alpha_mode_hides_local_controls_and_other_personas(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    manager = SessionManager(workspace=tmp_path)
    manager.personas.set_enabled("career", True)
    client = TestClient(create_app(manager))

    assert [agent["name"] for agent in client.get("/v1/agents").json()["agents"]] == [
        "career"
    ]
    assert client.get("/v1/settings").status_code == 403
    assert client.post(
        "/v1/workspaces/trust", json={"path": str(tmp_path), "trusted": True}
    ).status_code == 403
    assert client.post("/v1/personas/install", json={}).status_code == 403


def test_normal_mode_keeps_local_controls_available(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCAR_ALPHA_TEST", raising=False)
    manager = SessionManager(workspace=tmp_path)
    client = TestClient(create_app(manager))

    assert client.get("/v1/settings").status_code == 200


def test_alpha_allows_only_career_job_input_tools() -> None:
    tools = alpha.conversation_tools()

    assert "mcp__career__preview_public_job_url" not in tools
    assert "mcp__career__import_manual_jd" in tools
    assert "mcp__career__get_confirmed_resume" in tools
    assert "web_fetch" not in tools


def test_alpha_session_keeps_only_product_career_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_ALPHA_WORKSPACE", str(tmp_path))
    manager = SessionManager(workspace=tmp_path)
    manager.personas.set_enabled("career", True)

    def career_tool():
        return {}

    career_tool.__name__ = "mcp__career__get_resume_import_text"
    career_tool = ai.tool(career_tool)

    def unknown_mcp_tool():
        return {}

    unknown_mcp_tool.__name__ = "mcp__other__read_data"
    unknown_mcp_tool = ai.tool(unknown_mcp_tool)

    async def prepare_tools(*_args, **_kwargs):
        return [career_tool, unknown_mcp_tool]

    monkeypatch.setattr(manager, "prepare_mcp_tools", prepare_tools)
    client = TestClient(create_app(manager))

    with client.websocket_connect(
        f"/ws/session/alpha-tools?agent=career&workspace={tmp_path}"
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        names = set(manager._engines["alpha-tools"].registry.names())

    assert "load_skill" in names
    assert "mcp__career__get_resume_import_text" in names
    assert "mcp__other__read_data" not in names
    assert "shell" not in names
    assert "save_skill" not in names
