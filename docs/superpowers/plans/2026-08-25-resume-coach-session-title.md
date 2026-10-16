# AI Resume Coach Session Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every newly launched AI resume analysis conversation the deterministic title `公司 · 岗位名称` without adding company or position text to the Agent prompt.

**Architecture:** Extend the frontend-only launch payload with display metadata already loaded on the job page. Keep a pending title in `App`, persist it through the existing session rename API on the first `turn_start`, and let explicit rename semantics prevent the global model auto-title from replacing it.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, existing OpenWorker session REST API.

---

### Task 1: Carry Display-Only Job Metadata

**Files:**
- Modify: `surfaces/gui/src/careerResumeCoach.ts`
- Modify: `surfaces/gui/src/components/CareerResumeCoachLauncher.tsx`
- Test: `surfaces/gui/src/careerResumeCoach.test.ts`
- Test: `surfaces/gui/src/components/CareerResumeCoachLauncher.test.tsx`

- [x] **Step 1: Write failing payload tests**

Update fixtures to pass:

```ts
{
  jobId: "job-1",
  resumeId: "resume-1",
  companyName: "DeepSeek",
  position: "大模型算法工程师",
}
```

Assert the launcher emits all four fields, while `careerResumeCoachMessage()` still produces
a prompt containing only `job_id` and `resume_id`, with no company or position text.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerResumeCoach.test.ts src/components/CareerResumeCoachLauncher.test.tsx
```

Expected: FAIL because the payload does not yet carry `companyName` or `position`.

- [x] **Step 3: Implement the minimal payload change**

Extend `ResumeCoachLaunchPayload`:

```ts
export interface ResumeCoachLaunchPayload {
  jobId: string;
  resumeId: string;
  companyName: string;
  position: string;
}
```

Have the launcher pass `job.company.name || "未知公司"` and
`job.title || "未命名岗位"`. Keep `careerResumeCoachMessage()` unchanged so only the two IDs
enter the model prompt.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: all tests pass.

### Task 2: Persist the Deterministic Conversation Title

**Files:**
- Modify: `surfaces/gui/src/App.tsx`
- Test: `surfaces/gui/src/App.interview.test.tsx`

- [x] **Step 1: Write a failing App integration test**

Make the mocked job view launch with company and position. After the resume-coach turn emits
`turn_start`, assert:

```ts
expect(mocked.renameSession).toHaveBeenCalledWith(
  "coach-target",
  "DeepSeek · 大模型算法工程师",
);
```

Also retain the existing assertion that `userMessage` receives the Skill prompt containing
only `job_id` and `resume_id`.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/App.interview.test.tsx
```

Expected: FAIL because resume coaching does not schedule a deterministic title.

- [x] **Step 3: Implement title persistence**

Rename the existing title ref to a shared `pendingConversationTitle`. In
`startResumeCoach`, set:

```ts
pendingConversationTitle.current =
  `${payload.companyName || "未知公司"} · ${payload.position || "未命名岗位"}`;
```

Move the existing rename call and session refresh to `turn_start`. Continue clearing this ref
when launching a different workflow so titles cannot leak across conversations.

- [x] **Step 4: Run focused and full frontend verification**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerResumeCoach.test.ts \
  src/components/CareerResumeCoachLauncher.test.tsx \
  src/App.interview.test.tsx
npm test -- --run
npx tsc
cd ../..
bash deploy/build-frontend.sh
git diff --check
```

Expected: focused and full tests pass; TypeScript and Alpha build succeed.

- [x] **Step 5: Commit**

```bash
git add surfaces/gui/src/careerResumeCoach.ts \
  surfaces/gui/src/careerResumeCoach.test.ts \
  surfaces/gui/src/components/CareerResumeCoachLauncher.tsx \
  surfaces/gui/src/components/CareerResumeCoachLauncher.test.tsx \
  surfaces/gui/src/App.tsx \
  surfaces/gui/src/App.interview.test.tsx
git commit -m "fix(career): title resume coaching by job"
```

### Task 3: Deploy and Repair One Historical Title

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [x] **Step 1: Publish the Alpha frontend**

Copy the new hashed assets into `/opt/opencareer/deploy/web/assets`, then atomically replace
`/opt/opencareer/deploy/web/index.html`. Do not restart or rebuild the backend.

- [x] **Step 2: Verify a new conversation**

Launch AI resume analysis from a job and assert in the browser that the top bar and recent
conversation list show `公司 · 岗位名称`. Verify the persisted user message still displays
`开始 AI 简历诊断` and its model-facing content contains no added company or position text.

- [x] **Step 3: Repair only the known historical conversation**

List sessions and select the single title beginning with:

```text
Use the preloaded skill "career-resume-coach"
```

Read its persisted `job_id`, fetch the visible job, construct `公司 · 岗位名称`, and call the
existing session PATCH endpoint for that session ID only. Abort if the candidate count is not
exactly one.

- [x] **Step 4: Verify production invariants**

Confirm the new bundle loads, the repaired session has the expected title, all other session
IDs retain their previous titles, health reports PostgreSQL and Redis ready, and backend/Caddy
restart counts remain zero.

- [x] **Step 5: Record and commit deployment evidence**

Append exact test, bundle, browser, session ID, and runtime evidence to
`docs/11_DEVELOPMENT_LOG.md` and `docs/12_TONIGHT_PROGRESS.md`, then commit and push the
documentation.
