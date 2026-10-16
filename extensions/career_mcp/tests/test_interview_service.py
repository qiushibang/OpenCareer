import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.interview_repository import (
    InterviewRepository,
)
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.services.interviews import (
    InterviewService,
    InterviewServiceError,
)
from extensions.career_mcp.services.resumes import ResumeService


NOW = datetime(2026, 8, 10, 16, 0, tzinfo=timezone.utc)
JD = """职位：大模型算法工程师
公司：DeepSeek
岗位职责：
1. 负责大模型训练与评测
任职要求：
1. 熟悉 Python
"""
PROPOSAL = {
    "basic": {"name": "Zhang San", "summary": "AI 工程师"},
    "education": [],
    "experience": [],
    "project": [
        {
            "name": "知识库",
            "highlights": ["使用 Python 构建 RAG 服务"],
        }
    ],
    "skill": [{"name": "Python", "level": None, "evidence": None}],
    "missing_fields": [],
    "warnings": [],
}


def _seed(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    jobs = JobService(config)
    values = {
        "raw_text": JD,
        "source_url": "https://careers.deepseek.com/jobs/one",
        "company_name": "DeepSeek",
        "title": "大模型算法工程师",
    }
    preview = jobs.import_manual_jd(**values, confirmed=False)
    job_id = jobs.import_manual_jd(
        **values,
        preview_hash=preview["preview_hash"],
        confirmed=True,
    )["job_id"]
    resumes = ResumeService(
        config,
        private_root=tmp_path / "private",
        clock=lambda: NOW,
    )
    staged = resumes.stage_resume(
        filename="算法简历.txt",
        mime="text/plain",
        text="Zhang San Python RAG project experience",
    )
    resume_preview = resumes.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    resumes.confirm_resume_sections(
        resume_preview["preview_token"],
        ["basic", "project", "skill"],
        corrections={},
    )
    resume_id = resumes.list_resume_documents()[0]["id"]
    resumes.update_resume_document(
        resume_id,
        display_name="算法简历",
        target_roles=["大模型算法工程师"],
    )
    return config, resumes, None, job_id, resume_id


def test_service_creates_session_without_match_snapshot(tmp_path):
    config, _, _, job_id, resume_id = _seed(tmp_path)
    service = InterviewService(
        config,
        workspace=tmp_path / "workspace",
        clock=lambda: NOW,
    )

    created = service.create(
        job_id,
        resume_id,
        conversation_id="career-session-direct",
        difficulty="standard",
        duration_minutes=15,
    )

    assert created["status"] == "ready"
    assert created["blueprint"]["position"] == "大模型算法工程师"
    assert "snapshot_id" not in created
    assert "snapshot_id" not in str(created["blueprint"])


def _service(tmp_path):
    config, resume_service, match_service, job_id, resume_id = _seed(
        tmp_path
    )
    workspace = tmp_path / "workspace"
    service = InterviewService(
        config,
        workspace=workspace,
        clock=lambda: NOW,
    )
    return (
        service,
        workspace,
        resume_service,
        match_service,
        job_id,
        resume_id,
        None,
    )


def _create(service, job_id, resume_id, snapshot_id):
    del snapshot_id
    return service.create(
        job_id,
        resume_id,
        conversation_id="career-session-1",
        difficulty="standard",
        duration_minutes=15,
    )


def _evaluation(
    ref: str,
    turn: dict,
    action: str = "FOLLOW_UP",
) -> dict:
    quote = turn["answer_text"]
    return {
        "version": 2,
        "question_type": "past_behavior",
        "target_competency": turn["probe_dimension"],
        "active_dimensions": [
            {
                "name": name,
                "level": 4,
                "evidence": [quote],
                "missing_evidence": "",
            }
            for name in ("relevance", "specificity", "ownership", "outcome")
        ],
        "primary_pain": "需要继续验证",
        "reason": "回答已有证据，但仍需完成本轮训练。",
        "improvement": "继续说明关键决策和验证方式。",
        "fact_refs": [ref],
        "recommended_action": action,
    }


def _first_ref(session: dict) -> str:
    return session["blueprint"]["evidence_cards"][0]["fact_path"]


def _target(session: dict, target_id: str) -> dict:
    return next(
        item
        for item in session["blueprint"]["probe_plan"]
        if item["target_id"] == target_id
    )


def _start_question(session):
    target = session["blueprint"]["probe_plan"][0]
    evidence_ref = next(
        ref for ref in target["refs"] if not ref.startswith("requirement-")
    )
    return {
        "question": (
            f"你正在应聘{session['position']}，请结合简历中的相关"
            "项目介绍你的个人职责？"
        ),
        "refs": [evidence_ref],
        "topic": "个人职责",
        "probe_target": target["target_id"],
        "probe_dimension": "personal_contribution",
        "depth_level": 1,
    }


def _start(service, session):
    return service.start(
        session["id"],
        expected_version=session["version"],
        question=_start_question(session),
    )


def _follow_up_question(
    session: dict,
    *,
    question: str,
) -> dict:
    current = session["turns"][-1]
    target = _target(session, current["probe_target"])
    next_depth = int(current["depth_level"]) + 1
    return {
        "question": question,
        "refs": current["question_refs"],
        "topic": "项目深挖",
        "probe_target": current["probe_target"],
        "probe_dimension": target["dimensions"][next_depth - 1],
        "depth_level": next_depth,
    }


def _switch_question(
    session: dict,
    *,
    question: str,
) -> dict:
    current_target = session["turns"][-1]["probe_target"]
    target = next(
        item
        for item in session["blueprint"]["probe_plan"]
        if item["target_id"] != current_target
    )
    return {
        "question": question,
        "refs": [target["refs"][0]],
        "topic": "岗位能力",
        "probe_target": target["target_id"],
        "probe_dimension": target["dimensions"][0],
        "depth_level": 1,
    }


def test_service_creates_ready_session_without_match_snapshot(tmp_path):
    config, _, _, job_id, resume_id = _seed(tmp_path)
    service = InterviewService(
        config,
        workspace=tmp_path / "workspace",
        clock=lambda: NOW,
    )

    assert "snapshot_id" not in inspect.signature(
        service.create
    ).parameters
    created = service.create(
        job_id,
        resume_id,
        conversation_id="career-session-direct",
        difficulty="standard",
        duration_minutes=15,
    )

    assert "snapshot_id" not in created
    assert "snapshot_id" not in created["blueprint"]
    assert created["status"] == "ready"


def test_service_creates_ready_session_from_direct_sources(tmp_path):
    (
        service,
        _,
        _,
        _,
        job_id,
        resume_id,
        snapshot_id,
    ) = _service(tmp_path)

    created = _create(service, job_id, resume_id, snapshot_id)

    assert created["status"] == "ready"
    assert created["phase"] == "idle"
    assert created["version"] == 1
    assert created["question_budget"] == 5
    assert created["blueprint"]["position"] == "大模型算法工程师"
    assert created["blueprint"]["version"] == 2
    assert created["blueprint"]["role_tracks"]
    assert created["blueprint"]["evidence_cards"]
    assert created["blueprint"]["probe_plan"]
    assert created["conversation_id"] == "career-session-1"
    assert created["turns"] == []


def test_service_gets_interview_by_conversation(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)

    found = service.get_by_conversation("career-session-1")

    assert found is not None
    assert found["id"] == created["id"]
    assert service.get_by_conversation("career-session-missing") is None


def test_service_resumes_active_interview_for_same_job_and_resume(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)

    resumed = service.create(
        job_id,
        resume_id,
        conversation_id="new-conversation",
        difficulty="deep",
        duration_minutes=20,
    )

    assert resumed["id"] == created["id"]
    assert resumed["conversation_id"] == "career-session-1"
    connection = connect(service.config.database_path)
    assert connection.execute(
        "SELECT COUNT(*) FROM interview_sessions"
    ).fetchone()[0] == 1
    connection.close()


def test_service_creates_new_interview_after_completed_session(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    connection = connect(service.config.database_path)
    repository = InterviewRepository(connection)
    repository.update_session_if_version(
        created["id"],
        created["version"],
        status="completed",
        phase="idle",
        updated_at=NOW.isoformat(),
    )
    connection.commit()
    connection.close()

    replacement = service.create(
        job_id,
        resume_id,
        conversation_id="career-session-2",
        difficulty="standard",
        duration_minutes=15,
    )

    assert replacement["id"] != created["id"]
    assert replacement["conversation_id"] == "career-session-2"


def test_service_restart_cancels_active_interview_before_creating(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)

    replacement = service.create(
        job_id,
        resume_id,
        conversation_id="career-session-2",
        difficulty="standard",
        duration_minutes=15,
        restart=True,
    )

    assert replacement["id"] != created["id"]
    assert replacement["conversation_id"] == "career-session-2"
    assert service.get(created["id"])["status"] == "cancelled"


def test_service_binds_one_real_conversation_with_cas(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = service.create(
        job_id,
        resume_id,
        conversation_id=None,
        difficulty="standard",
        duration_minutes=15,
    )

    bound = service.bind_conversation(
        created["id"],
        expected_version=created["version"],
        conversation_id="career-session-real",
    )

    assert bound["conversation_id"] == "career-session-real"
    assert bound["version"] == created["version"] + 1
    with pytest.raises(InterviewServiceError) as conflict:
        service.bind_conversation(
            created["id"],
            expected_version=bound["version"],
            conversation_id="other-session",
        )
    assert conflict.value.code == "INTERVIEW_STATE_CONFLICT"


def test_service_rejects_binding_second_interview_to_conversation(
    tmp_path,
):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    first = _create(service, job_id, resume_id, snapshot_id)
    connection = connect(service.config.database_path)
    repository = InterviewRepository(connection)
    repository.update_session_if_version(
        first["id"],
        first["version"],
        status="cancelled",
        phase="idle",
        updated_at=NOW.isoformat(),
    )
    connection.commit()
    connection.close()
    unbound = service.create(
        job_id,
        resume_id,
        conversation_id=None,
        difficulty="standard",
        duration_minutes=15,
    )

    with pytest.raises(InterviewServiceError) as error:
        service.bind_conversation(
            unbound["id"],
            expected_version=unbound["version"],
            conversation_id="career-session-1",
        )

    assert error.value.code == "INTERVIEW_STATE_CONFLICT"


@pytest.mark.parametrize(
    ("difficulty", "duration"),
    [
        ("unknown", 15),
        ("standard", 30),
        ("standard", True),
    ],
)
def test_service_rejects_invalid_create_options(
    tmp_path,
    difficulty,
    duration,
):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)

    with pytest.raises(InterviewServiceError) as error:
        service.create(
            job_id,
            resume_id,
            conversation_id="career-session-1",
            difficulty=difficulty,
            duration_minutes=duration,
        )

    assert error.value.code == "INVALID_INPUT"


def test_service_rejects_missing_job_without_session(tmp_path):
    service, _, _, _, job_id, resume_id, _ = _service(tmp_path)

    with pytest.raises(InterviewServiceError) as error:
        _create(service, f"{job_id}-missing", resume_id, None)

    assert error.value.code == "JOB_NOT_FOUND"
    connection = connect(service.config.database_path)
    assert connection.execute(
        "SELECT COUNT(*) FROM interview_sessions"
    ).fetchone()[0] == 0
    connection.close()


def test_service_starts_and_accepts_one_answer(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)

    started = _start(service, created)
    turn = started["turns"][0]
    answered = service.submit_answer(
        created["id"],
        turn["id"],
        expected_version=started["version"],
        answer_text="我负责了岗位数据和简历匹配。",
    )

    assert started["status"] == "in_progress"
    assert started["phase"] == "waiting_for_answer"
    assert turn["turn_index"] == 1
    assert answered["phase"] == "evaluating"
    assert answered["turns"][0]["answer_text"] == (
        "我负责了岗位数据和简历匹配。"
    )

    with pytest.raises(InterviewServiceError) as duplicate:
        service.submit_answer(
            created["id"],
            turn["id"],
            expected_version=answered["version"],
            answer_text="覆盖回答",
        )
    assert duplicate.value.code == "TURN_ALREADY_ANSWERED"


def test_service_returns_specific_question_violation(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)

    with pytest.raises(InterviewServiceError) as error:
        service.start(
            created["id"],
            expected_version=created["version"],
            question={
                **_start_question(created),
                "question": "请介绍简历中的相关项目？",
            },
        )

    assert error.value.code == "QUESTION_VALIDATION_FAILED"
    assert error.value.violations == [
        {
            "code": "QUESTION_VALIDATION_FAILED",
            "message": "first question must name the target position",
        }
    ]


def test_service_rejects_old_session_version(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)

    with pytest.raises(InterviewServiceError) as error:
        service.submit_answer(
            created["id"],
            started["turns"][0]["id"],
            expected_version=created["version"],
            answer_text="旧版本回答",
        )

    assert error.value.code == "VERSION_CONFLICT"


def test_evaluate_and_next_is_atomic(tmp_path, monkeypatch):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)
    turn = started["turns"][0]
    answered = service.submit_answer(
        created["id"],
        turn["id"],
        expected_version=started["version"],
        answer_text="我负责了岗位数据和简历匹配。",
    )
    ref = _first_ref(answered)
    original_insert = InterviewRepository.insert_turn

    def fail_second_turn(repository, record):
        if record["turn_index"] == 2:
            raise RuntimeError("injected turn insert failure")
        return original_insert(repository, record)

    monkeypatch.setattr(
        InterviewRepository,
        "insert_turn",
        fail_second_turn,
    )

    with pytest.raises(RuntimeError):
        service.evaluate_and_next(
            created["id"],
            turn["id"],
            expected_version=answered["version"],
            evaluation=_evaluation(ref, answered["turns"][0]),
            next_action="FOLLOW_UP",
            next_reason="继续深挖个人贡献",
            next_question=_follow_up_question(
                answered,
                question="你在这个项目中具体负责什么？",
            ),
        )

    current = service.get(created["id"])
    assert current["version"] == answered["version"]
    assert current["turns"][0]["evaluation"] is None
    assert len(current["turns"]) == 1


def test_service_evaluates_and_creates_one_next_question(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)
    answered = service.submit_answer(
        created["id"],
        started["turns"][0]["id"],
        expected_version=started["version"],
        answer_text="我负责了岗位数据和简历匹配。",
    )
    ref = _first_ref(answered)

    next_state = service.evaluate_and_next(
        created["id"],
        answered["turns"][0]["id"],
        expected_version=answered["version"],
        evaluation=_evaluation(ref, answered["turns"][0]),
        next_action="FOLLOW_UP",
        next_reason="继续深挖个人贡献",
        next_question=_follow_up_question(
            answered,
            question="你在这个项目中具体负责什么？",
        ),
    )

    assert next_state["phase"] == "waiting_for_answer"
    assert len(next_state["turns"]) == 2
    assert next_state["turns"][0]["evaluation"]["question_score"] == 100
    assert next_state["turns"][1]["question_refs"] == (
        next_state["turns"][0]["question_refs"]
    )
    assert next_state["turns"][1]["probe_target"] == (
        next_state["turns"][0]["probe_target"]
    )
    assert next_state["turns"][1]["depth_level"] == 2


def test_service_rejects_an_action_that_disagrees_with_evaluation(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)
    answered = service.submit_answer(
        created["id"],
        started["turns"][0]["id"],
        expected_version=started["version"],
        answer_text="我们做了一些优化。",
    )
    turn = answered["turns"][0]
    evaluation = _evaluation(_first_ref(answered), turn, "FOLLOW_UP")
    for dimension in evaluation["active_dimensions"]:
        dimension["level"] = 0
        dimension["evidence"] = []
        dimension["missing_evidence"] = "缺少可验证证据"

    with pytest.raises(InterviewServiceError) as error:
        service.evaluate_and_next(
            created["id"],
            turn["id"],
            expected_version=answered["version"],
            evaluation=evaluation,
            next_action="SWITCH_TOPIC",
            next_reason="切换话题",
            next_question=_switch_question(
                answered,
                question="请说明另一项岗位要求？",
            ),
        )

    assert error.value.code == "EVALUATION_VALIDATION_FAILED"


def test_service_rejects_switching_topic_for_low_evidence(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)
    answered = service.submit_answer(
        created["id"],
        started["turns"][0]["id"],
        expected_version=started["version"],
        answer_text="我们做了一些优化。",
    )
    turn = answered["turns"][0]
    evaluation = _evaluation(_first_ref(answered), turn, "SWITCH_TOPIC")
    for dimension in evaluation["active_dimensions"]:
        dimension["level"] = 0
        dimension["evidence"] = []
        dimension["missing_evidence"] = "缺少可验证证据"

    with pytest.raises(InterviewServiceError) as error:
        service.evaluate_and_next(
            created["id"],
            turn["id"],
            expected_version=answered["version"],
            evaluation=evaluation,
            next_action="SWITCH_TOPIC",
            next_reason="切换话题",
            next_question=_switch_question(
                answered,
                question="请说明另一项岗位要求？",
            ),
        )

    assert error.value.code == "EVALUATION_VALIDATION_FAILED"


def test_service_allows_low_evidence_switch_at_target_max_depth(
    tmp_path,
):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    current = _start(service, created)
    target = _target(
        current,
        current["turns"][-1]["probe_target"],
    )
    while current["turns"][-1]["depth_level"] < target["max_depth"]:
        turn = current["turns"][-1]
        current = service.submit_answer(
            created["id"],
            turn["id"],
            expected_version=current["version"],
            answer_text="我说明了个人行动和结果。",
        )
        current = service.evaluate_and_next(
            created["id"],
            turn["id"],
            expected_version=current["version"],
            evaluation=_evaluation(
                _first_ref(current),
                current["turns"][-1],
            ),
            next_action="FOLLOW_UP",
            next_reason="继续深挖当前目标",
            next_question=_follow_up_question(
                current,
                question=(
                    f"请进一步说明第 "
                    f"{current['turns'][-1]['depth_level'] + 1} "
                    "层个人行动和结果？"
                ),
            ),
        )

    turn = current["turns"][-1]
    current = service.submit_answer(
        created["id"],
        turn["id"],
        expected_version=current["version"],
        answer_text="没有保留可验证的结果数据。",
    )
    evaluation = _evaluation(
        _first_ref(current),
        current["turns"][-1],
        "SWITCH_TOPIC",
    )
    for dimension in evaluation["active_dimensions"]:
        dimension["level"] = 0
        dimension["evidence"] = []
        dimension["missing_evidence"] = "缺少可验证证据"

    switched = service.evaluate_and_next(
        created["id"],
        turn["id"],
        expected_version=current["version"],
        evaluation=evaluation,
        next_action="SWITCH_TOPIC",
        next_reason="当前目标已到最大深度，切换到下一目标",
        next_question=_switch_question(
            current,
            question="请说明另一项岗位要求？",
        ),
    )

    assert switched["phase"] == "waiting_for_answer"
    assert switched["turns"][-1]["probe_target"] != turn["probe_target"]
    assert switched["turns"][-1]["depth_level"] == 1


def _complete_five_turns(service, session):
    current = _start(service, session)
    ref = _first_ref(current)
    for turn_index in range(1, 6):
        turn = current["turns"][-1]
        current = service.submit_answer(
            session["id"],
            turn["id"],
            expected_version=current["version"],
            answer_text=f"第 {turn_index} 轮回答，包含个人行动和结果。",
        )
        if turn_index < 5:
            switching = turn_index == 3
            current = service.evaluate_and_next(
                session["id"],
                turn["id"],
                expected_version=current["version"],
                evaluation=_evaluation(
                    ref,
                    current["turns"][-1],
                    "SWITCH_TOPIC" if switching else "FOLLOW_UP",
                ),
                next_action=(
                    "SWITCH_TOPIC" if switching else "FOLLOW_UP"
                ),
                next_reason="根据上一轮回答继续追问",
                next_question=(
                    _switch_question(
                        current,
                        question="请说明你会如何处理另一项岗位要求？",
                    )
                    if switching
                    else _follow_up_question(
                        current,
                        question=(
                            f"第 {turn_index + 1} 轮请进一步说明"
                            "你的个人行动和结果？"
                        ),
                    )
                ),
            )
        else:
            current = service.evaluate_and_next(
                session["id"],
                turn["id"],
                expected_version=current["version"],
                evaluation=_evaluation(ref, current["turns"][-1], "WRAP_UP"),
                next_action="WRAP_UP",
                next_reason="已完成五轮训练",
                next_question=None,
            )
    return current


def test_service_finishes_and_publishes_three_artifacts(tmp_path):
    service, workspace, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )
    created = _create(service, job_id, resume_id, snapshot_id)
    wrapping = _complete_five_turns(service, created)

    finished = service.finish(
        created["id"],
        expected_version=wrapping["version"],
        user_requested=False,
    )
    result = service.generate_report(
        created["id"],
        expected_version=finished["version"],
    )

    assert result["status"] == "completed"
    artifact_dir = (
        workspace / "artifacts" / "interviews" / created["id"]
    )
    assert {
        path.name for path in artifact_dir.iterdir() if path.is_file()
    } == {
        "transcript.md",
        "interview-report.md",
        "session.json",
    }
    assert result["report_sha256"]
    assert service.read_artifact(
        created["id"],
        "report",
    )["bytes"].startswith(b"# ")


def test_read_artifact_rejects_a_symlink(tmp_path):
    service, workspace, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )
    created = _create(service, job_id, resume_id, snapshot_id)
    wrapping = _complete_five_turns(service, created)
    finished = service.finish(
        created["id"],
        expected_version=wrapping["version"],
        user_requested=False,
    )
    service.generate_report(
        created["id"],
        expected_version=finished["version"],
    )
    report = (
        workspace
        / "artifacts"
        / "interviews"
        / created["id"]
        / "interview-report.md"
    )
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    report.unlink()
    report.symlink_to(outside)

    with pytest.raises(InterviewServiceError) as error:
        service.read_artifact(created["id"], "report")

    assert error.value.code == "PERSISTENCE_ERROR"


def test_user_can_finish_early_after_an_evaluated_turn(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)
    answered = service.submit_answer(
        created["id"],
        started["turns"][0]["id"],
        expected_version=started["version"],
        answer_text="我希望先结束本场面试。",
    )
    ref = _first_ref(answered)
    wrapping = service.evaluate_and_next(
        created["id"],
        answered["turns"][0]["id"],
        expected_version=answered["version"],
        evaluation=_evaluation(ref, answered["turns"][0], "WRAP_UP"),
        next_action="WRAP_UP",
        next_reason="用户请求提前结束",
        next_question=None,
        user_requested=True,
    )

    assert wrapping["phase"] == "generating_report"


def test_user_can_finish_while_waiting_for_the_next_question(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(tmp_path)
    created = _create(service, job_id, resume_id, snapshot_id)
    started = _start(service, created)
    answered = service.submit_answer(
        created["id"],
        started["turns"][0]["id"],
        expected_version=started["version"],
        answer_text="我已经完成一轮，希望提前结束。",
    )
    ref = _first_ref(answered)
    waiting = service.evaluate_and_next(
        created["id"],
        answered["turns"][0]["id"],
        expected_version=answered["version"],
        evaluation=_evaluation(ref, answered["turns"][0]),
        next_action="FOLLOW_UP",
        next_reason="原计划继续追问",
        next_question=_follow_up_question(
            answered,
            question="请继续说明你的个人贡献？",
        ),
    )

    finished = service.finish(
        created["id"],
        expected_version=waiting["version"],
        user_requested=True,
    )
    reported = service.generate_report(
        created["id"],
        expected_version=finished["version"],
    )

    assert finished["phase"] == "generating_report"
    assert len(finished["turns"]) == 1
    assert finished["turns"][0]["answer_text"]
    assert reported["status"] == "completed"


def test_report_write_failure_leaves_no_completed_session(
    tmp_path,
    monkeypatch,
):
    service, workspace, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )
    created = _create(service, job_id, resume_id, snapshot_id)
    wrapping = _complete_five_turns(service, created)
    finished = service.finish(
        created["id"],
        expected_version=wrapping["version"],
        user_requested=False,
    )

    def fail_replace(_source: Path, _target: Path):
        raise OSError("injected report publish failure")

    monkeypatch.setattr(
        "extensions.career_mcp.services.interviews.os.replace",
        fail_replace,
    )

    with pytest.raises(InterviewServiceError) as error:
        service.generate_report(
            created["id"],
            expected_version=finished["version"],
        )

    assert error.value.code == "PERSISTENCE_ERROR"
    current = service.get(created["id"])
    assert current["status"] != "completed"
    official = (
        workspace / "artifacts" / "interviews" / created["id"]
    )
    assert not official.exists()
