"""Phase 1 gate — built-in personas resolve to the same toolsets as the legacy agents.

The equivalence net: routing Code/Cowork through the persona registry must yield the exact
same tools the agent builders produce, and Ops (a markdown persona) must compose the knowledge
toolset. Ties back to the Phase 0 catalog equivalence."""

from __future__ import annotations

from pathlib import Path

from coworker.agents.base import AgentContext
from coworker.agents.code import code_agent
from coworker.agents.cowork import cowork_agent
from coworker.personas.registry import PersonaRegistry
from coworker.tools.todo import TodoList


def _ctx(tmp_path) -> AgentContext:
    return AgentContext(workspace=tmp_path, executor=object(), todo=TodoList())


def _names(agent, ctx) -> set:
    return {getattr(t, "__name__", "") for t in agent.build_tools(ctx)}


def test_code_persona_matches_builder(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    assert _names(reg.agent("code"), ctx) == _names(code_agent(), ctx)
    assert reg.agent("code").family == "code"


def test_cowork_persona_matches_builder(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    assert _names(reg.agent("cowork"), ctx) == _names(cowork_agent(), ctx)
    a = reg.agent("cowork")
    assert a.messaging and a.connectors


def test_ops_persona_composes_knowledge_toolset(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    # Ops uses the same capability list as Cowork (files/search/shell/todo).
    assert _names(reg.agent("ops"), ctx) == _names(cowork_agent(), ctx)
    a = reg.agent("ops")
    assert a.family == "knowledge" and a.messaging and a.connectors
    assert "read_file_lines" in _names(a, ctx)  # multi-root knowledge files


def test_career_persona_requires_a_project_workspace(tmp_path):
    reg = PersonaRegistry()
    ctx = _ctx(tmp_path)
    entry = reg.get("career")
    assert entry is not None
    assert _names(reg.agent("career"), ctx) == _names(cowork_agent(), ctx)
    assert entry.family == "code" and entry.tools == [
        "files",
        "search",
        "shell",
        "todo",
    ]
    assert entry.manifest is not None
    assert entry.manifest.messaging is False and entry.manifest.connectors is True
    assert entry.manifest.recommends[0].ref == "career"
    assert "read_file_lines" in _names(reg.agent("career"), ctx)


def test_career_persona_sets_durable_interview_boundaries():
    root = Path(__file__).resolve().parents[1]
    prompt = (
        root / "coworker" / "personas" / "builtin" / "career.md"
    ).read_text(encoding="utf-8")

    assert "current saved JD" in prompt
    assert "confirmed resume evidence" in prompt
    assert "Ask one main question at a time" in prompt
    assert "do not coach during the interview" in prompt
    assert "never treat interview answers as confirmed" in prompt


def test_code_keeps_single_root_file_tools(tmp_path):
    reg = PersonaRegistry()
    names = _names(reg.agent("code"), _ctx(tmp_path))
    assert "read_file" in names and "read_file_lines" not in names
    assert "git_log" in names  # code has git; cowork/ops do not
