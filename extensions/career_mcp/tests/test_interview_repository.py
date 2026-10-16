import sqlite3

import pytest

from extensions.career_mcp.database.interview_repository import (
    InterviewRepository,
)
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.tests.test_interview_service import _seed


NOW = "2026-08-10T16:00:00Z"


def _records(tmp_path):
    config, _, _, job_id, resume_id = _seed(tmp_path)
    connection = connect(config.database_path)
    session = {
        "id": "interview-1",
        "job_id": job_id,
        "resume_id": resume_id,
        "conversation_id": "career-session-1",
        "company": "DeepSeek",
        "position": "大模型算法工程师",
        "difficulty": "standard",
        "duration_minutes": 15,
        "question_budget": 8,
        "blueprint": {
            "version": 1,
            "question_budget": 8,
            "focus_areas": [],
        },
        "status": "ready",
        "phase": "idle",
        "started_at": None,
        "ended_at": None,
        "report_path": None,
        "transcript_path": None,
        "session_path": None,
        "report_sha256": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    turn = {
        "id": "turn-1",
        "session_id": session["id"],
        "turn_index": 1,
        "question_text": "请介绍与你申请岗位最相关的一段经历？",
        "question_refs": ["INTRO"],
        "answer_text": None,
        "evaluation": None,
        "next_action": None,
        "next_reason": None,
        "started_at": NOW,
        "answered_at": None,
        "evaluated_at": None,
    }
    return connection, session, turn


def test_repository_creates_and_maps_session(tmp_path):
    connection, session, _ = _records(tmp_path)
    repository = InterviewRepository(connection)

    created = repository.create_session(session)

    assert created["version"] == 1
    assert created["blueprint"]["question_budget"] == 8
    assert created["resume_id"] == session["resume_id"]
    assert created["conversation_id"] == "career-session-1"
    connection.close()


def test_repository_gets_session_by_conversation_id(tmp_path):
    connection, session, _ = _records(tmp_path)
    repository = InterviewRepository(connection)
    created = repository.create_session(session)

    found = repository.get_session_by_conversation_id(
        "career-session-1"
    )

    assert found is not None
    assert found["id"] == created["id"]
    assert repository.get_session_by_conversation_id("missing") is None
    connection.close()


def test_repository_gets_latest_active_session_for_job_and_resume(tmp_path):
    connection, session, _ = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)

    found = repository.get_active_session(
        session["job_id"],
        session["resume_id"],
    )

    assert found is not None
    assert found["id"] == session["id"]
    repository.update_session_if_version(
        session["id"],
        1,
        status="completed",
        phase="idle",
        updated_at=NOW,
    )
    assert (
        repository.get_active_session(
            session["job_id"],
            session["resume_id"],
        )
        is None
    )
    connection.close()


def test_repository_updates_session_only_at_expected_version(tmp_path):
    connection, session, _ = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)

    assert repository.update_session_if_version(
        session["id"],
        1,
        status="in_progress",
        phase="asking",
        started_at=NOW,
        updated_at=NOW,
    )
    assert not repository.update_session_if_version(
        session["id"],
        1,
        status="cancelled",
        phase="idle",
        updated_at=NOW,
    )
    saved = repository.get_session(session["id"])
    assert saved["version"] == 2
    assert saved["status"] == "in_progress"
    connection.close()


def test_repository_rejects_unknown_session_update_fields(tmp_path):
    connection, session, _ = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)

    with pytest.raises(ValueError):
        repository.update_session_if_version(
            session["id"],
            1,
            blueprint_json="untrusted",
        )

    connection.close()


def test_repository_inserts_maps_and_orders_turns(tmp_path):
    connection, session, turn = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)

    first = repository.insert_turn(turn)
    second = repository.insert_turn(
        {
            **turn,
            "id": "turn-2",
            "turn_index": 2,
            "question_text": "你在项目中具体负责什么？",
            "question_refs": ["project[0].highlights[0]"],
            "question_topic": "技术实现",
            "probe_target": "project[0]",
            "probe_dimension": "implementation",
            "depth_level": 2,
        }
    )

    assert first["question_refs"] == ["INTRO"]
    assert first["question_topic"] is None
    assert first["probe_target"] is None
    assert first["probe_dimension"] is None
    assert first["depth_level"] is None
    assert second["turn_index"] == 2
    assert second["question_topic"] == "技术实现"
    assert second["probe_target"] == "project[0]"
    assert second["probe_dimension"] == "implementation"
    assert second["depth_level"] == 2
    assert [
        item["id"]
        for item in repository.list_turns(session["id"])
    ] == ["turn-1", "turn-2"]
    assert repository.current_turn(session["id"])["id"] == "turn-2"
    connection.close()


def test_repository_rejects_duplicate_turn_index(tmp_path):
    connection, session, turn = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)
    repository.insert_turn(turn)

    with pytest.raises(sqlite3.IntegrityError):
        repository.insert_turn({**turn, "id": "turn-2"})

    connection.close()


def test_repository_deletes_only_an_unanswered_tail_turn(tmp_path):
    connection, session, turn = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)
    first = repository.insert_turn(turn)
    second = repository.insert_turn(
        {
            **turn,
            "id": "turn-2",
            "turn_index": 2,
            "question_text": "第二题",
        }
    )
    repository.answer_turn(
        first["id"],
        answer_text="第一题回答",
        answered_at=NOW,
    )

    assert repository.delete_unanswered_turn(first["id"]) is False
    assert repository.delete_unanswered_turn(second["id"]) is True
    assert [
        item["id"]
        for item in repository.list_turns(session["id"])
    ] == ["turn-1"]
    connection.close()


def test_repository_answers_each_turn_once(tmp_path):
    connection, session, turn = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)
    repository.insert_turn(turn)

    assert repository.answer_turn(
        turn["id"],
        answer_text="我负责了岗位数据和简历匹配。",
        answered_at=NOW,
    )
    assert not repository.answer_turn(
        turn["id"],
        answer_text="覆盖已有回答",
        answered_at=NOW,
    )
    saved = repository.current_turn(session["id"])
    assert saved["answer_text"] == "我负责了岗位数据和简历匹配。"
    connection.close()


def test_repository_evaluates_answered_turn_once(tmp_path):
    connection, session, turn = _records(tmp_path)
    repository = InterviewRepository(connection)
    repository.create_session(session)
    repository.insert_turn(turn)
    assert not repository.evaluate_turn(
        turn["id"],
        evaluation={"relevance": 8},
        next_action="FOLLOW_UP",
        next_reason="继续深挖",
        evaluated_at=NOW,
    )
    repository.answer_turn(
        turn["id"],
        answer_text="我负责了岗位数据和简历匹配。",
        answered_at=NOW,
    )

    assert repository.evaluate_turn(
        turn["id"],
        evaluation={"relevance": 8},
        next_action="FOLLOW_UP",
        next_reason="继续深挖",
        evaluated_at=NOW,
    )
    assert not repository.evaluate_turn(
        turn["id"],
        evaluation={"relevance": 9},
        next_action="DEEP_DIVE",
        next_reason="覆盖评价",
        evaluated_at=NOW,
    )
    saved = repository.current_turn(session["id"])
    assert saved["evaluation"] == {"relevance": 8}
    assert saved["next_action"] == "FOLLOW_UP"
    connection.close()
