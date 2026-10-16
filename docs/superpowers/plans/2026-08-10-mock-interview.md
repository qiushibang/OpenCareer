# Mock Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Career Agent mock interview that binds one saved job, one confirmed resume, and one fresh match snapshot; conducts at least five adaptive text or voice turns; and publishes a traceable transcript and review report.

**Architecture:** A dedicated InterviewView is backed by a linked Career Agent conversation. The Agent and `mock-interview` Skill generate one grounded question and one hidden evaluation per turn through Career MCP, while pure Domain/Service code owns state, references, CAS, privacy, and deterministic reports. Existing Tauri microphone capture is extended with an in-memory WAV mode; Python VoiceProvider adapters call Volcengine ASR/TTS and always degrade to text.

**Tech Stack:** Python 3.12, SQLite schema v10, FastAPI, FastMCP, OpenWorker TurnEngine/Skill/Provider Router, React 18, TypeScript, Vitest, Rust/Tauri, CPAL, httpx, websockets, Volcengine Speech APIs

---

## Authoritative References

- Design: `docs/superpowers/specs/2026-08-10-application-support-and-mock-interview-design.md`
- Input technical document: `CAREER_AGENT_MOCK_INTERVIEW_TECH_SPEC.md` supplied by the user.
- Volcengine ASR: <https://www.volcengine.com/docs/6561/1354869>
- Volcengine TTS: <https://www.volcengine.com/docs/6561/1598757>

The implementation uses the non-realtime `bigmodel_nostream` ASR WebSocket and
unidirectional HTTP TTS. It does not use RTC.

## File Map

**Create**

- `extensions/career_mcp/domain/interviews.py`: pure values, validation, state transitions, text metrics, report compilation.
- `extensions/career_mcp/database/interview_repository.py`: schema v10 row mapping and CAS operations.
- `extensions/career_mcp/services/interviews.py`: job/resume/snapshot binding, transactions, and artifact publication.
- `extensions/career_mcp/voice/base.py`: VoiceProvider and stable voice errors.
- `extensions/career_mcp/voice/volcengine_protocol.py`: Volcengine binary framing.
- `extensions/career_mcp/voice/volcengine.py`: ASR/TTS adapter.
- `extensions/career_mcp/services/interview_voice.py`: limits, credentials, and provider orchestration.
- `extensions/career_mcp/tests/test_interviews.py`
- `extensions/career_mcp/tests/test_interview_repository.py`
- `extensions/career_mcp/tests/test_interview_service.py`
- `extensions/career_mcp/tests/test_interview_tools.py`
- `extensions/career_mcp/tests/test_interview_voice.py`
- `.coworker/skills/mock-interview/SKILL.md`
- `surfaces/gui/src/careerInterview.ts`
- `surfaces/gui/src/careerInterview.test.ts`
- `surfaces/gui/src/components/InterviewView.tsx`
- `surfaces/gui/src/components/InterviewView.test.tsx`
- `tests/test_career_interview_api.py`

**Modify**

- `extensions/career_mcp/database/migrations.py`: schema v10.
- `extensions/career_mcp/server.py`: seven Career MCP tools.
- `coworker/server/app.py`: Interview HTTP, voice settings, ASR/TTS, artifact responses.
- `coworker/server/manager.py`: SecretStore-backed Volcengine speech profile.
- `tests/test_skills.py`: mock-interview Skill policy.
- `surfaces/gui/src/api.ts`: interview types and authenticated client functions.
- `surfaces/gui/src/components/CareerJobMatchPanel.tsx`: fresh single-resume interview action.
- `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`
- `surfaces/gui/src/components/CareerJobsView.tsx`: forward interview start.
- `surfaces/gui/src/App.tsx`: interview surface and linked Career session.
- `surfaces/gui/src/tauri.ts`: capture-only commands.
- `stt/src/lib.rs`: capture-only start and in-memory WAV.
- `surfaces/gui/src-tauri/src/lib.rs`: Tauri capture commands.
- `surfaces/gui/src-tauri/Cargo.toml`: direct `base64 = "0.22"` dependency.
- `docs/11_DEVELOPMENT_LOG.md`
- `docs/12_TONIGHT_PROGRESS.md`

## Stable Contracts

```python
DIFFICULTIES = ("simple", "standard", "deep")
DURATION_QUESTION_BUDGET = {10: 5, 15: 8, 20: 10}
NEXT_ACTIONS = (
    "FOLLOW_UP",
    "VERIFY_CLAIM",
    "DEEP_DIVE",
    "SWITCH_TOPIC",
    "WRAP_UP",
)
SESSION_STATUSES = (
    "created",
    "ready",
    "in_progress",
    "completed",
    "cancelled",
    "failed",
)
MAX_QUESTION_CHARS = 200
MAX_ANSWER_CHARS = 20_000
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_AUDIO_SECONDS = 300
```

Stable errors:

```text
INVALID_INPUT
JOB_NOT_FOUND
RESUME_NOT_FOUND
SNAPSHOT_MISMATCH
STALE_MATCH
INTERVIEW_NOT_FOUND
INTERVIEW_STATE_CONFLICT
TURN_NOT_FOUND
TURN_ALREADY_ANSWERED
QUESTION_VALIDATION_FAILED
EVALUATION_VALIDATION_FAILED
VERSION_CONFLICT
VOICE_NOT_CONFIGURED
ASR_FAILED
TTS_FAILED
REPORT_VALIDATION_FAILED
PERSISTENCE_ERROR
```

### Task 1: Interview Domain RED

**Files:**

- Create: `extensions/career_mcp/tests/test_interviews.py`

- [x] **Step 1: Write duration and Blueprint RED tests**

```python
import pytest

from extensions.career_mcp.domain.interviews import (
    InterviewValidationError,
    build_blueprint,
    question_budget,
)


def test_question_budget_is_fixed():
    assert question_budget(10) == 5
    assert question_budget(15) == 8
    assert question_budget(20) == 10
    with pytest.raises(InterviewValidationError):
        question_budget(30)


def test_blueprint_uses_only_current_match_references(match_result):
    blueprint = build_blueprint(
        match_result,
        resume_id="resume-1",
        snapshot_id="snapshot-1",
        difficulty="standard",
        duration_minutes=15,
    )
    assert blueprint["question_budget"] == 8
    assert blueprint["must_probe"] == ["requirement-2"]
    assert blueprint["candidate_strengths"] == [
        "project[0].highlights[0]"
    ]
    assert "secret@example.com" not in str(blueprint)
```

- [x] **Step 2: Write question and evaluation RED tests**

```python
from extensions.career_mcp.domain.interviews import (
    validate_evaluation,
    validate_question,
)


def test_question_requires_one_allowed_reference():
    question = validate_question(
        {
            "question": "为什么选择这个技术方案？",
            "refs": ["project[0].highlights[0]"],
            "topic": "project_decision",
        },
        allowed_refs={"project[0].highlights[0]", "requirement-1"},
        turn_index=2,
        previous_questions=[],
    )
    assert question["refs"] == ["project[0].highlights[0]"]


@pytest.mark.parametrize(
    "question",
    [
        {"question": "问题一？问题二？", "refs": ["requirement-1"]},
        {"question": "重复问题？", "refs": ["unknown"]},
        {"question": "太短", "refs": ["requirement-1"]},
    ],
)
def test_question_rejects_lists_unknown_refs_and_bad_length(question):
    with pytest.raises(InterviewValidationError):
        validate_question(
            question,
            allowed_refs={"requirement-1"},
            turn_index=2,
            previous_questions=["重复问题？"],
        )


def test_evaluation_is_bounded_and_grounded():
    result = validate_evaluation(
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
    assert result["evidence"] == 5
```

- [x] **Step 3: Write state and report RED tests**

```python
from extensions.career_mcp.domain.interviews import (
    compile_interview_artifacts,
    validate_transition,
)


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


def test_report_compiler_emits_three_private_safe_artifacts(session, turns):
    artifacts = compile_interview_artifacts(
        session,
        turns,
        generated_at="2026-08-10T16:00:00Z",
    )
    assert set(artifacts) == {
        "transcript.md",
        "interview-report.md",
        "session.json",
    }
    assert "## 逐题复盘" in artifacts["interview-report.md"]
    assert "训练反馈，不代表录用概率" in artifacts["interview-report.md"]
    assert "secret@example.com" not in str(artifacts)
```

- [x] **Step 4: Run RED**

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_interviews.py -q
```

Expected: import failure because `domain.interviews` does not exist.

- [x] **Step 5: Commit RED**

```bash
git add extensions/career_mcp/tests/test_interviews.py
git commit -m "test(interview): define domain contracts"
```

### Task 2: Interview Domain GREEN

**Files:**

- Create: `extensions/career_mcp/domain/interviews.py`

- [x] **Step 1: Add values and validation error**

```python
class InterviewValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


DIFFICULTIES = ("simple", "standard", "deep")
DURATION_QUESTION_BUDGET = {10: 5, 15: 8, 20: 10}
NEXT_ACTIONS = (
    "FOLLOW_UP",
    "VERIFY_CLAIM",
    "DEEP_DIVE",
    "SWITCH_TOPIC",
    "WRAP_UP",
)


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
    return DURATION_QUESTION_BUDGET[duration_minutes]
```

- [x] **Step 2: Implement Blueprint construction**

Implement:

```python
def build_blueprint(
    match_result: dict,
    *,
    resume_id: str,
    snapshot_id: str,
    difficulty: str,
    duration_minutes: int,
) -> dict:
```

It must select exactly one matching result, require `snapshot_status == "fresh"`,
copy requirement text/category/status, collect evidence paths only from that result,
put direct/related paths in `candidate_strengths`, and put `none` requirement IDs in
`candidate_risks` and `must_probe`. Generate stable IDs as
`requirement-{one_based_index}`; never copy sensitive Career Vault fields.

- [x] **Step 3: Implement question validation**

```python
def validate_question(
    proposal: object,
    *,
    allowed_refs: set[str],
    turn_index: int,
    previous_questions: list[str],
) -> dict:
```

Require a 5–200 character question, one or two Chinese/ASCII question marks at most,
one non-empty topic, unique refs, `INTRO` only on turn 1, at least one allowed ref,
and no normalized duplicate of an earlier question.

- [x] **Step 4: Implement evaluation and transition validation**

```python
def validate_evaluation(
    value: object,
    *,
    allowed_refs: set[str],
) -> dict:
```

Require integer scores 1–10 for `relevance`, `clarity`, `structure`, `depth`, and
`evidence`; 0–5 issues; 1–5 coaching structure items; and only allowed fact refs.
Reject sensitive values and qualification/probability phrases using
`domain.privacy.contains_sensitive_value`.

Implement:

```python
def validate_transition(
    *,
    status: str,
    phase: str,
    event: str,
    answered_turns: int,
    question_budget: int,
    user_requested: bool = False,
) -> tuple[str, str]:
```

- [x] **Step 5: Implement deterministic artifact compilation**

```python
def compile_interview_artifacts(
    session: dict,
    turns: list[dict],
    *,
    generated_at: str,
) -> dict[str, str]:
```

Render fixed transcript and report headings from the design. Compute answer lengths,
average/min/max, counts for `然后/就是/其实/我觉得`, counts for `我们/我`, and numeric
tokens. `session.json` must use sorted compact JSON and exclude conversation messages,
credentials, audio, private paths, and Career Vault data not referenced by Blueprint.

- [x] **Step 6: Run GREEN**

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_interviews.py -q
```

Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add extensions/career_mcp/domain/interviews.py
git commit -m "feat(interview): add deterministic domain"
```

### Task 3: Schema v10 Transactional Migration

**Files:**

- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/tests/test_migrations.py`

- [x] **Step 1: Write schema v10 RED**

Add a test that migrates a v9 database and asserts:

```python
assert schema_version(connection) == 10
assert {
    row["name"]
    for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
} >= {"interview_sessions", "interview_turns"}
assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
```

Add a failure-injection test that raises on the second interview DDL statement, reconnects,
and asserts version remains 9 and neither interview table remains. Retry migration and assert
version 10.

- [x] **Step 2: Run RED**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_migrations.py -q
```

Expected: schema remains 9.

- [x] **Step 3: Add v10 using individual `execute()` calls**

Set `SCHEMA_VERSION = 10`. Add the two DDL statements and indexes from the design under:

```python
if version < 10 <= SCHEMA_VERSION:
    for statement in INTERVIEW_V10_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (10, utc_now_iso()),
    )
```

Do not use `executescript()` inside the v10 migration because it implicitly commits.

- [x] **Step 4: Run GREEN**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_resume_repository.py \
  extensions/career_mcp/tests/test_match_repository.py -q
```

Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add \
  extensions/career_mcp/database/migrations.py \
  extensions/career_mcp/tests/test_migrations.py
git commit -m "feat(interview): add schema v10"
```

### Task 4: Interview Repository And CAS

**Files:**

- Create: `extensions/career_mcp/database/interview_repository.py`
- Create: `extensions/career_mcp/tests/test_interview_repository.py`

- [x] **Step 1: Write Repository RED**

Cover:

```python
def test_repository_creates_and_maps_session(connection):
    repository = InterviewRepository(connection)
    created = repository.create_session(SESSION)
    assert created["version"] == 1
    assert created["blueprint"]["question_budget"] == 8


def test_repository_updates_session_only_at_expected_version(connection):
    repository = InterviewRepository(connection)
    repository.create_session(SESSION)
    assert repository.update_session_if_version(
        SESSION["id"],
        1,
        status="in_progress",
        phase="asking",
        now=NOW,
    )
    assert not repository.update_session_if_version(
        SESSION["id"],
        1,
        status="cancelled",
        phase="idle",
        now=NOW,
    )


def test_repository_rejects_duplicate_turn_index(connection):
    repository = InterviewRepository(connection)
    repository.create_session(SESSION)
    repository.insert_turn(TURN)
    with pytest.raises(sqlite3.IntegrityError):
        repository.insert_turn({**TURN, "id": "turn-2"})
```

- [x] **Step 2: Run RED**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_repository.py -q
```

Expected: import failure.

- [x] **Step 3: Implement the Repository**

Provide this exact public API:

```text
InterviewRepository(connection: sqlite3.Connection)
create_session(record: dict) -> dict
get_session(session_id: str) -> dict | None
update_session_if_version(
    session_id: str,
    expected_version: int,
    **changes: object,
) -> bool
insert_turn(record: dict) -> dict
current_turn(session_id: str) -> dict | None
list_turns(session_id: str) -> list[dict]
answer_turn(
    turn_id: str,
    *,
    answer_text: str,
    answered_at: str,
) -> bool
evaluate_turn(
    turn_id: str,
    *,
    evaluation: dict,
    next_action: str,
    next_reason: str,
    evaluated_at: str,
) -> bool
```

Serialize JSON with `ensure_ascii=False`, `sort_keys=True`, and compact separators.

- [x] **Step 4: Run GREEN**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_repository.py -q
```

Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add \
  extensions/career_mcp/database/interview_repository.py \
  extensions/career_mcp/tests/test_interview_repository.py
git commit -m "feat(interview): add transactional repository"
```

### Task 5: Interview Service State Machine

**Files:**

- Create: `extensions/career_mcp/services/interviews.py`
- Create: `extensions/career_mcp/tests/test_interview_service.py`

- [x] **Step 1: Write create/start/answer RED**

Using the existing `_seed()` fixture from `test_match_service`, prove:

```python
created = service.create(
    job_id,
    resume_id,
    snapshot_id,
    conversation_id="career-session-1",
    difficulty="standard",
    duration_minutes=15,
)
assert created["status"] == "ready"
assert created["question_budget"] == 8
assert created["blueprint"]["position"]

started = service.start(
    created["id"],
    expected_version=created["version"],
    question={
        "question": "请介绍与你申请这个岗位最相关的一段经历？",
        "refs": ["INTRO"],
        "topic": "self_introduction",
    },
)
assert started["phase"] == "waiting_for_answer"
assert started["turns"][0]["turn_index"] == 1

answered = service.submit_answer(
    created["id"],
    started["turns"][0]["id"],
    expected_version=started["version"],
    answer_text="我负责了一个本地 Agent 项目。",
)
assert answered["phase"] == "evaluating"
```

Also assert stale snapshots, deleted resumes, old CAS versions, wrong turn IDs, duplicate answers,
and sensitive/path-bearing errors produce stable codes without partial rows.

- [x] **Step 2: Write next/finish/report RED**

Prove `evaluate_and_next()` saves evaluation and creates turn 2 in one transaction. Inject a
failure into `insert_turn` and assert neither evaluation nor session version commits.

Complete five turns, finish, generate report, and assert all three files appear together under
`artifacts/interviews/<session-id>/`. Inject rename/commit failures and assert no published
partial directory and no completed session.

- [x] **Step 3: Run RED**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_service.py -q
```

Expected: import failure.

- [x] **Step 4: Implement Service signatures**

```text
InterviewServiceError(
    code: str,
    message: str,
    *,
    violations: list[dict[str, str]] | None = None,
)
InterviewService(config=None, *, workspace=None, clock=None, match_service=None)
create(
    job_id: str,
    resume_id: str,
    snapshot_id: str,
    *,
    conversation_id: str | None,
    difficulty: str,
    duration_minutes: int,
) -> dict
get(session_id: str) -> dict
start(
    session_id: str,
    *,
    expected_version: int,
    question: object,
) -> dict
submit_answer(
    session_id: str,
    turn_id: str,
    *,
    expected_version: int,
    answer_text: str,
) -> dict
evaluate_and_next(
    session_id: str,
    turn_id: str,
    *,
    expected_version: int,
    evaluation: object,
    next_action: str,
    next_reason: str,
    next_question: object | None,
) -> dict
finish(
    session_id: str,
    *,
    expected_version: int,
    user_requested: bool,
) -> dict
generate_report(
    session_id: str,
    *,
    expected_version: int,
) -> dict
read_artifact(session_id: str, kind: str) -> dict
```

- [x] **Step 5: Revalidate match inputs**

`create()` must call:

```python
match_service.analyze(
    job_id,
    [resume_id],
    expected_snapshot_ids=[snapshot_id],
)
```

Use that exact response for Blueprint; never accept job text, resume text, or Blueprint from the
request.

- [x] **Step 6: Implement transactional report publication**

Compile all content before creating the final directory. Write three files in a random private
sibling directory, fsync files and directory, rename the whole directory, then update the
session to completed in the same guarded operation. On database failure, delete or quarantine the
published directory as `.orphan-<uuid>`.

- [x] **Step 7: Run GREEN**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interviews.py -q
```

Expected: all pass.

- [x] **Step 8: Commit**

```bash
git add \
  extensions/career_mcp/services/interviews.py \
  extensions/career_mcp/tests/test_interview_service.py
git commit -m "feat(interview): add transactional service"
```

### Task 6: Career MCP And Mock Interview Skill

**Files:**

- Modify: `extensions/career_mcp/server.py`
- Create: `extensions/career_mcp/tests/test_interview_tools.py`
- Create: `.coworker/skills/mock-interview/SKILL.md`
- Modify: `tests/test_skills.py`

- [x] **Step 1: Write MCP RED**

Test all seven named functions against an injected fake `InterviewService`. Assert exact argument
forwarding, stable error mapping, `violations` pass-through, and registration in FastMCP.

- [x] **Step 2: Write Skill RED**

Require the Skill to contain:

```text
Ask exactly one question per turn.
Previous Interview Turns
FOLLOW_UP
VERIFY_CLAIM
DEEP_DIVE
SWITCH_TOPIC
WRAP_UP
不得显示隐藏评分
不得写回 Career Vault
不得虚构
```

- [x] **Step 3: Run RED**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_tools.py \
  tests/test_skills.py -q
```

Expected: missing tools and Skill.

- [x] **Step 4: Add MCP wrappers**

Add `_interview_service()` and wrappers matching:

```text
create_interview_session(
    job_id: str,
    resume_id: str,
    snapshot_id: str,
    difficulty: str = "standard",
    duration_minutes: int = 15,
) -> dict
get_interview_session(session_id: str) -> dict
start_mock_interview(
    session_id: str,
    expected_version: int,
    question: dict,
) -> dict
submit_interview_answer(
    session_id: str,
    turn_id: str,
    expected_version: int,
    answer_text: str,
) -> dict
get_next_interview_question(
    session_id: str,
    turn_id: str,
    expected_version: int,
    evaluation: dict,
    next_action: str,
    next_reason: str,
    next_question: dict | None = None,
) -> dict
finish_interview(
    session_id: str,
    expected_version: int,
    user_requested: bool = False,
) -> dict
generate_interview_report(
    session_id: str,
    expected_version: int,
) -> dict
```

Register `get_interview_session` with `readOnlyHint=True`,
`idempotentHint=True`, and `openWorldHint=False`. Register the other six tools with
`readOnlyHint=False` and `openWorldHint=False`; set `idempotentHint=True` only for
`start_mock_interview`, `finish_interview`, and `generate_interview_report`.

`create_interview_session` must always pass `conversation_id=None` to the Service. The model
cannot know the authoritative OpenWorker conversation ID; Task 15 binds it from the GUI.

- [x] **Step 5: Write the Skill workflow**

The Skill must call `get_interview_session` before every question, use only returned allowed refs,
submit the answer before evaluating it, call `get_next_interview_question` once, and stop after
one question. It must call finish/report only after WRAP_UP or explicit user end.

- [x] **Step 6: Run GREEN**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_tools.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_skills.py -q
```

Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add \
  extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_interview_tools.py \
  .coworker/skills/mock-interview/SKILL.md \
  tests/test_skills.py
git commit -m "feat(interview): expose career agent tools"
```

### Task 7: Authenticated Interview HTTP API

**Files:**

- Modify: `coworker/server/app.py`
- Create: `tests/test_career_interview_api.py`

- [x] **Step 1: Write HTTP RED**

Create a client with real job/resume/snapshot inputs. Test create/get/start/answer/next/finish/report
and artifact downloads. Parameterize `None`, arrays, strings, numbers, and booleans for every
object body and require `400 INVALID_INPUT`.

Assert responses never contain:

```python
for forbidden in (
    "secret@example.com",
    "13800001234",
    "private_path",
    "access_token",
    "audio_bytes",
):
    assert forbidden not in json.dumps(response.json())
```

- [x] **Step 2: Run RED**

```bash
.venv/bin/pytest tests/test_career_interview_api.py -q
```

Expected: 404 for missing endpoints.

- [x] **Step 3: Add service/error helpers**

Add `career_interview_service()` and a stable `career_interview_error()` mapping the design codes
to 400, 404, or 409. Log only unexpected `PERSISTENCE_ERROR`; never interpolate exception text
into public responses.

- [x] **Step 4: Add endpoints**

Implement the endpoints from the design with `body: Any = Body(None)` and explicit object
validation before passing values to Service. Artifact endpoints return attachment responses for
`transcript`, `report`, and `session`.

- [x] **Step 5: Run GREEN**

```bash
.venv/bin/pytest \
  tests/test_career_interview_api.py \
  tests/test_career_jobs_api.py \
  tests/test_server.py -q
```

Expected: all pass except the already-known optional Bedrock dependency tests, which are not in
this command.

- [x] **Step 6: Commit**

```bash
git add coworker/server/app.py tests/test_career_interview_api.py
git commit -m "feat(interview): add authenticated HTTP API"
```

### Task 8: GUI API And Text InterviewView

**Files:**

- Modify: `surfaces/gui/src/api.ts`
- Create: `surfaces/gui/src/careerInterview.ts`
- Create: `surfaces/gui/src/careerInterview.test.ts`
- Create: `surfaces/gui/src/components/InterviewView.tsx`
- Create: `surfaces/gui/src/components/InterviewView.test.tsx`

- [x] **Step 1: Add RED API URL tests**

Test encoded session/turn IDs and JSON bodies for create/get/start/answer/next/finish/report.
Use the existing global fetch mock pattern from `careerJobsApi.test.ts`.

- [x] **Step 2: Add RED view tests**

Render InterviewView with fake API functions and assert:

- one current question is visible;
- hidden scores are absent during `in_progress`;
- answer text remains editable before submit;
- submit sends the linked Agent prompt once with Skill `mock-interview`;
- polling refreshes to the next turn;
- five answered turns expose finish/report;
- ASR/TTS failures retain text controls;
- VERSION_CONFLICT refreshes without clearing an unsent draft.

- [x] **Step 3: Run RED**

```bash
cd surfaces/gui
npx vitest run \
  src/careerInterview.test.ts \
  src/components/InterviewView.test.tsx
```

Expected: missing modules.

- [x] **Step 4: Add API types and helpers**

Define:

```typescript
export type InterviewStatus =
  | "created" | "ready" | "in_progress"
  | "completed" | "cancelled" | "failed";

export interface CareerInterviewTurn {
  id: string;
  turn_index: number;
  question_text: string;
  question_refs: string[];
  answer_text: string | null;
  evaluation: Record<string, unknown> | null;
  next_action: string | null;
}

export interface CareerInterviewSession {
  id: string;
  job_id: string;
  resume_id: string;
  snapshot_id: string;
  conversation_id: string | null;
  company: string | null;
  position: string;
  difficulty: "simple" | "standard" | "deep";
  duration_minutes: 10 | 15 | 20;
  question_budget: 5 | 8 | 10;
  status: InterviewStatus;
  phase: string;
  version: number;
  turns: CareerInterviewTurn[];
  report_path?: string | null;
}
```

Add authenticated functions for every HTTP endpoint.

- [x] **Step 5: Add prompt framing**

In `careerInterview.ts`, implement:

```typescript
export const interviewStartPrompt = (sessionId: string) =>
  `开始模拟面试。interview_session_id=${sessionId}。` +
  "加载 mock-interview Skill，只提出并保存一道问题。";

export const interviewAnswerPrompt = (
  sessionId: string,
  turnId: string,
  answer: string,
) =>
  `提交模拟面试回答。interview_session_id=${sessionId}；` +
  `turn_id=${turnId}。\n\n候选人回答：\n${answer}`;
```

Reject empty or over-20,000-character answers before building a prompt.

- [x] **Step 6: Implement the text view**

`InterviewView` accepts:

```typescript
{
  interviewId: string;
  onAgentTurn: (prompt: string, skill: "mock-interview") => void;
  onClose: () => void;
}
```

Poll while phase is `asking/evaluating/generating_report`; stop polling in
`waiting_for_answer/idle`. Keep the draft local until submit. Never render `evaluation` before
completed status.

- [x] **Step 7: Run GREEN**

```bash
cd surfaces/gui
npx vitest run \
  src/careerInterview.test.ts \
  src/components/InterviewView.test.tsx
```

Expected: all pass.

- [x] **Step 8: Commit**

```bash
git add \
  surfaces/gui/src/api.ts \
  surfaces/gui/src/careerInterview.ts \
  surfaces/gui/src/careerInterview.test.ts \
  surfaces/gui/src/components/InterviewView.tsx \
  surfaces/gui/src/components/InterviewView.test.tsx
git commit -m "feat(interview): add text interview view"
```

### Task 9: Job Entry And Linked Career Session

**Files:**

- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.tsx`
- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [x] **Step 1: Write RED entry tests**

For exactly one fresh match, assert a “模拟面试” button opens duration and difficulty controls and
emits:

```typescript
{
  jobId,
  resumeId,
  snapshotId,
  durationMinutes: 15,
  difficulty: "standard",
}
```

Assert no action for stale or multi-resume results.

- [x] **Step 2: Write RED App surface test**

Assert starting an interview:

- generates a new Career conversation ID;
- creates an InterviewSession with that ID;
- switches to InterviewView;
- invokes the linked session through `send(prompt, undefined, "mock-interview")`;
- returns to the original job surface without deleting the Career conversation.

For more than one fresh match, require an explicit resume selector and emit the selected
resume/snapshot pair. Do not hide the interview action.

- [x] **Step 3: Run RED**

```bash
cd surfaces/gui
npx vitest run \
  src/components/CareerJobMatchPanel.test.tsx \
  src/components/InterviewView.test.tsx
```

- [x] **Step 4: Wire the entry**

Add `onStartInterview` through MatchPanel and JobsView. Add `"interview"` to App's surface union,
store `activeInterviewId`, render InterviewView, and pass:

```typescript
onAgentTurn={(prompt, skill) => send(prompt, undefined, skill)}
```

Use a freshly generated session ID as `conversation_id` when creating the interview so the
TurnEngine and InterviewSession remain linked.

This direct Job Radar entry remains valid because the GUI creates both IDs. The Agent conversation
entry follows Task 15 instead: MCP creates an unbound InterviewSession and the GUI binds the real
current `sessionId` after the tool succeeds.

- [x] **Step 5: Run GREEN**

```bash
cd surfaces/gui
npx vitest run \
  src/components/CareerJobMatchPanel.test.tsx \
  src/components/CareerJobsView.test.tsx \
  src/components/InterviewView.test.tsx
```

- [x] **Step 6: Commit**

```bash
git add \
  surfaces/gui/src/components/CareerJobMatchPanel.tsx \
  surfaces/gui/src/components/CareerJobMatchPanel.test.tsx \
  surfaces/gui/src/components/CareerJobsView.tsx \
  surfaces/gui/src/App.tsx
git commit -m "feat(interview): link job radar to career session"
```

### Task 10: Capture-Only Tauri Audio

**Files:**

- Modify: `stt/src/lib.rs`
- Modify: `surfaces/gui/src-tauri/src/lib.rs`
- Modify: `surfaces/gui/src-tauri/Cargo.toml`
- Modify: `surfaces/gui/src/tauri.ts`

- [x] **Step 1: Write Rust RED**

Add tests for:

```rust
#[test]
fn wav_encoder_writes_pcm16_mono_header() {
    let bytes = encode_wav_mono(&[0.0, 0.5, -0.5], 16_000);
    assert_eq!(&bytes[0..4], b"RIFF");
    assert_eq!(&bytes[8..12], b"WAVE");
    assert_eq!(u16::from_le_bytes([bytes[22], bytes[23]]), 1);
    assert_eq!(u32::from_le_bytes(bytes[24..28].try_into().unwrap()), 16_000);
}
```

Add a state test proving `start_capture()` does not require a Whisper model, while existing
`start()` still does.

- [x] **Step 2: Run RED**

```bash
cargo test --manifest-path stt/Cargo.toml
```

Expected: missing capture and encoder functions.

- [x] **Step 3: Implement capture-only methods**

Refactor the common stop operation into:

```rust
fn stop_recording(&self) -> Result<RecordedAudio, String>;

pub fn start_capture(&self) -> Result<(), String> {
    self.start_worker()
}

pub fn stop_wav(&self) -> Result<Vec<u8>, String> {
    let audio = self.stop_recording()?;
    let samples = resample_mono(&audio.samples, audio.sample_rate);
    Ok(encode_wav_mono(&samples, WHISPER_SAMPLE_RATE))
}
```

Keep `start()` checking the local model before calling the shared worker start. Keep
`stop_and_transcribe()` behavior unchanged.

- [x] **Step 4: Add Tauri commands**

Add direct dependency:

```toml
base64 = "0.22"
```

Expose `start_interview_capture`, `stop_interview_capture`, and
`cancel_interview_capture`. `stop_interview_capture` returns:

```rust
#[derive(Serialize)]
struct CapturedAudio {
    mime: &'static str,
    data_base64: String,
}
```

Register the commands in `generate_handler!`.

- [x] **Step 5: Add TypeScript bridge**

```typescript
export type CapturedAudio = {
  mime: "audio/wav";
  data_base64: string;
};
export const startInterviewCapture = () =>
  invokeStrict<void>("start_interview_capture");
export const stopInterviewCapture = () =>
  invokeStrict<CapturedAudio>("stop_interview_capture");
export const cancelInterviewCapture = () =>
  invokeStrict<void>("cancel_interview_capture");
```

- [x] **Step 6: Run GREEN**

```bash
cargo test --manifest-path stt/Cargo.toml
cargo check --manifest-path surfaces/gui/src-tauri/Cargo.toml
```

Expected: both pass.

- [x] **Step 7: Commit**

```bash
git add \
  stt/src/lib.rs \
  surfaces/gui/src-tauri/src/lib.rs \
  surfaces/gui/src-tauri/Cargo.toml \
  surfaces/gui/src-tauri/Cargo.lock \
  surfaces/gui/src/tauri.ts
git commit -m "feat(interview): expose transient audio capture"
```

### Task 11: VoiceProvider And Volcengine Protocol

**Files:**

- Create: `extensions/career_mcp/voice/__init__.py`
- Create: `extensions/career_mcp/voice/base.py`
- Create: `extensions/career_mcp/voice/volcengine_protocol.py`
- Create: `extensions/career_mcp/voice/volcengine.py`
- Create: `extensions/career_mcp/services/interview_voice.py`
- Create: `extensions/career_mcp/tests/test_interview_voice.py`

- [x] **Step 1: Write RED provider tests**

Use injected fake WebSocket and HTTP transports. Assert:

- ASR uses `bigmodel_nostream`, 16 kHz mono WAV/PCM, 200 ms chunks, a final negative sequence,
  and configured auth/resource headers.
- TTS uses `/api/v3/tts/unidirectional`, speaker, MP3/24 kHz, and concatenates only decoded audio
  chunks.
- new API key auth emits `X-Api-Key`; legacy auth emits App ID + Access Token.
- timeout, malformed JSON, provider status, empty transcript, and empty audio map to stable errors.
- exception messages never include keys or provider response bodies.

- [x] **Step 2: Write RED service privacy tests**

Patch file writes and assert `transcribe()` and `synthesize()` never call them. Assert max bytes,
MIME, duration, text length, and credential absence fail before transport calls.

- [x] **Step 3: Run RED**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_voice.py -q
```

- [x] **Step 4: Implement binary framing**

Implement the official four-byte header:

```python
def frame_header(
    *,
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
) -> bytes:
    return bytes(
        [
            (1 << 4) | 1,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0,
        ]
    )
```

Add big-endian payload length/sequence framing, gzip JSON request, 200 ms audio packet splitting,
final negative sequence, and server response parsing exactly matching the official ASR document.
Tests must assert exact frame bytes rather than only mocking the high-level method.

- [x] **Step 5: Implement VoiceProvider and Volcengine adapter**

Use:

```python
class VoiceProvider(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh-CN",
    ) -> str:
        raise NotImplementedError

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "interviewer",
    ) -> bytes:
        raise NotImplementedError
```

Resolve credentials from `voice:volcengine` SecretStore profile, with environment override. Do
not log full request headers, bodies, transcript, or audio.

- [x] **Step 6: Implement bounded voice service**

Validate WAV MIME, RIFF/WAVE header, 20 MB, five minutes, question text 5–200 chars, and configured
credentials before invoking the provider. Public failures contain only
`VOICE_NOT_CONFIGURED/ASR_FAILED/TTS_FAILED`.

- [x] **Step 7: Run GREEN**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_voice.py -q
```

- [x] **Step 8: Commit**

```bash
git add \
  extensions/career_mcp/voice \
  extensions/career_mcp/services/interview_voice.py \
  extensions/career_mcp/tests/test_interview_voice.py
git commit -m "feat(interview): add volcengine voice provider"
```

### Task 12: SecretStore Voice Settings And Voice HTTP

**Files:**

- Modify: `coworker/server/manager.py`
- Modify: `coworker/server/app.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_career_interview_api.py`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/components/SettingsView.tsx`

- [x] **Step 1: Write RED settings tests**

Assert save stores `voice:volcengine`, status returns only booleans/non-secret resource/voice IDs,
and GET never returns API key/access token.

- [x] **Step 2: Write RED voice HTTP tests**

Assert base64 decode, MIME/size validation, authenticated response types, and stable errors. Patch
provider and assert audio/transcript never appear in logs or JSON errors.

- [x] **Step 3: Implement manager settings**

Add:

```text
get_voice_provider() -> dict[str, Any]
set_voice_provider(fields: object) -> dict[str, Any]
remove_voice_provider() -> dict[str, Any]
```

Accept `api_key` or legacy `app_id + access_token`, plus ASR resource ID, TTS resource ID, and
speaker. Return only `configured`, `auth_mode`, resource IDs, and speaker.

- [x] **Step 4: Add voice endpoints**

```text
GET    /v1/settings/voice-provider
POST   /v1/settings/voice-provider
DELETE /v1/settings/voice-provider
POST   /v1/career/interviews/voice/transcribe
POST   /v1/career/interviews/voice/synthesize
```

Return audio as `audio/mpeg`, not JSON base64.

- [x] **Step 5: Add minimal Voice Settings fields**

Extend the existing Voice tab with cloud interview voice status and fields. Secret inputs always
render blank after save; non-secret resource IDs and speaker may prefill.

- [x] **Step 6: Run regression**

```bash
.venv/bin/pytest \
  tests/test_settings.py \
  tests/test_career_interview_api.py \
  extensions/career_mcp/tests/test_interview_voice.py -q
cd surfaces/gui
npx vitest run src/components/Composer.voice.test.tsx
```

- [x] **Step 7: Commit**

```bash
git add \
  coworker/server/manager.py \
  coworker/server/app.py \
  tests/test_settings.py \
  tests/test_career_interview_api.py \
  surfaces/gui/src/api.ts \
  surfaces/gui/src/components/SettingsView.tsx
git commit -m "feat(interview): configure cloud voice"
```

### Task 13: Voice InterviewView

**Files:**

- Modify: `surfaces/gui/src/components/InterviewView.tsx`
- Modify: `surfaces/gui/src/components/InterviewView.test.tsx`

- [x] **Step 1: Write voice RED tests**

With a mocked Tauri bridge, test start, live recording state, stop, ASR, editable transcript,
explicit submit, cancel, and cleanup. Test TTS autoplay/replay and URL revocation. Test ASR/TTS
failure keeps question and text input usable.

- [x] **Step 2: Run RED**

```bash
cd surfaces/gui
npx vitest run src/components/InterviewView.test.tsx
```

- [x] **Step 3: Implement voice flow**

Use Tauri capture only when `isTauri()`. After stop, call `transcribeInterviewAudio`, put result
in the editable answer box, and require the existing submit button. Fetch TTS only when a new
question ID appears; create one object URL, play it, and revoke it on question change/unmount.

- [x] **Step 4: Run GREEN**

```bash
cd surfaces/gui
npx vitest run \
  src/components/InterviewView.test.tsx \
  src/components/Composer.voice.test.tsx
```

- [x] **Step 5: Commit**

```bash
git add \
  surfaces/gui/src/components/InterviewView.tsx \
  surfaces/gui/src/components/InterviewView.test.tsx
git commit -m "feat(interview): add turn-based voice UX"
```

### Task 14: Real Five-Turn Acceptance And Closeout

**Files:**

- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [x] **Step 1: Configure real Volcengine credentials**

Use the Settings Voice tab or the machine-local SecretStore. Never add values to Git. Confirm GET
status shows configured without returning secret values.

- [x] **Step 2: Run real ASR/TTS smoke**

Record:

```text
我负责基于 OpenWorker 构建本地求职 Agent。
```

Require the editable transcript to retain `OpenWorker` and `求职 Agent`. Synthesize and play:

```text
请介绍与你申请这个岗位最相关的一段经历。
```

Record latency and provider request IDs only; do not record audio or full provider bodies.

- [x] **Step 3: Run a five-turn linked Career Agent interview**

Use one real saved job, one confirmed resume, and one fresh snapshot. Verify:

- exactly one question per turn;
- at least one FOLLOW_UP or VERIFY_CLAIM references the preceding answer;
- all question refs exist in Blueprint;
- no score appears before completion;
- user can finish after five answered turns;
- three Artifact files are published.

- [x] **Step 4: Run adversarial checks**

Test stale snapshot, deleted resume, old CAS version, duplicate answer, duplicate question,
unknown fact ref, two-question proposal, score outside 1–10, sensitive value in evaluation,
provider timeout, malformed audio, 20 MB boundary, cancel during capture, TTS failure, artifact
symlink, report write failure, and Career Vault row counts before/after.

- [x] **Step 5: Run focused backend and GUI suites**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interviews.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_tools.py \
  extensions/career_mcp/tests/test_interview_voice.py \
  tests/test_career_interview_api.py \
  tests/test_skills.py -q

cd surfaces/gui
npm test -- --run
npm run build
```

Expected: all pass; existing Vite size/import warnings may remain.

- [x] **Step 6: Verify schema and privacy**

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from extensions.career_mcp.database.migrations import connect, migrate, schema_version

with TemporaryDirectory() as directory:
    connection = connect(Path(directory) / "career.sqlite3")
    migrate(connection)
    print("schema", schema_version(connection))
    print("foreign_keys", connection.execute("PRAGMA foreign_key_check").fetchall())
    connection.close()
PY
```

Expected:

```text
schema 10
foreign_keys []
```

Search logs, database, artifacts, workspace, and temporary directories for access tokens and audio
extensions. Require no credential or audio residue.

- [x] **Step 7: Record evidence**

Append exact commands, test counts, session ID, job/resume/snapshot IDs, artifact hashes, five-turn
actions, voice latency, adversarial findings, and remaining risks to the development log. Mark
application support and Mock Interview complete only if all Gates pass.

- [x] **Step 8: Commit closeout**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: close mock interview gate"
```

### Task 15: Authoritative Agent Conversation Binding

**Files:**

- Modify: `extensions/career_mcp/database/interview_repository.py`
- Modify: `extensions/career_mcp/services/interviews.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `coworker/server/app.py`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/careerInterview.ts`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `.coworker/skills/mock-interview/SKILL.md`
- Test: `extensions/career_mcp/tests/test_interview_service.py`
- Test: `extensions/career_mcp/tests/test_interview_tools.py`
- Test: `tests/test_career_interview_api.py`
- Test: `surfaces/gui/src/careerInterview.test.ts`
- Test: `surfaces/gui/src/App.interview.test.tsx`

Real TurnEngine acceptance proved that the model can invent a plausible
`conversation_id`. Treat the GUI's current OpenWorker `sessionId` as the only authority.

- [x] **Step 1: Write and run Service, MCP, HTTP, helper, and App RED**

Require one-time CAS binding, no MCP `conversation_id` parameter, an HTTP bind route, one
`VERSION_CONFLICT` refresh/retry, and navigation only after successful binding.

- [x] **Step 2: Implement the minimal binding boundary**

MCP creation writes `conversation_id=None`. The GUI parses only a successful Career create tool
UUID, gets the current InterviewSession version, binds the current real `sessionId` over HTTP, and
opens InterviewView only after success. The Service rejects rebinding to a different conversation.

- [x] **Step 3: Run focused GREEN**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_service.py::test_service_binds_one_real_conversation_with_cas \
  extensions/career_mcp/tests/test_interview_tools.py::test_interview_tools_are_registered \
  tests/test_career_interview_api.py::test_interview_http_binds_the_current_conversation -q

cd surfaces/gui
npm test -- --run src/careerInterview.test.ts src/App.interview.test.tsx
```

Expected: backend `3 passed`; GUI `11 passed`.

- [x] **Step 4: Re-run the real Career Agent creation entry**

Create an interview through a real Career TurnEngine conversation and require the persisted
`conversation_id` to equal that exact OpenWorker session ID. Reject placeholder or model-generated
values such as `current-career-conversation`.

### Task 16: Original Specification Completion Audit

**Files:**

- Modify: `extensions/career_mcp/domain/interviews.py`
- Modify: `extensions/career_mcp/tests/test_interviews.py`
- Modify: `.coworker/skills/mock-interview/SKILL.md`
- Modify: `tests/test_skills.py`
- Create: `docs/17_MOCK_INTERVIEW_COMPLETION_AUDIT.md`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [x] **Step 1: Map all 23 MVP Done Definition items to authoritative evidence**

Classify each item as proved, partially proved, or incomplete. Do not treat fake provider tests as
evidence of real Volcengine operation.

- [x] **Step 2: Write RED for locally missing specification behavior**

Require report output for repeated expressions, off-topic degree, STAR/structure completeness,
and per-question reference optimization. Require the Skill to declare supported first-version
question types.

- [x] **Step 3: Implement deterministic report and Skill coverage**

Reuse hidden relevance and structure scores; count repeated normalized clauses without another
model call. Reference optimization may only recommend restructuring the original answer with
confirmed facts.

- [x] **Step 4: Run regression**

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interviews.py \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interview_service.py \
  extensions/career_mcp/tests/test_interview_tools.py \
  extensions/career_mcp/tests/test_interview_voice.py \
  tests/test_career_interview_api.py \
  tests/test_skills.py -q

cd surfaces/gui
npm test -- --run
npm run build

cd ../..
cargo test --manifest-path stt/Cargo.toml
```

Evidence: backend `78 passed, 1 warning`; GUI 40 files and `202 passed`; Rust `6 passed`;
production build, Python compile, and `git diff --check` passed.

- [x] **Step 5: Close the three real Voice requirements**

Configure real credentials, run Chinese ASR and TTS smoke, then complete five real voice turns.
Final audit result: all 23 MVP Done Definition items are proved.
