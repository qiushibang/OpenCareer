"""Pure contracts and artifact compilation for Career mock interviews."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter

from .interview_intelligence import (
    build_evidence_cards,
    build_probe_plan,
)
from .privacy import contains_sensitive_value

DIFFICULTIES = ("simple", "standard", "deep")
DURATION_QUESTION_BUDGET = {10: 5, 15: 8, 20: 10}
NEXT_ACTIONS = (
    "FOLLOW_UP",
    "VERIFY_CLAIM",
    "DEEP_DIVE",
    "SWITCH_TOPIC",
    "WRAP_UP",
)
SCORE_FIELDS = (
    "relevance",
    "clarity",
    "structure",
    "depth",
    "evidence",
)
EVALUATION_V2_TEMPLATES = {
    "past_behavior": {
        "required": {"relevance", "specificity", "ownership", "outcome"},
        "optional": {"reasoning", "reflection", "clarity"},
    },
    "product_case": {
        "required": {
            "relevance",
            "product_problem",
            "reasoning",
            "prioritization",
            "validation",
        },
        "optional": {"tradeoff", "clarity"},
    },
    "technical_knowledge": {
        "required": {"relevance", "technical_correctness", "clarity"},
        "optional": {"boundary", "tradeoff"},
    },
    "coding": {
        "required": {
            "relevance",
            "technical_correctness",
            "testing",
            "boundary",
        },
        "optional": {"complexity", "clarity"},
    },
    "system_design": {
        "required": {"relevance", "architecture", "tradeoff", "reliability"},
        "optional": {"scale", "evolution", "clarity"},
    },
    "ai_ml_case": {
        "required": {"relevance", "problem_formulation", "data", "evaluation"},
        "optional": {"baseline", "error_analysis", "deployment"},
    },
    "failure_reflection": {
        "required": {"relevance", "ownership", "diagnosis", "reflection"},
        "optional": {"outcome", "clarity"},
    },
}
_FORBIDDEN_CONCLUSION = re.compile(
    r"(?:匹配率|录用概率|符合岗位资格|不符合岗位资格|胜任岗位)"
)
_COMPOUND_QUESTION = re.compile(
    r"[，,；;]\s*(?:以及|并且|同时|另外|此外|还)\s*"
    r"(?:请|你|您)*(?:为什么|为何|怎么|如何|什么|哪(?:个|些)?|"
    r"是否|能否|可以|介绍|说明|描述|谈谈)"
)
_PARALLEL_REQUEST_SPLIT = re.compile(
    r"(?:，|,)?\s*(?:以及|并且|同时|另外|此外|还要|"
    r"并(?=说明|介绍|描述|分析|解释|谈谈|给出|如何|怎么|"
    r"提升|降低))\s*"
)
_REQUIREMENTS_HEADING = re.compile(
    r"(?:^|\n)[ \t]*(?:任职要求|岗位要求|职位要求|任职资格|任职条件)"
    r"(?:[ \t]*[：:][ \t]*|[ \t]*(?=\n|$))"
)
_SECTION_BOUNDARY = re.compile(
    r"(?:^|\n)[ \t]*(?:岗位职责|工作职责|职位描述|部门|发布日期|"
    r"岗位编码|职位编码|职位\s*ID|招聘项目|工作地点|学历要求|"
    r"工作年限|招聘人数|优先条件|岗位亮点|部门介绍|更新时间|"
    r"更新时间戳|薪资福利|福利待遇)"
    r"(?:[ \t]*[：:][ \t]*|[ \t]*(?=\n|$))"
)
_NUMBERED_ITEM = re.compile(r"(?:^|\n)\s*\d{1,2}[.)、．]\s*")
_DIMENSION_INTENT_PATTERNS = {
    "context": re.compile(
        r"背景|业务场景|业务约束|启动原因|问题来源"
    ),
    "personal_contribution": re.compile(
        r"(?:你|个人).{0,8}(?:负责|职责|贡献|承担|主导|决策)|"
        r"具体负责"
    ),
    "architecture": re.compile(
        r"整体架构|系统架构|架构设计|模块划分"
    ),
    "implementation": re.compile(
        r"代码实现|实现细节|如何实现|怎么实现"
    ),
    "performance": re.compile(
        r"性能|p\d{2,3}\s*延迟|延迟|吞吐"
    ),
    "strategy": re.compile(r"产品策略|策略选择|战略"),
    "metrics": re.compile(
        r"成功指标|衡量指标|指标体系|北极星指标"
    ),
    "evaluation": re.compile(r"评测|验证效果|效果验证"),
    "user_problem": re.compile(r"用户问题|用户痛点|用户需求"),
    "feature_design": re.compile(r"功能设计|交互设计|产品方案"),
    "tradeoff": re.compile(r"取舍|权衡"),
    "result": re.compile(r"最终结果|项目成果|业务结果"),
}
_DIMENSION_INTENT_COMPATIBILITY = {
    "optimization": {"performance"},
    "inference": {"performance"},
    "business_tradeoff": {"tradeoff"},
}
_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"(?<!\w)\d+(?:\.\d+)?%?(?!\w)")
_CLAUSE_SPLIT = re.compile(r"[。！？!?；;，,\n]+")
_FILLERS = ("然后", "就是", "其实", "我觉得")


class InterviewValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def question_budget(duration_minutes: int) -> int:
    if (
        not isinstance(duration_minutes, int)
        or isinstance(duration_minutes, bool)
        or duration_minutes not in DURATION_QUESTION_BUDGET
    ):
        raise InterviewValidationError(
            "INVALID_INPUT",
            "duration_minutes must be 10, 15, or 20",
        )
    return 5


def _requirements_from_job(job: dict) -> list[object]:
    requirements = job.get("requirements")
    if isinstance(requirements, list) and requirements:
        return requirements

    raw_description = job.get("description_raw")
    description = (
        raw_description.strip()
        if isinstance(raw_description, str)
        else ""
    )
    heading = _REQUIREMENTS_HEADING.search(description)
    if heading is None:
        return []
    section = description[heading.end() :]
    boundary = _SECTION_BOUNDARY.search(section)
    if boundary is not None:
        section = section[: boundary.start()]

    numbered = _NUMBERED_ITEM.split(section)
    candidates = numbered[1:] if len(numbered) > 1 else section.splitlines()
    parsed: list[object] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = re.sub(r"^(?:[-*•])\s*", "", candidate).strip()
        value = _text(value)
        if value and value not in seen:
            parsed.append(value)
            seen.add(value)
    return parsed


def build_blueprint(
    job: dict,
    *,
    resume_id: str,
    difficulty: str,
    duration_minutes: int,
    resume_sections: dict,
) -> dict:
    if difficulty not in DIFFICULTIES:
        raise InterviewValidationError(
            "INVALID_INPUT",
            "difficulty must be simple, standard, or deep",
        )
    budget = question_budget(duration_minutes)
    if (
        not isinstance(job, dict)
        or not _text(job.get("id"))
        or not _text(job.get("title"))
    ):
        raise InterviewValidationError(
            "JOB_NOT_FOUND",
            "job is not available",
        )
    requirements = _requirements_from_job(job)
    if not requirements:
        raise InterviewValidationError(
            "INVALID_INPUT",
            "job has no requirements",
        )
    if not isinstance(resume_sections, dict) or not resume_sections:
        raise InterviewValidationError(
            "RESUME_NOT_FOUND",
            "confirmed resume sections are unavailable",
        )

    job_requirements: list[dict] = []
    for index, requirement in enumerate(requirements, start=1):
        text = _text(
            requirement.get("requirement")
            if isinstance(requirement, dict)
            else requirement
        )
        if not text:
            raise InterviewValidationError(
                "INVALID_INPUT",
                "job requirement must be non-empty",
            )
        job_requirements.append(
            {
                "requirement_id": f"requirement-{index}",
                "requirement": text,
            }
        )

    company = job.get("company")
    role_tracks = ["general"]
    evidence_cards = build_evidence_cards(resume_sections)
    probe_plan = build_probe_plan(
        role_tracks=role_tracks,
        requirements=job_requirements,
        evidence_cards=evidence_cards,
        difficulty=difficulty,
        question_budget=budget,
    )
    return {
        "version": 2,
        "company": _text(
            company.get("name") if isinstance(company, dict) else ""
        ),
        "position": _text(job.get("title")),
        "difficulty": difficulty,
        "duration_minutes": duration_minutes,
        "question_budget": budget,
        "role_tracks": role_tracks,
        "job_requirements": job_requirements,
        "evidence_cards": evidence_cards,
        "probe_plan": probe_plan,
    }


def blueprint_refs(blueprint: dict) -> set[str]:
    if blueprint.get("version") == 2:
        return {
            value
            for target in blueprint.get("probe_plan", [])
            if isinstance(target, dict)
            for value in target.get("refs", [])
            if isinstance(value, str) and value
        }
    refs: set[str] = set()
    for area in blueprint.get("focus_areas", []):
        if not isinstance(area, dict):
            continue
        requirement_id = area.get("requirement_id")
        if isinstance(requirement_id, str) and requirement_id:
            refs.add(requirement_id)
        for path in area.get("evidence_paths", []):
            if isinstance(path, str) and path:
                refs.add(path)
    return refs


def validate_question(
    proposal: object,
    *,
    blueprint: dict,
    turn_index: int,
    previous_turns: list[dict],
    next_action: str | None = None,
) -> dict:
    if not isinstance(proposal, dict):
        _question_error("question proposal must be an object")
    if not isinstance(blueprint, dict):
        _question_error("question blueprint must be an object")
    question = _text(proposal.get("question"))
    topic = _text(proposal.get("topic"))
    refs = proposal.get("refs")
    if not 5 <= len(question) <= 200:
        _question_error("question must contain between 5 and 200 characters")
    if not 1 <= len(topic) <= 80:
        _question_error("question topic is invalid")
    if (
        question.count("?") + question.count("？") > 1
        or _COMPOUND_QUESTION.search(question)
        or len(
            [
                clause
                for clause in re.split(r"[。！？!?；;\n]+", question)
                if clause.strip()
            ]
        )
        > 1
    ):
        _question_error("question proposal contains multiple questions")
    if contains_sensitive_value(question):
        _question_error("question contains a sensitive value")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 5:
        _question_error("question requires between one and five references")
    if not all(isinstance(value, str) and value.strip() for value in refs):
        _question_error("question references must be non-empty strings")
    normalized_refs = [value.strip() for value in refs]
    if len(set(normalized_refs)) != len(normalized_refs):
        _question_error("question references must be unique")
    allowed_refs = blueprint_refs(blueprint)
    if blueprint.get("version") != 2:
        if "INTRO" in normalized_refs:
            if turn_index != 1 or normalized_refs != ["INTRO"]:
                _question_error(
                    "INTRO is allowed only for the first question"
                )
        elif any(value not in allowed_refs for value in normalized_refs):
            _question_error("question contains an unknown reference")
    elif any(value not in allowed_refs for value in normalized_refs):
        _question_error("question contains an unknown reference")
    normalized_question = _normalized(question)
    if normalized_question in {
        _normalized(turn.get("question_text"))
        for turn in previous_turns
        if isinstance(turn, dict)
    }:
        _question_error("question duplicates an earlier turn")
    result = {
        "question": question,
        "refs": normalized_refs,
        "topic": topic,
    }
    if blueprint.get("version") != 2:
        return result

    targets = {
        item["target_id"]: item
        for item in blueprint.get("probe_plan", [])
        if isinstance(item, dict)
        and isinstance(item.get("target_id"), str)
    }
    probe_target = _text(proposal.get("probe_target"))
    probe_dimension = _text(proposal.get("probe_dimension"))
    depth_level = proposal.get("depth_level")
    target = targets.get(probe_target)
    if target is None:
        _question_error("question contains an unknown probe target")
    if probe_dimension not in target.get("dimensions", []):
        _question_error("question contains an unknown probe dimension")
    _validate_single_dimension_question(
        question,
        probe_dimension,
    )
    if (
        not isinstance(depth_level, int)
        or isinstance(depth_level, bool)
        or not 1 <= depth_level <= int(target.get("max_depth", 0))
    ):
        _question_error("question depth is outside the probe plan")
    if any(ref not in target.get("refs", []) for ref in normalized_refs):
        _question_error("question refs are outside the probe target")

    evidence_paths = {
        card["fact_path"]
        for card in blueprint.get("evidence_cards", [])
        if isinstance(card, dict)
        and isinstance(card.get("fact_path"), str)
    }
    if turn_index == 1:
        if depth_level != 1:
            _question_error("first question must start at depth one")
        position = _text(blueprint.get("position"))
        if position and _normalized(position) not in normalized_question:
            _question_error("first question must name the target position")
        if evidence_paths:
            if (
                target.get("target_type")
                not in {"resume_project", "resume_work"}
                or not any(
                    ref in evidence_paths for ref in normalized_refs
                )
            ):
                _question_error(
                    "first question requires a resume fact target"
                )
        else:
            if (
                target.get("target_type") != "job_requirement"
                or any(
                    not ref.startswith("requirement-")
                    for ref in normalized_refs
                )
            ):
                _question_error(
                    "first question without evidence must use a job target"
                )
            if re.search(
                r"(?:结合|根据)你的(?:项目|经历|简历)|"
                r"你在(?:该|这个)?项目中",
                question,
            ):
                _question_error(
                    "question implies unavailable resume evidence"
                )
    else:
        if not previous_turns or next_action not in NEXT_ACTIONS:
            _question_error("next question requires previous turn and action")
        previous = previous_turns[-1]
        previous_target = previous.get("probe_target")
        previous_depth = previous.get("depth_level")
        if next_action in {"FOLLOW_UP", "VERIFY_CLAIM", "DEEP_DIVE"}:
            if (
                probe_target != previous_target
                or not isinstance(previous_depth, int)
                or depth_level != previous_depth + 1
            ):
                _question_error(
                    "deepening must keep target and advance one depth"
                )
        elif next_action == "SWITCH_TOPIC":
            if probe_target == previous_target or depth_level != 1:
                _question_error(
                    "topic switch requires a new target at depth one"
                )
        else:
            _question_error("wrap up cannot create a next question")

    return {
        **result,
        "probe_target": probe_target,
        "probe_dimension": probe_dimension,
        "depth_level": depth_level,
    }


def validate_evaluation(
    value: object,
    *,
    allowed_refs: set[str],
    expected_target: str | None = None,
    answer_text: str | None = None,
) -> dict:
    if not isinstance(value, dict):
        _evaluation_error("evaluation must be an object")
    if value.get("version") != 2:
        _evaluation_error("new evaluations must use version 2")
    return _validate_evaluation_v2(
        value,
        allowed_refs=allowed_refs,
        expected_target=expected_target,
        answer_text=answer_text,
    )


def _validate_evaluation_v2(
    value: dict,
    *,
    allowed_refs: set[str],
    expected_target: str | None,
    answer_text: str | None,
) -> dict:
    question_type = _text(value.get("question_type"))
    template = EVALUATION_V2_TEMPLATES.get(question_type)
    if template is None:
        _evaluation_error(
            "question_type must be one of: "
            + ", ".join(EVALUATION_V2_TEMPLATES)
        )
    target_competency = _text(value.get("target_competency"))
    if not 1 <= len(target_competency) <= 80:
        _evaluation_error("target_competency is invalid")
    if expected_target is not None and target_competency != expected_target:
        _evaluation_error("target_competency does not match the current probe")
    normalized_answer = _normalized(answer_text or "")
    raw_dimensions = value.get("active_dimensions")
    if not isinstance(raw_dimensions, list) or not raw_dimensions:
        _evaluation_error("active_dimensions is invalid")
    allowed_dimensions = template["required"] | template["optional"]
    dimensions: list[dict] = []
    names: set[str] = set()
    weighted_total = 0
    maximum_total = 0
    for raw in raw_dimensions:
        if not isinstance(raw, dict):
            _evaluation_error("active dimension must be an object")
        name = _text(raw.get("name"))
        level = raw.get("level")
        if (
            name not in allowed_dimensions
            or name in names
            or not isinstance(level, int)
            or isinstance(level, bool)
            or not 0 <= level <= 4
        ):
            _evaluation_error("active dimension is invalid")
        evidence = _text_list(
            raw.get("evidence"),
            field="dimension evidence",
            minimum=0,
            maximum=5,
        )
        missing = _text(raw.get("missing_evidence"))
        if len(missing) > 240:
            _evaluation_error("missing_evidence is invalid")
        if not evidence and not missing:
            _evaluation_error(
                "dimension requires evidence or missing_evidence"
            )
        if answer_text is not None and any(
            _normalized(quote) not in normalized_answer
            for quote in evidence
        ):
            _evaluation_error(
                "dimension evidence must quote the current answer"
            )
        weight = 2 if name in template["required"] else 1
        weighted_total += level * weight
        maximum_total += 4 * weight
        names.add(name)
        dimensions.append(
            {
                "name": name,
                "level": level,
                "evidence": evidence,
                "missing_evidence": missing,
            }
        )
    if not template["required"] <= names:
        _evaluation_error("required evaluation dimension is missing")
    refs = _text_list(
        value.get("fact_refs"),
        field="fact_refs",
        minimum=0,
        maximum=10,
    )
    if len(set(refs)) != len(refs) or any(
        ref not in allowed_refs for ref in refs
    ):
        _evaluation_error("evaluation contains an unknown fact reference")
    primary_pain = _bounded_evaluation_text(
        value.get("primary_pain"), "primary_pain", 120
    )
    reason = _bounded_evaluation_text(value.get("reason"), "reason", 500)
    improvement = _bounded_evaluation_text(
        value.get("improvement"), "improvement", 300
    )
    action = _text(value.get("recommended_action"))
    if action not in NEXT_ACTIONS:
        _evaluation_error("recommended_action is invalid")
    public_text = "\n".join(
        [
            primary_pain,
            reason,
            improvement,
            *(item for dimension in dimensions for item in dimension["evidence"]),
            *(dimension["missing_evidence"] for dimension in dimensions),
        ]
    )
    if (
        contains_sensitive_value(public_text)
        or _FORBIDDEN_CONCLUSION.search(public_text)
    ):
        _evaluation_error("evaluation contains forbidden content")
    score = (weighted_total * 100 + maximum_total // 2) // maximum_total
    return {
        "version": 2,
        "question_type": question_type,
        "target_competency": target_competency,
        "active_dimensions": dimensions,
        "question_score": score,
        "primary_pain": primary_pain,
        "reason": reason,
        "improvement": improvement,
        "fact_refs": refs,
        "recommended_action": action,
    }


def _bounded_evaluation_text(
    value: object,
    field: str,
    maximum: int,
) -> str:
    text = _text(value)
    if not 1 <= len(text) <= maximum:
        _evaluation_error(f"{field} is invalid")
    return text


def validate_transition(
    *,
    status: str,
    phase: str,
    event: str,
    answered_turns: int,
    question_budget: int,
    user_requested: bool = False,
) -> tuple[str, str]:
    if (
        status != "in_progress"
        or phase != "evaluating"
        or event not in NEXT_ACTIONS
        or not isinstance(answered_turns, int)
        or not 0 <= answered_turns <= question_budget
    ):
        raise InterviewValidationError(
            "INTERVIEW_STATE_CONFLICT",
            "interview transition is invalid",
        )
    if answered_turns >= question_budget and event != "WRAP_UP":
        raise InterviewValidationError(
            "INTERVIEW_STATE_CONFLICT",
            "question budget requires wrap up",
        )
    if event == "WRAP_UP":
        if answered_turns < 5 and not user_requested:
            raise InterviewValidationError(
                "INTERVIEW_STATE_CONFLICT",
                "agent cannot wrap up before five answered turns",
            )
        return "in_progress", "generating_report"
    return "in_progress", "asking"


def compile_interview_artifacts(
    session: dict,
    turns: list[dict],
    *,
    generated_at: str,
) -> dict[str, str]:
    if not isinstance(session, dict) or not isinstance(turns, list):
        raise InterviewValidationError(
            "REPORT_VALIDATION_FAILED",
            "session and turns are required",
        )
    ordered = sorted(turns, key=lambda item: int(item["turn_index"]))
    if not ordered or any(not item.get("answer_text") for item in ordered):
        raise InterviewValidationError(
            "REPORT_VALIDATION_FAILED",
            "all report turns must have answers",
        )
    transcript = _compile_transcript(session, ordered)
    report = _compile_report(session, ordered, generated_at)
    public_session = {
        key: session.get(key)
        for key in (
            "id",
            "job_id",
            "resume_id",
            "snapshot_id",
            "conversation_id",
            "company",
            "position",
            "difficulty",
            "duration_minutes",
            "question_budget",
            "status",
            "started_at",
            "ended_at",
        )
    }
    public_session["blueprint"] = session.get("blueprint")
    public_session["turn_count"] = len(ordered)
    public_session["generated_at"] = generated_at
    session_json = json.dumps(
        public_session,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    artifacts = {
        "transcript.md": transcript,
        "interview-report.md": report,
        "session.json": session_json + "\n",
    }
    if any(
        contains_sensitive_value(content)
        for content in artifacts.values()
    ):
        raise InterviewValidationError(
            "REPORT_VALIDATION_FAILED",
            "interview artifact contains a sensitive value",
        )
    return artifacts


def _compile_transcript(session: dict, turns: list[dict]) -> str:
    lines = [
        "# 模拟面试逐字稿",
        "",
        f"- 公司：{_safe_text(session.get('company'))}",
        f"- 岗位：{_safe_text(session.get('position'))}",
        f"- 面试 Session：`{_safe_text(session.get('id'))}`",
        "",
    ]
    for turn in turns:
        lines.extend(
            [
                f"## 第 {turn['turn_index']} 轮",
                "",
                f"**问题：** {_safe_text(turn.get('question_text'))}",
                "",
                f"**回答：** {_safe_text(turn.get('answer_text'))}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _compile_report(
    session: dict,
    turns: list[dict],
    generated_at: str,
) -> str:
    if any(
        turn.get("evaluation", {}).get("version") == 2
        for turn in turns
    ):
        return _compile_report_v2(session, turns, generated_at)
    answers = [_safe_text(turn.get("answer_text")) for turn in turns]
    lengths = [len(_normalized(answer)) for answer in answers]
    average = round(sum(lengths) / len(lengths), 1)
    filler_counts = {
        filler: sum(answer.count(filler) for answer in answers)
        for filler in _FILLERS
    }
    repeated_expressions = _repeated_expression_count(answers)
    joined = "\n".join(answers)
    dimension_scores = {
        field: round(
            sum(int(turn["evaluation"][field]) for turn in turns)
            / len(turns),
            1,
        )
        for field in SCORE_FIELDS
    }
    issues = Counter(
        issue
        for turn in turns
        for issue in turn["evaluation"].get("issues", [])
    )
    strengths = [
        _score_label(field)
        for field, score in dimension_scores.items()
        if score >= 7
    ]
    lines = [
        "# 模拟面试复盘",
        "",
        "> 以下内容是训练反馈，不代表录用概率或岗位资格判断。",
        "",
        "## 岗位与简历",
        "",
        f"- 公司：{_safe_text(session.get('company'))}",
        f"- 岗位：{_safe_text(session.get('position'))}",
        f"- 简历 ID：`{_safe_text(session.get('resume_id'))}`",
        f"- 匹配快照 ID：`{_safe_text(session.get('snapshot_id'))}`",
        "",
        "## 面试概况",
        "",
        f"- 完成轮次：{len(turns)}",
        f"- 难度：{_safe_text(session.get('difficulty'))}",
        f"- 计划时长：{session.get('duration_minutes')} 分钟",
        "",
        "## 能力维度评价",
        "",
    ]
    for field in SCORE_FIELDS:
        lines.append(
            f"- {_score_label(field)}：{dimension_scores[field]}/10"
        )
    lines.extend(["", "## 优势", ""])
    lines.extend(
        [f"- {value}" for value in strengths]
        or ["- 当前没有达到 7/10 的稳定优势维度。"]
    )
    lines.extend(["", "## 主要问题", ""])
    lines.extend(
        [f"- {issue}（{count} 次）" for issue, count in issues.items()]
        or ["- 当前评价没有记录重复问题。"]
    )
    lines.extend(
        [
            "",
            "## Transcript 分析",
            "",
            f"- 回答总字数：{sum(lengths)}",
            f"- 平均回答长度：{average} 字",
            f"- 最长回答：{max(lengths)} 字",
            f"- 最短回答：{min(lengths)} 字",
        ]
    )
    lines.extend(
        f"- {filler}：{count} 次"
        for filler, count in filler_counts.items()
    )
    lines.extend(
        [
            f"- 我们：{joined.count('我们')} 次",
            f"- 我：{joined.count('我')} 次",
            f"- 数字或百分比：{len(_NUMBER.findall(joined))} 次",
            f"- 重复表达：{repeated_expressions} 次",
            (
                "- 偏题程度："
                f"{round(10 - dimension_scores['relevance'], 1)}/10"
            ),
            (
                "- STAR/结构完整度："
                f"{dimension_scores['structure']}/10"
            ),
            "",
            "## 逐题复盘",
            "",
        ]
    )
    for turn in turns:
        evaluation = turn["evaluation"]
        coaching_structure = " → ".join(
            evaluation.get("coaching_structure", [])
        )
        lines.extend(
            [
                f"### Q{turn['turn_index']}："
                f"{_safe_text(turn.get('question_text'))}",
                "",
                f"- 原回答：{_safe_text(turn.get('answer_text'))}",
                (
                    "- 主要问题："
                    + (
                        "；".join(evaluation.get("issues", []))
                        or "未记录"
                    )
                ),
                f"- 推荐表达结构：{coaching_structure}",
                (
                    f"- 参考优化：按“{coaching_structure}”重组原回答；"
                    "只使用原回答和已确认事实。"
                ),
                (
                    "- 事实引用："
                    + (
                        "、".join(evaluation.get("fact_refs", []))
                        or "无"
                    )
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## 下一次训练建议",
            "",
            "- 优先补充个人行动、证据和可验证结果。",
            "- 对“我们”的表述继续追问个人职责边界。",
            "- 只使用已确认简历事实和本场原回答进行改进。",
            "",
            "## 数据版本与生成时间",
            "",
            f"- 生成时间：{generated_at}",
            f"- Interview Session：`{_safe_text(session.get('id'))}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _compile_report_v2(
    session: dict,
    turns: list[dict],
    generated_at: str,
) -> str:
    lines = [
        "# 模拟面试复盘",
        "",
        "> 以下内容是训练反馈，不代表录用概率或岗位资格判断。",
        "",
        "## 面试概况",
        "",
        f"- 公司：{_safe_text(session.get('company'))}",
        f"- 岗位：{_safe_text(session.get('position'))}",
        f"- 完成题数：{len(turns)}",
        "",
        "## 逐题复盘",
        "",
    ]
    for turn in turns:
        evaluation = turn["evaluation"]
        if evaluation.get("version") != 2:
            legacy_scores = [
                int(evaluation.get(field, 0))
                for field in SCORE_FIELDS
            ]
            score = round(sum(legacy_scores) * 2)
            pain = "；".join(evaluation.get("issues", [])) or "历史评价未记录"
            reason = "该题使用历史五维评价，已转换为单题总分展示。"
            improvement = (
                " → ".join(evaluation.get("coaching_structure", []))
                or "补充个人行动、证据和结果。"
            )
        else:
            score = evaluation["question_score"]
            pain = evaluation.get("primary_pain")
            reason = evaluation.get("reason")
            improvement = evaluation.get("improvement")
        lines.extend(
            [
                f"### Q{turn['turn_index']}："
                f"{_safe_text(turn.get('question_text'))}",
                "",
                f"- 本题得分：{score}/100",
                f"- 主要痛点：{_safe_text(pain)}",
                f"- 原因：{_safe_text(reason)}",
                f"- 优化策略：{_safe_text(improvement)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 说明",
            "",
            "- 单题分数表示该回答对本题目标的达成度，不表示录用概率。",
            "- 优化建议只使用本场回答和已确认事实，不补写候选人未提供的经历。",
            "",
            f"- 报告生成时间：{generated_at}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE.sub(" ", value).strip()


def _safe_text(value: object) -> str:
    text = _text(value)
    return "[已隐藏敏感信息]" if contains_sensitive_value(text) else text


def _normalized(value: object) -> str:
    return unicodedata.normalize("NFKC", _text(value)).casefold()


def _repeated_expression_count(answers: list[str]) -> int:
    clauses = [
        normalized
        for answer in answers
        for clause in _CLAUSE_SPLIT.split(answer)
        if len(normalized := _normalized(clause)) >= 4
    ]
    return sum(count - 1 for count in Counter(clauses).values())


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _validate_single_dimension_question(
    question: str,
    probe_dimension: str,
) -> None:
    clauses = [
        clause.strip()
        for clause in _PARALLEL_REQUEST_SPLIT.split(question)
        if clause.strip()
    ]
    if len(clauses) < 2:
        return
    intents = {
        intent
        for clause in clauses
        for intent, pattern in _DIMENSION_INTENT_PATTERNS.items()
        if pattern.search(_normalized(clause))
    }
    if len(intents) > 1:
        _question_error(
            "question text spans multiple probe dimensions"
        )
    allowed = _DIMENSION_INTENT_COMPATIBILITY.get(
        probe_dimension,
        {probe_dimension},
    )
    if intents and not intents <= allowed:
        _question_error(
            "question text conflicts with probe dimension"
        )


def _text_list(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> list[str]:
    if (
        not isinstance(value, list)
        or not minimum <= len(value) <= maximum
        or not all(
            isinstance(item, str)
            and 1 <= len(_text(item)) <= 120
            for item in value
        )
    ):
        _evaluation_error(f"{field} is invalid")
    return [_text(item) for item in value]


def _question_error(message: str):
    raise InterviewValidationError(
        "QUESTION_VALIDATION_FAILED",
        message,
    )


def _evaluation_error(message: str):
    raise InterviewValidationError(
        "EVALUATION_VALIDATION_FAILED",
        message,
    )


def _score_label(field: str) -> str:
    return {
        "relevance": "岗位相关性",
        "clarity": "表达清晰度",
        "structure": "结构化表达",
        "depth": "回答深度",
        "evidence": "证据与数据",
    }[field]
