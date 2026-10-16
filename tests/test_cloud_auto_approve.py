"""Cloud approval relaxation: the alpha auto-allow whitelist and its boundaries.

模拟面试 / AI 分析 previously prompted an approval card for every career MCP
call because the MCP bridge defaults every tool to EXTERNAL risk. The cloud
alpha now runs sessions in Mode.CUSTOM with an explicit read-only whitelist
(alpha.AUTO_APPROVE_TOOLS). Write tools keep asking, and the agent surface
still contains no shell / file-write / delete tools.
"""

from pathlib import Path
from types import SimpleNamespace

import aisuite as ai

from fastapi.testclient import TestClient

from coworker.permissions import Mode, PermissionEngine
from coworker.server import SessionManager, create_app
from coworker.server import alpha
from coworker.sessions import SessionRecord
from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient, ToolCall


def test_auto_approve_whitelist_stays_inside_the_alpha_surface() -> None:
    assert alpha.AUTO_APPROVE_TOOLS <= alpha.conversation_tools()

    # The persisted-data writes keep their approval card.
    for writer in (
        "mcp__career__import_manual_jd",
        "mcp__career__confirm_resume_sections",
        "mcp__career__update_job_tracking",
    ):
        assert writer not in alpha.AUTO_APPROVE_TOOLS


def test_auto_approve_whitelist_never_includes_destructive_tools() -> None:
    # The agent on the server must structurally be unable to run shell, write
    # arbitrary files, or delete anything: none of those exist on the surface,
    # and none may ever enter the auto-allow set.
    for dangerous in (
        "run_shell",
        "write_file",
        "replace_in_file",
        "apply_patch",
        "delete_file",
        "remove_path",
    ):
        assert dangerous not in alpha.conversation_tools()
        assert dangerous not in alpha.AUTO_APPROVE_TOOLS


def _custom_engine() -> PermissionEngine:
    return PermissionEngine(
        workspace_root=Path("/tmp/alpha-ws"),
        mode=Mode.CUSTOM,
        auto_allow_tools=set(alpha.AUTO_APPROVE_TOOLS),
    )


def test_custom_mode_auto_approves_whitelisted_reads() -> None:
    engine = _custom_engine()
    for tool in (
        "mcp__career__get_job",
        "mcp__career__get_confirmed_resume",
        "mcp__career__get_next_interview_question",
        "load_skill",
    ):
        decision = engine.evaluate(
            tool, {}, SimpleNamespace(requires_approval=True, category="mcp")
        )
        assert decision.allowed, (tool, decision.reason)
        assert not decision.needs_user


def test_custom_mode_still_asks_for_writes() -> None:
    engine = _custom_engine()
    # Real MCP bridge metadata: requires_approval defaults to True (mcp.json),
    # which classifies the call EXTERNAL — exactly what production sees.
    metadata = SimpleNamespace(requires_approval=True, category="mcp")
    for writer in (
        "mcp__career__import_manual_jd",
        "mcp__career__confirm_resume_sections",
        "mcp__career__update_job_tracking",
    ):
        decision = engine.evaluate(writer, {}, metadata)
        assert not decision.allowed
        assert decision.needs_user


def test_configure_alpha_puts_cloud_managers_in_custom_mode(
    tmp_path, monkeypatch
) -> None:
    """configure_alpha switches the cloud SessionManager to CUSTOM with the
    whitelist, so mock interview / AI analysis run without approval cards."""
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_ALPHA_WORKSPACE", str(tmp_path / "alpha-workspace"))
    workspace = tmp_path / "alpha-workspace"
    workspace.mkdir()

    from coworker.server import run as server_run

    app = server_run.build_app(str(workspace), "test:model", "interactive")
    manager = app.state.manager
    assert manager.mode is Mode.CUSTOM
    assert manager.auto_allow_tools == set(alpha.AUTO_APPROVE_TOOLS)

    client = TestClient(app)
    assert client.get("/v1/health").status_code == 200


def test_alpha_ws_reseeds_auto_allow_after_the_clear(tmp_path, monkeypatch):
    """The alpha WS handler clears engine allowlists after get_engine; the BYOK
    whitelist must be re-seeded AFTER that clear or every career call prompts."""
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_ALPHA_WORKSPACE", str(tmp_path / "alpha-workspace"))
    workspace = tmp_path / "alpha-workspace"
    workspace.mkdir()

    from coworker.server import run as server_run

    app = server_run.build_app(str(workspace), "test:model", "interactive")
    manager = app.state.manager

    engine = manager.get_engine("ws-check", agent="career")
    # 模拟 WS 处理器的既有顺序：先收紧，再回种。
    engine.registry.retain(alpha.conversation_tools())
    engine.permissions.auto_allow_tools.clear()
    engine.permissions.auto_allow_tools.update(
        alpha.AUTO_APPROVE_TOOLS & alpha.conversation_tools()
    )

    mcp_meta = SimpleNamespace(requires_approval=True, category="mcp")
    decision = engine.permissions.evaluate("mcp__career__search_jobs", {}, mcp_meta)
    assert decision.allowed and not decision.needs_user
    writer = engine.permissions.evaluate(
        "mcp__career__confirm_resume_sections", {}, mcp_meta
    )
    assert not writer.allowed and writer.needs_user


def test_alpha_ws_restored_interview_defaults_to_safe_auto_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_ALPHA_WORKSPACE", str(tmp_path))
    manager = SessionManager(workspace=tmp_path)
    manager.personas.set_enabled("career", True)
    manager.session_store.save(SessionRecord(
        session_id="existing-interview", workspace=str(tmp_path),
        model="test:model", mode="interactive", agent="career",
    ))
    metadata = SimpleNamespace(requires_approval=True, category="mcp")
    with TestClient(create_app(manager)).websocket_connect(
        f"/ws/session/existing-interview?agent=career&workspace={tmp_path}"
    ) as ws:
        ready = ws.receive_json()
        assert ready["data"]["mode"] == "custom"
        permissions = manager._engines["existing-interview"].permissions
        for name in alpha.AUTO_APPROVE_TOOLS:
            decision = permissions.evaluate(name, {}, metadata)
            assert decision.allowed and not decision.needs_user, name
        decision = permissions.evaluate("mcp__career__confirm_resume_sections", {}, metadata)
        assert not decision.allowed and decision.needs_user


def test_alpha_actual_interview_tool_call_and_legacy_auto_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_ALPHA_WORKSPACE", str(tmp_path))
    name = "mcp__career__get_interview_session"
    calls = []

    def interview_tool(session_id: str) -> dict:
        calls.append(session_id)
        return {"id": session_id}

    interview_tool.__name__ = name
    tool = ai.tool(interview_tool)
    tool.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name=name, category="mcp", risk_level="medium", requires_approval=True,
    )

    class Provider(ProviderClient):
        def __init__(self):
            self.turns = [
                AssistantTurn(tool_calls=[ToolCall(
                    id="call-1", name=name, arguments={"session_id": "interview-1"},
                )]),
                AssistantTurn(text="done", finish_reason="stop"),
                AssistantTurn(text="mode synchronized", finish_reason="stop"),
                AssistantTurn(text="legacy mode synchronized", finish_reason="stop"),
            ]

        def complete(self, **kwargs):
            return self.turns.pop(0)

        def capabilities(self, model):
            return ModelCapabilities()

    manager = SessionManager(workspace=tmp_path, provider=Provider())
    manager.personas.set_enabled("career", True)

    async def prepare_tools(*args, **kwargs):
        return [tool]

    monkeypatch.setattr(manager, "prepare_mcp_tools", prepare_tools)
    metadata = SimpleNamespace(requires_approval=True, category="mcp")
    with TestClient(create_app(manager)).websocket_connect(
        f"/ws/session/approval-flow?agent=career&workspace={tmp_path}"
    ) as ws:
        assert ws.receive_json()["data"]["mode"] == "custom"
        ws.send_json({"type": "user_message", "text": "start interview"})
        events = []
        while True:
            kind = ws.receive_json()["type"]
            # Fail immediately instead of hanging on an unexpected approval.
            assert kind != "permission_required"
            events.append(kind)
            if kind == "turn_done":
                break
        assert "tool_finished" in events
        assert calls == ["interview-1"]
        permissions = manager._engines["approval-flow"].permissions
        for mode, expected in (("interactive", Mode.INTERACTIVE), ("auto", Mode.CUSTOM)):
            ws.send_json({"type": "set_mode", "mode": mode})
            ws.send_json({"type": "user_message", "text": "check mode"})
            while ws.receive_json()["type"] != "turn_done":
                pass
            assert permissions.mode is expected
            if expected is Mode.INTERACTIVE:
                assert permissions.evaluate(name, {}, metadata).needs_user
            decision = permissions.evaluate("mcp__career__confirm_resume_sections", {}, metadata)
            assert decision.needs_user and not decision.allowed
        assert permissions.evaluate(name, {}, metadata).allowed
