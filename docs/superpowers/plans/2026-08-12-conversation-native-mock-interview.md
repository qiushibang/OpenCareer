# Conversation-Native Mock Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run every mock interview inside the standard Career Agent Conversation so it appears in recent sessions, survives reload, supports text and voice, and continues into review without switching to a separate page.

**Architecture:** Keep InterviewSession as the authoritative interview state and OpenWorker Conversation as the authoritative message/runtime state. Resolve InterviewSession by `conversation_id`, render a compact interview bar above the standard Transcript, and send internal Skill prompts with a separate user-facing display string. Extract voice behavior from `InterviewView`, then delete the independent interview surface after parity tests pass.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, React 18, TypeScript, Vitest, Testing Library, existing OpenWorker WebSocket Session and Career Interview services.

---

## Worktree And Scope Rules

- Work in the existing shared worktree; do not reset unrelated changes.
- Do not modify Agent Loop, Provider Router, permissions, MCP tool contracts, or Conversation persistence semantics.
- Do not add a new database or duplicate Interview Turn content into Conversation metadata.
- Run RED before every production edit.
- Keep `InterviewView` until the standard Conversation path reaches feature parity; delete it only in Task 8.

## File Map

- Modify `extensions/career_mcp/database/interview_repository.py`
  - Lookup InterviewSession by Conversation ID.
- Modify `extensions/career_mcp/services/interviews.py`
  - Expose lookup and enforce one Interview per Conversation.
- Modify `extensions/career_mcp/tests/test_interview_repository.py`
- Modify `extensions/career_mcp/tests/test_interview_service.py`
- Modify `coworker/server/app.py`
  - Add HTTP lookup and safe Skill display sidecar handling.
- Modify `tests/test_career_interview_api.py`
- Modify `tests/test_server.py`
- Modify `surfaces/gui/src/api.ts`
  - Query interview by Conversation and send optional display text.
- Modify `surfaces/gui/src/careerInterview.ts`
  - Pair internal prompts with user-visible text.
- Modify `surfaces/gui/src/careerInterview.test.ts`
- Create `surfaces/gui/src/useConversationInterview.ts`
- Create `surfaces/gui/src/useConversationInterview.test.tsx`
- Create `surfaces/gui/src/useInterviewVoice.ts`
- Create `surfaces/gui/src/useInterviewVoice.test.tsx`
- Create `surfaces/gui/src/components/ConversationInterviewBar.tsx`
- Create `surfaces/gui/src/components/ConversationInterviewBar.test.tsx`
- Modify `surfaces/gui/src/components/Composer.tsx`
- Modify `surfaces/gui/src/App.tsx`
- Modify `surfaces/gui/src/App.interview.test.tsx`
- Delete `surfaces/gui/src/components/InterviewView.tsx`
- Delete `surfaces/gui/src/components/InterviewView.test.tsx`
- Modify `docs/11_DEVELOPMENT_LOG.md`
- Modify `docs/12_TONIGHT_PROGRESS.md`

### Task 1: Conversation-To-Interview Domain Lookup

**Files:**
- Modify: `extensions/career_mcp/database/interview_repository.py`
- Modify: `extensions/career_mcp/services/interviews.py`
- Test: `extensions/career_mcp/tests/test_interview_repository.py`
- Test: `extensions/career_mcp/tests/test_interview_service.py`

- [ ] **Step 1: Add Repository RED**

Add:

```python
def test_repository_gets_session_by_conversation_id(tmp_path):
    connection, session, _ = _records(tmp_path)
    repository = InterviewRepository(connection)
    first = repository.create_session(session)

    found = repository.get_session_by_conversation_id(
        "career-conversation-1"
    )

    assert found is not None
    assert found["id"] == first["id"]
    assert repository.get_session_by_conversation_id("missing") is None
    connection.close()
```

- [ ] **Step 2: Run Repository RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_repository.py::test_repository_gets_session_by_conversation_id \
  -q
```

Expected: FAIL because `get_session_by_conversation_id` does not exist.

- [ ] **Step 3: Implement Repository lookup**

Add:

```python
def get_session_by_conversation_id(
    self,
    conversation_id: str,
) -> dict | None:
    row = self.connection.execute(
        """
        SELECT *
        FROM interview_sessions
        WHERE conversation_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()
    return self._session(row) if row else None
```

- [ ] **Step 4: Add Service RED**

Add tests:

```python
def test_service_gets_interview_by_conversation(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )
    created = _create(service, job_id, resume_id, snapshot_id)

    found = service.get_by_conversation("career-session-1")

    assert found is not None
    assert found["id"] == created["id"]
    assert service.get_by_conversation("career-session-missing") is None


def test_service_rejects_second_interview_for_conversation(tmp_path):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )
    created = _create(service, job_id, resume_id, snapshot_id)

    with pytest.raises(InterviewServiceError) as error:
        service.create(
            created["job_id"],
            created["resume_id"],
            created["snapshot_id"],
            conversation_id="career-session-1",
            difficulty="standard",
            duration_minutes=15,
        )

    assert error.value.code == "INTERVIEW_STATE_CONFLICT"
```

Add bind coverage:

```python
def test_service_rejects_binding_second_interview_to_conversation(
    tmp_path,
):
    service, _, _, _, job_id, resume_id, snapshot_id = _service(
        tmp_path
    )
    _create(service, job_id, resume_id, snapshot_id)
    unbound = service.create(
        job_id,
        resume_id,
        snapshot_id,
        conversation_id=None,
        difficulty="standard",
        duration_minutes=15,
    )

    with pytest.raises(InterviewServiceError) as error:
        service.bind_conversation(
            unbound["id"],
            expected_version=unbound["version"],
            conversation_id="career-session-1",
        )

    assert error.value.code == "INTERVIEW_STATE_CONFLICT"
```

- [ ] **Step 5: Run Service RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_service.py \
  -k "conversation" -q
```

Expected: new lookup and duplicate tests fail.

- [ ] **Step 6: Implement Service lookup and uniqueness**

Add:

```python
def get_by_conversation(
    self,
    conversation_id: str,
) -> dict | None:
    conversation = self._identifier(conversation_id)
    connection = connect(self.config.database_path)
    try:
        repository = InterviewRepository(connection)
        session = repository.get_session_by_conversation_id(conversation)
        return (
            self._with_turns(repository, session)
            if session is not None
            else None
        )
    finally:
        connection.close()
```

Inside `create()`, after `BEGIN IMMEDIATE` and before `create_session(record)`:

```python
if (
    normalized_conversation
    and repository.get_session_by_conversation_id(
        normalized_conversation
    )
    is not None
):
    self._raise("INTERVIEW_STATE_CONFLICT")
```

Inside `bind_conversation()`, after loading the target session:

```python
bound = repository.get_session_by_conversation_id(conversation)
if bound is not None and bound["id"] != normalized_id:
    self._raise("INTERVIEW_STATE_CONFLICT")
```

- [ ] **Step 7: Run GREEN**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interview_service.py \
  -q
```

Expected: all pass.

### Task 2: HTTP And GUI Conversation Lookup

**Files:**
- Modify: `coworker/server/app.py`
- Modify: `tests/test_career_interview_api.py`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/careerInterview.test.ts`

- [ ] **Step 1: Add HTTP RED**

Add:

```python
def test_interview_http_gets_by_conversation(
    tmp_path,
    monkeypatch,
):
    client, job_id, resume_id, snapshot_id = (
        _client_with_interview_inputs(tmp_path, monkeypatch)
    )
    created = _create(
        client,
        job_id,
        resume_id,
        snapshot_id,
    ).json()["interview"]

    response = client.get(
        "/v1/career/interviews",
        params={"conversation_id": "career-session-1"},
    )
    missing = client.get(
        "/v1/career/interviews",
        params={"conversation_id": "career-session-missing"},
    )

    assert response.status_code == 200
    assert response.json()["interview"]["id"] == created["id"]
    assert missing.status_code == 200
    assert missing.json() == {"ok": True, "interview": None}
```

- [ ] **Step 2: Run HTTP RED**

Run:

```bash
.venv/bin/pytest \
  tests/test_career_interview_api.py::test_interview_http_gets_by_conversation \
  -q
```

Expected: FAIL because GET on the collection is not registered.

- [ ] **Step 3: Implement HTTP lookup**

Register before `@app.get("/v1/career/interviews/{session_id}")`:

```python
@app.get("/v1/career/interviews")
def career_interview_get_by_conversation(
    conversation_id: str,
):
    try:
        interview = career_interview_service().get_by_conversation(
            conversation_id
        )
        return {"ok": True, "interview": interview}
    except Exception as exc:
        return career_interview_error(exc)
```

- [ ] **Step 4: Add GUI API RED**

In `careerInterview.test.ts`, add:

```typescript
it("queries an interview by encoded conversation id", async () => {
  fetchMock.mockResolvedValueOnce({
    json: async () => ({ ok: true, interview: null }),
  });

  await getCareerInterviewByConversation("conversation/one");

  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining(
      "/v1/career/interviews?conversation_id=conversation%2Fone",
    ),
  );
});
```

- [ ] **Step 5: Implement GUI API lookup**

Add to `api.ts`:

```typescript
export interface CareerInterviewResult {
  ok: boolean;
  error?: { code: string; message: string };
  interview?: CareerInterviewSession | null;
}

export interface CareerInterviewTurn {
  id: string;
  turn_index: number;
  question_text: string;
  question_refs: string[];
  answer_text: string | null;
  evaluation: Record<string, unknown> | null;
  next_action: string | null;
  next_reason?: string | null;
  question_topic?: string | null;
  probe_target?: string | null;
  probe_dimension?: string | null;
  depth_level?: number | null;
}

export async function getCareerInterviewByConversation(
  conversationId: string,
): Promise<CareerInterviewResult> {
  const query = new URLSearchParams({
    conversation_id: conversationId,
  });
  const res = await fetch(`${careerInterviewUrl()}?${query}`);
  return res.json();
}
```

- [ ] **Step 6: Run GREEN**

Run:

```bash
.venv/bin/pytest tests/test_career_interview_api.py -q
cd surfaces/gui && npm test -- --run src/careerInterview.test.ts
```

Expected: both pass.

### Task 3: Safe User-Facing Display Sidecar

**Files:**
- Modify: `surfaces/gui/src/api.ts`
- Modify: `coworker/server/app.py`
- Modify: `tests/test_server.py`
- Modify: `surfaces/gui/src/careerInterview.ts`
- Modify: `surfaces/gui/src/careerInterview.test.ts`

- [ ] **Step 1: Add server RED**

Extend the existing WebSocket user-message test with:

```python
ws.send_json(
    {
        "type": "user_message",
        "text": (
            "提交模拟面试回答。"
            "interview_session_id=interview-1；turn_id=turn-1。"
            "\n\n候选人回答：\n这是我的原始回答"
        ),
        "display": "这是我的原始回答",
        "skill": "mock-interview",
        "model": "aiden:deepseek-v4-flash",
    }
)
```

Assert the persisted user message keeps internal `content` and has
`_display == "这是我的原始回答"`; also assert a message with `display` but no `skill` receives
`input_rejected`.

- [ ] **Step 2: Run server RED**

Run:

```bash
.venv/bin/pytest tests/test_server.py -k "display and user_message" -q
```

Expected: the custom display is ignored or rejected by current code.

- [ ] **Step 3: Implement Session payload support**

Change `Session.userMessage` in `api.ts`:

```typescript
userMessage(
  text: string,
  attachments?: unknown[],
  model?: string,
  skill?: string,
  display?: string,
) {
  this.send({
    type: "user_message",
    text,
    ...(model ? { model } : {}),
    ...(attachments?.length ? { attachments } : {}),
    ...(skill ? { skill } : {}),
    ...(display !== undefined ? { display } : {}),
  });
}
```

In the server `user_message` branch, read and validate the optional value immediately after
`skill = message.get("skill")` has passed the existing Skill-name validation:

```python
raw_display = message.get("display")
if raw_display is not None:
    if (
        skill is None
        or not isinstance(raw_display, str)
        or not raw_display.strip()
        or len(raw_display) > _MAX_MESSAGE_TEXT_CHARS
    ):
        await reject_input(
            "Invalid display text for skill message."
        )
        continue
    display = raw_display.strip()
```

When Skill framing sets its default, preserve the custom value:

```python
if display is None:
    display = f"/{skill}" + (f" {text}" if text else "")
```

- [ ] **Step 4: Add prompt/display RED**

Add to `careerInterview.test.ts`:

```typescript
it("separates an interview answer from its visible text", () => {
  expect(
    interviewAnswerMessage("interview-1", "turn-1", "  我的回答  "),
  ).toEqual({
    prompt: expect.stringContaining(
      "interview_session_id=interview-1",
    ),
    display: "我的回答",
  });
});
```

- [ ] **Step 5: Implement message helpers**

Change the helpers to return:

```typescript
export type InterviewAgentMessage = {
  prompt: string;
  display: string;
};

export const interviewStartMessage = (
  sessionId: string,
): InterviewAgentMessage => ({
  prompt: interviewStartPrompt(sessionId),
  display: "开始模拟面试",
});

export const interviewAnswerMessage = (
  sessionId: string,
  turnId: string,
  answer: string,
): InterviewAgentMessage => {
  const normalized = normalizeInterviewAnswer(answer);
  return {
    prompt:
      `提交模拟面试回答。interview_session_id=${sessionId}；` +
      `turn_id=${turnId}。\n\n候选人回答：\n${normalized}`,
    display: normalized,
  };
};
```

Keep `interviewStartPrompt` and `interviewAnswerPrompt` as compatibility wrappers until Task 7.

- [ ] **Step 6: Run GREEN**

Run:

```bash
.venv/bin/pytest tests/test_server.py -k "display or user_message" -q
cd surfaces/gui && npm test -- --run src/careerInterview.test.ts
```

Expected: all selected tests pass.

### Task 4: Conversation Interview State Hook

**Files:**
- Create: `surfaces/gui/src/useConversationInterview.ts`
- Create: `surfaces/gui/src/useConversationInterview.test.tsx`

- [ ] **Step 1: Write Hook RED**

Create a harness that changes `conversationId` and assert:

```typescript
it("restores and polls the interview for the active conversation", async () => {
  api.getCareerInterviewByConversation
    .mockResolvedValueOnce({
      ok: true,
      interview: session({ phase: "evaluating" }),
    })
    .mockResolvedValueOnce({
      ok: true,
      interview: session({ phase: "waiting_for_answer" }),
    });

  render(<Harness conversationId="career-conversation-1" />);

  expect(await screen.findByText("interview-1")).toBeTruthy();
  await act(async () => vi.advanceTimersByTime(1_000));
  expect(api.getCareerInterviewByConversation).toHaveBeenCalledTimes(2);
});
```

Also assert a null interview renders no active state, and query failure preserves the last loaded
interview while exposing a retryable Chinese error.

- [ ] **Step 2: Run Hook RED**

Run:

```bash
cd surfaces/gui && npm test -- --run src/useConversationInterview.test.tsx
```

Expected: FAIL because the hook does not exist.

- [ ] **Step 3: Implement the Hook**

Create:

```typescript
import { useCallback, useEffect, useState } from "react";
import {
  getCareerInterviewByConversation,
  type CareerInterviewSession,
} from "./api";

const POLL_PHASES = new Set([
  "asking",
  "evaluating",
  "generating_report",
]);

export function useConversationInterview(
  conversationId: string,
  enabled: boolean,
) {
  const [interview, setInterview] =
    useState<CareerInterviewSession | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!enabled || !conversationId) {
      setInterview(null);
      setError("");
      return;
    }
    try {
      const response = await getCareerInterviewByConversation(
        conversationId,
      );
      if (!response.ok) {
        setError(
          response.error?.message || "无法读取模拟面试状态。",
        );
        return;
      }
      setInterview(response.interview || null);
      setError("");
    } catch {
      setError("无法连接模拟面试服务，可稍后重试。");
    }
  }, [conversationId, enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!interview || !POLL_PHASES.has(interview.phase)) return;
    const timer = window.setTimeout(() => void refresh(), 1_000);
    return () => window.clearTimeout(timer);
  }, [interview, refresh]);

  return { interview, error, refresh };
}
```

- [ ] **Step 4: Run GREEN**

Run the Step 2 command.

Expected: all Hook tests pass.

### Task 5: Compact Conversation Interview Bar

**Files:**
- Create: `surfaces/gui/src/components/ConversationInterviewBar.tsx`
- Create: `surfaces/gui/src/components/ConversationInterviewBar.test.tsx`

- [ ] **Step 1: Add component RED**

Test the four visible states:

```typescript
it("shows user-facing progress without internal ids", () => {
  render(
    <ConversationInterviewBar
      interview={session({
        status: "in_progress",
        phase: "waiting_for_answer",
      })}
      error=""
      busy={false}
      onStart={vi.fn()}
      onFinish={vi.fn()}
      onReplay={vi.fn()}
      onRetry={vi.fn()}
      onDownload={vi.fn()}
      onReviewPrompt={vi.fn()}
    />,
  );

  expect(screen.getByText(/第 1 \\/ 8 题/)).toBeTruthy();
  expect(screen.getByText(/个人贡献/)).toBeTruthy();
  expect(screen.queryByText(/project\\[0\\]|turn-1|depth/i)).toBeNull();
});
```

Add tests for ready start, generating report, completed downloads, and error retry.

- [ ] **Step 2: Run component RED**

Run:

```bash
cd surfaces/gui && npm test -- --run \
  src/components/ConversationInterviewBar.test.tsx
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement user-facing labels**

Use fixed maps:

```typescript
const DIMENSION_LABELS: Record<string, string> = {
  context: "项目背景",
  personal_contribution: "个人贡献",
  implementation: "技术实现",
  architecture: "系统架构",
  performance: "性能优化",
  evaluation: "评测验证",
  metrics: "成功指标",
  strategy: "产品策略",
  inference: "推理优化",
};
```

Derive the current unanswered Turn and render a single compact `<section
data-testid="conversation-interview-bar">`. Never render `probe_target`, raw refs, fact paths, or
depth.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command.

Expected: component tests pass.

### Task 6: Conversation-First Launch, Transcript, And Composer

**Files:**
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/App.interview.test.tsx`
- Modify: `surfaces/gui/src/components/Composer.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`

- [ ] **Step 1: Replace old surface expectations with RED**

Remove the `InterviewView` mock. Add:

```typescript
it("starts an interview in the standard conversation", async () => {
  mocked.createCareerInterview.mockResolvedValue({
    ok: true,
    interview: {
      id: "interview-1",
      conversation_id: "career-conversation",
      position: "大模型算法工程师",
      status: "ready",
      phase: "idle",
      version: 1,
      turns: [],
    },
  });
  mocked.getCareerInterviewByConversation.mockResolvedValue({
    ok: true,
    interview: null,
  });

  render(<App />);
  fireEvent.click(await screen.findByRole("button", {
    name: "打开岗位雷达",
  }));
  fireEvent.click(screen.getByRole("button", {
    name: "从岗位启动面试",
  }));

  expect(
    await screen.findByTestId("conversation-interview-bar"),
  ).toBeTruthy();
  expect(screen.getByRole("textbox")).toBeTruthy();
  expect(screen.queryByText(/面试页面/)).toBeNull();
});
```

Add tests that selecting a recent session restores the bar, an ordinary Career session does not
show it, and the first completed turn renames the session.

- [ ] **Step 2: Run App RED**

Run:

```bash
cd surfaces/gui && npm test -- --run src/App.interview.test.tsx
```

Expected: old separate Interview surface expectations fail.

- [ ] **Step 3: Switch launch to Conversation**

In `startMockInterview`, replace:

```typescript
setActiveInterviewId(linked.interviewId);
setSurface("interview");
```

with:

```typescript
pendingInterviewTitle.current =
  `模拟面试 · ${payload.position}`;
setSurface("session");
queuedInterviewTurn.current = {
  ...interviewStartMessage(linked.interviewId),
  skill: "mock-interview",
};
```

Extend `InterviewLaunchPayload` with the existing job title as `position`.

Use:

```typescript
export interface InterviewLaunchPayload {
  jobId: string;
  resumeId: string;
  snapshotId: string;
  position: string;
  durationMinutes: 10 | 15 | 20;
  difficulty: "simple" | "standard" | "deep";
}
```

When `CareerJobsView` calls `onStartInterview`, add:

```typescript
position: interviewJob.title || "未命名岗位",
```

Extend the queued message type:

```typescript
const queuedInterviewTurn = useRef<{
  prompt: string;
  display: string;
  skill: "mock-interview";
} | null>(null);
```

When the socket opens, send all four values:

```typescript
send(
  queued.prompt,
  undefined,
  queued.skill,
  queued.display,
);
```

Initialize Conversation lookup at App level:

```typescript
const conversationInterview = useConversationInterview(
  sessionId,
  agent === "career" && surface === "session",
);
```

Change the queued-turn effect guard from `surface !== "interview"` to
`surface !== "session"`, so the first question starts only after the standard Conversation socket
connects.

For an Interview created through the Career Agent tool loop, keep the current binding call but
replace the independent-page transition with:

```typescript
void bindCreatedCareerInterview(interviewId, sessionId)
  .then(async () => {
    setInterviewLaunchError("");
    setSurface("session");
    await conversationInterview.refresh();
  })
  .catch((error) => {
    setInterviewLaunchError(
      error instanceof Error
        ? error.message
        : "无法恢复模拟面试。",
    );
  });
```

- [ ] **Step 4: Send visible and internal text separately**

Change the local `send` helper:

```typescript
const send = (
  text: string,
  attachments?: Attachment[],
  skill?: string,
  display?: string,
) => {
  const shown =
    display ?? (skill ? `/${skill}${text ? ` ${text}` : ""}` : text);
  setItems((current) => [
    ...current,
    {
      kind: "user",
      text: shown,
      attachments,
      ts: Date.now() / 1000,
    },
  ]);
  sessionRef.current?.userMessage(
    text,
    attachments,
    composerModel.model,
    skill,
    display,
  );
  followLatest();
};
```

When the active interview has an unanswered Turn, Composer `onSend` uses:

```typescript
const message = interviewAnswerMessage(
  interview.id,
  currentTurn.id,
  text,
);
send(
  message.prompt,
  undefined,
  "mock-interview",
  message.display,
);
```

Completed interviews and normal Career sessions continue through regular `send`.

- [ ] **Step 5: Render the bar and dynamic Composer**

Above `.main-scroll`, render:

```tsx
{conversationInterview.interview && (
  <ConversationInterviewBar
    interview={conversationInterview.interview}
    error={conversationInterview.error}
    busy={running}
    onStart={startCurrentInterview}
    onFinish={finishCurrentInterview}
    onReplay={interviewVoice.replayQuestion}
    onRetry={conversationInterview.refresh}
    onDownload={downloadInterviewArtifact}
    onReviewPrompt={prefillComposer}
  />
)}
```

Set Composer placeholder to `输入回答，或使用语音回答…` only while waiting for an interview
answer. Preserve the existing Career placeholder otherwise.

- [ ] **Step 6: Rename after persistence**

On the first `turn_end` after launch:

```typescript
const title = pendingInterviewTitle.current;
if (title) {
  pendingInterviewTitle.current = "";
  void renameSession(sessionId, title).then(() => refreshSessions());
}
void conversationInterview.refresh();
```

- [ ] **Step 7: Run App GREEN**

Run:

```bash
cd surfaces/gui && npm test -- --run \
  src/App.interview.test.tsx \
  src/components/Transcript.test.tsx \
  src/components/Composer.skills.test.tsx
```

Expected: all pass and no internal IDs appear in visible message assertions.

### Task 7: Move Voice Into The Standard Composer

**Files:**
- Create: `surfaces/gui/src/useInterviewVoice.ts`
- Create: `surfaces/gui/src/useInterviewVoice.test.tsx`
- Modify: `surfaces/gui/src/components/Composer.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: Add voice Hook RED**

Port the existing Browser/Tauri cases from `InterviewView.test.tsx`:

```typescript
it("transcribes into an editable draft without sending", async () => {
  api.transcribeInterviewAudio.mockResolvedValue({
    ok: true,
    transcript: "识别后的回答",
  });
  const onTranscript = vi.fn();
  const onSend = vi.fn();
  render(
    <Harness
      questionId="turn-1"
      question="请介绍项目背景"
      onTranscript={onTranscript}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "开始录音" }));
  fireEvent.click(screen.getByRole("button", { name: "停止录音" }));

  await waitFor(() =>
    expect(onTranscript).toHaveBeenCalledWith("识别后的回答"),
  );
  expect(onSend).not.toHaveBeenCalled();
});
```

Also port permission error, empty audio, cancel, automatic stop, question change, unmount cleanup, TTS
auto-play, and replay tests.

- [ ] **Step 2: Run voice RED**

Run:

```bash
cd surfaces/gui && npm test -- --run src/useInterviewVoice.test.tsx
```

Expected: FAIL because the Hook does not exist.

- [ ] **Step 3: Extract voice behavior**

Create `useInterviewVoice.ts`:

```typescript
import { useEffect, useRef, useState } from "react";

import {
  synthesizeInterviewQuestion,
  transcribeInterviewAudio,
} from "./api";
import {
  createInterviewAudioCapture,
  interviewAudioCaptureSupported,
  type InterviewAudioCapture,
} from "./interviewAudioCapture";

function microphoneStartError(error: unknown): string {
  const name =
    error && typeof error === "object" && "name" in error
      ? String(error.name)
      : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "未获得麦克风权限，请在浏览器地址栏允许后重试。";
  }
  if (name === "NotFoundError") {
    return "未检测到可用麦克风，请连接设备后重试。";
  }
  return "无法启动麦克风，请直接输入文字回答。";
}

export function useInterviewVoice({
  questionId,
  question,
  onTranscript,
}: {
  questionId?: string;
  question?: string;
  onTranscript: (text: string) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [recordingLevel, setRecordingLevel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [questionAudioReady, setQuestionAudioReady] =
    useState(false);
  const capture = useRef<InterviewAudioCapture | null>(null);
  const captureEpoch = useRef(0);
  const stopping = useRef(false);
  const stopRef = useRef<() => Promise<void>>(async () => undefined);
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef("");
  const supported = interviewAudioCaptureSupported();

  useEffect(() => {
    if (!questionId || !question) return;
    let active = true;
    setError("");
    setQuestionAudioReady(false);
    void synthesizeInterviewQuestion(question)
      .then((blob) => {
        if (!active) return;
        const url = URL.createObjectURL(blob);
        const next = new Audio(url);
        audio.current = next;
        audioUrl.current = url;
        setQuestionAudioReady(true);
        return next.play();
      })
      .catch(() => {
        if (active) {
          setError("问题语音不可用，请直接阅读文字问题。");
        }
      });
    return () => {
      active = false;
      audio.current?.pause();
      audio.current = null;
      setQuestionAudioReady(false);
      if (audioUrl.current) {
        URL.revokeObjectURL(audioUrl.current);
        audioUrl.current = "";
      }
    };
  }, [questionId, question]);

  const stopRecording = async () => {
    if (stopping.current || !capture.current) return;
    stopping.current = true;
    setBusy(true);
    setError("");
    setRecording(false);
    setRecordingLevel(0);
    try {
      const captured = await capture.current.stop();
      const result = await transcribeInterviewAudio(captured);
      const transcript = result.transcript?.trim();
      if (!result.ok || !transcript) {
        throw new Error("empty transcript");
      }
      onTranscript(transcript);
    } catch {
      await capture.current.cancel().catch(() => undefined);
      setError("语音识别失败，请直接输入文字回答。");
    } finally {
      stopping.current = false;
      setBusy(false);
    }
  };
  stopRef.current = stopRecording;

  const startRecording = async () => {
    const epoch = captureEpoch.current + 1;
    captureEpoch.current = epoch;
    setError("");
    setRecordingLevel(0);
    try {
      if (!capture.current) {
        capture.current = createInterviewAudioCapture();
      }
      await capture.current.start(
        setRecordingLevel,
        () => void stopRef.current(),
      );
      if (captureEpoch.current !== epoch) {
        await capture.current.cancel();
        return;
      }
      setRecording(true);
    } catch (caught) {
      if (captureEpoch.current !== epoch) return;
      setError(microphoneStartError(caught));
    }
  };

  const cancelRecording = async () => {
    captureEpoch.current += 1;
    setRecording(false);
    setRecordingLevel(0);
    try {
      await capture.current?.cancel();
    } finally {
      setBusy(false);
    }
  };

  const replayQuestion = () => {
    if (!audio.current) return;
    audio.current.currentTime = 0;
    void audio.current.play().catch(() => {
      setError("问题语音不可用，请直接阅读文字问题。");
    });
  };

  useEffect(
    () => () => {
      captureEpoch.current += 1;
      void capture.current?.cancel().catch(() => undefined);
    },
    [questionId],
  );

  return {
    supported,
    recording,
    recordingLevel,
    busy,
    error,
    questionAudioReady,
    startRecording,
    stopRecording,
    cancelRecording,
    replayQuestion,
  };
}
```

- [ ] **Step 4: Add Composer voice slot**

Add an optional prop:

```typescript
interviewVoiceSlot?: React.ReactNode;
```

Render it in the Composer action row immediately before the send/interrupt control. In `App.tsx`,
pass a small control using `VoiceRecordingMeter` and the Hook actions only while an interview is
waiting for an answer. `onTranscript` calls `prefillComposer(text)`.

- [ ] **Step 5: Run voice GREEN**

Run:

```bash
cd surfaces/gui && npm test -- --run \
  src/useInterviewVoice.test.tsx \
  src/interviewAudioCapture.test.ts \
  src/browserAudioCapture.test.ts \
  src/components/VoiceRecordingMeter.test.tsx
```

Expected: all pass.

### Task 8: Remove The Independent Surface And Run Real Acceptance

**Files:**
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/App.interview.test.tsx`
- Delete: `surfaces/gui/src/components/InterviewView.tsx`
- Delete: `surfaces/gui/src/components/InterviewView.test.tsx`
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Delete the independent path**

Remove:

- `InterviewView` import and render branch.
- `"interview"` from the `surface` union.
- `activeInterviewId`.
- the special `surface === "interview"` queued-turn condition.
- the floating approval card used only by the old surface.

Delete `InterviewView.tsx` and its test after every moved behavior has a passing replacement test.

- [ ] **Step 2: Run focused regression**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_interview_repository.py \
  extensions/career_mcp/tests/test_interview_service.py \
  tests/test_career_interview_api.py \
  tests/test_server.py \
  -q

cd surfaces/gui && npm test -- --run \
  src/App.interview.test.tsx \
  src/careerInterview.test.ts \
  src/useConversationInterview.test.tsx \
  src/useInterviewVoice.test.tsx \
  src/components/ConversationInterviewBar.test.tsx \
  src/components/Transcript.test.tsx \
  src/components/Composer.skills.test.tsx
```

Expected: all pass.

- [ ] **Step 3: Run GUI full regression and build**

Run:

```bash
cd surfaces/gui
npm test -- --run
npm run build
```

Expected: all GUI tests pass; production build succeeds with no new warnings.

- [ ] **Step 4: Run browser acceptance**

Start Server and GUI, then verify:

1. Open Job Radar.
2. Start an interview from a real job.
3. Confirm standard Transcript remains visible.
4. Confirm recent sessions contains `模拟面试 · {岗位}`.
5. Complete one text answer.
6. Complete one browser microphone answer after editing the transcript.
7. Refresh the browser and select the same recent session.
8. Finish at least five turns.
9. Ask one review follow-up in the same Conversation.
10. Download report and transcript.
11. Confirm no internal Interview/Turn IDs appear in visible bubbles.
12. Confirm no HTTP, console, page, microphone cleanup, or approval errors.

- [ ] **Step 5: Run final backend checks**

Run:

```bash
.venv/bin/python -m compileall -q \
  coworker \
  extensions/career_mcp
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 6: Record evidence**

Append to `docs/11_DEVELOPMENT_LOG.md`:

- changed files;
- RED/GREEN counts;
- browser Session and Interview IDs;
- recent-session title;
- reload and same-session review proof;
- voice proof;
- Artifact hashes;
- privacy and console results;
- remaining risks.

Update the mock-interview row in `docs/12_TONIGHT_PROGRESS.md` from independent-page behavior to
Conversation-native behavior.
