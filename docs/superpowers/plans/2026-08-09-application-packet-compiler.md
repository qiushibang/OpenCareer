# Application Packet Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, approval-gated compiler that creates official Markdown application packets only from fresh Career match snapshots and blocks invalid output before writing.

**Architecture:** A pure Domain module validates and renders the existing `MatchService` response. `ApplicationPacketService` verifies opaque IDs through `MatchService`, compiles the packet, and atomically writes to a fixed workspace directory. A new Career MCP tool exposes that service; the Career Skill is narrowed so official packets cannot be generated through free-form `write_file`.

**Tech Stack:** Python 3.12, pathlib, pytest, FastMCP, existing Career Domain/Service patterns, OpenWorker MCP approval.

---

## File Map

- Create `extensions/career_mcp/domain/application_packets.py`: pure packet validation, rendering, defensive scan, safe filename.
- Create `extensions/career_mcp/services/application_packets.py`: input validation, MatchService integration, atomic workspace write.
- Create `extensions/career_mcp/tests/test_application_packets.py`: Domain RED/GREEN coverage.
- Create `extensions/career_mcp/tests/test_application_packet_service.py`: Service RED/GREEN coverage.
- Modify `extensions/career_mcp/server.py`: service factory, MCP function, error mapping, tool registration.
- Modify `extensions/career_mcp/tests/test_resume_tools.py`: MCP parameter and stable error tests.
- Modify `.coworker/skills/career-application-packet/SKILL.md`: require the compiler tool and prohibit free-form official writes.
- Modify `tests/test_skills.py`: lock the Skill contract.
- Modify `docs/11_DEVELOPMENT_LOG.md`: record implementation and evidence.
- Modify `docs/12_TONIGHT_PROGRESS.md`: update the stage gate and next task.

### Task 1: Pure Domain Compiler

**Files:**
- Create: `extensions/career_mcp/tests/test_application_packets.py`
- Create: `extensions/career_mcp/domain/application_packets.py`

- [ ] **Step 1: Write the failing happy-path test**

Create a minimal authoritative match result with one `direct` and one `none`
requirement, then assert the wished-for API:

```python
from extensions.career_mcp.domain.application_packets import compile_application_packet


def test_compile_application_packet_renders_traceable_fixed_sections():
    packet = compile_application_packet(_match_result())

    assert packet["validation"] == {"passed": True, "violations": []}
    assert packet["markdown"].startswith("# 申请准备包\n")
    assert packet["markdown"].count("## 岗位与官方来源") == 1
    assert "snapshot-1" in packet["markdown"]
    assert "使用 Python 构建服务" in packet["markdown"]
    assert "暂无已确认佐证" in packet["markdown"]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_application_packets.py
```

Expected: collection fails because `application_packets` does not exist.

- [ ] **Step 3: Add the minimal compiler API**

Implement:

```python
class ApplicationPacketValidationError(ValueError):
    def __init__(self, violations: list[dict[str, str]]) -> None:
        super().__init__("application packet validation failed")
        self.violations = violations


def compile_application_packet(match_result: dict, *, generated_at: str) -> dict:
    validate_match_result(match_result)
    markdown = render_application_packet(match_result, generated_at=generated_at)
    validate_rendered_packet(markdown, match_result)
    return {
        "markdown": markdown,
        "validation": {"passed": True, "violations": []},
    }
```

The renderer must emit the eight approved headings in fixed order and copy job,
resume, snapshot, requirement, evidence excerpt, path, section, status and
matched terms without semantic rewriting.

- [ ] **Step 4: Run the happy-path test and verify GREEN**

Run the same command. Expected: the happy-path test passes.

- [ ] **Step 5: Add RED tests for structural invariants**

Add separate tests that reject:

```python
def _violation_codes(result: dict) -> list[str]:
    with pytest.raises(ApplicationPacketValidationError) as error:
        compile_application_packet(result, generated_at=NOW)
    return [item["code"] for item in error.value.violations]


def test_compile_rejects_none_with_evidence():
    result = _match_result()
    result["results"][0]["requirements"][1]["evidence"] = [
        {
            "section": "skill",
            "path": "skill[0].name",
            "excerpt": "Python",
            "matched_terms": ["python"],
        }
    ]
    assert "NONE_HAS_EVIDENCE" in _violation_codes(result)


def test_compile_rejects_duplicate_snapshot_ids():
    result = _match_result()
    result["results"].append(copy.deepcopy(result["results"][0]))
    assert "DUPLICATE_SNAPSHOT" in _violation_codes(result)


def test_compile_rejects_non_fresh_result():
    result = _match_result()
    result["results"][0]["snapshot_status"] = "stale_resume"
    assert "STALE_MATCH" in _violation_codes(result)


def test_compile_rejects_missing_job_or_resume_identity():
    result = _match_result()
    result["results"][0]["resume"]["id"] = ""
    assert "MISSING_ID" in _violation_codes(result)


def test_compile_rejects_unknown_evidence_status():
    result = _match_result()
    result["results"][0]["requirements"][0]["status"] = "maybe"
    assert "INVALID_STATUS" in _violation_codes(result)
```

Each test must assert `ApplicationPacketValidationError.violations` contains a
stable code such as `NONE_HAS_EVIDENCE`, `DUPLICATE_SNAPSHOT`,
`STALE_MATCH`, `MISSING_ID`, or `INVALID_STATUS`.

- [ ] **Step 6: Run the structural tests and verify RED**

Expected: at least one invalid input is accepted by the minimal compiler.

- [ ] **Step 7: Implement structural validation**

Use explicit type and membership checks. Do not infer missing values and do not
mutate the MatchService response. Collect deterministic violations in traversal
order and raise once before rendering.

- [ ] **Step 8: Add RED tests for output safety**

Cover:

```python
@pytest.mark.parametrize(
    "forbidden",
    [
        "13800001234",
        "secret@example.com",
        "/Users/example/private.pdf",
        "100% 匹配",
        "符合岗位资格",
        "约 5 个月",
    ],
)
def test_compile_rejects_forbidden_rendered_content(forbidden):
    result = _match_result()
    result["job"]["title"] = forbidden

    assert "FORBIDDEN_CONTENT" in _violation_codes(result)
```

Also assert a `none` requirement never causes any resume excerpt to appear in
the “建议重点强调” section.

- [ ] **Step 9: Run safety tests and verify RED**

Expected: the compiler accepts at least one forbidden payload.

- [ ] **Step 10: Implement defensive scanning and fixed templates**

Use conservative patterns for mainland phone numbers, email addresses, absolute
paths, percentage match language, qualification verdicts, and derived tenure.
The normal renderer must never create those expressions.

- [ ] **Step 11: Run Domain tests and full matching tests**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_application_packets.py \
  extensions/career_mcp/tests/test_matching.py \
  extensions/career_mcp/tests/test_match_service.py
```

Expected: all pass.

- [ ] **Step 12: Commit**

```bash
git add \
  extensions/career_mcp/domain/application_packets.py \
  extensions/career_mcp/tests/test_application_packets.py
git commit -m "feat(career): compile traceable application packets"
```

### Task 2: Atomic Application Packet Service

**Files:**
- Create: `extensions/career_mcp/tests/test_application_packet_service.py`
- Create: `extensions/career_mcp/services/application_packets.py`

- [ ] **Step 1: Write the failing Service success test**

Seed a real job and confirmed resume using the existing test helpers, create a
fresh snapshot with `MatchService.analyze`, and assert:

```python
result = service.create(job_id, [resume_id], [snapshot_id])

target = workspace / result["artifact_path"]
assert target.is_file()
assert target.read_text(encoding="utf-8").startswith("# 申请准备包")
assert result["validation"]["passed"] is True
assert result["snapshot_ids"] == [snapshot_id]
```

- [ ] **Step 2: Run the Service test and verify RED**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_application_packet_service.py
```

Expected: collection fails because `ApplicationPacketService` does not exist.

- [ ] **Step 3: Implement the minimal Service**

Create:

```python
class ApplicationPacketServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ApplicationPacketService:
    def __init__(
        self,
        config: CareerConfig | None = None,
        *,
        workspace: Path | None = None,
        clock=None,
        match_service: MatchService | None = None,
    ) -> None:
        self.config = config or CareerConfig.from_env()
        self.workspace = (workspace or Path.cwd()).resolve()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._match_service = match_service or MatchService(
            self.config,
            clock=self._clock,
        )

    def create(
        self,
        job_id: str,
        resume_ids: list[str],
        snapshot_ids: list[str],
    ) -> dict:
        match_result = self._match_service.analyze(
            job_id,
            resume_ids,
            expected_snapshot_ids=snapshot_ids,
        )
        generated_at = self._iso(self._now())
        compiled = compile_application_packet(
            match_result,
            generated_at=generated_at,
        )
        relative_path = application_packet_path(
            match_result,
            snapshot_ids=snapshot_ids,
            generated_at=generated_at,
        )
        self._atomic_write(relative_path, compiled["markdown"])
        return {
            "artifact_path": relative_path.as_posix(),
            "snapshot_ids": list(snapshot_ids),
            "validation": compiled["validation"],
        }
```

The default workspace is `Path.cwd().resolve()`. The target directory is always
`workspace / "artifacts" / "application-packets"`. Call:

```python
match_service.analyze(
    job_id,
    resume_ids,
    expected_snapshot_ids=snapshot_ids,
)
```

Map `MatchServiceError` without exposing internal paths. Compile fully before
creating the target directory.

- [ ] **Step 4: Implement safe deterministic filename and atomic write**

The Domain filename helper must retain Chinese letters and ASCII alphanumerics,
replace all other runs with `-`, trim separators, cap each component, and never
return `.` or `..`.

Write UTF-8 content to a same-directory `.tmp` file, flush and close it, then
call `os.replace(temporary, target)`. In `finally`, unlink any remaining
temporary file.

- [ ] **Step 5: Run the success test and verify GREEN**

Expected: pass and only one official Markdown file exists.

- [ ] **Step 6: Add RED no-side-effect tests**

Cover invalid length, duplicate IDs, mismatched snapshot IDs, stale inputs,
compiler validation failure and simulated `os.replace` failure. For each:

```python
assert list((workspace / "artifacts").rglob("*")) == []
```

or, after a pre-existing successful file, assert its bytes are unchanged.

- [ ] **Step 7: Implement stable error mapping**

Map:

```text
INVALID_INPUT
JOB_NOT_FOUND
RESUME_NOT_FOUND
SNAPSHOT_MISMATCH
STALE_MATCH
PACKET_VALIDATION_FAILED
PERSISTENCE_ERROR
```

Do not include absolute workspace paths in messages.

- [ ] **Step 8: Verify Service and matching regression**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_application_packet_service.py \
  extensions/career_mcp/tests/test_match_service.py
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add \
  extensions/career_mcp/services/application_packets.py \
  extensions/career_mcp/tests/test_application_packet_service.py
git commit -m "feat(career): write validated application packets atomically"
```

### Task 3: Protected MCP Tool and Skill Contract

**Files:**
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_resume_tools.py`
- Modify: `.coworker/skills/career-application-packet/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: Write failing MCP tests**

Add:

```python
def test_create_application_packet_uses_shared_service(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server,
        "_application_packet_service",
        lambda: SimpleNamespace(
            create=lambda job_id, resume_ids, snapshot_ids: (
                calls.append((job_id, resume_ids, snapshot_ids))
                or {"artifact_path": "artifacts/application-packets/a.md"}
            )
        ),
    )

    result = server.create_application_packet(
        "job-1",
        ["resume-1"],
        ["snapshot-1"],
    )

    assert result["ok"] is True
    assert calls == [("job-1", ["resume-1"], ["snapshot-1"])]


def test_create_application_packet_returns_stable_service_error(monkeypatch):
    def fail(*_args):
        raise ApplicationPacketServiceError(
            "SNAPSHOT_MISMATCH",
            "match snapshots no longer match current inputs",
        )

    monkeypatch.setattr(
        server,
        "_application_packet_service",
        lambda: SimpleNamespace(create=fail),
    )

    result = server.create_application_packet(
        "job-1",
        ["resume-1"],
        ["snapshot-old"],
    )

    assert result["error"]["code"] == "SNAPSHOT_MISMATCH"
    assert "/Users/" not in result["error"]["message"]
```

Assert the exact ordered arguments are passed and error payload contains the
stable code but no absolute path.

- [ ] **Step 2: Write failing Skill tests**

Require:

```python
assert "create_application_packet" in packet
assert "不得使用 `write_file`" in packet
assert "artifacts/application-packets/" in packet
```

Remove assertions that require the Agent to manually render the eight sections;
the compiler now owns that contract.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_skills.py
```

Expected: missing tool and Skill contract failures.

- [ ] **Step 4: Register the MCP tool**

Add a factory and function:

```python
def _application_packet_service() -> ApplicationPacketService:
    return ApplicationPacketService()


def create_application_packet(
    job_id: str,
    resume_ids: list[str],
    snapshot_ids: list[str],
) -> dict:
    try:
        return _ok(
            _application_packet_service().create(
                job_id,
                resume_ids,
                snapshot_ids,
            )
        )
    except ApplicationPacketServiceError as exc:
        return _error(exc.code, str(exc))
```

Register with `mcp.tool()(create_application_packet)`. The workspace Career MCP
server already defaults to `requires_approval=true`; add a regression in
`tests/test_mcp.py` only if this invariant is not already covered.

- [ ] **Step 5: Narrow the Skill**

Require the sequence:

```text
get_candidate_profile(include_sensitive=false)
create_application_packet(job_id, resume_ids, snapshot_ids)
```

State that official files under `artifacts/application-packets/` must never be
created or edited with `write_file`, `replace_in_file`, shell redirection or a
model-authored Markdown body.

- [ ] **Step 6: Run focused tests and verify GREEN**

Expected: all pass.

- [ ] **Step 7: Run live stdio discovery**

Use the existing MCP SDK smoke command or test helper and assert
`create_application_packet` is discoverable with all three required arguments.

- [ ] **Step 8: Commit**

```bash
git add \
  extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  .coworker/skills/career-application-packet/SKILL.md \
  tests/test_skills.py
git commit -m "feat(career): expose protected application packet compiler"
```

### Task 4: Real Artifact and Regression Gate

**Files:**
- Modify: `artifacts/application-packets/deepseek-agi管培生-申请准备包-20260809.md`

- [ ] **Step 1: Run focused backend regression**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_application_packets.py \
  extensions/career_mcp/tests/test_application_packet_service.py \
  extensions/career_mcp/tests/test_matching.py \
  extensions/career_mcp/tests/test_match_service.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py \
  tests/test_skills.py
```

- [ ] **Step 2: Regenerate the real DeepSeek artifact**

Call `create_application_packet` with:

```text
job_id=ad9b82d1-e411-4677-bbe8-8ca535357a71
resume_ids=[0ff8c6a3-0996-478a-aaf5-9cc9f95296a8]
snapshot_ids=[ad17d0bb-dc26-4e44-b24f-fc5bccb4c88e]
```

If the snapshot is stale, stop with `SNAPSHOT_MISMATCH`; do not silently replace
the supplied ID. Re-run the GUI match explicitly before creating a new packet.

- [ ] **Step 3: Audit the real artifact**

Assert:

- eight headings in order;
- four requirements;
- three `none`, one `related`;
- exactly seven evidence entries for the related requirement;
- no phone, email, private path, qualification verdict, percentage or derived tenure;
- job, resume and snapshot IDs match the tool result.

- [ ] **Step 4: Run complete backend and GUI gates**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py \
  tests/test_mcp.py \
  tests/test_skills.py \
  tests/test_builtin_personas.py

cd surfaces/gui
npm test -- --run
npm run build
```

- [ ] **Step 5: Run database and diff integrity checks**

```bash
sqlite3 career/career.sqlite3 \
  'PRAGMA user_version; PRAGMA foreign_key_check;'
git diff --check
```

Expected: schema v6, no foreign-key rows, no whitespace errors.

### Task 5: Documentation and Adversarial Review

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Record implementation evidence**

Document the Domain, Service, MCP, Skill, real artifact, test counts, approval
behavior and any warnings. Do not claim the next stage has started.

- [ ] **Step 2: Perform two independent adversarial reviews**

Review one axis per thread:

1. Security and invariant bypass: sensitive values, path traversal, stale
   snapshot, partial file, direct `write_file`, approval bypass.
2. Product correctness: evidence count, `none` preservation, deterministic
   templates, idempotency, actionable errors, no qualification inference.

- [ ] **Step 3: Fix every critical or major finding with TDD**

For each accepted finding, first add a failing regression test, verify RED,
apply the smallest fix, then verify focused and complete suites.

- [ ] **Step 4: Update the stage compass**

Mark the application packet compiler complete only after both reviews report no
remaining critical or major issue. Set the next task to “岗位收藏与申请跟踪设计”.

- [ ] **Step 5: Commit documentation**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record application packet compiler acceptance"
```
