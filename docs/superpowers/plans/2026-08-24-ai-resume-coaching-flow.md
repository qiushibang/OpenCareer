# AI Resume Coaching Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visible scripted job/resume matching workflow with a single-resume launcher that automatically starts an AI-led Career Conversation for resume diagnosis, rewriting guidance, and targeted interview preparation.

**Architecture:** Keep the existing deterministic matching service untouched for mock-interview compatibility, but remove it entirely from the new resume-coaching path. Add one tenant-scoped, read-only MCP tool for a selected confirmed resume; replace the old tailored-resume Skill with an AI coaching Skill; then wire a minimal GUI launcher to a dedicated queued Career turn carrying only opaque job and resume IDs.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, FastAPI/OpenWorker MCP, Python 3.12, pytest, SQLite/PostgreSQL tenant-scoped resume services.

---

## Preconditions And Change Discipline

The current worktree contains unrelated, uncommitted changes, including changes in
`App.tsx`, `CareerJobsView.tsx`, `CareerJobMatchPanel.tsx`, server code, tests, and
deployment files. Before every task:

```bash
git status --short
git diff --stat
```

Preserve all unrelated edits. Stage and commit only the files listed by the current
task. Do not deploy this work; local implementation does not change the running alpha.

## File Map

- `extensions/career_mcp/server.py`: expose the selected confirmed resume through a
  read-only MCP tool; do not add matching logic.
- `extensions/career_mcp/tests/test_resume_tools.py`: verify delegation, masking, and
  stable errors for the MCP tool.
- `.coworker/skills/career-resume-coach/SKILL.md`: define the AI-only diagnosis,
  clarification, rewriting, and interview-preparation workflow. Add it first while
  the old Skill remains available, then remove the old Skill during the atomic GUI
  cutover.
- `.coworker/skills/career-tailored-resume/SKILL.md`: remove the superseded
  snapshot/draft/export Skill only after all frontend references are removed.
- `tests/test_skills.py`: lock the new Skill contract and prohibit old tools.
- `surfaces/gui/src/careerResumeCoach.ts`: define the opaque launch payload and queued
  Conversation message.
- `surfaces/gui/src/careerResumeCoach.test.ts`: verify prompt privacy and absence of
  snapshot/matching instructions.
- `surfaces/gui/src/careerApplicationPacket.ts`,
  `surfaces/gui/src/careerApplicationPacket.test.ts`,
  `surfaces/gui/src/careerTailoredResume.ts`, and
  `surfaces/gui/src/careerTailoredResume.test.ts`: remove unused frontend launch
  helpers after their entries disappear.
- `surfaces/gui/src/components/CareerResumeCoachLauncher.tsx`: implement the
  single-resume AI coaching launcher without disturbing the currently shipped panel.
- `surfaces/gui/src/components/CareerResumeCoachLauncher.test.tsx`: verify launcher
  behavior independently before the atomic cutover.
- `surfaces/gui/src/components/CareerJobMatchPanel.tsx` and
  `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`: remove during the atomic
  cutover after the new launcher and App flow pass.
- `surfaces/gui/src/components/CareerTailoredResumePanel.tsx` and
  `surfaces/gui/src/components/CareerTailoredResumePanel.test.tsx`: remove as
  unreferenced visible draft/export UI during the cutover; backend services remain.
- `surfaces/gui/src/components/CareerJobsView.tsx`: replace packet/tailored callbacks
  with the new coaching callback while preserving mock interview matching.
- `surfaces/gui/src/components/CareerJobsView.test.tsx`: verify the job-detail entry.
- `surfaces/gui/src/App.tsx`: queue and automatically send one independent Career
  coaching turn while preserving the trusted workspace.
- `surfaces/gui/src/App.interview.test.tsx`: cover automatic send, exactly-once
  behavior, and missing-workspace failure without weakening interview tests.
- `docs/11_DEVELOPMENT_LOG.md` and `docs/12_TONIGHT_PROGRESS.md`: append verified
  implementation evidence.

### Task 1: Add The Read-Only Confirmed Resume MCP Tool

**Files:**
- Modify: `extensions/career_mcp/tests/test_resume_tools.py`
- Modify: `extensions/career_mcp/server.py`

- [ ] **Step 1: Write the failing delegation and masking tests**

Add focused tests that use the real resume service for masking and a stub for the
stable error contract:

```python
def test_get_confirmed_resume_returns_only_selected_masked_document(
    tmp_path,
    monkeypatch,
):
    staged = _stage(tmp_path, monkeypatch)
    preview = server.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    server.confirm_resume_sections(
        preview["data"]["preview_token"],
        ["basic"],
        {},
    )
    resume_id = server.list_confirmed_resumes()["data"]["resumes"][0]["id"]

    result = server.get_confirmed_resume(resume_id)

    assert result["ok"] is True
    assert result["data"]["id"] == resume_id
    assert result["data"]["sections"]["basic"]["phone"] == "*******1234"
    assert result["data"]["sections"]["basic"]["email"] == "z***@example.com"
    serialized = str(result["data"])
    assert "private_path" not in serialized
    assert "upload_token" not in serialized


def test_get_confirmed_resume_returns_stable_not_found_error(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("CAREER_PRIVATE_DIR", str(tmp_path / "private"))

    result = server.get_confirmed_resume("missing-resume")

    assert result["ok"] is False
    assert result["error"]["code"] == "RESUME_NOT_FOUND"
    assert "private" not in result["error"]["message"].lower()
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest \
  extensions/career_mcp/tests/test_resume_tools.py::test_get_confirmed_resume_returns_only_selected_masked_document \
  extensions/career_mcp/tests/test_resume_tools.py::test_get_confirmed_resume_returns_stable_not_found_error \
  -q
```

Expected: both tests fail because `server.get_confirmed_resume` does not exist.

- [ ] **Step 3: Implement the minimal MCP wrapper**

Add beside `list_confirmed_resumes`:

```python
def get_confirmed_resume(resume_id: str) -> dict:
    """Return one confirmed resume with sensitive facts masked."""
    try:
        return _ok(
            _resume_service().get_resume_document(
                resume_id,
                include_sensitive=False,
            )
        )
    except ResumeServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )
```

Register it as explicitly read-only:

```python
mcp.tool(
    annotations={
        "title": "读取已确认简历",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)(get_confirmed_resume)
```

Do not add a new repository query. Both SQLite `ResumeService` and cloud
`PostgresResumeService` already implement `get_resume_document()` with masking, missing
record behavior, and tenant isolation.

- [ ] **Step 4: Run MCP and PostgreSQL tenant regressions**

Run:

```bash
python -m pytest extensions/career_mcp/tests/test_resume_tools.py -q
python -m pytest \
  tests/test_postgres_resume_service.py::test_resume_service_lists_only_current_tenant_and_masks_detail \
  -q
```

Expected: all selected tests pass. The PostgreSQL test must continue returning
`RESUME_NOT_FOUND` for another tenant's resume.

- [ ] **Step 5: Commit only the MCP tool**

```bash
git add extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_resume_tools.py
git commit -m "feat(career): expose confirmed resume to agent"
```

### Task 2: Add The AI Resume Coaching Skill

**Files:**
- Create: `.coworker/skills/career-resume-coach/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: Update the Skill contract test first**

Add `career-resume-coach` to the expected workspace Skill names while retaining
`career-tailored-resume` until the final cutover. Add this independent contract:

```python
    assert loader.names() == [
        "career-application-packet",
        "career-interview-evaluation",
        "career-jd-analysis",
        "career-job-search",
        "career-resume-coach",
        "career-resume-import",
        "career-tailored-resume",
        "mock-interview",
    ]

    coach = loader.get("career-resume-coach").instructions
    for required in (
        "get_job",
        "get_confirmed_resume",
        "项目与实习证据",
        "基础能力覆盖",
        "JD 缺失项",
        "需要用户补充的真实事实",
        "保留",
        "删除",
        "补充",
        "重写",
        "加粗",
        "核心问题",
        "可能追问",
        "面试官验证的能力点",
        "JOB_NOT_FOUND",
        "RESUME_NOT_FOUND",
    ):
        assert required in coach
    for forbidden in (
        "match_job_to_profile",
        "prepare_tailored_resume",
        "submit_tailored_resume_proposals",
        "create_application_packet",
        "validate_application_packet",
        "include_sensitive=true",
        "DOCX",
        "PDF",
    ):
        assert forbidden not in coach
```

Also assert the priority order from the normalized text:

```python
    assert coach.index("项目经历") < coach.index("实习与工作经历")
    assert coach.index("实习与工作经历") < coach.index("基础能力与技能")
    assert coach.index("基础能力与技能") < coach.index("教育经历")
```

- [ ] **Step 2: Run the Skill test and verify RED**

Run:

```bash
python -m pytest tests/test_skills.py::test_workspace_career_skills_are_discoverable -q
```

Expected: FAIL because `career-resume-coach` is absent.

- [ ] **Step 3: Add the Skill**

Create the new Skill with this complete contract:

```markdown
---
name: career-resume-coach
description: Analyze one saved job and one confirmed resume with AI, then guide factual resume revisions and targeted interview preparation.
---

# Career Resume Coach

Use AI reasoning to compare one saved job with one selected confirmed resume. Do not
use scripted matching, scores, keyword counts, or match snapshots.

## Required Workflow

1. Accept exactly one `job_id` and one `resume_id`.
2. Call `get_job(job_id)`.
3. Call `get_confirmed_resume(resume_id)`.
4. Analyze in this order: 项目经历, 实习与工作经历, 基础能力与技能, 教育经历.
5. Treat 教育经历 only as an explicit JD gate for degree, major, or graduation time.
6. First respond with exactly these sections:
   - 项目与实习证据
   - 基础能力覆盖
   - JD 缺失项
   - 需要用户补充的真实事实
7. A missing item means only that the resume does not show it. Ask the user; never
   infer that the user lacks or possesses it.
8. After the user explicitly states or confirms missing facts, provide section-level
   changes labeled 保留, 删除, 补充, 重写, or 加粗. Include the source fact, linked JD
   requirement, reason, and copyable wording.
9. In the same response, organize interview preparation by relevant project or
   internship: 核心问题, 可能追问, 面试官验证的能力点, and 当前简历尚未支撑该回答的事实.

## Error Handling

- On `JOB_NOT_FOUND`, stop and ask the user to reopen a visible saved job.
- On `RESUME_NOT_FOUND`, stop and ask the user to select an available confirmed resume.
- On any tool failure, explain the failure in Chinese. Never fall back to chat memory,
  unconfirmed text, or scripted matching.

## Hard Prohibitions

- Never call matching, application-packet, tailored-draft, export, file-write, or shell tools.
- Never request or expose sensitive contact information.
- Never invent skills, metrics, dates, responsibilities, seniority, or outcomes.
- Never write confirmed conversational additions back to Career Vault.
- Never generate a file or claim that the resume itself was edited.
- Never produce a generic interview question bank unrelated to the selected JD and resume.
```

Create the new directory without changing the old Skill. Keeping both during this
intermediate commit ensures the currently shipped frontend remains functional.

- [ ] **Step 4: Run the Skill test and verify GREEN**

Run:

```bash
python -m pytest tests/test_skills.py::test_workspace_career_skills_are_discoverable -q
```

Expected: PASS, with both Skills discoverable during the compatibility window.

- [ ] **Step 5: Commit the new Skill**

```bash
git add .coworker/skills/career-resume-coach/SKILL.md \
  tests/test_skills.py
git commit -m "feat(career): add AI resume coaching skill"
```

### Task 3: Define The Opaque AI Coaching Message

**Files:**
- Create: `surfaces/gui/src/careerResumeCoach.ts`
- Create: `surfaces/gui/src/careerResumeCoach.test.ts`

- [ ] **Step 1: Write the failing message contract test**

Create:

```typescript
import { describe, expect, it } from "vitest";

import { careerResumeCoachMessage } from "./careerResumeCoach";

describe("careerResumeCoachMessage", () => {
  it("uses only opaque job and resume ids for AI-led diagnosis", () => {
    const message = careerResumeCoachMessage({
      jobId: "job-1",
      resumeId: "resume-1",
    });

    expect(message).toEqual({
      prompt: [
        "请使用 career-resume-coach Skill 分析目标岗位与已确认简历。",
        "job_id=job-1",
        "resume_id=resume-1",
        "先输出诊断并追问缺失事实；用户确认后再给出逐段改写与面试准备。",
        "全部分析由 AI 完成，不要调用岗位匹配、申请材料包或文件导出工具。",
      ].join("\n"),
      display: "开始 AI 简历诊断",
      skill: "career-resume-coach",
    });
    expect(message.prompt).not.toMatch(
      /snapshot|private_path|upload_token|include_sensitive=true|@|138\d{8}/,
    );
  });
});
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerResumeCoach.test.ts
```

Expected: FAIL because `careerResumeCoach.ts` does not exist.

- [ ] **Step 3: Implement the minimal message builder**

Create:

```typescript
export interface ResumeCoachLaunchPayload {
  jobId: string;
  resumeId: string;
}

export interface ResumeCoachTurn {
  prompt: string;
  display: string;
  skill: "career-resume-coach";
}

export function careerResumeCoachMessage(
  payload: ResumeCoachLaunchPayload,
): ResumeCoachTurn {
  return {
    prompt: [
      "请使用 career-resume-coach Skill 分析目标岗位与已确认简历。",
      `job_id=${payload.jobId}`,
      `resume_id=${payload.resumeId}`,
      "先输出诊断并追问缺失事实；用户确认后再给出逐段改写与面试准备。",
      "全部分析由 AI 完成，不要调用岗位匹配、申请材料包或文件导出工具。",
    ].join("\n"),
    display: "开始 AI 简历诊断",
    skill: "career-resume-coach",
  };
}
```

Keep the old packet/tailored prompt files in this intermediate commit because the
currently shipped frontend still imports them. They are removed atomically in Task 5.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerResumeCoach.test.ts
npx tsc
```

Expected: PASS and TypeScript exits zero.

- [ ] **Step 5: Commit the message contract**

```bash
git add surfaces/gui/src/careerResumeCoach.ts \
  surfaces/gui/src/careerResumeCoach.test.ts
git commit -m "feat(gui): define AI resume coaching turn"
```

### Task 4: Build The Single-Resume Launcher In Isolation

**Files:**
- Create: `surfaces/gui/src/components/CareerResumeCoachLauncher.test.tsx`
- Create: `surfaces/gui/src/components/CareerResumeCoachLauncher.tsx`

- [ ] **Step 1: Write launcher tests for the new behavior**

Create the test file with the standard Vitest/Testing Library imports, mock only
`getCareerResumes`, and define a minimal `CareerJobDetail` plus two confirmed resume
summaries. Add these behavior tests:

```typescript
it("selects one confirmed resume and starts AI coaching", async () => {
  arrange();
  const onStartAnalysis = vi.fn();
  render(
    <CareerResumeCoachLauncher
      job={job}
      onStartAnalysis={onStartAnalysis}
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: "AI 分析与改简历" }),
  );
  fireEvent.click(await screen.findByLabelText("算法简历"));
  fireEvent.click(
    screen.getByRole("button", { name: "进入 Career Agent" }),
  );

  expect(onStartAnalysis).toHaveBeenCalledWith({
    jobId: "job-1",
    resumeId: "resume-1",
  });
  expect(screen.queryByText("岗位与简历证据匹配")).toBeNull();
  expect(screen.queryByText("生成申请准备包")).toBeNull();
  expect(screen.queryByText("生成定制简历建议")).toBeNull();
});

it("keeps exactly one resume selected", async () => {
  arrange();
  render(
    <CareerResumeCoachLauncher
      job={job}
      onStartAnalysis={vi.fn()}
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: "AI 分析与改简历" }),
  );
  fireEvent.click(await screen.findByLabelText("算法简历"));
  fireEvent.click(screen.getByLabelText("通用简历"));

  expect(
    (screen.getByLabelText("算法简历") as HTMLInputElement).checked,
  ).toBe(false);
  expect(
    (screen.getByLabelText("通用简历") as HTMLInputElement).checked,
  ).toBe(true);
});
```

Retain focused tests for an empty resume list and `getCareerResumes()` failure. Assert
that no matching API is mocked or called.

- [ ] **Step 2: Run the component tests and verify RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/components/CareerResumeCoachLauncher.test.tsx
```

Expected: FAIL because `CareerResumeCoachLauncher` does not exist.

- [ ] **Step 3: Implement the minimal launcher**

Create the component with one required callback:

```typescript
import { useState } from "react";

import {
  getCareerResumes,
  type CareerJobDetail,
  type CareerResumeSummary,
} from "../api";
import type { ResumeCoachLaunchPayload } from "../careerResumeCoach";

export function CareerResumeCoachLauncher({
  job,
  onStartAnalysis,
}: {
  job: CareerJobDetail;
  onStartAnalysis: (payload: ResumeCoachLaunchPayload) => void;
}) {
  const [open, setOpen] = useState(false);
  const [resumes, setResumes] = useState<CareerResumeSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const openLauncher = async () => {
    setOpen(true);
    setLoading(true);
    setError("");
    try {
      const response = await getCareerResumes();
      if (!response.ok) {
        setError(response.error?.message || "无法读取简历库。");
        return;
      }
      const confirmed = (response.resumes || []).filter(
        (resume) => resume.confirmed_sections.length > 0,
      );
      setResumes(confirmed);
      setSelectedId(confirmed.length === 1 ? confirmed[0].id : "");
    } catch {
      setError("无法连接简历服务。");
    } finally {
      setLoading(false);
    }
  };

  const submit = () => {
    if (!selectedId) return;
    onStartAnalysis({
      jobId: job.id,
      resumeId: selectedId,
    });
    setOpen(false);
  };

  return (
    <>
      <button
        className="shrink-0 rounded-lg border border-accent px-3.5 py-2 text-[12.5px] text-accent"
        onClick={() => void openLauncher()}
      >
        AI 分析与改简历
      </button>

      {open && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="career-resume-coach-title"
            className="max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-lg border border-line bg-panel p-4 shadow-xl sm:p-5"
          >
            <header className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2
                  id="career-resume-coach-title"
                  className="text-base font-semibold"
                >
                  选择用于分析的简历
                </h2>
                <p className="mt-1 break-words text-[12px] text-muted">
                  {job.company.name} · {job.title || "未命名岗位"}
                </p>
              </div>
              <button
                className="shrink-0 text-sm text-muted"
                onClick={() => setOpen(false)}
              >
                关闭
              </button>
            </header>

            {error && (
              <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            {loading ? (
              <div className="py-10 text-center text-sm text-muted">
                正在读取简历…
              </div>
            ) : resumes.length === 0 ? (
              <p className="mt-4 rounded-lg bg-paper p-4 text-sm text-muted">
                暂无已确认简历，请前往我的求职档案导入并确认简历。
              </p>
            ) : (
              <div className="mt-4 space-y-2">
                {resumes.map((resume) => (
                  <label
                    key={resume.id}
                    className="flex min-w-0 items-start gap-3 rounded-lg border border-line bg-paper p-3"
                  >
                    <input
                      type="radio"
                      name="career-resume-coach"
                      aria-label={resume.display_name}
                      checked={selectedId === resume.id}
                      onChange={() => setSelectedId(resume.id)}
                    />
                    <span className="min-w-0 break-words text-sm">
                      {resume.display_name}
                    </span>
                  </label>
                ))}
              </div>
            )}

            <div className="mt-4 flex justify-end">
              <button
                className="rounded-lg bg-accent px-4 py-2 text-sm text-white disabled:opacity-40"
                disabled={!selectedId || loading}
                onClick={submit}
              >
                进入 Career Agent
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
```

Do not import `createCareerJobMatches`, `getCareerJobMatches`, packet/tailored payload
types, or `CareerTailoredResumePanel`. Leave `CareerJobMatchPanel` unchanged until
Task 5 so this commit adds tested code without changing the shipped flow.

- [ ] **Step 4: Run the component tests and verify GREEN**

Run:

```bash
cd surfaces/gui
npm test -- --run src/components/CareerResumeCoachLauncher.test.tsx
npx tsc
```

Expected: PASS. Search the new component:

```bash
rg -n "岗位与简历证据匹配|生成申请准备包|生成定制简历建议|CareerTailoredResumePanel" \
  src/components/CareerResumeCoachLauncher.tsx
```

Expected: no matches.

- [ ] **Step 5: Commit the launcher**

```bash
git add surfaces/gui/src/components/CareerResumeCoachLauncher.tsx \
  surfaces/gui/src/components/CareerResumeCoachLauncher.test.tsx
git commit -m "feat(gui): add AI resume coaching launcher"
```

### Task 5: Atomically Cut Over To One Automatic Career Coaching Turn

**Files:**
- Delete: `.coworker/skills/career-tailored-resume/SKILL.md`
- Modify: `tests/test_skills.py`
- Delete: `surfaces/gui/src/careerApplicationPacket.ts`
- Delete: `surfaces/gui/src/careerApplicationPacket.test.ts`
- Delete: `surfaces/gui/src/careerTailoredResume.ts`
- Delete: `surfaces/gui/src/careerTailoredResume.test.ts`
- Delete: `surfaces/gui/src/components/CareerJobMatchPanel.tsx`
- Delete: `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`
- Delete: `surfaces/gui/src/components/CareerTailoredResumePanel.tsx`
- Delete: `surfaces/gui/src/components/CareerTailoredResumePanel.test.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.test.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/interfaceTheme.test.ts`
- Modify: `surfaces/gui/src/App.interview.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: Add failing automatic-send tests**

Extend the mocked `CareerJobsView` parameter type and add a second button:

```tsx
CareerJobsView: ({
  onStartInterview,
  onStartResumeCoach,
}: {
  onStartInterview: (payload: Record<string, unknown>) => void;
  onStartResumeCoach: (payload: {
    jobId: string;
    resumeId: string;
  }) => void;
}) => (
  <>
<button
  onClick={() =>
    onStartResumeCoach({
      jobId: "job-1",
      resumeId: "resume-1",
    })
  }
>
  从岗位启动简历诊断
</button>
    <button
      onClick={() =>
        onStartInterview({
          jobId: "job-1",
          resumeId: "resume-1",
          snapshotId: "snapshot-1",
          position: "大模型算法工程师",
          durationMinutes: 15,
          difficulty: "standard",
        })
      }
    >
      从岗位启动面试
    </button>
  </>
),
```

Add a successful launch test:

```typescript
it("automatically sends one AI resume coaching turn", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "打开岗位雷达" }));
  fireEvent.click(
    await screen.findByRole("button", {
      name: "从岗位启动简历诊断",
    }),
  );

  await waitFor(() =>
    expect(mocked.userMessage).toHaveBeenCalledWith(
      expect.stringContaining("job_id=job-1"),
      undefined,
      "career-resume-coach",
      "开始 AI 简历诊断",
    ),
  );
  expect(mocked.userMessage).toHaveBeenCalledTimes(1);
  const prompt = String(mocked.userMessage.mock.calls[0][0]);
  expect(prompt).toContain("resume_id=resume-1");
  expect(prompt).not.toContain("snapshot");
});
```

Add a missing-workspace test:

```typescript
it("does not create or send coaching without a trusted workspace", async () => {
  mocked.sessionWorkspace = "";
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "打开岗位雷达" }));
  fireEvent.click(
    await screen.findByRole("button", {
      name: "从岗位启动简历诊断",
    }),
  );

  expect(
    await screen.findByText(
      "AI 简历诊断需要可信工作区，请先打开 OpenCareer 项目工作区。",
    ),
  ).toBeTruthy();
  expect(mocked.userMessage).not.toHaveBeenCalled();
});
```

In `CareerJobsView.test.tsx`, replace the old entry assertion with:

```typescript
expect(
  screen.getByRole("button", { name: "AI 分析与改简历" }),
).toBeTruthy();
expect(screen.queryByRole("button", { name: "匹配简历" })).toBeNull();
```

- [ ] **Step 2: Run the App test and verify RED**

Run:

```bash
cd surfaces/gui
npm test -- --run \
  src/App.interview.test.tsx \
  src/components/CareerJobsView.test.tsx
```

Expected: FAIL because `CareerJobsView` has no `onStartResumeCoach` callback and App
has no queued coaching turn.

- [ ] **Step 3: Wire the launcher through `CareerJobsView`**

Replace the `CareerJobMatchPanel` import with `CareerResumeCoachLauncher`. Replace the
two old generation props with:

```typescript
onStartResumeCoach?: (payload: ResumeCoachLaunchPayload) => void;
```

Pass it to `CareerResumeCoachLauncher` as `onStartAnalysis`. Delete
`CareerJobMatchPanel.tsx` and its old evidence-matrix test after the import is changed.
Do not alter `startInterviewFromSetup`; its compatibility matching remains unchanged.

- [ ] **Step 4: Implement an independent queued coaching turn**

Import `careerResumeCoachMessage`, `ResumeCoachLaunchPayload`, and `ResumeCoachTurn`.
Remove the old application-packet and tailored-resume imports and callbacks.

Add independent state:

```typescript
const [resumeCoachLaunchError, setResumeCoachLaunchError] = useState("");
const queuedResumeCoachTurn = useRef<ResumeCoachTurn | null>(null);
```

Add an effect parallel to, but independent from, the interview queue:

```typescript
useEffect(() => {
  if (
    !connected ||
    surface !== "session" ||
    !queuedResumeCoachTurn.current
  ) {
    return;
  }
  const queued = queuedResumeCoachTurn.current;
  queuedResumeCoachTurn.current = null;
  send(
    queued.prompt,
    undefined,
    queued.skill,
    queued.display,
  );
}, [connected, surface, sessionId]);
```

Add the launch function:

```typescript
const startResumeCoach = (payload: ResumeCoachLaunchPayload) => {
  setResumeCoachLaunchError("");
  if (!workspace) {
    setResumeCoachLaunchError(
      "AI 简历诊断需要可信工作区，请先打开 OpenCareer 项目工作区。",
    );
    return;
  }
  queuedResumeCoachTurn.current = careerResumeCoachMessage(payload);
  setItems([]);
  setUsage(emptyUsage());
  setStreaming("");
  setTodo([]);
  setRunning(false);
  setConnected(false);
  setAgent("career");
  setBranch(null);
  setShowGate(false);
  setSessionId(newId());
  setSurface("session");
};
```

Pass `onStartResumeCoach={startResumeCoach}` to `CareerJobsView`. Render the launch
error with `role="alert"` while preserving the existing interview error. Clear the
queued ref after send so reconnects cannot send a duplicate turn.

- [ ] **Step 5: Remove obsolete frontend launch helpers and the old Skill**

Delete the four old frontend prompt files, both old match-panel files, both now
unreferenced `CareerTailoredResumePanel` files, and
`.coworker/skills/career-tailored-resume/SKILL.md`. In `tests/test_skills.py`, remove
`career-tailored-resume` from the exact catalog and delete its old draft/export
assertion block. Keep all application-packet backend code and its Skill unchanged in
this phase.

Update `interfaceTheme.test.ts` to import `CareerResumeCoachLauncher.tsx?raw` instead
of the two deleted Career panel files, and retain the existing retired-palette
assertion for the new launcher.

The final exact Skill catalog must be:

```python
    assert loader.names() == [
        "career-application-packet",
        "career-interview-evaluation",
        "career-jd-analysis",
        "career-job-search",
        "career-resume-coach",
        "career-resume-import",
        "mock-interview",
    ]
```

Confirm there are no remaining frontend imports:

```bash
rg -n "careerApplicationPacket|careerTailoredResume|onGeneratePacket|onGenerateTailoredResume" \
  surfaces/gui/src
```

Expected: no matches.

- [ ] **Step 6: Run App, component, Skill, and prompt tests**

Run:

```bash
cd surfaces/gui
npm test -- --run \
  src/App.interview.test.tsx \
  src/careerResumeCoach.test.ts \
  src/components/CareerResumeCoachLauncher.test.tsx \
  src/components/CareerJobsView.test.tsx
npx tsc
cd -
python -m pytest tests/test_skills.py::test_workspace_career_skills_are_discoverable -q
```

Expected: all tests pass and TypeScript exits zero.

- [ ] **Step 7: Prove the new frontend path has no scripted matching call**

Run:

```bash
rg -n "createCareerJobMatches|getCareerJobMatches|snapshotId|snapshot_id" \
  surfaces/gui/src/careerResumeCoach.ts \
  surfaces/gui/src/components/CareerResumeCoachLauncher.tsx
```

Expected: no matches in the two new-flow files. `CareerJobsView.tsx` may still contain
matching calls only inside the existing mock-interview setup.

- [ ] **Step 8: Commit the atomic cutover**

```bash
git add .coworker/skills/career-tailored-resume/SKILL.md \
  tests/test_skills.py \
  surfaces/gui/src/careerApplicationPacket.ts \
  surfaces/gui/src/careerApplicationPacket.test.ts \
  surfaces/gui/src/careerTailoredResume.ts \
  surfaces/gui/src/careerTailoredResume.test.ts \
  surfaces/gui/src/components/CareerJobMatchPanel.tsx \
  surfaces/gui/src/components/CareerJobMatchPanel.test.tsx \
  surfaces/gui/src/components/CareerTailoredResumePanel.tsx \
  surfaces/gui/src/components/CareerTailoredResumePanel.test.tsx \
  surfaces/gui/src/components/CareerJobsView.tsx \
  surfaces/gui/src/components/CareerJobsView.test.tsx \
  surfaces/gui/src/interfaceTheme.test.ts \
  surfaces/gui/src/App.tsx \
  surfaces/gui/src/App.interview.test.tsx
git commit -m "feat(gui): auto-start AI resume coaching"
```

### Task 6: Run Regression Gates And Record Evidence

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Run focused backend and Skill tests**

```bash
python -m pytest \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_skills.py \
  tests/test_postgres_resume_service.py \
  -q
```

Expected: PASS. PostgreSQL tests may skip only when their documented test database is
not configured; record that explicitly rather than claiming a pass.

- [ ] **Step 2: Run focused and full GUI tests**

```bash
cd surfaces/gui
npm test -- --run \
  src/careerResumeCoach.test.ts \
  src/components/CareerResumeCoachLauncher.test.tsx \
  src/components/CareerJobsView.test.tsx \
  src/App.interview.test.tsx
npm test -- --run
npx tsc
cd -
```

Expected: all focused tests, the full Vitest suite, and TypeScript pass.

- [ ] **Step 3: Build the alpha frontend and run repository smoke gates**

```bash
bash deploy/build-frontend.sh
python -m coworker.server.run --help
python -m extensions.career_mcp.crawl_cli --list
```

Expected: alpha build succeeds, both Python commands exit zero, and no desktop-only
dependency is pulled into the cloud build.

- [ ] **Step 4: Validate both Compose files without exposing secrets**

Use the existing local `deploy/.env` if present. If it is absent, provide temporary
non-secret values only for configuration rendering; never print or commit the real
file.

```bash
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
```

Expected: both commands exit zero. Origin and token rules remain byte-for-byte
unchanged by this feature.

- [ ] **Step 5: Verify desktop and 375×812 layouts with Playwright**

Start the local alpha frontend using a free port:

```bash
cd surfaces/gui
npm run alpha -- --host 127.0.0.1 --port 5199
```

Using the `webapp-testing` Skill, inspect desktop and `375×812` viewports. Verify:

- “AI 分析与改简历” is visible in the job detail.
- The modal fits inside the viewport.
- Resume names wrap without covering radio controls or the submit button.
- There is no horizontal scroll.
- Submitting enters the standard Career Conversation and shows one user turn,
  “开始 AI 简历诊断”.
- Browser console has no new errors.

Record screenshots outside tracked source directories unless the repository already
has an established evidence path. Stop the dev server before finishing.

- [ ] **Step 6: Append exact evidence to project logs**

Append a dated section to both logs containing:

- files and behavior changed;
- exact test/build commands and pass counts;
- confirmation that the new path does not call scripted matching;
- desktop and `375×812` inspection result;
- any skipped PostgreSQL or browser Gate;
- statement that alpha was not deployed.

Do not rewrite historical entries.

- [ ] **Step 7: Run final hygiene checks**

```bash
git diff --check
git status --short
git diff -- \
  extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  .coworker/skills/career-resume-coach/SKILL.md \
  tests/test_skills.py \
  surfaces/gui/src/careerResumeCoach.ts \
  surfaces/gui/src/careerResumeCoach.test.ts \
  surfaces/gui/src/components/CareerResumeCoachLauncher.tsx \
  surfaces/gui/src/components/CareerResumeCoachLauncher.test.tsx \
  surfaces/gui/src/components/CareerJobsView.tsx \
  surfaces/gui/src/components/CareerJobsView.test.tsx \
  surfaces/gui/src/App.tsx \
  surfaces/gui/src/App.interview.test.tsx \
  docs/11_DEVELOPMENT_LOG.md \
  docs/12_TONIGHT_PROGRESS.md
```

Expected: no whitespace errors and every changed line maps to this specification.
Unrelated pre-existing worktree changes remain untouched.

- [ ] **Step 8: Commit verification evidence**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: record AI resume coaching acceptance"
```

## Completion Criteria

The implementation is complete only when:

- the visible evidence matrix and application/tailored-resume launch entries are gone;
- the selected resume starts exactly one Career Agent diagnosis turn;
- the new path contains no match API, match snapshot, keyword score, or scripted
  analysis dependency;
- the Agent can read exactly one tenant-visible, confirmed, masked resume;
- the coaching Skill enforces the approved diagnosis, rewriting, and interview
  preparation structure;
- mock-interview matching remains operational;
- focused tests, full GUI tests, TypeScript, alpha build, Python smoke checks, Compose
  validation, and responsive inspection have recorded results;
- no deployment has occurred.
