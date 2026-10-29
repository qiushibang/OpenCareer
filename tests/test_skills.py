"""Agents (Code/Chat) + SKILL.md loader (catalog + load_skill)."""

from __future__ import annotations

from pathlib import Path

from coworker.agent import build_engine
from coworker.agents import AgentContext, chat_agent, code_agent, get_agent
from coworker.providers import ModelCapabilities
from coworker.skills import SkillLoader, skill_catalog_text, skill_tools
from coworker.tools import ToolRegistry
from coworker.tools.shell import LocalExecutor
from coworker.tools.todo import TodoList


class _Stub:
    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()


# -- agents ---------------------------------------------------------------------


def test_code_agent_tools(tmp_path):
    ex = LocalExecutor(cwd=tmp_path, default_timeout=5)
    try:
        ctx = AgentContext(workspace=tmp_path, executor=ex, todo=TodoList())
        names = {getattr(t, "__name__", "?") for t in code_agent().build_tools(ctx)}
        assert {
            "read_file",
            "write_file",
            "git_status",
            "run_shell",
            "todo_write",
        } <= names
    finally:
        ex.close()


def test_chat_agent_has_no_workspace_tools():
    assert chat_agent().build_tools(AgentContext()) == []
    assert chat_agent().needs_workspace is False
    assert code_agent().needs_workspace is True


def test_get_agent_fallback():
    assert get_agent("chat").name == "chat"
    # Unknown ids fall back to the default persona (Cowork), per the persona registry.
    assert get_agent("nope").name == "cowork"


# -- SKILL.md loader ------------------------------------------------------------


def _make_skill(skills_dir, name, desc, body):
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n{body}", encoding="utf-8"
    )


def test_skill_loader_catalog_and_load(tmp_path):
    skills_dir = tmp_path / "skills"
    _make_skill(
        skills_dir, "pdf", "extract text from PDFs", "Use pdfplumber to extract text."
    )
    loader = SkillLoader([skills_dir])

    assert loader.catalog() == [
        {"name": "pdf", "description": "extract text from PDFs"}
    ]
    assert "pdf: extract text from PDFs" in skill_catalog_text(loader)

    reg = ToolRegistry()
    reg.register_all(skill_tools(loader))
    loaded = reg.execute("load_skill", {"name": "pdf"})
    assert "pdfplumber" in loaded["instructions"]
    assert reg.execute("load_skill", {"name": "missing"})["error"]


def test_workspace_career_skills_are_discoverable():
    root = Path(__file__).parents[1]
    loader = SkillLoader([root / ".coworker" / "skills"])

    assert loader.names() == [
        "career-catalog-query",
        "career-interview-evaluation",
        "career-interview-prep",
        "career-jd-analysis",
        "career-job-fit",
        "career-job-search",
        "career-resume-coach",
        "career-resume-import",
        "mock-interview",
    ]
    coach = loader.get("career-resume-coach").instructions
    for required in (
        "get_job",
        "get_confirmed_resume",
        "项目与实习证据",
        "基础能力覆盖",
        "JD 缺失项",
        "需要用户补充的真实事实",
        "保留",
        "删除",
        "补充",
        "重写",
        "加粗",
        "核心问题",
        "可能追问",
        "面试官验证的能力点",
        "JOB_NOT_FOUND",
        "RESUME_NOT_FOUND",
    ):
        assert required in coach
    for forbidden in (
        "match_job_to_profile",
        "prepare_tailored_resume",
        "submit_tailored_resume_proposals",
        "create_application_packet",
        "validate_application_packet",
        "include_sensitive=true",
        "DOCX",
        "PDF",
    ):
        assert forbidden not in coach
    assert coach.index("项目经历") < coach.index("实习与工作经历")
    assert coach.index("实习与工作经历") < coach.index("基础能力与技能")
    assert coach.index("基础能力与技能") < coach.index("教育经历")

    instructions = loader.get("career-job-search").instructions
    required = {
        "get_job_radar_digest",
        "list_sources",
        "search_jobs",
        "get_job",
        "list_recent_job_events",
        "source URL",
        "active",
        "pagination",
    }
    assert all(value in instructions for value in required)
    assert "mock data" not in instructions
    assert "do not fabricate" in instructions.lower()

    jd = loader.get("career-jd-analysis").instructions
    for required in (
        "preview_public_job_url",
        "confirmed=false",
        "preview_hash",
        "确认并开始面试",
        "取消",
        "ask_user",
    ):
        assert required in jd

    resume = loader.get("career-resume-import").instructions
    for required in (
        "get_resume_import_text",
        "preview_resume_import",
        "confirm_resume_sections",
        "get_candidate_profile",
        "explicit",
        "section",
        "masked",
    ):
        assert required in resume
    assert "Never ask the user to copy, paste, read, or provide an upload token" in resume
    assert "Import resume PDF/DOCX" in resume
    assert "never call `confirm_resume_sections`" in resume.lower()
    for required in (
        "待确认识别结果",
        "姓名",
        "联系方式",
        "数字",
        "日期",
        "公司",
        "学校",
    ):
        assert required in resume
    for required in (
        "`basic` must be an object",
        "`education`, `experience`, `project`, and `skill` must be lists",
        "`missing_fields`",
        "`warnings`",
    ):
        assert required in resume

    interview = loader.get("mock-interview").instructions
    interview_flat = " ".join(interview.split())
    for required in (
        "Ask exactly one question per turn.",
        "Previous Interview Turns",
        "FOLLOW_UP",
        "VERIFY_CLAIM",
        "DEEP_DIVE",
        "SWITCH_TOPIC",
        "WRAP_UP",
        "不得显示隐藏评分",
        "不得写回 Career Vault",
        "不得虚构",
        "Creation Workflow",
        "list_confirmed_resumes",
        "preview_hash",
        "确认并开始面试",
        "create_interview_session",
        "No InterviewSession ID",
        "ask_user",
        "STOP this turn",
        '"question":',
        '"topic":',
        "version 2 evaluation",
        "active dimensions",
        "0–100 score",
        "The question text must request only one `probe_dimension`.",
        "Before WRAP_UP, use at least one role-specific dimension",
        "行为面试",
        "产品场景题",
        "技术理解",
        "公司动机",
    ):
        assert required in interview
    assert "match_job_to_profile" not in interview
    assert "snapshot_id" not in interview
    assert (
        "Do not call `start_mock_interview` in the creation turn"
        in interview_flat
    )
    for required in (
        "Do not include setup statements before the question.",
        "Use exactly one sentence ending with exactly one question mark.",
        "Include the exact current job title",
        "If `evidence` is 4 or lower",
        "do not use `SWITCH_TOPIC`",
        "career-interview-evaluation` Skill is preloaded",
        "Do not call `load_skill`",
        "Retry `get_next_interview_question` at most once",
        "Do not call unrelated Career tools",
    ):
        assert required in interview_flat
    for required in (
        "evidence_cards",
        "role_tracks",
        "probe_plan",
        "highest-priority resume target",
        "probe_target",
        "probe_dimension",
        "depth_level",
        "model_choice",
        "implementation",
        "feature_design",
    ):
        assert required in interview
    assert "请简单介绍一下你自己。" not in interview

    evaluation = loader.get("career-interview-evaluation").instructions
    evaluation_flat = " ".join(evaluation.split())
    for required in (
        "get_interview_session",
        "question_type",
        "target_competency",
        "active_dimensions",
        "primary_pain",
        "missing_evidence",
        "0–4",
        "FOLLOW_UP",
        "VERIFY_CLAIM",
        "DEEP_DIVE",
        "SWITCH_TOPIC",
        "录用概率",
        "口音",
        "STAR",
        "样本",
        "基线",
        "口径",
        "个人贡献",
    ):
        assert required in evaluation
    assert "Do not invent metrics, responsibilities, results, or difficulties." in (
        evaluation_flat
    )
    assert (
        "Set `target_competency` to the current turn's `probe_dimension` "
        "exactly"
    ) in evaluation_flat
    assert "Never use `probe_target`" in evaluation_flat


# -- engine assembly per agent --------------------------------------------------


def test_build_engine_chat(tmp_path):
    engine = build_engine(agent=chat_agent(), provider=_Stub())
    assert "load_skill" in engine.registry.names()
    assert "read_file" not in engine.registry.names()
    assert engine.executor is None
    assert engine.agent_name == "chat"


def test_build_engine_code_has_agents_md_and_skills(tmp_path):
    (tmp_path / "AGENTS.md").write_text("PROJECT RULE: prefer pathlib.")
    engine = build_engine(agent=code_agent(), workspace=tmp_path, provider=_Stub())
    try:
        assert "prefer pathlib" in engine.messages[0]["content"]
        assert "todo_write" in engine.registry.names()
        assert "load_skill" in engine.registry.names()
        assert engine.agent_name == "code"
    finally:
        engine.executor.close()
