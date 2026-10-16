import json
import runpy
from pathlib import Path

import pytest

from extensions.career_mcp.domain.interviews import (
    build_blueprint,
    validate_question,
)
from extensions.career_mcp.domain.privacy import contains_sensitive_value


FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "acceptance"
    / "fixtures"
)
_validate = runpy.run_path(
    str(FIXTURE_DIR.parent / "resume_grounded_interview_gate.py")
)["_validate"]


def _job(fixture: dict) -> dict:
    return {
        "id": "job-1",
        "title": fixture["job"]["title"],
        "company": {"name": "验收公司"},
        "requirements": fixture["job"]["requirements"],
    }


@pytest.mark.parametrize(
    "fixture_name",
    [
        "interview_algorithm.json",
        "interview_engineering.json",
        "interview_product.json",
    ],
)
def test_three_track_fixtures_build_grounded_depth_chain(
    fixture_name: str,
) -> None:
    fixture = json.loads(
        (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    )
    blueprint = build_blueprint(
        _job(fixture),
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=fixture["resume"]["sections"],
    )

    assert blueprint["role_tracks"] == ["general"]
    assert blueprint["evidence_cards"]
    assert not contains_sensitive_value(
        json.dumps(blueprint, ensure_ascii=False)
    )
    target = blueprint["probe_plan"][0]
    evidence_ref = next(
        ref for ref in target["refs"] if not ref.startswith("requirement-")
    )
    first = validate_question(
        {
            "question": (
                f"你正在应聘{fixture['job']['title']}，请结合简历中的"
                "相关项目介绍你的个人职责？"
            ),
            "topic": "个人职责",
            "refs": [evidence_ref],
            "probe_target": target["target_id"],
            "probe_dimension": "personal_contribution",
            "depth_level": 1,
        },
        blueprint=blueprint,
        turn_index=1,
        previous_turns=[],
    )
    required_dimension = next(
        dimension
        for dimension in fixture["required_dimensions"]
        if dimension in target["dimensions"]
    )
    second = validate_question(
        {
            "question": "请进一步说明这个项目中最关键的实现细节？",
            "topic": "岗位深挖",
            "refs": first["refs"],
            "probe_target": target["target_id"],
            "probe_dimension": required_dimension,
            "depth_level": 2,
        },
        blueprint=blueprint,
        turn_index=2,
        previous_turns=[
            {
                "question_text": first["question"],
                "probe_target": first["probe_target"],
                "probe_dimension": first["probe_dimension"],
                "depth_level": first["depth_level"],
            }
        ],
        next_action="DEEP_DIVE",
    )

    assert first["depth_level"] == 1
    assert second["depth_level"] == 2
    assert second["probe_target"] == first["probe_target"]
    assert second["probe_dimension"] in fixture["required_dimensions"]


def test_real_gate_ignores_machine_ids_in_privacy_text_scan(
    tmp_path: Path,
) -> None:
    session_id = "a1380000-1234-b000-b000-b00000000000"
    artifact_dir = (
        tmp_path / "artifacts" / "interviews" / session_id
    )
    artifact_dir.mkdir(parents=True)
    for name in (
        "interview-report.md",
        "session.json",
        "transcript.md",
    ):
        (artifact_dir / name).write_text("安全内容", encoding="utf-8")
    blueprint = {
        "version": 2,
        "role_tracks": ["general"],
        "probe_plan": [
            {
                "target_id": "project[0]",
                "refs": ["requirement-1"],
            }
        ],
    }
    turns = [
        {
            "question_text": (
                "请介绍大模型算法工程师岗位相关项目的背景"
                if index == 1
                else "请继续说明当前维度的细节"
            ),
            "question_refs": ["requirement-1"],
            "answer_text": "这是不包含敏感信息的回答",
            "evaluation": {"relevance": 8},
            "probe_target": "project[0]",
            "probe_dimension": "context",
            "depth_level": index,
        }
        for index in range(1, 6)
    ]

    result = _validate(
        {
            "job": {"title": "大模型算法工程师"},
            "expected_tracks": ["algorithm"],
            "required_dimensions": ["context"],
        },
        {
            "id": session_id,
            "status": "completed",
            "blueprint": blueprint,
            "turns": turns,
        },
        tmp_path,
    )

    assert result["privacy_passed"] is True

    turns[0]["answer_text"] = "请联系手机号 13800001234"
    with pytest.raises(AssertionError):
        _validate(
            {
                "job": {"title": "大模型算法工程师"},
                "expected_tracks": ["algorithm"],
                "required_dimensions": ["context"],
            },
            {
                "id": session_id,
                "status": "completed",
                "blueprint": blueprint,
                "turns": turns,
            },
            tmp_path,
        )
