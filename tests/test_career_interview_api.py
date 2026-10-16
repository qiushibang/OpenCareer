from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from coworker.server.app import create_app
from coworker.server.manager import SessionManager
from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.services.resumes import ResumeService


JD = """职位：大模型算法工程师
公司：DeepSeek
工作地点：北京
岗位职责：
1. 负责大模型训练与评测
任职要求：
1. 必须熟悉 Python
"""
PROPOSAL = {
    "basic": {
        "name": "Zhang San",
        "phone": "13800001234",
        "email": "secret@example.com",
        "location": "北京",
        "summary": "AI 工程师",
    },
    "education": [],
    "experience": [],
    "project": [],
    "skill": [{"name": "Python", "level": None, "evidence": None}],
    "missing_fields": [],
    "warnings": [],
}


def _client_with_interview_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    jobs = JobService()
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
    resume_service = ResumeService()
    staged = resume_service.stage_resume(
        filename="算法简历.txt",
        mime="text/plain",
        text="Zhang San Python experience",
    )
    preview = resume_service.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    resume_service.confirm_resume_sections(
        preview["preview_token"],
        ["basic", "skill"],
        corrections={},
    )
    resume_id = resume_service.list_resume_documents()[0]["id"]
    resume_service.update_resume_document(
        resume_id,
        display_name="算法简历",
        target_roles=["大模型算法工程师"],
    )
    return (
        TestClient(
            create_app(SessionManager(data_dir=tmp_path / "state"))
        ),
        job_id,
        resume_id,
        None,
    )


def _create(client, job_id, resume_id, snapshot_id):
    del snapshot_id
    return client.post(
        "/v1/career/interviews",
        json={
            "job_id": job_id,
            "resume_id": resume_id,
            "conversation_id": "career-session-1",
            "difficulty": "standard",
            "duration_minutes": 15,
        },
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
            for name in (
                "relevance",
                "specificity",
                "ownership",
                "outcome",
            )
        ],
        "primary_pain": "需要继续验证",
        "reason": "回答已有证据，但仍需完成本轮训练。",
        "improvement": "继续说明关键决策和验证方式。",
        "fact_refs": [ref],
        "recommended_action": action,
    }


def _target(session: dict, target_id: str) -> dict:
    return next(
        item
        for item in session["blueprint"]["probe_plan"]
        if item["target_id"] == target_id
    )


def _first_question(session: dict) -> dict:
    target = session["blueprint"]["probe_plan"][0]
    evidence_ref = next(
        ref for ref in target["refs"] if not ref.startswith("requirement-")
    )
    return {
        "question": (
            f"你正在应聘{session['position']}，请结合简历中的相关"
            "事实介绍你的个人职责？"
        ),
        "refs": [evidence_ref],
        "topic": "个人职责",
        "probe_target": target["target_id"],
        "probe_dimension": "personal_contribution",
        "depth_level": 1,
    }


def _follow_up_question(session: dict, index: int) -> dict:
    current = session["turns"][-1]
    target = _target(session, current["probe_target"])
    depth = int(current["depth_level"]) + 1
    return {
        "question": (
            f"第 {index} 轮请进一步说明你的个人行动和结果？"
        ),
        "refs": current["question_refs"],
        "topic": "岗位深挖",
        "probe_target": current["probe_target"],
        "probe_dimension": target["dimensions"][depth - 1],
        "depth_level": depth,
    }


def _switch_question(session: dict) -> dict:
    current_target = session["turns"][-1]["probe_target"]
    target = next(
        item
        for item in session["blueprint"]["probe_plan"]
        if item["target_id"] != current_target
    )
    return {
        "question": "请说明你会如何处理另一项岗位能力要求？",
        "refs": [target["refs"][0]],
        "topic": "岗位能力",
        "probe_target": target["target_id"],
        "probe_dimension": target["dimensions"][0],
        "depth_level": 1,
    }


def test_interview_http_create_get_start_answer_and_next(
    tmp_path,
    monkeypatch,
):
    client, job_id, resume_id, snapshot_id = (
        _client_with_interview_inputs(tmp_path, monkeypatch)
    )
    created_response = _create(
        client,
        job_id,
        resume_id,
        snapshot_id,
    )
    assert created_response.status_code == 200
    created = created_response.json()["interview"]
    assert created["status"] == "ready"

    fetched = client.get(f"/v1/career/interviews/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["interview"]["id"] == created["id"]

    started_response = client.post(
        f"/v1/career/interviews/{created['id']}/start",
        json={
            "expected_version": created["version"],
            "question": _first_question(created),
        },
    )
    assert started_response.status_code == 200
    started = started_response.json()["interview"]
    turn = started["turns"][0]

    answered_response = client.post(
        f"/v1/career/interviews/{created['id']}/answers",
        json={
            "turn_id": turn["id"],
            "expected_version": started["version"],
            "answer_text": "我负责了本地岗位数据和简历匹配。",
        },
    )
    assert answered_response.status_code == 200
    answered = answered_response.json()["interview"]
    ref = answered["blueprint"]["evidence_cards"][0]["fact_path"]

    next_response = client.post(
        f"/v1/career/interviews/{created['id']}/next",
        json={
            "turn_id": turn["id"],
            "expected_version": answered["version"],
            "evaluation": _evaluation(
                ref,
                answered["turns"][0],
            ),
            "next_action": "FOLLOW_UP",
            "next_reason": "继续深挖个人贡献",
            "next_question": _follow_up_question(answered, 2),
        },
    )
    assert next_response.status_code == 200
    next_state = next_response.json()["interview"]
    assert next_state["turns"][-1]["turn_index"] == 2
    assert (
        next_state["turns"][0]["evaluation"]["question_score"]
        == 100
    )
    for forbidden in (
        "secret@example.com",
        "13800001234",
        "private_path",
        "access_token",
        "audio_bytes",
    ):
        assert forbidden not in next_response.text


def test_interview_http_gets_by_conversation(
    tmp_path,
    monkeypatch,
):
    client, job_id, resume_id, snapshot_id = (
        _client_with_interview_inputs(tmp_path, monkeypatch)
    )
    created = _create(
        client,
        job_id,
        resume_id,
        snapshot_id,
    ).json()["interview"]

    response = client.get(
        "/v1/career/interviews",
        params={"conversation_id": "career-session-1"},
    )
    missing = client.get(
        "/v1/career/interviews",
        params={"conversation_id": "career-session-missing"},
    )

    assert response.status_code == 200
    assert response.json()["interview"]["id"] == created["id"]
    assert missing.status_code == 200
    assert missing.json() == {"ok": True, "interview": None}


def test_interview_http_resumes_or_restarts_active_session(
    tmp_path,
    monkeypatch,
):
    client, job_id, resume_id, snapshot_id = (
        _client_with_interview_inputs(tmp_path, monkeypatch)
    )
    created = _create(
        client,
        job_id,
        resume_id,
        snapshot_id,
    ).json()["interview"]
    payload = {
        "job_id": job_id,
        "resume_id": resume_id,
        "conversation_id": "career-session-2",
        "difficulty": "standard",
        "duration_minutes": 15,
    }

    resumed = client.post(
        "/v1/career/interviews",
        json=payload,
    ).json()["interview"]
    restarted = client.post(
        "/v1/career/interviews",
        json={**payload, "restart": True},
    ).json()["interview"]

    assert resumed["id"] == created["id"]
    assert resumed["conversation_id"] == "career-session-1"
    assert restarted["id"] != created["id"]
    assert restarted["conversation_id"] == "career-session-2"
    assert (
        client.get(
            f"/v1/career/interviews/{created['id']}"
        ).json()["interview"]["status"]
        == "cancelled"
    )


def test_interview_http_binds_the_current_conversation(
    tmp_path,
    monkeypatch,
):
    client, job_id, resume_id, snapshot_id = (
        _client_with_interview_inputs(tmp_path, monkeypatch)
    )
    created_response = client.post(
        "/v1/career/interviews",
        json={
            "job_id": job_id,
            "resume_id": resume_id,
            "conversation_id": None,
            "difficulty": "standard",
            "duration_minutes": 15,
        },
    )
    created = created_response.json()["interview"]

    response = client.post(
        f"/v1/career/interviews/{created['id']}/conversation",
        json={
            "expected_version": created["version"],
            "conversation_id": "career-session-real",
        },
    )

    assert response.status_code == 200
    bound = response.json()["interview"]
    assert bound["conversation_id"] == "career-session-real"
    assert bound["version"] == created["version"] + 1


@pytest.mark.parametrize(
    "payload",
    [None, [], "invalid", 1, True],
)
def test_interview_http_rejects_non_object_create_json(
    tmp_path,
    monkeypatch,
    payload,
):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state"))
    )

    response = client.post("/v1/career/interviews", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_interview_http_returns_stable_errors(tmp_path, monkeypatch):
    client, job_id, resume_id, _ = _client_with_interview_inputs(
        tmp_path,
        monkeypatch,
    )

    missing_job = _create(
        client,
        f"{job_id}-missing",
        resume_id,
        None,
    )
    missing = client.get("/v1/career/interviews/missing")

    assert missing_job.status_code == 404
    assert missing_job.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "INTERVIEW_NOT_FOUND"
    serialized = json.dumps(
        [missing_job.json(), missing.json()],
        ensure_ascii=False,
    )
    assert "/Users/" not in serialized
    assert "sqlite" not in serialized.lower()


def test_interview_http_finishes_reports_and_downloads_artifacts(
    tmp_path,
    monkeypatch,
):
    client, job_id, resume_id, snapshot_id = (
        _client_with_interview_inputs(tmp_path, monkeypatch)
    )
    created = _create(
        client,
        job_id,
        resume_id,
        snapshot_id,
    ).json()["interview"]
    current = client.post(
        f"/v1/career/interviews/{created['id']}/start",
        json={
            "expected_version": created["version"],
            "question": _first_question(created),
        },
    ).json()["interview"]
    ref = current["blueprint"]["evidence_cards"][0]["fact_path"]

    for index in range(1, 6):
        turn = current["turns"][-1]
        current = client.post(
            f"/v1/career/interviews/{created['id']}/answers",
            json={
                "turn_id": turn["id"],
                "expected_version": current["version"],
                "answer_text": (
                    f"第 {index} 轮回答包含个人行动和可验证结果。"
                ),
            },
        ).json()["interview"]
        switching = index == 3
        action = (
            "WRAP_UP"
            if index == 5
            else "SWITCH_TOPIC"
            if switching
            else "FOLLOW_UP"
        )
        current = client.post(
            f"/v1/career/interviews/{created['id']}/next",
            json={
                "turn_id": turn["id"],
                "expected_version": current["version"],
                "evaluation": _evaluation(
                    ref,
                    current["turns"][-1],
                    action,
                ),
                "next_action": action,
                "next_reason": "根据上一轮回答继续",
                "next_question": (
                    None
                    if index == 5
                    else _switch_question(current)
                    if switching
                    else _follow_up_question(current, index + 1)
                ),
            },
        ).json()["interview"]

    finished_response = client.post(
        f"/v1/career/interviews/{created['id']}/finish",
        json={
            "expected_version": current["version"],
            "user_requested": False,
        },
    )
    assert finished_response.status_code == 200
    finished = finished_response.json()["interview"]
    report_response = client.post(
        f"/v1/career/interviews/{created['id']}/report",
        json={"expected_version": finished["version"]},
    )

    assert report_response.status_code == 200
    assert report_response.json()["interview"]["status"] == "completed"
    for kind, content_type in (
        ("transcript", "text/markdown"),
        ("report", "text/markdown"),
        ("session", "application/json"),
    ):
        downloaded = client.get(
            f"/v1/career/interviews/{created['id']}/artifacts/{kind}"
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith(content_type)
        assert downloaded.content


def test_interview_voice_http_decodes_wav_and_returns_mpeg(
    tmp_path,
    monkeypatch,
):
    import base64

    import coworker.server.app as app_module

    class FakeVoiceService:
        def __init__(self):
            self.audio = None
            self.text = None

        async def transcribe(self, audio, *, mime):
            self.audio = (audio, mime)
            return "可编辑的识别文本"

        async def synthesize(self, text):
            self.text = text
            return b"mp3-audio"

    fake = FakeVoiceService()
    monkeypatch.setattr(
        app_module,
        "career_interview_voice_service",
        lambda: fake,
        raising=False,
    )
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state"))
    )
    wav = b"RIFF" + b"\x00" * 4 + b"WAVEprivate-audio"

    transcript = client.post(
        "/v1/career/interviews/voice/transcribe",
        json={
            "mime": "audio/wav",
            "data_base64": base64.b64encode(wav).decode(),
        },
    )
    speech = client.post(
        "/v1/career/interviews/voice/synthesize",
        json={"text": "请介绍你的项目经历。"},
    )

    assert transcript.status_code == 200
    assert transcript.json() == {
        "ok": True,
        "transcript": "可编辑的识别文本",
    }
    assert "private-audio" not in transcript.text
    assert fake.audio == (wav, "audio/wav")
    assert speech.status_code == 200
    assert speech.headers["content-type"].startswith("audio/mpeg")
    assert speech.content == b"mp3-audio"
    assert fake.text == "请介绍你的项目经历。"


def test_interview_voice_http_rejects_invalid_input_and_hides_errors(
    tmp_path,
    monkeypatch,
):
    import coworker.server.app as app_module
    from extensions.career_mcp.services.interview_voice import (
        InterviewVoiceServiceError,
    )

    class FailingVoiceService:
        async def transcribe(self, audio, *, mime):
            raise InterviewVoiceServiceError("ASR_FAILED")

        async def synthesize(self, text):
            raise InterviewVoiceServiceError("TTS_FAILED")

    monkeypatch.setattr(
        app_module,
        "career_interview_voice_service",
        FailingVoiceService,
        raising=False,
    )
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state"))
    )

    invalid = client.post(
        "/v1/career/interviews/voice/transcribe",
        json={"mime": "audio/wav", "data_base64": "not-base64"},
    )
    failed = client.post(
        "/v1/career/interviews/voice/synthesize",
        json={"text": "private transcript speech-secret-key"},
    )

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_INPUT"
    assert failed.status_code == 400
    assert failed.json()["error"]["code"] == "TTS_FAILED"
    assert "private transcript" not in failed.text
    assert "speech-secret-key" not in failed.text
