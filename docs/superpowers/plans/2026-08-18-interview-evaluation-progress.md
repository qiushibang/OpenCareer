# Interview Evaluation and Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the dedicated interview evaluation Skill, deterministic per-question scoring, concise evidence-based reports, a five-slot dynamic progress panel, and unfinished Conversation recovery.

**Architecture:** The model selects applicable evidence levels under a strict Skill contract; domain code validates dimensions and computes the score. InterviewSession remains the sole business-state source for both the top bar and right rail. Existing `evaluation_json` stores versioned v2 objects.

**Tech Stack:** Python, Markdown Skill, React 18, TypeScript, Vitest, pytest.

---

### Task 1: Evaluation Skill contract

**Files:**
- Create: `.coworker/skills/career-interview-evaluation/SKILL.md`
- Modify: `.coworker/skills/mock-interview/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] Write RED assertions for triggers, input order, dynamic dimensions, 0–4 anchors, evidence quotes, one pain, reason, strategy, prohibited bias, no fabrication, and same-target low-evidence follow-up.
- [ ] Add the Skill with valid frontmatter and strict JSON example.
- [ ] Make `mock-interview` delegate evaluation rules without duplicating them.
- [ ] Run `pytest -q tests/test_skills.py`; expect PASS.
- [ ] Commit `feat(interview): add evaluation skill`.

### Task 2: Evaluation v2 validation and scoring

**Files:**
- Modify: `extensions/career_mcp/domain/interviews.py`
- Test: `tests/test_interview_domain.py`

- [ ] Write RED parameterized tests for behavior, product, technical, coding, system design, AI/ML, and reflection templates.
- [ ] Assert unknown dimensions, wrong anchors, unknown refs, sensitive text, and model-supplied score manipulation are rejected.
- [ ] Implement template weights and deterministic 0–100 calculation.
- [ ] Keep v1 read compatibility but accept only v2 for new evaluation.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(interview): validate evidence-based scores`.

### Task 3: Repository and service compatibility

**Files:**
- Modify: `extensions/career_mcp/database/interview_repository.py`
- Modify: `extensions/career_mcp/services/interviews.py`
- Test: `tests/test_interview_service.py`

- [ ] Write RED tests storing/reloading v2, concurrent version conflict, answer persistence before evaluation retry, and transition rules.
- [ ] Persist v2 in existing `evaluation_json`; do not add a schema migration.
- [ ] Ensure invalid evaluation does not duplicate or lose the candidate answer.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(interview): persist evaluation v2`.

### Task 4: Report compiler

**Files:**
- Modify: `extensions/career_mcp/domain/interviews.py`
- Test: `tests/test_interview_report.py`

- [ ] Write RED snapshots for the visible fields: score, pain, evidence reason, and one strategy.
- [ ] Assert fixed five-dimension averages, STAR completeness, and raw number-count heuristics are absent from v2 reports.
- [ ] Preserve v1 report rendering for historical sessions.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `feat(interview): simplify evidence-based reports`.

### Task 5: Five-slot progress panel

**Files:**
- Create: `surfaces/gui/src/components/InterviewProgressPanel.tsx`
- Create: `surfaces/gui/src/components/InterviewProgressPanel.test.tsx`
- Modify: `surfaces/gui/src/components/RightRail.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] Write RED tests for five slots, blue completed, green current, gray pending, dynamic labels, long questions, and evaluation retry.
- [ ] Assert replay, early finish, and separate flow status controls are absent.
- [ ] Feed the component from `useConversationInterview`; do not create local workflow state.
- [ ] Run focused Vitest tests; expect PASS.
- [ ] Commit `feat(gui): show interview question progress`.

### Task 6: Unfinished Conversation recovery

**Files:**
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/careerInterview.ts`
- Modify: `extensions/career_mcp/services/interviews.py`
- Test: `surfaces/gui/src/careerInterview.test.ts`
- Test: `tests/test_interview_service.py`

- [ ] Write RED tests that same job/resume resumes one unfinished Conversation, completed interview creates a new one, and explicit restart archives the old one.
- [ ] Add a service query for active session by user/job/resume.
- [ ] Remove unconditional `newId()` from the recovery path.
- [ ] Run focused Python and GUI tests; expect PASS.
- [ ] Commit `fix(interview): resume unfinished conversations`.

### Task 7: Skill load latency

**Files:**
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/careerInterview.ts`
- Modify: `coworker/server/app.py`
- Test: `tests/test_session_skills.py`
- Test: `surfaces/gui/src/careerInterview.test.ts`

- [ ] Write RED tests proving only the first turn requests the two Skills and later answers send no Skill field.
- [ ] Use session Skill hash state from the context plan for server-side enforcement.
- [ ] Run focused tests; expect PASS.
- [ ] Commit `perf(interview): avoid repeated skill loads`.

### Task 8: Full interview gate

- [ ] Run all interview Python tests.
- [ ] Run `cd surfaces/gui && npx tsc`.
- [ ] Run full GUI tests.
- [ ] Run `bash deploy/build-frontend.sh`.
- [ ] Use browser automation at desktop and mobile widths to verify no overlap and all five states.
- [ ] Run one adversarial five-question interview with three strong and two incomplete answers.
- [ ] Verify report evidence, same-target follow-up, artifacts, Conversation recovery, and PostgreSQL records.
- [ ] Record evidence and commit `docs(interview): record evaluation and progress gate`.
