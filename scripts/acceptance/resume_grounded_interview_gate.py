"""Run isolated real-model mock interviews for algorithm, engineering, and product roles."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from coworker.agent import build_engine
from coworker.engine import ApprovalOutcome
from coworker.permissions import Mode
from coworker.personas.registry import PersonaRegistry
from coworker.providers import ProviderRouter
from coworker.secrets import SecretStore
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.domain.interviews import blueprint_refs
from extensions.career_mcp.domain.privacy import contains_sensitive_value
from extensions.career_mcp.services.interviews import (
    InterviewService,
    InterviewServiceError,
)
from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.services.resumes import ResumeService


FIXTURE_NAMES = (
    "interview_algorithm.json",
    "interview_engineering.json",
    "interview_product.json",
)

ANSWERS = {
    "algorithm": (
        "我负责推理服务的方案设计和核心实现。先用离线样本建立准确率基线，"
        "再实现动态批处理并分析显存峰值，最终把 P95 延迟降低约 25%。",
        "模型侧我比较了全量精度和量化方案，使用固定数据集做消融实验；我个人"
        "实现评测脚本，并用吞吐、延迟和任务准确率共同决定上线版本。",
        "训练和推理数据按业务场景分层抽样，我检查长尾样本和错误类别，发现主要"
        "问题来自超长输入，因此增加长度分桶和失败样本回归集。",
        "上线前我设计了准确率、吞吐量和 P95 延迟门禁，并用同一硬件环境重复"
        "三轮测试；结果未达门禁时自动阻止发布。",
        "如果重做，我会更早建立线上回放数据集，并把误差分析按场景自动聚类，"
        "减少人工排查时间。",
    ),
    "engineering": (
        "我负责会话并发控制和事务边界。写入时使用版本号做 CAS，所有状态变化"
        "放在同一事务内，避免两个入口同时提交导致覆盖。",
        "实现上我把 Service、Repository 和纯校验函数分开，Service 负责事务，"
        "Repository 只持久化；失败注入测试证明第二次写入失败会完整回滚。",
        "并发冲突返回稳定错误码，客户端刷新后再重试。我还验证了重复请求、旧版本"
        "写入和半完成 Turn，确保数据库不会留下不一致状态。",
        "可靠性方面我加入外键检查、唯一索引和原子发布，观察指标包括冲突率、失败率"
        "和请求延迟，异常时保留可追踪的会话版本。",
        "如果重新设计，我会补充更细的事务耗时和冲突来源指标，并对高频冲突增加"
        "指数退避，但不会放松版本校验。",
    ),
    "product": (
        "我负责定义求职 Agent 的核心流程和验收标准。先访谈用户确认岗位发现、"
        "匹配、材料生成和模拟面试四个关键任务，再按任务成功率排序迭代。",
        "功能设计上我把 JD、已确认简历和输出证据关联起来，用户能看到每项建议"
        "来自哪里；没有证据时明确提示缺口，不生成看似合理的经历。",
        "评测体系包含任务完成率、事实错误率、完成时长和关键步骤流失率。我负责"
        "定义样本和门禁，并用对抗样本检查虚构事实与隐私泄漏。",
        "一次测试中用户找不到模拟面试入口，我把入口前移到每个岗位列表和详情页，"
        "再观察启动成功率和首次提问耗时，确认流程明显缩短。",
        "如果继续迭代，我会按岗位类型拆分复盘质量指标，并访谈未完成用户，验证"
        "问题来自内容质量还是交互成本。",
    ),
}


async def _approve(_request) -> ApprovalOutcome:
    return ApprovalOutcome.ONCE


def _load_fixture(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"fixture must be an object: {path}")
    return value


def _seed(
    config: CareerConfig,
    fixture: dict,
) -> tuple[str, str]:
    requirements = fixture["job"]["requirements"]
    raw_jd = "\n".join(
        [
            f"职位：{fixture['job']['title']}",
            "公司：验收公司",
            "工作地点：北京",
            "岗位职责：",
            "1. 负责目标岗位核心工作",
            "任职要求：",
            *[
                f"{index}. {requirement}"
                for index, requirement in enumerate(requirements, start=1)
            ],
        ]
    )
    job_id = JobService(config).import_manual_jd(
        raw_text=raw_jd,
        source_url="https://careers.example.com/acceptance",
        company_name="验收公司",
        title=fixture["job"]["title"],
        confirmed=True,
    )["job_id"]

    sections = fixture["resume"]["sections"]
    proposal = {
        "basic": sections.get("basic", {}),
        "education": sections.get("education", []),
        "experience": sections.get("experience", []),
        "project": sections.get("project", []),
        "skill": sections.get("skill", []),
        "missing_fields": [],
        "warnings": [],
    }
    resume_service = ResumeService(
        config,
        private_root=config.data_dir / "private",
    )
    staged = resume_service.stage_resume(
        filename=f"{fixture['resume']['display_name']}.txt",
        mime="text/plain",
        text=json.dumps(proposal, ensure_ascii=False),
    )
    preview = resume_service.preview_resume_import(
        staged["upload_token"],
        proposal,
    )
    resume_service.confirm_resume_sections(
        preview["preview_token"],
        ["basic", "project", "skill"],
        corrections={},
    )
    documents = resume_service.list_resume_documents()
    if len(documents) != 1:
        raise RuntimeError(
            "isolated acceptance database must contain one resume"
        )
    resume_id = documents[0]["id"]
    return job_id, resume_id


def _tool(
    name: str,
    implementation: Callable,
) -> Callable:
    implementation.__name__ = name
    return implementation


def _interview_tools(service: InterviewService) -> list[Callable]:
    def invoke(operation: Callable[[], dict]) -> dict:
        try:
            return {"ok": True, "data": operation()}
        except InterviewServiceError as exc:
            return {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "violations": exc.violations,
                },
            }

    def get_session(session_id: str) -> dict:
        """Read one mock interview and all ordered turns."""
        return invoke(lambda: service.get(session_id))

    def start(
        session_id: str,
        expected_version: int,
        question: dict,
    ) -> dict:
        """Validate and save the first mock-interview question."""
        return invoke(
            lambda: service.start(
                session_id,
                expected_version=expected_version,
                question=question,
            )
        )

    def submit(
        session_id: str,
        turn_id: str,
        expected_version: int,
        answer_text: str,
    ) -> dict:
        """Save the candidate's exact answer to the current question."""
        return invoke(
            lambda: service.submit_answer(
                session_id,
                turn_id,
                expected_version=expected_version,
                answer_text=answer_text,
            )
        )

    def next_question(
        session_id: str,
        turn_id: str,
        expected_version: int,
        evaluation: dict,
        next_action: str,
        next_reason: str,
        next_question: dict | None = None,
        user_requested: bool = False,
    ) -> dict:
        """Save one hidden evaluation and atomically create the next question."""
        return invoke(
            lambda: service.evaluate_and_next(
                session_id,
                turn_id,
                expected_version=expected_version,
                evaluation=evaluation,
                next_action=next_action,
                next_reason=next_reason,
                next_question=next_question,
                user_requested=user_requested,
            )
        )

    def finish(
        session_id: str,
        expected_version: int,
        user_requested: bool = False,
    ) -> dict:
        """Finish a mock interview after its final answer was evaluated."""
        return invoke(
            lambda: service.finish(
                session_id,
                expected_version=expected_version,
                user_requested=user_requested,
            )
        )

    def report(session_id: str, expected_version: int) -> dict:
        """Generate the official transcript, report, and session artifacts."""
        return invoke(
            lambda: service.generate_report(
                session_id,
                expected_version=expected_version,
            )
        )

    return [
        _tool("get_interview_session", get_session),
        _tool("start_mock_interview", start),
        _tool("submit_interview_answer", submit),
        _tool("get_next_interview_question", next_question),
        _tool("finish_interview", finish),
        _tool("generate_interview_report", report),
    ]


async def _run_turn(engine, prompt: str) -> list[dict]:
    message_start = len(engine.messages)
    events = [event async for event in engine.run(prompt)]
    errors = [
        event.data
        for event in events
        if event.type.value in {"error", "interrupted"}
    ]
    if errors:
        raise RuntimeError(f"real model turn failed: {errors}")
    tools = [
        event.data
        for event in events
        if event.type.value == "tool_finished"
    ]
    failed = [item for item in tools if item.get("status") != "ok"]
    print(
        "[real-ai] tools="
        + ",".join(
            f"{item.get('name')}:{item.get('status')}"
            for item in tools
        ),
        flush=True,
    )
    if failed:
        tail = [
            str(message.get("content") or message.get("text") or "")[:500]
            for message in engine.messages[-8:]
            if message.get("role") in {"tool", "notice"}
        ]
        print(
            "[real-ai] failed-tool-context="
            + json.dumps(tail, ensure_ascii=False),
            flush=True,
        )
    rejected = []
    for message in engine.messages[message_start:]:
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        try:
            result = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and result.get("ok") is False:
            rejected.append(result.get("error"))
    if rejected:
        print(
            "[real-ai] business-rejections="
            + json.dumps(rejected, ensure_ascii=False),
            flush=True,
        )
    return tools


def _artifact_hashes(workspace: Path, session_id: str) -> dict[str, str]:
    directory = workspace / "artifacts" / "interviews" / session_id
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _privacy_content(session: dict) -> str:
    return json.dumps(
        {
            "company": session.get("company"),
            "position": session.get("position"),
            "blueprint": session.get("blueprint"),
            "turns": [
                {
                    field: turn.get(field)
                    for field in (
                        "question_text",
                        "answer_text",
                        "evaluation",
                        "next_reason",
                        "question_topic",
                    )
                }
                for turn in session.get("turns", [])
                if isinstance(turn, dict)
            ],
        },
        ensure_ascii=False,
    )


def _validate(
    fixture: dict,
    session: dict,
    workspace: Path,
) -> dict:
    turns = session["turns"]
    assert session["status"] == "completed"
    assert session["blueprint"]["version"] == 2
    assert session["blueprint"]["role_tracks"] == ["general"]
    assert len(turns) >= 5
    assert all(turn["answer_text"] and turn["evaluation"] for turn in turns)
    assert fixture["job"]["title"] in turns[0]["question_text"]
    first_target = turns[0]["probe_target"]
    assert turns[0]["depth_level"] == 1
    assert any(
        turn["probe_target"] == first_target
        and int(turn["depth_level"] or 0) >= 2
        for turn in turns
    )
    dimensions = {turn["probe_dimension"] for turn in turns}
    assert dimensions.intersection(fixture["required_dimensions"])
    allowed_refs = blueprint_refs(session["blueprint"])
    for turn in turns:
        assert turn["question_text"].count("?") + turn[
            "question_text"
        ].count("？") <= 1
        assert set(turn["question_refs"]) <= allowed_refs
    assert not contains_sensitive_value(_privacy_content(session))
    return {
        "session_id": session["id"],
        "role_tracks": session["blueprint"]["role_tracks"],
        "turn_count": len(turns),
        "first_question": turns[0]["question_text"],
        "depth_chain": [
            {
                "target": turn["probe_target"],
                "dimension": turn["probe_dimension"],
                "depth": turn["depth_level"],
            }
            for turn in turns
        ],
        "artifact_hashes": _artifact_hashes(workspace, session["id"]),
        "privacy_passed": True,
    }


async def _run_fixture(
    fixture_path: Path,
    *,
    model: str,
    workspace: Path,
    secrets: SecretStore,
) -> dict:
    fixture = _load_fixture(fixture_path)
    track = fixture["expected_tracks"][0]
    with tempfile.TemporaryDirectory(
        prefix=f"opencareer-{track}-"
    ) as directory:
        root = Path(directory)
        config = CareerConfig(data_dir=root / "career")
        job_id, resume_id = _seed(config, fixture)
        service = InterviewService(
            config,
            workspace=root / "workspace",
        )
        created = service.create(
            job_id,
            resume_id,
            conversation_id=f"acceptance-{track}",
            difficulty="standard",
            duration_minutes=15,
        )
        provider = ProviderRouter(secrets, default_provider="openai")
        engine = build_engine(
            agent=PersonaRegistry().agent("career"),
            workspace=workspace,
            model=model,
            mode=Mode.AUTO,
            approver=_approve,
            provider=provider,
            max_iterations=12,
            extra_tools=_interview_tools(service),
            secrets=secrets,
            session_id=f"acceptance-{track}",
        )
        try:
            await _run_turn(
                engine,
                "加载 mock-interview Skill。"
                f"开始这场模拟面试。interview_session_id={created['id']}。"
                "根据当前 JD、已确认简历和 Blueprint 提出并保存第一题。",
            )
            current = service.get(created["id"])
            if not current["turns"]:
                raise RuntimeError("real model did not create the first question")
            print(
                "[real-ai] first-question="
                + current["turns"][0]["question_text"],
                flush=True,
            )

            for index, answer in enumerate(ANSWERS[track], start=1):
                current = service.get(created["id"])
                turn = current["turns"][-1]
                if turn["answer_text"] is not None:
                    raise RuntimeError(
                        "expected one unanswered interview turn; "
                        f"status={current['status']}; "
                        f"phase={current['phase']}; "
                        f"turns={len(current['turns'])}; "
                        f"last_action={turn['next_action']}"
                    )
                suffix = (
                    "这是第五轮回答，请按流程结束面试并生成复盘报告。"
                    if index == 5
                    else "请根据回答继续本场面试。"
                )
                await _run_turn(
                    engine,
                    "提交模拟面试回答。"
                    f"interview_session_id={created['id']}；"
                    f"turn_id={turn['id']}。\n\n候选人回答：\n"
                    f"{answer}\n\n{suffix}",
                )
                saved = service.get(created["id"])
                print(
                    f"[real-ai] answer-{index}-saved "
                    f"status={saved['status']} phase={saved['phase']} "
                    f"turns={len(saved['turns'])}",
                    flush=True,
                )

            current = service.get(created["id"])
            if current["status"] != "completed":
                await _run_turn(
                    engine,
                    "结束模拟面试。"
                    f"interview_session_id={created['id']}。"
                    "完成当前评价并生成面试报告。",
                )
            return _validate(
                fixture,
                service.get(created["id"]),
                root / "workspace",
            )
        finally:
            if engine.executor is not None:
                engine.executor.close()


async def _main(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    fixture_dir = Path(args.fixture_dir).expanduser().resolve()
    secrets = SecretStore()
    results = []
    names = (args.fixture,) if args.fixture else FIXTURE_NAMES
    for name in names:
        print(f"[real-ai] running {name}", flush=True)
        result = await _run_fixture(
            fixture_dir / name,
            model=args.model,
            workspace=workspace,
            secrets=secrets,
        )
        results.append(result)
        print(
            f"[real-ai] passed {name}: "
            f"{result['turn_count']} turns",
            flush=True,
        )
    output = {
        "model": args.model,
        "results": results,
    }
    if args.output:
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument(
        "--fixture-dir",
        default=str(Path(__file__).parent / "fixtures"),
    )
    parser.add_argument("--fixture", choices=FIXTURE_NAMES)
    parser.add_argument("--output")
    return parser.parse_args()


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(asyncio.run(_main(parse_args())))
