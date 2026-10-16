# Resume-Grounded Interview Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every new mock interview use a Blueprint v2 that contains bounded confirmed-resume evidence, deterministic job-role tracks, a role-specific probe plan, and validated multi-turn depth metadata.

**Architecture:** Add a pure `interview_intelligence` Domain module for role classification, evidence-card selection, and probe-plan construction. `InterviewService` loads confirmed resume sections and builds Blueprint v2; schema v11 persists question topic/target/dimension/depth while existing v1 sessions remain readable. Persona and Skill prompts consume the structured contract, while Service validation remains the authority.

**Tech Stack:** Python 3.10+, SQLite migrations, existing Career Domain/Service/Repository layers, OpenWorker Persona/Skill loader, Vitest for the GUI task prompt, pytest, real Aiden TurnEngine acceptance.

---

## Scope And Worktree Rules

- Implement only the intelligence core in
  `docs/superpowers/specs/2026-08-11-resume-grounded-interview-intelligence-design.md`.
- Do not migrate `InterviewView` into the standard conversation UI.
- Do not add interview-history UI or APIs.
- Do not implement streaming ASR/TTS.
- Do not modify Agent Loop, Provider Router, MCP Client, permissions, or core Conversation storage.
- The shared worktree already contains unrelated changes. Before every commit, inspect
  `git diff -- <paths>` and stage only task-owned hunks. Never reset or overwrite pre-existing
  changes.
- Default tests must remain offline. The real-model Gate is an explicit command.

## File Map

- Create `extensions/career_mcp/domain/interview_intelligence.py`
  - Role-track constants and deterministic classifier.
  - Evidence-card selection and grouping.
  - Probe-plan construction and dimension catalog.
- Create `extensions/career_mcp/tests/test_interview_intelligence.py`
  - Pure Domain tests for classification, evidence, privacy, priorities, and depth.
- Modify `extensions/career_mcp/domain/interviews.py`
  - Build Blueprint v2.
  - Derive allowed refs.
  - Dispatch v1/v2 question validation.
  - Validate probe target, dimension, depth, and transitions.
- Modify `extensions/career_mcp/tests/test_interviews.py`
  - Blueprint v2 and validator RED/GREEN coverage.
- Modify `extensions/career_mcp/database/migrations.py`
  - Upgrade schema 10 to 11.
- Modify `extensions/career_mcp/database/interview_repository.py`
  - Persist/map four nullable Turn metadata fields.
- Modify `extensions/career_mcp/tests/test_migrations.py`
  - Schema v11 and v10 upgrade tests.
- Modify `extensions/career_mcp/tests/test_interview_repository.py`
  - New Turn metadata and v1 null compatibility.
- Modify `extensions/career_mcp/services/interviews.py`
  - Load selected confirmed resume sections.
  - Build Blueprint v2.
  - Pass complete previous turns and next action into validation.
  - Persist validated metadata.
- Modify `extensions/career_mcp/tests/test_interview_service.py`
  - Blueprint creation, first/next question metadata, transaction, v1 compatibility.
- Modify `.coworker/skills/mock-interview/SKILL.md`
  - Replace fixed first question with Blueprint-driven workflow.
  - Add role-specific and depth rules.
- Modify `coworker/personas/builtin/career.md`
  - Add only durable interview principles.
- Modify `tests/test_skills.py`
  - Static Skill contract.
- Modify `tests/test_builtin_personas.py`
  - Persona interview principles.
- Modify `surfaces/gui/src/careerInterview.ts`
  - Natural Blueprint-driven start instruction.
- Modify `surfaces/gui/src/careerInterview.test.ts`
  - Prompt contract.
- Create `scripts/acceptance/resume_grounded_interview_gate.py`
  - Explicit algorithm/engineering/product real-model Gate.
- Create `scripts/acceptance/fixtures/interview_algorithm.json`
- Create `scripts/acceptance/fixtures/interview_engineering.json`
- Create `scripts/acceptance/fixtures/interview_product.json`
- Modify `docs/11_DEVELOPMENT_LOG.md`
- Modify `docs/12_TONIGHT_PROGRESS.md`

### Task 1: Deterministic Role Tracks

**Files:**
- Create: `extensions/career_mcp/domain/interview_intelligence.py`
- Create: `extensions/career_mcp/tests/test_interview_intelligence.py`

- [ ] **Step 1: Write classifier RED tests**

```python
from extensions.career_mcp.domain.interview_intelligence import (
    classify_role_tracks,
)


def test_role_tracks_prioritize_title_and_allow_mixed_roles():
    assert classify_role_tracks(
        "大模型推理算法工程师",
        ["负责模型训练、推理服务和性能优化"],
    ) == ["algorithm", "engineering"]
    assert classify_role_tracks(
        "AI 产品经理",
        ["设计评测体系和产品策略"],
    ) == ["product"]


def test_role_tracks_fall_back_to_general():
    assert classify_role_tracks("项目负责人", ["推进项目交付"]) == [
        "general"
    ]
```

- [ ] **Step 2: Run classifier tests and observe RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_intelligence.py \
  -q
```

Expected: collection fails because `interview_intelligence` does not exist.

- [ ] **Step 3: Implement the minimal classifier**

Create:

```python
"""Pure, deterministic intelligence inputs for mock interviews."""

from __future__ import annotations

import re
import unicodedata

ROLE_TRACKS = ("algorithm", "engineering", "product", "general")

_ROLE_SIGNALS = {
    "algorithm": (
        "算法", "模型", "机器学习", "深度学习", "nlp", "cv",
        "推荐", "训练", "推理",
    ),
    "engineering": (
        "开发", "工程师", "后端", "前端", "客户端", "架构",
        "平台", "基础设施", "sre",
    ),
    "product": (
        "产品经理", "产品策划", "产品运营", "策略产品", "商业产品",
    ),
}


def _normalized(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", value).casefold(),
    ).strip()


def _matches(text: str) -> list[str]:
    return [
        track
        for track in ("algorithm", "engineering", "product")
        if any(signal in text for signal in _ROLE_SIGNALS[track])
    ]


def classify_role_tracks(
    title: str,
    requirements: list[str],
) -> list[str]:
    title_tracks = _matches(_normalized(title))
    if title_tracks:
        return title_tracks
    requirement_text = _normalized(" ".join(requirements))
    requirement_tracks = _matches(requirement_text)
    return requirement_tracks or ["general"]
```

- [ ] **Step 4: Run classifier tests and observe GREEN**

Run the Step 2 command.

Expected: `2 passed`.

- [ ] **Step 5: Commit the isolated classifier**

```bash
git add \
  extensions/career_mcp/domain/interview_intelligence.py \
  extensions/career_mcp/tests/test_interview_intelligence.py
git diff --cached --check
git commit -m "feat(interview): classify job role tracks"
```

### Task 2: Bounded Resume Evidence Cards

**Files:**
- Modify: `extensions/career_mcp/domain/interview_intelligence.py`
- Modify: `extensions/career_mcp/tests/test_interview_intelligence.py`

- [ ] **Step 1: Add evidence-card RED tests**

```python
from extensions.career_mcp.domain.interview_intelligence import (
    build_evidence_cards,
)


def test_evidence_cards_prioritize_hard_matches_and_group_projects():
    cards = build_evidence_cards(
        {
            "project": [{
                "name": "OpenCareer",
                "highlights": [
                    "使用 Python 构建岗位匹配服务",
                    "设计 CAS 并发控制",
                ],
            }],
            "basic": {
                "summary": "求职 Agent 产品与工程经验",
                "email": "secret@example.com",
            },
        },
        [{
            "requirement_id": "requirement-1",
            "category": "hard",
            "evidence": [{
                "path": "project[0].highlights[0]",
            }],
        }],
    )

    assert cards[0] == {
        "fact_path": "project[0].highlights[0]",
        "section": "project",
        "group_path": "project[0]",
        "excerpt": "使用 Python 构建岗位匹配服务",
        "requirement_ids": ["requirement-1"],
    }
    assert "secret@example.com" not in str(cards)
    assert all(len(card["excerpt"]) <= 300 for card in cards)


def test_evidence_cards_are_unique_and_bounded():
    sections = {
        "project": [
            {"highlights": [f"项目证据 {index}"]}
            for index in range(20)
        ]
    }
    cards = build_evidence_cards(sections, [])
    assert len(cards) == 16
    assert len({card["fact_path"] for card in cards}) == 16
```

- [ ] **Step 2: Run the new tests and observe RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_intelligence.py \
  -q
```

Expected: fails because `build_evidence_cards` is missing.

- [ ] **Step 3: Implement evidence-card selection**

Add these public contracts and helpers:

```python
from .matching import build_evidence_entries

MAX_EVIDENCE_CARDS = 16
MAX_EVIDENCE_CHARS = 300
_GROUP_PATH = re.compile(r"^((?:project|work)\[\d+\])")


def _group_path(path: str) -> str:
    match = _GROUP_PATH.match(path)
    return match.group(1) if match else path.split(".", 1)[0]


def build_evidence_cards(
    sections: dict,
    requirements: list[dict],
) -> list[dict]:
    requirement_refs: dict[str, list[str]] = {}
    hard_paths: set[str] = set()
    for requirement in requirements:
        requirement_id = str(requirement.get("requirement_id") or "")
        for item in requirement.get("evidence", []):
            path = str(item.get("path") or "")
            if not path or not requirement_id:
                continue
            requirement_refs.setdefault(path, []).append(requirement_id)
            if requirement.get("category") == "hard":
                hard_paths.add(path)

    ranked = []
    for entry in build_evidence_entries(sections):
        path = str(entry["path"])
        if path in hard_paths:
            rank = 0
        elif path in requirement_refs:
            rank = 1
        elif entry["section"] in {"project", "work"}:
            rank = 2
        else:
            rank = 3
        ranked.append((rank, path, entry))

    cards = []
    seen: set[str] = set()
    for _, path, entry in sorted(ranked, key=lambda item: item[:2]):
        if path in seen:
            continue
        seen.add(path)
        cards.append({
            "fact_path": path,
            "section": str(entry["section"]),
            "group_path": _group_path(path),
            "excerpt": " ".join(str(entry["excerpt"]).split())[
                :MAX_EVIDENCE_CHARS
            ],
            "requirement_ids": sorted(set(requirement_refs.get(path, []))),
        })
        if len(cards) == MAX_EVIDENCE_CARDS:
            break
    return cards
```

The implementation must continue relying on `build_evidence_entries()` for
sensitive-key/value filtering. Do not add a second privacy regex.

- [ ] **Step 4: Run Domain tests and observe GREEN**

Run the Step 2 command.

Expected: all tests pass.

- [ ] **Step 5: Commit evidence cards**

```bash
git add \
  extensions/career_mcp/domain/interview_intelligence.py \
  extensions/career_mcp/tests/test_interview_intelligence.py
git diff --cached --check
git commit -m "feat(interview): build bounded resume evidence"
```

### Task 3: Role-Specific Probe Plan

**Files:**
- Modify: `extensions/career_mcp/domain/interview_intelligence.py`
- Modify: `extensions/career_mcp/tests/test_interview_intelligence.py`

- [ ] **Step 1: Add probe-plan RED tests**

```python
from extensions.career_mcp.domain.interview_intelligence import (
    build_probe_plan,
)


def test_standard_engineering_probe_prioritizes_core_project():
    plan = build_probe_plan(
        role_tracks=["engineering"],
        requirements=[{
            "requirement_id": "requirement-1",
            "category": "hard",
            "evidence_status": "direct",
            "evidence_paths": ["project[0].highlights[0]"],
        }],
        evidence_cards=[{
            "fact_path": "project[0].highlights[0]",
            "section": "project",
            "group_path": "project[0]",
            "excerpt": "设计 CAS 并发控制",
            "requirement_ids": ["requirement-1"],
        }],
        difficulty="standard",
        question_budget=8,
    )

    assert plan[0]["target_id"] == "project[0]"
    assert plan[0]["target_type"] == "resume_project"
    assert plan[0]["max_depth"] == 3
    assert {"implementation", "concurrency", "reliability"} <= set(
        plan[0]["dimensions"]
    )


def test_product_and_missing_requirement_targets_are_safe():
    plan = build_probe_plan(
        role_tracks=["product"],
        requirements=[{
            "requirement_id": "requirement-2",
            "category": "hard",
            "evidence_status": "none",
            "evidence_paths": [],
        }],
        evidence_cards=[],
        difficulty="simple",
        question_budget=5,
    )
    assert plan[0]["target_type"] == "job_requirement"
    assert plan[0]["refs"] == ["requirement-2"]
    assert plan[0]["max_depth"] == 1
    assert "feature_design" in plan[0]["dimensions"]
    assert {item["target_type"] for item in plan} >= {
        "job_requirement",
        "role_scenario",
        "reflection",
    }
```

- [ ] **Step 2: Run probe tests and observe RED**

Run the Task 2 test command.

Expected: fails because `build_probe_plan` is missing.

- [ ] **Step 3: Implement dimensions, priority, and depth**

Add:

```python
COMMON_DIMENSIONS = (
    "context", "personal_contribution", "result", "evidence",
    "tradeoff", "failure", "reflection",
)
TRACK_DIMENSIONS = {
    "algorithm": (
        "data", "model_choice", "training", "inference", "experiment",
        "evaluation", "error_analysis", "optimization",
    ),
    "engineering": (
        "architecture", "implementation", "interface", "data_structure",
        "concurrency", "consistency", "performance", "reliability",
        "observability", "security",
    ),
    "product": (
        "user_problem", "strategy", "feature_design", "workflow",
        "evaluation", "metrics", "experiment", "iteration",
        "prioritization", "business_tradeoff",
    ),
    "general": (),
}


def _dimensions(role_tracks: list[str]) -> list[str]:
    values = list(COMMON_DIMENSIONS)
    for track in role_tracks:
        values.extend(TRACK_DIMENSIONS[track])
    return list(dict.fromkeys(values))


def _max_depth(difficulty: str, *, core: bool) -> int:
    if difficulty == "simple":
        return 1
    if difficulty == "standard":
        return 3 if core else 2
    return 4 if core else 3


def build_probe_plan(
    *,
    role_tracks: list[str],
    requirements: list[dict],
    evidence_cards: list[dict],
    difficulty: str,
    question_budget: int,
) -> list[dict]:
    requirement_by_id = {
        item["requirement_id"]: item for item in requirements
    }
    groups: dict[str, list[dict]] = {}
    for card in evidence_cards:
        groups.setdefault(card["group_path"], []).append(card)

    candidates = []
    for group_path, cards in groups.items():
        requirement_ids = sorted({
            requirement_id
            for card in cards
            for requirement_id in card["requirement_ids"]
        })
        hard = any(
            requirement_by_id[requirement_id]["category"] == "hard"
            for requirement_id in requirement_ids
        )
        priority = 100 if hard else 90 if len(requirement_ids) > 1 else 70
        refs = [*requirement_ids, *[card["fact_path"] for card in cards]]
        candidates.append({
            "target_id": group_path,
            "target_type": (
                "resume_project"
                if group_path.startswith("project[")
                else "resume_work"
            ),
            "priority": priority,
            "refs": list(dict.fromkeys(refs)),
            "dimensions": _dimensions(role_tracks),
        })

    for requirement in requirements:
        if requirement["evidence_status"] not in {"none", "related"}:
            continue
        candidates.append({
            "target_id": requirement["requirement_id"],
            "target_type": "job_requirement",
            "priority": (
                95 if requirement["category"] == "hard" else 60
            ),
            "refs": [requirement["requirement_id"]],
            "dimensions": _dimensions(role_tracks),
        })

    if requirements:
        anchor_ref = requirements[0]["requirement_id"]
        candidates.extend([
            {
                "target_id": "role-scenario",
                "target_type": "role_scenario",
                "priority": 40,
                "refs": [anchor_ref],
                "dimensions": _dimensions(role_tracks),
            },
            {
                "target_id": "reflection",
                "target_type": "reflection",
                "priority": 20,
                "refs": [anchor_ref],
                "dimensions": list(COMMON_DIMENSIONS),
            },
        ])

    candidates.sort(key=lambda item: (-item["priority"], item["target_id"]))
    for index, candidate in enumerate(candidates):
        candidate["max_depth"] = _max_depth(
            difficulty,
            core=index == 0,
        )
    return candidates[:question_budget]
```

Validate `difficulty` and every `role_track` before building; raise
`InterviewValidationError("INVALID_INPUT", ...)` through the caller rather
than allowing a `KeyError`.

- [ ] **Step 4: Run pure Domain tests**

Expected: role, evidence, and probe tests pass.

- [ ] **Step 5: Commit probe planning**

```bash
git add \
  extensions/career_mcp/domain/interview_intelligence.py \
  extensions/career_mcp/tests/test_interview_intelligence.py
git diff --cached --check
git commit -m "feat(interview): plan role-specific probes"
```

### Task 4: Blueprint v2 Assembly

**Files:**
- Modify: `extensions/career_mcp/domain/interviews.py`
- Modify: `extensions/career_mcp/tests/test_interviews.py`

- [ ] **Step 1: Replace the v1 Blueprint expectation with RED v2 assertions**

Update `_blueprint()` to pass confirmed sections:

```python
def _blueprint() -> dict:
    return build_blueprint(
        _match_result(),
        resume_id="resume-1",
        snapshot_id="snapshot-1",
        difficulty="standard",
        duration_minutes=15,
        resume_sections={
            "project": [{
                "name": "OpenCareer",
                "highlights": ["使用 Python 构建服务"],
            }],
        },
    )
```

Add:

```python
def test_blueprint_v2_contains_grounded_interview_context():
    blueprint = _blueprint()

    assert blueprint["version"] == 2
    assert blueprint["role_tracks"] == ["algorithm", "engineering"]
    assert blueprint["job_requirements"][0]["requirement_id"] == (
        "requirement-1"
    )
    assert blueprint["evidence_cards"][0]["excerpt"] == (
        "使用 Python 构建服务"
    )
    assert blueprint["probe_plan"][0]["target_id"] == "project[0]"
    assert "secret@example.com" not in str(blueprint)
```

- [ ] **Step 2: Run Blueprint tests and observe RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interviews.py \
  -q
```

Expected: `build_blueprint()` rejects `resume_sections` or returns version 1.

- [ ] **Step 3: Assemble Blueprint v2**

Change the signature:

```python
def build_blueprint(
    match_result: dict,
    *,
    resume_id: str,
    snapshot_id: str,
    difficulty: str,
    duration_minutes: int,
    resume_sections: dict,
) -> dict:
```

After selecting the one fresh result, normalize each requirement into:

```python
{
    "requirement_id": f"requirement-{index}",
    "requirement": _text(requirement.get("requirement")),
    "category": requirement.get("category"),
    "evidence_status": requirement.get("status"),
    "evidence_paths": evidence_paths,
    "evidence": [
        {"path": _text(item.get("path"))}
        for item in evidence
        if isinstance(item, dict) and _text(item.get("path"))
    ],
}
```

Then call:

```python
role_tracks = classify_role_tracks(
    _text(job.get("title")),
    [item["requirement"] for item in job_requirements],
)
evidence_cards = build_evidence_cards(
    resume_sections,
    job_requirements,
)
probe_plan = build_probe_plan(
    role_tracks=role_tracks,
    requirements=job_requirements,
    evidence_cards=evidence_cards,
    difficulty=difficulty,
    question_budget=budget,
)
```

Return version 2 with the exact keys from the design. Keep
`candidate_strengths`, `candidate_risks`, and `must_probe` for report
compatibility.

- [ ] **Step 4: Update `blueprint_refs()` for v1 and v2**

```python
def blueprint_refs(blueprint: dict) -> set[str]:
    if blueprint.get("version") == 2:
        return {
            value
            for target in blueprint.get("probe_plan", [])
            for value in target.get("refs", [])
            if isinstance(value, str) and value
        }
    # Preserve the existing focus_areas implementation for v1 sessions.
```

- [ ] **Step 5: Run Blueprint and artifact tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interviews.py \
  -q
```

Expected: all tests pass, including v1 fixture artifact compilation.

- [ ] **Step 6: Commit Blueprint v2**

```bash
git add \
  extensions/career_mcp/domain/interviews.py \
  extensions/career_mcp/tests/test_interviews.py
git diff --cached --check
git commit -m "feat(interview): assemble blueprint v2"
```

### Task 5: Strict v2 Question Validation

**Files:**
- Modify: `extensions/career_mcp/domain/interviews.py`
- Modify: `extensions/career_mcp/tests/test_interviews.py`

- [ ] **Step 1: Add v2 validator RED tests**

```python
def _v2_question(**overrides):
    value = {
        "question": (
            "你正在应聘大模型算法工程师，请结合 OpenCareer 项目"
            "介绍你的个人职责。"
        ),
        "topic": "个人职责",
        "refs": [
            "requirement-1",
            "project[0].highlights[0]",
        ],
        "probe_target": "project[0]",
        "probe_dimension": "personal_contribution",
        "depth_level": 1,
    }
    value.update(overrides)
    return value


def test_v2_first_question_requires_job_and_resume_refs():
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


def test_v2_follow_up_keeps_target_and_advances_one_depth():
    previous = [{
        "question_text": "第一题",
        "probe_target": "project[0]",
        "probe_dimension": "personal_contribution",
        "depth_level": 1,
    }]
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


def test_v2_switch_topic_requires_new_target_at_depth_one():
    with pytest.raises(InterviewValidationError):
        validate_question(
            _v2_question(depth_level=2),
            blueprint=_blueprint(),
            turn_index=2,
            previous_turns=[{
                "question_text": "第一题",
                "probe_target": "project[0]",
                "probe_dimension": "context",
                "depth_level": 1,
            }],
            next_action="SWITCH_TOPIC",
        )
```

- [ ] **Step 2: Run validator tests and observe RED**

Run the Task 4 pytest command.

Expected: fails because the current validator accepts only `allowed_refs` and
does not return probe metadata.

- [ ] **Step 3: Dispatch validation by Blueprint version**

Change the public contract:

```python
def validate_question(
    proposal: object,
    *,
    blueprint: dict,
    turn_index: int,
    previous_turns: list[dict],
    next_action: str | None = None,
) -> dict:
```

Keep the current text, compound-question, sensitive-value, refs, and duplicate
checks in one shared helper. For `blueprint.version != 2`, preserve the
existing `INTRO` rule and derive previous question strings from
`previous_turns`.

For v2:

```python
targets = {
    item["target_id"]: item
    for item in blueprint.get("probe_plan", [])
}
target = targets.get(probe_target)
if target is None:
    _question_error("question contains an unknown probe target")
if probe_dimension not in target["dimensions"]:
    _question_error("question contains an unknown probe dimension")
if not 1 <= depth_level <= int(target["max_depth"]):
    _question_error("question depth is outside the probe plan")
```

Apply the first-question and transition rules exactly as specified. Return:

```python
{
    "question": question,
    "refs": normalized_refs,
    "topic": topic,
    "probe_target": probe_target,
    "probe_dimension": probe_dimension,
    "depth_level": depth_level,
}
```

- [ ] **Step 4: Add no-evidence safe-fallback coverage**

Build a Blueprint with no cards and assert:

```python
validated = validate_question(
    {
        "question": "你会如何设计一个模型效果评测方案？",
        "topic": "岗位场景",
        "refs": ["requirement-1"],
        "probe_target": "requirement-1",
        "probe_dimension": "evaluation",
        "depth_level": 1,
    },
    blueprint=blueprint_without_cards,
    turn_index=1,
    previous_turns=[],
)
assert validated["probe_target"] == "requirement-1"
```

Also reject wording containing `结合你的经历` or `你在项目中` when no
evidence cards exist.

Implement that boundary as:

```python
if (
    not blueprint.get("evidence_cards")
    and re.search(
        r"(?:结合|根据)你的(?:项目|经历|简历)|你在(?:该|这个)?项目中",
        question,
    )
):
    _question_error(
        "question implies resume evidence that is not available"
    )
```

- [ ] **Step 5: Run Domain tests**

Expected: all v1 and v2 tests pass.

- [ ] **Step 6: Commit strict validation**

```bash
git add \
  extensions/career_mcp/domain/interviews.py \
  extensions/career_mcp/tests/test_interviews.py
git diff --cached --check
git commit -m "feat(interview): validate probe depth and targets"
```

### Task 6: Schema v11 And Turn Persistence

**Files:**
- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/database/interview_repository.py`
- Modify: `extensions/career_mcp/tests/test_migrations.py`
- Modify: `extensions/career_mcp/tests/test_interview_repository.py`

- [ ] **Step 1: Add schema v11 RED tests**

```python
def test_schema_v11_adds_interview_probe_metadata(tmp_path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)

    assert schema_version(connection) == 11
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(interview_turns)"
        )
    }
    assert {
        "question_topic",
        "probe_target",
        "probe_dimension",
        "depth_level",
    } <= columns
```

Add a v10 database fixture with one existing Turn, migrate it, and assert the
four new columns are null for that row.

- [ ] **Step 2: Run migration tests and observe RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_migrations.py \
  -q
```

Expected: schema is 10 and columns are absent.

- [ ] **Step 3: Implement atomic schema v11 migration**

Set:

```python
SCHEMA_VERSION = 11
```

Before the final `PRAGMA user_version`, add:

```python
if version < 11 <= SCHEMA_VERSION:
    for statement in (
        "ALTER TABLE interview_turns ADD COLUMN question_topic TEXT",
        "ALTER TABLE interview_turns ADD COLUMN probe_target TEXT",
        "ALTER TABLE interview_turns ADD COLUMN probe_dimension TEXT",
        (
            "ALTER TABLE interview_turns ADD COLUMN depth_level INTEGER "
            "CHECK(depth_level IS NULL OR depth_level >= 1)"
        ),
    ):
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (11, utc_now_iso()),
    )
```

- [ ] **Step 4: Add repository RED metadata assertions**

Extend the v2 Turn fixture:

```python
"question_topic": "技术实现",
"probe_target": "project[0]",
"probe_dimension": "implementation",
"depth_level": 2,
```

Assert `insert_turn()`, `current_turn()`, and `list_turns()` return these exact
values. Keep one v1 Turn fixture without the keys and assert all four mapped
values are null.

- [ ] **Step 5: Persist and map nullable metadata**

Add the four columns to `INSERT INTO interview_turns`, values, and `_turn()`:

```python
"question_topic": row["question_topic"],
"probe_target": row["probe_target"],
"probe_dimension": row["probe_dimension"],
"depth_level": (
    int(row["depth_level"])
    if row["depth_level"] is not None
    else None
),
```

Use `record.get(...)` so v1 callers remain valid.

- [ ] **Step 6: Run migration and repository tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  -q
```

Expected: all pass and `PRAGMA foreign_key_check` returns no rows.

- [ ] **Step 7: Commit persistence**

Stage only task-owned hunks from these already-modified shared files:

```bash
git add \
  extensions/career_mcp/database/migrations.py \
  extensions/career_mcp/database/interview_repository.py \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_interview_repository.py
git diff --cached --check
git commit -m "feat(interview): persist probe metadata"
```

### Task 7: Service Integration And Transaction Safety

**Files:**
- Modify: `extensions/career_mcp/services/interviews.py`
- Modify: `extensions/career_mcp/tests/test_interview_service.py`

- [ ] **Step 1: Add create-session RED assertions**

```python
def test_service_creates_blueprint_v2_from_confirmed_resume(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )

    created = _create(service, job_id, resume_id, snapshot_id)

    assert created["blueprint"]["version"] == 2
    assert created["blueprint"]["evidence_cards"]
    assert created["blueprint"]["probe_plan"]
    assert created["blueprint"]["role_tracks"]
```

- [ ] **Step 2: Upgrade Service test question helpers to v2**

Replace `_start()` and add `_next_question()`:

```python
def _start(service, session):
    target = session["blueprint"]["probe_plan"][0]
    requirement_ref = next(
        ref for ref in target["refs"] if ref.startswith("requirement-")
    )
    evidence_ref = next(
        ref for ref in target["refs"] if not ref.startswith("requirement-")
    )
    return service.start(
        session["id"],
        expected_version=session["version"],
        question={
            "question": (
                f"你正在应聘{session['position']}，请结合简历中的相关项目"
                "介绍你的个人职责。"
            ),
            "topic": "个人职责",
            "refs": [requirement_ref, evidence_ref],
            "probe_target": target["target_id"],
            "probe_dimension": "personal_contribution",
            "depth_level": 1,
        },
    )


def _next_question(session, *, question: str, dimension: str) -> dict:
    current = session["turns"][-1]
    return {
        "question": question,
        "topic": "项目深挖",
        "refs": current["question_refs"],
        "probe_target": current["probe_target"],
        "probe_dimension": dimension,
        "depth_level": int(current["depth_level"]) + 1,
    }
```

Replace every v2 Service test's literal `next_question` with this helper.
Keep one explicit v1 historical fixture to test the legacy validator.

- [ ] **Step 3: Observe RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_service.py \
  -q
```

Expected: created Blueprint is version 1 or `build_blueprint` lacks
`resume_sections`.

- [ ] **Step 4: Load the selected confirmed resume**

After `MatchService.analyze()` and before `build_blueprint()`:

```python
connection = connect(self.config.database_path)
try:
    resume = ResumeRepository(connection).get_resume_match_input(
        normalized_resume
    )
finally:
    connection.close()
if resume is None:
    self._raise("RESUME_NOT_FOUND")
```

Import `ResumeRepository` and pass `resume["sections"]` into
`build_blueprint()`. Do not add sections to the returned Session outside the
bounded Blueprint.

- [ ] **Step 5: Update first-question Service validation**

Change `start()` to call:

```python
validated = validate_question(
    question,
    blueprint=session["blueprint"],
    turn_index=1,
    previous_turns=[],
)
```

Persist all returned metadata:

```python
"question_topic": validated.get("topic"),
"probe_target": validated.get("probe_target"),
"probe_dimension": validated.get("probe_dimension"),
"depth_level": validated.get("depth_level"),
```

- [ ] **Step 6: Update next-question validation**

Pass:

```python
validated_question = validate_question(
    next_question,
    blueprint=session["blueprint"],
    turn_index=len(turns) + 1,
    previous_turns=turns,
    next_action=next_action,
)
```

Persist the same four metadata fields in the new Turn.

- [ ] **Step 7: Add transition and rollback tests**

Add one test that successfully stores depth 1 then depth 2 on the same target.
Add one test where `InterviewRepository.insert_turn` fails for turn 2 and
assert:

```python
current = service.get(created["id"])
assert current["version"] == answered["version"]
assert current["turns"][0]["evaluation"] is None
assert len(current["turns"]) == 1
```

Keep the existing CAS and stale-snapshot assertions unchanged.

- [ ] **Step 8: Run Service, Repository, Domain, and tool tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_intelligence.py \
  extensions/career_mcp/tests/test_interviews.py \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_tools.py \
  -q
```

Expected: all pass.

- [ ] **Step 9: Commit Service integration**

```bash
git add \
  extensions/career_mcp/services/interviews.py \
  extensions/career_mcp/tests/test_interview_service.py
git diff --cached --check
git commit -m "feat(interview): ground sessions in confirmed resume"
```

### Task 8: Persona, Skill, And Start Prompt

**Files:**
- Modify: `coworker/personas/builtin/career.md`
- Modify: `.coworker/skills/mock-interview/SKILL.md`
- Modify: `tests/test_builtin_personas.py`
- Modify: `tests/test_skills.py`
- Modify: `surfaces/gui/src/careerInterview.ts`
- Modify: `surfaces/gui/src/careerInterview.test.ts`

- [ ] **Step 1: Add Persona and Skill RED contract tests**

In `tests/test_skills.py`:

```python
def test_mock_interview_skill_uses_blueprint_v2_probe_contract():
    root = Path(__file__).resolve().parents[1]
    instructions = SkillLoader([
        root / ".coworker" / "skills"
    ]).get("mock-interview").instructions

    assert "evidence_cards" in instructions
    assert "role_tracks" in instructions
    assert "probe_plan" in instructions
    assert "probe_target" in instructions
    assert "probe_dimension" in instructions
    assert "depth_level" in instructions
    assert "请简单介绍一下你自己。" not in instructions
    for dimension in (
        "model_choice",
        "implementation",
        "feature_design",
    ):
        assert dimension in instructions
```

In `tests/test_builtin_personas.py`, import `Path` and add:

```python
def test_career_persona_sets_durable_interview_boundaries():
    root = Path(__file__).resolve().parents[1]
    prompt = (
        root / "coworker" / "personas" / "builtin" / "career.md"
    ).read_text(encoding="utf-8")

    assert "current saved JD" in prompt
    assert "confirmed resume evidence" in prompt
    assert "Ask one main question at a time" in prompt
    assert "do not coach during the interview" in prompt
    assert "never treat interview answers as confirmed" in prompt
```

- [ ] **Step 2: Run prompt contract tests and observe RED**

Run:

```bash
.venv/bin/pytest \
  tests/test_skills.py \
  tests/test_builtin_personas.py \
  -q
```

Expected: fixed first question remains and v2 terms are absent.

- [ ] **Step 3: Add only durable Persona principles**

Append to the Career Persona body:

```markdown
When conducting a mock interview, behave as a realistic interviewer. Ground
each question in the current saved JD and confirmed resume evidence returned
by Career MCP. Ask one main question at a time, do not coach during the
interview, do not expose hidden evaluation, and never treat interview answers
as confirmed Career Vault facts.
```

Do not copy tool schemas, role dimensions, or workflow steps into Persona.

- [ ] **Step 4: Rewrite the Skill Start and Answer workflows**

The Start Workflow must:

1. Read Blueprint v2.
2. Select the highest-priority target.
3. Use its evidence excerpt and linked requirement.
4. Submit one question with all six fields.
5. Use a requirement-only knowledge/scenario question when cards are empty.

The Answer Workflow must:

1. Evaluate current answer without exposing scores.
2. Continue the same target when the answer is vague, uses “we”, or lacks
   evidence and depth remains.
3. Use only dimensions listed on the target.
4. Submit target/dimension/depth on every next question.
5. Switch target only with `SWITCH_TOPIC` and depth 1.

Include the exact track examples from the design and retain the existing
creation, CAS, finish, privacy, and one-question rules.

- [ ] **Step 5: Add GUI start-prompt RED assertion**

```typescript
expect(interviewStartPrompt("session/one")).toBe(
  "开始这场模拟面试。interview_session_id=session/one。" +
    "加载 mock-interview Skill，根据当前 JD、已确认简历和 " +
    "Blueprint 提出并保存一道针对性问题。",
);
```

- [ ] **Step 6: Implement the natural Blueprint-driven start prompt**

Change only `interviewStartPrompt`. Keep answer/finish prompts unchanged in
this phase because natural conversation message projection belongs to
subsystem 2.

- [ ] **Step 7: Run prompt and GUI tests**

Run:

```bash
.venv/bin/pytest tests/test_skills.py tests/test_builtin_personas.py -q
cd surfaces/gui
npm test -- src/careerInterview.test.ts
```

Expected: all pass.

- [ ] **Step 8: Commit prompts without unrelated Persona/GUI hunks**

```bash
git add \
  coworker/personas/builtin/career.md \
  .coworker/skills/mock-interview/SKILL.md \
  tests/test_builtin_personas.py \
  tests/test_skills.py \
  surfaces/gui/src/careerInterview.ts \
  surfaces/gui/src/careerInterview.test.ts
git diff --cached --check
git commit -m "feat(interview): drive questions from grounded probes"
```

### Task 9: Offline Regression, Real Three-Track Gate, And Documentation

**Files:**
- Create: `scripts/acceptance/resume_grounded_interview_gate.py`
- Create: `scripts/acceptance/fixtures/interview_algorithm.json`
- Create: `scripts/acceptance/fixtures/interview_engineering.json`
- Create: `scripts/acceptance/fixtures/interview_product.json`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Create three concrete acceptance fixtures**

`interview_algorithm.json`:

```json
{
  "job": {
    "title": "大模型推理算法工程师",
    "requirements": [
      "熟悉大模型训练和推理优化",
      "能够设计离线评测与误差分析",
      "熟练使用 Python"
    ]
  },
  "resume": {
    "display_name": "算法验收简历",
    "sections": {
      "basic": {
        "email": "algorithm-secret@example.com",
        "phone": "13800001234"
      },
      "project": [{
        "name": "推理服务优化",
        "highlights": [
          "使用 Python 实现批处理推理服务并优化显存占用",
          "设计准确率、吞吐量和 P95 延迟离线评测"
        ]
      }]
    }
  },
  "expected_tracks": ["algorithm", "engineering"],
  "required_dimensions": ["model_choice", "evaluation", "optimization"]
}
```

`interview_engineering.json`:

```json
{
  "job": {
    "title": "Agent 平台后端研发工程师",
    "requirements": [
      "负责 Agent 工具调用平台架构设计",
      "熟悉并发控制、事务和故障恢复",
      "具备 Python 后端开发经验"
    ]
  },
  "resume": {
    "display_name": "研发验收简历",
    "sections": {
      "basic": {
        "email": "engineering-secret@example.com",
        "phone": "13900001234"
      },
      "project": [{
        "name": "OpenCareer",
        "highlights": [
          "设计基于 CAS 的模拟面试会话并发控制",
          "实现事务 Service、SQLite Repository 和故障回滚测试"
        ]
      }]
    }
  },
  "expected_tracks": ["engineering"],
  "required_dimensions": ["implementation", "concurrency", "reliability"]
}
```

`interview_product.json`:

```json
{
  "job": {
    "title": "AI 产品经理",
    "requirements": [
      "负责 AI Agent 产品策略和功能设计",
      "建立产品评测体系和成功指标",
      "基于用户反馈推动产品迭代"
    ]
  },
  "resume": {
    "display_name": "产品验收简历",
    "sections": {
      "basic": {
        "email": "product-secret@example.com",
        "phone": "13700001234"
      },
      "project": [{
        "name": "求职 Agent",
        "highlights": [
          "定义岗位发现、匹配、申请材料和模拟面试核心流程",
          "使用任务成功率、事实错误率和用户完成时长评测功能"
        ]
      }]
    }
  },
  "expected_tracks": ["product"],
  "required_dimensions": [
    "strategy",
    "feature_design",
    "evaluation",
    "metrics"
  ]
}
```

- [ ] **Step 2: Implement the explicit acceptance runner**

The runner must:

1. Require `--model` and `--workspace`.
2. Create a temporary Career data directory.
3. Seed one job and confirmed resume per fixture.
4. Generate a fresh match and InterviewSession.
5. Bind one real OpenWorker Session.
6. Run Start + eight answer turns through TurnEngine and
   `mock-interview`.
7. Use deterministic fixture answers aligned to each question.
8. Load final InterviewSession and artifacts.
9. Validate the assertions below.
10. Delete temporary database, artifacts, and state in `finally`.

Return non-zero if:

```python
assert session["blueprint"]["version"] == 2
assert session["blueprint"]["role_tracks"] == fixture["expected_tracks"]
assert len(session["turns"]) >= 5
assert session["turns"][0]["probe_target"]
assert session["turns"][0]["depth_level"] == 1
assert any(
    turn["depth_level"] >= 2
    for turn in session["turns"]
    if turn["probe_target"] == session["turns"][0]["probe_target"]
)
assert set(fixture["required_dimensions"]) & {
    turn["probe_dimension"] for turn in session["turns"]
}
assert not contains_sensitive_value(
    json.dumps(session, ensure_ascii=False)
)
```

Also assert each question has at most one question mark and references only
`blueprint_refs()`.

- [ ] **Step 3: Run the complete offline backend regression**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests tests -q
```

Expected: all tests pass with no network access.

- [ ] **Step 4: Run GUI regression and production build**

Run:

```bash
cd surfaces/gui
npm test
npm run build
```

Expected: all GUI tests and TypeScript/Vite build pass. Existing bundle-size
warnings are allowed; new errors are not.

- [ ] **Step 5: Run schema and privacy checks**

Run:

```bash
.venv/bin/python -m compileall \
  extensions/career_mcp/domain \
  extensions/career_mcp/services \
  extensions/career_mcp/database
git diff --check
```

Open the test database in the acceptance runner and assert:

```sql
PRAGMA user_version;      -- 11
PRAGMA foreign_key_check; -- zero rows
```

- [ ] **Step 6: Run the real Aiden three-track Gate**

Run:

```bash
.venv/bin/python \
  scripts/acceptance/resume_grounded_interview_gate.py \
  --model aiden:deepseek-v4-flash \
  --workspace "$PWD"
```

Expected:

- Algorithm, engineering, and product sessions complete.
- Each first question names the role and one real fixture experience.
- Each core target reaches depth 2 or greater.
- Each session uses at least one required role-specific dimension.
- All three artifact sets pass privacy and reference validation.

- [ ] **Step 7: Perform adversarial review**

Attempt:

- An evidence card with email, phone, and private path.
- A product role mislabeled by technical requirement words.
- A mixed algorithm/engineering title.
- A no-evidence resume.
- A same-target depth jump from 1 to 3.
- `SWITCH_TOPIC` without changing target.
- A fabricated ref.
- A compound question.
- A v1 historical Session.

Every attack must be rejected or safely downgraded by deterministic code.
Do not loosen tests to accept model output.

- [ ] **Step 8: Update progress documents**

Record:

- Files changed.
- Schema v11 migration evidence.
- Offline/backend/GUI/build command counts.
- The three real Session IDs.
- Role tracks, first questions, depth chains, and dimensions.
- Artifact hashes and privacy results.
- Remaining subsystem 2 and subsystem 3 work.

- [ ] **Step 9: Commit acceptance and documentation**

```bash
git add \
  scripts/acceptance/resume_grounded_interview_gate.py \
  scripts/acceptance/fixtures/interview_algorithm.json \
  scripts/acceptance/fixtures/interview_engineering.json \
  scripts/acceptance/fixtures/interview_product.json \
  docs/11_DEVELOPMENT_LOG.md \
  docs/12_TONIGHT_PROGRESS.md
git diff --cached --check
git commit -m "test(interview): verify grounded role-specific probing"
```

## Final Acceptance Checklist

- [ ] New sessions always use Blueprint v2.
- [ ] v1 sessions remain readable and use legacy validation.
- [ ] Role tracks are deterministic and mixed roles are supported.
- [ ] Evidence cards are confirmed, bounded, deduplicated, and private.
- [ ] Probe plans prioritize hard JD requirements and relevant projects.
- [ ] First questions are role + resume grounded when evidence exists.
- [ ] No-evidence interviews use safe job knowledge/scenario wording.
- [ ] Every v2 Turn persists topic, target, dimension, and depth.
- [ ] Same-target deepening and topic switching are Service-validated.
- [ ] Fixed generic first-question text is removed from the Skill.
- [ ] Persona remains concise and does not duplicate the Skill.
- [ ] Backend, GUI, build, schema, foreign-key, and privacy checks pass.
- [ ] Real algorithm, engineering, and product TurnEngine Gates pass.
- [ ] Development log identifies subsystem 2 as the next task.
