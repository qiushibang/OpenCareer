import inspect
from types import SimpleNamespace

from extensions.career_mcp import server
from extensions.career_mcp.services.interviews import (
    InterviewServiceError,
)


TOOL_NAMES = {
    "list_confirmed_resumes",
    "create_interview_session",
    "get_interview_session",
    "start_mock_interview",
    "submit_interview_answer",
    "get_next_interview_question",
    "finish_interview",
    "generate_interview_report",
}


def test_interview_tools_are_registered():
    assert TOOL_NAMES <= set(server.mcp._tool_manager._tools)
    parameters = inspect.signature(
        server.create_interview_session
    ).parameters
    assert "conversation_id" not in parameters
    assert "snapshot_id" not in parameters


def test_next_question_tool_exposes_strict_evaluation_schema():
    parameters = server.mcp._tool_manager._tools[
        "get_next_interview_question"
    ].parameters
    evaluation = parameters["properties"]["evaluation"]
    schema = parameters["$defs"][evaluation["$ref"].split("/")[-1]]

    assert schema["properties"]["version"]["const"] == 2
    assert schema["properties"]["question_type"]["enum"] == [
        "past_behavior",
        "product_case",
        "technical_knowledge",
        "coding",
        "system_design",
        "ai_ml_case",
        "failure_reflection",
    ]
    assert schema["additionalProperties"] is False
    dimension_ref = schema["properties"]["active_dimensions"]["items"]["$ref"]
    dimension = parameters["$defs"][dimension_ref.split("/")[-1]]
    dimension_names = dimension["properties"]["name"]["enum"]
    assert "relevance" in dimension_names
    assert "ownership" in dimension_names
    assert "technical_correctness" in dimension_names
    assert "personal_contribution" not in dimension_names
    assert "evidence" not in dimension_names
    assert "structure" not in dimension_names
    assert "depth" not in dimension_names
    assert "name" not in dimension["required"]
    assert parameters["properties"]["next_action"]["enum"] == [
        "FOLLOW_UP",
        "VERIFY_CLAIM",
        "DEEP_DIVE",
        "SWITCH_TOPIC",
        "WRAP_UP",
    ]


def test_interview_context_tool_returns_only_resume_selection_summaries(
    monkeypatch,
):
    calls = []
    resumes = SimpleNamespace(
        list_resume_documents=lambda: (
            calls.append(("resumes",))
            or [
                {
                    "id": "resume-1",
                    "filename": "private-name.pdf",
                    "display_name": "算法简历",
                    "target_roles": ["算法工程师"],
                    "source_kind": "pdf",
                    "status": "confirmed",
                    "confirmed_sections": ["basic", "project"],
                    "created_at": "2026-08-10T00:00:00Z",
                    "updated_at": "2026-08-10T01:00:00Z",
                    "private_path": "/Users/private/resume.pdf",
                }
            ]
        )
    )
    monkeypatch.setattr(server, "_resume_service", lambda: resumes)

    listed_resumes = server.list_confirmed_resumes()

    assert listed_resumes["data"]["resumes"] == [
        {
            "id": "resume-1",
            "display_name": "算法简历",
            "target_roles": ["算法工程师"],
            "status": "confirmed",
            "confirmed_sections": ["basic", "project"],
            "updated_at": "2026-08-10T01:00:00Z",
        }
    ]
    assert calls == [("resumes",)]
    assert "private_path" not in str(listed_resumes)


def test_create_get_start_and_answer_forward_to_shared_service(monkeypatch):
    calls = []
    service = SimpleNamespace(
        create=lambda *args, **kwargs: (
            calls.append(("create", args, kwargs))
            or {"id": "interview-1", "version": 1}
        ),
        get=lambda session_id: (
            calls.append(("get", session_id))
            or {"id": session_id, "version": 1}
        ),
        start=lambda session_id, **kwargs: (
            calls.append(("start", session_id, kwargs))
            or {"id": session_id, "version": 2}
        ),
        submit_answer=lambda session_id, turn_id, **kwargs: (
            calls.append(("answer", session_id, turn_id, kwargs))
            or {"id": session_id, "version": 3}
        ),
    )
    monkeypatch.setattr(server, "_interview_service", lambda: service)

    created = server.create_interview_session(
        "job-1",
        "resume-1",
        "standard",
        15,
    )
    fetched = server.get_interview_session("interview-1")
    started = server.start_mock_interview(
        "interview-1",
        1,
        {
            "question": "请介绍相关经历？",
            "refs": ["INTRO"],
            "topic": "intro",
        },
    )
    answered = server.submit_interview_answer(
        "interview-1",
        "turn-1",
        2,
        "我的回答",
    )

    assert all(result["ok"] for result in (
        created,
        fetched,
        started,
        answered,
    ))
    assert calls == [
        (
            "create",
            ("job-1", "resume-1"),
            {
                "conversation_id": None,
                "difficulty": "standard",
                "duration_minutes": 15,
            },
        ),
        ("get", "interview-1"),
        (
            "start",
            "interview-1",
            {
                "expected_version": 1,
                "question": {
                    "question": "请介绍相关经历？",
                    "refs": ["INTRO"],
                    "topic": "intro",
                },
            },
        ),
        (
            "answer",
            "interview-1",
            "turn-1",
            {
                "expected_version": 2,
                "answer_text": "我的回答",
            },
        ),
    ]


def test_next_finish_and_report_forward_to_shared_service(monkeypatch):
    calls = []
    service = SimpleNamespace(
        evaluate_and_next=lambda session_id, turn_id, **kwargs: (
            calls.append(("next", session_id, turn_id, kwargs))
            or {"id": session_id, "version": 4}
        ),
        finish=lambda session_id, **kwargs: (
            calls.append(("finish", session_id, kwargs))
            or {"id": session_id, "version": 5}
        ),
        generate_report=lambda session_id, **kwargs: (
            calls.append(("report", session_id, kwargs))
            or {
                "id": session_id,
                "version": 6,
                "status": "completed",
            }
        ),
    )
    monkeypatch.setattr(server, "_interview_service", lambda: service)
    evaluation = {
        "relevance": 8,
        "clarity": 7,
        "structure": 6,
        "depth": 8,
        "evidence": 5,
        "issues": ["证据不足"],
        "coaching_structure": ["背景", "行动", "结果"],
        "fact_refs": ["project[0].highlights[0]"],
    }
    question = {
        "question": "你具体负责什么？",
        "refs": ["project[0].highlights[0]"],
        "topic": "contribution",
    }

    next_result = server.get_next_interview_question(
        "interview-1",
        "turn-1",
        3,
        evaluation,
        "FOLLOW_UP",
        "继续深挖",
        question,
        True,
    )
    finished = server.finish_interview(
        "interview-1",
        4,
        False,
    )
    report = server.generate_interview_report("interview-1", 5)

    assert next_result["ok"] is True
    assert finished["ok"] is True
    assert report["data"]["status"] == "completed"
    assert calls == [
        (
            "next",
            "interview-1",
            "turn-1",
            {
                "expected_version": 3,
                "evaluation": evaluation,
                "next_action": "FOLLOW_UP",
                "next_reason": "继续深挖",
                "next_question": question,
                "user_requested": True,
            },
        ),
        (
            "finish",
            "interview-1",
            {
                "expected_version": 4,
                "user_requested": False,
            },
        ),
        (
            "report",
            "interview-1",
            {"expected_version": 5},
        ),
    ]


def test_next_tool_fills_required_dimension_names_from_question_type(
    monkeypatch,
):
    calls = []
    service = SimpleNamespace(
        evaluate_and_next=lambda session_id, turn_id, **kwargs: (
            calls.append((session_id, turn_id, kwargs))
            or {"id": session_id, "version": 4}
        )
    )
    monkeypatch.setattr(server, "_interview_service", lambda: service)
    evaluation = server.InterviewEvaluationInput.model_validate(
        {
            "version": 2,
            "question_type": "past_behavior",
            "target_competency": "personal_contribution",
            "active_dimensions": [
                {
                    "level": level,
                    "evidence": [],
                    "missing_evidence": "缺少证据",
                }
                for level in (2, 1, 1, 0)
            ],
            "primary_pain": "个人贡献不清",
            "reason": "缺少个人行动和结果。",
            "improvement": "补充个人行动和结果。",
            "fact_refs": [],
            "recommended_action": "FOLLOW_UP",
        }
    )

    result = server.get_next_interview_question(
        "interview-1",
        "turn-1",
        3,
        evaluation,
        "FOLLOW_UP",
        "继续追问",
        {
            "question": "请说明你个人采取的关键行动？",
            "topic": "个人贡献",
            "refs": ["experience[0]"],
            "probe_target": "experience[0]",
            "probe_dimension": "ownership",
            "depth_level": 2,
        },
    )

    assert result["ok"] is True
    names = [
        item["name"]
        for item in calls[0][2]["evaluation"]["active_dimensions"]
    ]
    assert names == ["relevance", "specificity", "ownership", "outcome"]


def test_interview_tool_returns_stable_service_error(monkeypatch):
    def fail(_session_id):
        raise InterviewServiceError(
            "INTERVIEW_NOT_FOUND",
            "private /Users/example/interview.sqlite3",
            violations=[
                {
                    "code": "UNKNOWN_REF",
                    "message": "private path omitted",
                }
            ],
        )

    monkeypatch.setattr(
        server,
        "_interview_service",
        lambda: SimpleNamespace(get=fail),
    )

    result = server.get_interview_session("missing")

    assert result["ok"] is False
    assert result["error"]["code"] == "INTERVIEW_NOT_FOUND"
    assert result["error"]["message"] == "模拟面试操作失败。"
    assert result["error"]["violations"] == [
        {
            "code": "UNKNOWN_REF",
            "message": "private path omitted",
        }
    ]
    assert "/Users/" not in str(result)
