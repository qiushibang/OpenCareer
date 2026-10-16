import json

import pytest

from extensions.career_mcp.domain.interviews import (
    InterviewValidationError,
    build_blueprint,
    compile_interview_artifacts,
    question_budget,
    validate_evaluation,
    validate_question,
    validate_transition,
)


NOW = "2026-08-10T16:00:00Z"
JOB = {
    "id": "job-1",
    "title": "大模型算法工程师",
    "company": {"slug": "deepseek", "name": "DeepSeek"},
    "status": "active",
    "source_url": "https://example.com/jobs/1",
    "description_raw": "负责大模型服务研发。",
    "responsibilities": ["负责大模型服务研发"],
    "requirements": ["熟悉 Python", "具备模型评测经验"],
}
RESUME_SECTIONS = {
    "project": [
        {
            "name": "OpenCareer",
            "highlights": ["使用 Python 构建服务"],
        }
    ]
}


def _blueprint() -> dict:
    return build_blueprint(
        JOB,
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=RESUME_SECTIONS,
    )


def _session() -> dict:
    return {
        "id": "interview-1",
        "job_id": "job-1",
        "resume_id": "resume-1",
        "conversation_id": "career-session-1",
        "company": "DeepSeek",
        "position": "大模型算法工程师",
        "difficulty": "standard",
        "duration_minutes": 15,
        "question_budget": 8,
        "blueprint": _blueprint(),
        "status": "in_progress",
        "phase": "evaluating",
        "version": 12,
        "started_at": "2026-08-10T15:30:00Z",
        "ended_at": None,
    }


def _legacy_blueprint() -> dict:
    return {
        "version": 1,
        "focus_areas": [
            {
                "requirement_id": "requirement-1",
                "evidence_paths": ["project[0].highlights[0]"],
            }
        ],
    }


def _v2_question(**overrides) -> dict:
    value = {
        "question": (
            "你正在应聘大模型算法工程师，请结合 OpenCareer 项目"
            "介绍你的个人职责。"
        ),
        "topic": "个人职责",
        "refs": ["project[0].highlights[0]"],
        "probe_target": "project[0]",
        "probe_dimension": "personal_contribution",
        "depth_level": 1,
    }
    value.update(overrides)
    return value


def _v2_blueprint_with_dimension(dimension: str) -> dict:
    blueprint = _blueprint()
    dimensions = blueprint["probe_plan"][0]["dimensions"]
    if dimension not in dimensions:
        dimensions.append(dimension)
    return blueprint


def _turns() -> list[dict]:
    questions = [
        "请介绍与你申请这个岗位最相关的一段经历？",
        "你在这个项目中具体负责什么？",
        "为什么选择这个技术方案？",
        "你如何验证项目结果有效？",
        "如果重新开始，你会调整什么？",
    ]
    answers = [
        "我负责基于 OpenWorker 构建本地求职 Agent。",
        "我们先分析需求，然后我负责岗位数据和简历匹配。",
        "因为已有 Agent Loop，我把精力放在求职领域能力。",
        "我通过 72 项测试和用户流程验证结果。",
        "我会更早建立验收门禁，减少后续返工的情况。",
    ]
    return [
        {
            "id": f"turn-{index}",
            "session_id": "interview-1",
            "turn_index": index,
            "question_text": question,
            "question_refs": (
                ["INTRO"]
                if index == 1
                else ["project[0].highlights[0]"]
            ),
            "answer_text": answer,
            "evaluation": {
                "relevance": 8,
                "clarity": 7,
                "structure": 6,
                "depth": 7,
                "evidence": 6,
                "issues": ["结果证据仍可更具体"],
                "coaching_structure": ["背景", "个人行动", "结果"],
                "fact_refs": ["project[0].highlights[0]"],
            },
            "next_action": (
                "WRAP_UP" if index == 5 else "FOLLOW_UP"
            ),
            "next_reason": "继续深挖上一轮回答",
            "started_at": f"2026-08-10T15:{index:02d}:00Z",
            "answered_at": f"2026-08-10T15:{index:02d}:30Z",
            "evaluated_at": f"2026-08-10T15:{index:02d}:40Z",
        }
        for index, (question, answer) in enumerate(
            zip(questions, answers),
            start=1,
        )
    ]


def test_question_budget_is_fixed():
    assert question_budget(10) == 5
    assert question_budget(15) == 5
    assert question_budget(20) == 5
    with pytest.raises(InterviewValidationError) as error:
        question_budget(30)
    assert error.value.code == "INVALID_INPUT"


def test_blueprint_uses_only_direct_job_and_resume_references():
    blueprint = _blueprint()

    assert blueprint["question_budget"] == 5
    assert blueprint["job_requirements"][0]["requirement_id"] == (
        "requirement-1"
    )
    assert blueprint["job_requirements"][1]["requirement_id"] == (
        "requirement-2"
    )
    assert "secret@example.com" not in str(blueprint)
    assert "13800001234" not in str(blueprint)
    assert "snapshot_id" not in str(blueprint)
    assert "snapshot_status" not in str(blueprint)
    assert "evidence_status" not in str(blueprint)
    assert "candidate_strengths" not in blueprint
    assert "candidate_risks" not in blueprint
    assert "must_probe" not in blueprint


def test_blueprint_extracts_requirements_from_official_job_description():
    job = {
        **JOB,
        "description_raw": (
            "部门：集团信息技术部\n\n"
            "岗位职责：1. 负责数字化产品全生命周期管理\n"
            "2. 推动跨团队合作落地\n\n"
            "任职要求：1. 5年及以上 B 端产品工作经验\n"
            "2. 具备完整的产品方法论\n"
            "3. 有 AI 产品落地经验者优先\n\n"
            "发布日期：2026-09-15\n\n岗位编码：A189018"
        ),
        "requirements": [],
    }

    blueprint = build_blueprint(
        job,
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=RESUME_SECTIONS,
    )

    assert [item["requirement"] for item in blueprint["job_requirements"]] == [
        "5年及以上 B 端产品工作经验",
        "具备完整的产品方法论",
        "有 AI 产品落地经验者优先",
    ]


@pytest.mark.parametrize(
    "trailer",
    [
        "学历要求：本科\n\n工作年限：3年",
        "更新时间：2026-09-15",
        "招聘人数：2\n\n职位编码：DD-1",
        "优先条件：有 AI 经验\n\n岗位亮点：弹性办公",
        "部门介绍：负责基础平台\n\n更新时间戳：123456",
        "职位 ID：BD-1\n\n招聘项目：社会招聘",
    ],
)
def test_blueprint_stops_before_official_job_metadata(trailer):
    job = {
        **JOB,
        "description_raw": (
            "岗位职责：负责平台建设\n\n"
            "岗位要求：1. 熟悉 Python\n2. 沟通良好\n\n"
            f"{trailer}"
        ),
        "requirements": [],
    }

    blueprint = build_blueprint(
        job,
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=RESUME_SECTIONS,
    )

    assert [item["requirement"] for item in blueprint["job_requirements"]] == [
        "熟悉 Python",
        "沟通良好",
    ]


def test_blueprint_extracts_requirement_section_without_colon():
    job = {
        **JOB,
        "description_raw": (
            "岗位职责\n负责大模型数据体系建设。\n\n"
            "岗位要求\n1. 具备数据处理经验\n2. 熟悉机器学习\n\n"
            "更新时间\n2026-09-15"
        ),
        "requirements": [],
    }

    blueprint = build_blueprint(
        job,
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=RESUME_SECTIONS,
    )

    assert [item["requirement"] for item in blueprint["job_requirements"]] == [
        "具备数据处理经验",
        "熟悉机器学习",
    ]


def test_blueprint_does_not_treat_requirement_prefixes_as_boundaries():
    job = {
        **JOB,
        "description_raw": (
            "岗位职责\n负责平台建设\n\n岗位要求\n"
            "1. 工作年限3年以上\n"
            "2. 部门协作能力强\n"
            "3. 工作地点可接受出差\n"
            "4. 学历要求本科及以上"
        ),
        "requirements": [],
    }

    blueprint = build_blueprint(
        job,
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=RESUME_SECTIONS,
    )

    assert [item["requirement"] for item in blueprint["job_requirements"]] == [
        "工作年限3年以上",
        "部门协作能力强",
        "工作地点可接受出差",
        "学历要求本科及以上",
    ]


def test_blueprint_v2_contains_grounded_interview_context():
    blueprint = build_blueprint(
        JOB,
        resume_id="resume-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections=RESUME_SECTIONS,
    )

    assert blueprint["version"] == 2
    assert blueprint["role_tracks"] == ["general"]
    assert blueprint["job_requirements"][0]["requirement_id"] == (
        "requirement-1"
    )
    assert blueprint["evidence_cards"][0]["excerpt"] == (
        "使用 Python 构建服务"
    )
    assert blueprint["probe_plan"][0]["target_id"] == "project[0]"
    assert "secret@example.com" not in str(blueprint)


def test_blueprint_rejects_incomplete_direct_sources():
    with pytest.raises(InterviewValidationError) as job_error:
        build_blueprint(
            {},
            resume_id="resume-1",
            difficulty="standard",
            duration_minutes=15,
            resume_sections=RESUME_SECTIONS,
        )
    assert job_error.value.code == "JOB_NOT_FOUND"

    with pytest.raises(InterviewValidationError) as resume_error:
        build_blueprint(
            JOB,
            resume_id="resume-1",
            difficulty="standard",
            duration_minutes=15,
            resume_sections={},
        )
    assert resume_error.value.code == "RESUME_NOT_FOUND"


def test_question_requires_one_allowed_reference():
    question = validate_question(
        {
            "question": "为什么选择这个技术方案？",
            "refs": ["project[0].highlights[0]"],
            "topic": "project_decision",
        },
        blueprint=_legacy_blueprint(),
        turn_index=2,
        previous_turns=[],
    )

    assert question["refs"] == ["project[0].highlights[0]"]


def test_question_rejects_two_requests_joined_under_one_question_mark():
    with pytest.raises(InterviewValidationError) as error:
        validate_question(
            {
                "question": (
                    "你好，请先简单介绍一下你自己，以及你为什么对 "
                    "AI Agent 工程师这个岗位感兴趣？"
                ),
                "refs": ["INTRO"],
                "topic": "self_introduction",
            },
            blueprint={"version": 1, "focus_areas": []},
            turn_index=1,
            previous_turns=[],
        )

    assert error.value.code == "QUESTION_VALIDATION_FAILED"


@pytest.mark.parametrize(
    "question",
    [
        {
            "question": "问题一？问题二？",
            "refs": ["requirement-1"],
            "topic": "list",
        },
        {
            "question": "重复问题？",
            "refs": ["unknown"],
            "topic": "unknown",
        },
        {
            "question": "太短",
            "refs": ["requirement-1"],
            "topic": "short",
        },
    ],
)
def test_question_rejects_lists_unknown_refs_and_bad_length(question):
    with pytest.raises(InterviewValidationError) as error:
        validate_question(
            question,
            blueprint=_legacy_blueprint(),
            turn_index=2,
            previous_turns=[{"question_text": "重复问题？"}],
        )
    assert error.value.code == "QUESTION_VALIDATION_FAILED"


def test_intro_reference_is_only_allowed_for_first_turn():
    first = validate_question(
        {
            "question": "请介绍与你申请岗位最相关的一段经历？",
            "refs": ["INTRO"],
            "topic": "self_introduction",
        },
        blueprint=_legacy_blueprint(),
        turn_index=1,
        previous_turns=[],
    )
    assert first["refs"] == ["INTRO"]

    with pytest.raises(InterviewValidationError):
        validate_question(
            {
                "question": "请再次介绍你自己？",
                "refs": ["INTRO"],
                "topic": "repeat_intro",
            },
            blueprint=_legacy_blueprint(),
            turn_index=2,
            previous_turns=[],
        )


def test_v2_first_question_uses_selected_fact_target_refs():
    validated = validate_question(
        _v2_question(),
        blueprint=_blueprint(),
        turn_index=1,
        previous_turns=[],
    )
    assert validated["probe_target"] == "project[0]"
    assert validated["depth_level"] == 1

    with pytest.raises(InterviewValidationError):
        validate_question(
            _v2_question(refs=["requirement-1"]),
            blueprint=_blueprint(),
            turn_index=1,
            previous_turns=[],
        )


def test_v2_first_question_must_name_position():
    with pytest.raises(InterviewValidationError) as error:
        validate_question(
            _v2_question(
                question="请结合 OpenCareer 项目介绍你的个人职责？"
            ),
            blueprint=_blueprint(),
            turn_index=1,
            previous_turns=[],
        )

    assert error.value.code == "QUESTION_VALIDATION_FAILED"


def test_v2_rejects_two_requests_split_by_a_period():
    with pytest.raises(InterviewValidationError) as error:
        validate_question(
            _v2_question(
                question=(
                    "请介绍你在 OpenCareer 项目中的角色和背景。"
                    "这个项目解决了什么问题，你具体负责哪些部分？"
                )
            ),
            blueprint=_blueprint(),
            turn_index=1,
            previous_turns=[],
        )

    assert error.value.code == "QUESTION_VALIDATION_FAILED"


def test_v2_rejects_parallel_requests_for_different_dimensions():
    with pytest.raises(InterviewValidationError) as error:
        validate_question(
            _v2_question(
                question=(
                    "请介绍你参与的推理服务优化项目背景，以及你作为"
                    "大模型算法工程师具体负责的工作"
                ),
                probe_dimension="context",
            ),
            blueprint=_blueprint(),
            turn_index=1,
            previous_turns=[],
        )

    assert str(error.value) == (
        "question text spans multiple probe dimensions"
    )


@pytest.mark.parametrize(
    ("question", "dimension"),
    [
        (
            "你正在应聘大模型算法工程师，请说明整体架构，"
            "并介绍如何优化 P95 延迟",
            "architecture",
        ),
        (
            "你正在应聘大模型算法工程师，请说明产品策略，"
            "同时介绍你定义的成功指标",
            "strategy",
        ),
    ],
)
def test_v2_rejects_other_cross_dimension_requests(
    question,
    dimension,
):
    with pytest.raises(InterviewValidationError):
        validate_question(
            _v2_question(
                question=question,
                probe_dimension=dimension,
            ),
            blueprint=_v2_blueprint_with_dimension(dimension),
            turn_index=1,
            previous_turns=[],
        )


@pytest.mark.parametrize(
    ("question", "dimension"),
    [
        (
            "你正在应聘大模型算法工程师，请介绍项目背景"
            "以及当时的业务约束",
            "context",
        ),
        (
            "你正在应聘大模型算法工程师，请说明你负责的模块"
            "和个人决策",
            "personal_contribution",
        ),
        (
            "你正在应聘大模型算法工程师，请说明如何降低延迟"
            "并提升吞吐量",
            "performance",
        ),
    ],
)
def test_v2_allows_parallel_details_within_one_dimension(
    question,
    dimension,
):
    validated = validate_question(
        _v2_question(
            question=question,
            probe_dimension=dimension,
        ),
        blueprint=_v2_blueprint_with_dimension(dimension),
        turn_index=1,
        previous_turns=[],
    )

    assert validated["probe_dimension"] == dimension


def test_v1_keeps_legacy_single_sentence_behavior():
    validated = validate_question(
        {
            "question": "请介绍项目背景以及你具体负责的工作",
            "refs": ["INTRO"],
            "topic": "legacy",
        },
        blueprint={"version": 1, "focus_areas": []},
        turn_index=1,
        previous_turns=[],
    )

    assert validated["topic"] == "legacy"


def test_v2_deep_dive_keeps_target_and_advances_one_depth():
    previous = [
        {
            "question_text": "第一题",
            "probe_target": "project[0]",
            "probe_dimension": "personal_contribution",
            "depth_level": 1,
        }
    ]
    validated = validate_question(
        _v2_question(
            question="你如何实现这个项目的核心服务？",
            probe_dimension="implementation",
            depth_level=2,
        ),
        blueprint=_blueprint(),
        turn_index=2,
        previous_turns=previous,
        next_action="DEEP_DIVE",
    )
    assert validated["depth_level"] == 2

    with pytest.raises(InterviewValidationError):
        validate_question(
            _v2_question(
                question="请直接说明第三层实现细节？",
                probe_dimension="performance",
                depth_level=3,
            ),
            blueprint=_blueprint(),
            turn_index=2,
            previous_turns=previous,
            next_action="DEEP_DIVE",
        )


def test_v2_switch_topic_requires_new_target_at_depth_one():
    with pytest.raises(InterviewValidationError):
        validate_question(
            _v2_question(
                question="请切换到另一个主题继续说明？",
                depth_level=2,
            ),
            blueprint=_blueprint(),
            turn_index=2,
            previous_turns=[
                {
                    "question_text": "第一题",
                    "probe_target": "project[0]",
                    "probe_dimension": "context",
                    "depth_level": 1,
                }
            ],
            next_action="SWITCH_TOPIC",
        )


def test_v2_no_evidence_rejects_fabricated_experience_wording():
    blueprint = {
        "version": 2,
        "evidence_cards": [],
        "probe_plan": [
            {
                "target_id": "requirement-1",
                "target_type": "job_requirement",
                "refs": ["requirement-1"],
                "dimensions": ["evaluation"],
                "max_depth": 1,
            }
        ],
    }
    validated = validate_question(
        {
            "question": "你会如何设计一个模型效果评测方案？",
            "topic": "岗位场景",
            "refs": ["requirement-1"],
            "probe_target": "requirement-1",
            "probe_dimension": "evaluation",
            "depth_level": 1,
        },
        blueprint=blueprint,
        turn_index=1,
        previous_turns=[],
    )
    assert validated["probe_target"] == "requirement-1"

    with pytest.raises(InterviewValidationError):
        validate_question(
            {
                **validated,
                "question": "请结合你的经历说明如何评测模型效果？",
            },
            blueprint=blueprint,
            turn_index=1,
            previous_turns=[],
        )


def test_v2_resume_cards_can_ground_first_question_without_matching():
    blueprint = {
        "version": 2,
        "position": "后端研发工程师",
        "evidence_cards": [
            {
                "fact_path": "project[0].highlights[0]",
                "excerpt": "实现本地服务",
                "requirement_ids": [],
            }
        ],
        "probe_plan": [
            {
                "target_id": "project[0]",
                "target_type": "resume_project",
                "refs": ["project[0].highlights[0]"],
                "dimensions": ["implementation"],
                "max_depth": 3,
            },
            {
                "target_id": "requirement-1",
                "target_type": "job_requirement",
                "refs": ["requirement-1"],
                "dimensions": ["architecture"],
                "max_depth": 2,
            },
        ],
    }

    validated = validate_question(
        {
            "question": "应聘后端研发工程师时你在该项目中负责什么？",
            "topic": "项目职责",
            "refs": ["project[0].highlights[0]"],
            "probe_target": "project[0]",
            "probe_dimension": "implementation",
            "depth_level": 1,
        },
        blueprint=blueprint,
        turn_index=1,
        previous_turns=[],
    )

    assert validated["probe_target"] == "project[0]"


def test_evaluation_is_bounded_and_grounded():
    with pytest.raises(InterviewValidationError):
        validate_evaluation(
        {
            "relevance": 8,
            "clarity": 7,
            "structure": 6,
            "depth": 8,
            "evidence": 5,
            "issues": ["结果证据不足"],
            "coaching_structure": ["背景", "个人行动", "结果"],
            "fact_refs": ["project[0].highlights[0]"],
        },
        allowed_refs={"project[0].highlights[0]"},
    )


def test_evaluation_v2_uses_template_weights_and_ignores_model_score():
    result = validate_evaluation(
        {
            "version": 2,
            "question_type": "past_behavior",
            "target_competency": "product_judgment",
            "active_dimensions": [
                {
                    "name": "relevance",
                    "level": 4,
                    "evidence": ["我先确认了目标用户"],
                    "missing_evidence": "",
                },
                {
                    "name": "specificity",
                    "level": 3,
                    "evidence": ["访谈了三类用户"],
                    "missing_evidence": "样本口径",
                },
                {
                    "name": "ownership",
                    "level": 2,
                    "evidence": ["我负责需求排序"],
                    "missing_evidence": "决策依据",
                },
                {
                    "name": "outcome",
                    "level": 1,
                    "evidence": [],
                    "missing_evidence": "结果和验证方式",
                },
            ],
            "question_score": 100,
            "primary_pain": "结果无法验证",
            "reason": "说明了行动，但没有结果或验证方式。",
            "improvement": "补充结果、口径和验证方式。",
            "fact_refs": ["project[0].highlights[0]"],
            "recommended_action": "FOLLOW_UP",
        },
        allowed_refs={"project[0].highlights[0]"},
        expected_target="product_judgment",
        answer_text=(
            "我先确认了目标用户，访谈了三类用户，"
            "我负责需求排序。"
        ),
    )

    assert result["version"] == 2
    assert result["question_score"] == 63


def test_evaluation_v2_rejects_evidence_not_in_the_answer():
    value = {
        "version": 2,
        "question_type": "past_behavior",
        "target_competency": "ownership",
        "active_dimensions": [
            {
                "name": "relevance",
                "level": 2,
                "evidence": ["我把转化率提升了 30%"],
                "missing_evidence": "",
            },
            {
                "name": "specificity",
                "level": 1,
                "evidence": [],
                "missing_evidence": "缺少具体行动",
            },
            {
                "name": "ownership",
                "level": 1,
                "evidence": [],
                "missing_evidence": "缺少个人贡献",
            },
            {
                "name": "outcome",
                "level": 0,
                "evidence": [],
                "missing_evidence": "缺少结果",
            },
        ],
        "primary_pain": "证据不足",
        "reason": "回答没有提供可验证结果。",
        "improvement": "补充本人行动和结果口径。",
        "fact_refs": [],
        "recommended_action": "FOLLOW_UP",
    }

    with pytest.raises(InterviewValidationError):
        validate_evaluation(
            value,
            allowed_refs=set(),
            expected_target="ownership",
            answer_text="我们做了一些优化。",
        )


def test_evaluation_v2_rejects_a_different_probe_target():
    value = {
        "version": 2,
        "question_type": "past_behavior",
        "target_competency": "strategy",
        "active_dimensions": [
            {
                "name": "relevance",
                "level": 1,
                "evidence": ["我负责需求排序"],
                "missing_evidence": "",
            },
            {
                "name": "specificity",
                "level": 1,
                "evidence": [],
                "missing_evidence": "缺少细节",
            },
            {
                "name": "ownership",
                "level": 1,
                "evidence": ["我负责需求排序"],
                "missing_evidence": "",
            },
            {
                "name": "outcome",
                "level": 0,
                "evidence": [],
                "missing_evidence": "缺少结果",
            },
        ],
        "primary_pain": "结果不足",
        "reason": "没有结果。",
        "improvement": "补充结果。",
        "fact_refs": [],
        "recommended_action": "FOLLOW_UP",
    }

    with pytest.raises(InterviewValidationError):
        validate_evaluation(
            value,
            allowed_refs=set(),
            expected_target="ownership",
            answer_text="我负责需求排序。",
        )


def test_evaluation_v2_rejects_a_dimension_outside_the_template():
    value = {
        "version": 2,
        "question_type": "technical_knowledge",
        "target_competency": "technical_correctness",
        "active_dimensions": [
            {
                "name": "ownership",
                "level": 2,
                "evidence": [],
                "missing_evidence": "个人职责",
            }
        ],
        "primary_pain": "缺少证据",
        "reason": "当前无法判断。",
        "improvement": "补充依据。",
        "fact_refs": [],
        "recommended_action": "FOLLOW_UP",
    }

    with pytest.raises(InterviewValidationError):
        validate_evaluation(value, allowed_refs=set())


def test_evaluation_error_lists_allowed_question_types():
    with pytest.raises(InterviewValidationError) as error:
        validate_evaluation(
            {
                "version": 2,
                "question_type": "project",
            },
            allowed_refs=set(),
        )

    assert error.value.code == "EVALUATION_VALIDATION_FAILED"
    assert str(error.value) == (
        "question_type must be one of: past_behavior, product_case, "
        "technical_knowledge, coding, system_design, ai_ml_case, "
        "failure_reflection"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"relevance": 11},
        {"fact_refs": ["other-resume.fact"]},
        {"issues": ["候选人有 100% 录用概率"]},
        {"issues": ["联系候选人 13800001234"]},
    ],
)
def test_evaluation_rejects_invalid_scores_refs_and_conclusions(change):
    value = {
        "relevance": 8,
        "clarity": 7,
        "structure": 6,
        "depth": 8,
        "evidence": 5,
        "issues": ["结果证据不足"],
        "coaching_structure": ["背景", "个人行动", "结果"],
        "fact_refs": ["project[0].highlights[0]"],
        **change,
    }
    with pytest.raises(InterviewValidationError) as error:
        validate_evaluation(
            value,
            allowed_refs={"project[0].highlights[0]"},
        )
    assert error.value.code == "EVALUATION_VALIDATION_FAILED"


def test_session_requires_five_turns_before_agent_wrap_up():
    with pytest.raises(InterviewValidationError):
        validate_transition(
            status="in_progress",
            phase="evaluating",
            event="WRAP_UP",
            answered_turns=4,
            question_budget=8,
            user_requested=False,
        )
    assert validate_transition(
        status="in_progress",
        phase="evaluating",
        event="WRAP_UP",
        answered_turns=4,
        question_budget=8,
        user_requested=True,
    ) == ("in_progress", "generating_report")


def test_question_budget_forces_wrap_up():
    assert validate_transition(
        status="in_progress",
        phase="evaluating",
        event="WRAP_UP",
        answered_turns=8,
        question_budget=8,
        user_requested=False,
    ) == ("in_progress", "generating_report")
    with pytest.raises(InterviewValidationError):
        validate_transition(
            status="in_progress",
            phase="evaluating",
            event="FOLLOW_UP",
            answered_turns=8,
            question_budget=8,
            user_requested=False,
        )


def test_report_compiler_emits_three_private_safe_artifacts():
    turns = _turns()
    turns[0]["answer_text"] = (
        "我负责数据清洗。我负责数据清洗。"
    )
    artifacts = compile_interview_artifacts(
        _session(),
        turns,
        generated_at=NOW,
    )

    assert set(artifacts) == {
        "transcript.md",
        "interview-report.md",
        "session.json",
    }
    report = artifacts["interview-report.md"]
    assert "## 逐题复盘" in report
    assert "训练反馈，不代表录用概率" in report
    assert "平均回答长度" in report
    assert "然后：1 次" in report
    assert "我们：1 次" in report
    assert "重复表达：1 次" in report
    assert "偏题程度：2.0/10" in report
    assert "STAR/结构完整度：6.0/10" in report
    assert (
        "参考优化：按“背景 → 个人行动 → 结果”重组原回答"
        in report
    )
    assert "72" in report
    assert "secret@example.com" not in str(artifacts)
    assert "13800001234" not in str(artifacts)

    session_json = json.loads(artifacts["session.json"])
    assert session_json["id"] == "interview-1"
    assert "evaluation" not in session_json
    assert "audio" not in str(session_json).lower()


def test_report_compiler_uses_single_score_for_v2_turns():
    turns = _turns()
    for turn in turns:
        turn["evaluation"] = {
            "version": 2,
            "question_type": "past_behavior",
            "target_competency": "ownership",
            "active_dimensions": [
                {
                    "name": "relevance",
                    "level": 3,
                    "evidence": ["我负责岗位数据"],
                    "missing_evidence": "",
                }
            ],
            "question_score": 75,
            "primary_pain": "个人贡献不够具体",
            "reason": "说明了职责，但没有交代关键决策。",
            "improvement": "补充本人做出的关键决策。",
            "fact_refs": [],
            "recommended_action": "FOLLOW_UP",
        }

    report = compile_interview_artifacts(
        _session(),
        turns,
        generated_at=NOW,
    )["interview-report.md"]

    assert "本题得分：75/100" in report
    assert "主要痛点：个人贡献不够具体" in report
    assert "原因：说明了职责，但没有交代关键决策。" in report
    assert "优化策略：补充本人做出的关键决策。" in report
    assert "## 能力维度评价" not in report
    assert "STAR/结构完整度" not in report


def test_report_compiler_handles_mixed_historical_evaluations():
    turns = _turns()
    turns[1]["evaluation"] = {
        "version": 2,
        "question_type": "past_behavior",
        "target_competency": "ownership",
        "active_dimensions": [],
        "question_score": 50,
        "primary_pain": "证据不足",
        "reason": "缺少个人行动。",
        "improvement": "补充个人行动。",
        "fact_refs": [],
        "recommended_action": "FOLLOW_UP",
    }

    report = compile_interview_artifacts(
        _session(),
        turns,
        generated_at=NOW,
    )["interview-report.md"]

    assert "本题得分" in report
    assert "历史五维评价" in report
