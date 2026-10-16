# Single-Dimension Interview Question Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject Blueprint v2 questions that use one declared `probe_dimension` while explicitly asking for answers from multiple semantic dimensions.

**Architecture:** Extend the existing deterministic question validator with a small set of high-confidence Chinese intent patterns. Only explicit parallel clauses are compared, so natural single-focus questions and Blueprint v1 remain compatible. The Skill contract prevents invalid generation before the Service gate rejects it.

**Tech Stack:** Python 3.10+, regular expressions, pytest, OpenWorker Skill loader, existing real-Aiden acceptance script.

---

## File Map

- Modify `extensions/career_mcp/domain/interviews.py`
  - Detect explicit parallel clauses and their high-confidence dimension intents.
- Modify `extensions/career_mcp/tests/test_interviews.py`
  - Lock down reject/pass/v1 compatibility behavior.
- Modify `.coworker/skills/mock-interview/SKILL.md`
  - Require question text to request only the declared dimension.
- Modify `tests/test_skills.py`
  - Keep the Skill instruction machine-checkable.
- Modify `docs/11_DEVELOPMENT_LOG.md`
  - Record RED/GREEN, regression, and real-model evidence.
- Modify `docs/12_TONIGHT_PROGRESS.md`
  - Close the remaining quality-risk item.

### Task 1: Deterministic Cross-Dimension Gate

**Files:**
- Modify: `extensions/career_mcp/tests/test_interviews.py`
- Modify: `extensions/career_mcp/domain/interviews.py`

- [ ] **Step 1: Add the real leaked-question RED**

Add:

```python
def test_v2_rejects_parallel_requests_for_different_dimensions():
    with pytest.raises(InterviewValidationError) as error:
        validate_question(
            _v2_question(
                question=(
                    "请介绍你参与的推理服务优化项目背景，"
                    "以及你作为大模型推理算法工程师具体负责的工作"
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
```

- [ ] **Step 2: Run the RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interviews.py::test_v2_rejects_parallel_requests_for_different_dimensions \
  -q
```

Expected: FAIL because the current validator accepts the single-sentence question.

- [ ] **Step 3: Add adversarial RED cases**

Add this helper and parametrized rejects:

```python
def _v2_blueprint_with_dimension(dimension: str) -> dict:
    blueprint = _blueprint()
    dimensions = blueprint["probe_plan"][0]["dimensions"]
    if dimension not in dimensions:
        dimensions.append(dimension)
    return blueprint


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
```

Add allowed cases:

```python
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
```

Add v1 compatibility:

```python
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
```

The required reject pairs are:

```python
[
    (
        "请说明整体架构，并介绍如何优化 P95 延迟",
        "architecture",
    ),
    (
        "请说明产品策略，同时介绍你定义的成功指标",
        "strategy",
    ),
]
```

- [ ] **Step 4: Implement the minimal pure detector**

Add module constants:

```python
_PARALLEL_REQUEST_SPLIT = re.compile(
    r"(?:，|,)?\s*(?:以及|并且|同时|另外|此外|还要|"
    r"并(?=说明|介绍|描述|分析|解释|谈谈|给出|如何|怎么|"
    r"提升|降低))\s*"
)
_DIMENSION_INTENT_PATTERNS = {
    "context": re.compile(
        r"背景|业务场景|业务约束|启动原因|问题来源"
    ),
    "personal_contribution": re.compile(
        r"(?:你|个人).{0,8}(?:负责|职责|贡献|承担|主导|决策)|"
        r"具体负责"
    ),
    "architecture": re.compile(r"整体架构|系统架构|架构设计|模块划分"),
    "implementation": re.compile(r"代码实现|实现细节|如何实现|怎么实现"),
    "performance": re.compile(r"性能|p\d{2,3}\s*延迟|延迟|吞吐"),
    "strategy": re.compile(r"产品策略|策略选择|战略"),
    "metrics": re.compile(r"成功指标|衡量指标|指标体系|北极星指标"),
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
```

Add:

```python
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
```

Call it only after Blueprint v2 has validated `probe_dimension`.

- [ ] **Step 5: Run GREEN and focused regression**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interviews.py \
  extensions/career_mcp/tests/test_interview_service.py \
  -q
```

Expected: all pass.

### Task 2: Skill Generation Contract

**Files:**
- Modify: `tests/test_skills.py`
- Modify: `.coworker/skills/mock-interview/SKILL.md`

- [ ] **Step 1: Add Skill RED**

Require this exact text in the existing mock-interview contract test:

```python
"The question text must request only one `probe_dimension`."
```

- [ ] **Step 2: Run the RED**

Run:

```bash
.venv/bin/pytest \
  tests/test_skills.py::test_workspace_career_skills_are_discoverable \
  -q
```

Expected: FAIL because the instruction is absent.

- [ ] **Step 3: Add the minimal instruction**

Add under Blueprint v2 Contract:

```markdown
- The question text must request only one `probe_dimension`. Do not combine
  background with personal contribution, architecture with performance, or
  strategy with metrics in one question.
```

- [ ] **Step 4: Run GREEN**

Run the Step 2 command.

Expected: PASS.

### Task 3: Regression, Real Model, and Evidence

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`
- Create: `artifacts/interview-acceptance/real-algorithm-single-dimension-20260812.json`

- [ ] **Step 1: Run the full focused regression**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_intelligence.py \
  extensions/career_mcp/tests/test_interviews.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_tools.py \
  extensions/career_mcp/tests/test_resume_grounded_interview_acceptance.py \
  tests/test_skills.py \
  tests/test_builtin_personas.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Rerun the real algorithm interview**

Run:

```bash
COWORKER_STATE_DIR="$PWD/.local-state" \
.venv/bin/python \
  scripts/acceptance/resume_grounded_interview_gate.py \
  --model aiden:deepseek-v4-flash \
  --workspace "$PWD" \
  --fixture interview_algorithm.json \
  --output \
  artifacts/interview-acceptance/real-algorithm-single-dimension-20260812.json
```

Expected:

- five completed turns;
- first question contains the position and resume project;
- first question requests only one dimension;
- depth reaches at least two;
- all three artifacts and privacy gate pass.

- [ ] **Step 3: Record evidence**

Append the rejected real-model attempts, final depth chain, hashes, test counts,
and residual limitations to `docs/11_DEVELOPMENT_LOG.md`. Update the
JD/resume-grounded interview row in `docs/12_TONIGHT_PROGRESS.md`.

- [ ] **Step 4: Final checks**

Run:

```bash
.venv/bin/python -m compileall -q \
  extensions/career_mcp/domain \
  extensions/career_mcp/services
git diff --check
```

Expected: both commands exit 0.
