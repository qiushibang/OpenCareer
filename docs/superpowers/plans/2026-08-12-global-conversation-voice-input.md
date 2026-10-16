# Global Conversation Voice Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Conversation immediate, visible voice-input feedback while removing mock-interview question playback.

**Architecture:** Add a browser-only `useConversationVoice` controller around the existing in-memory capture and豆包 ASR APIs. Render its state through a focused `ConversationVoiceControl`, pass that control to every Composer from `App`, and keep the existing Tauri local Whisper path inside Composer. Remove all production imports and callbacks that synthesize or replay interview questions.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, existing Browser AudioWorklet capture, existing Tauri dictation commands, existing Career voice HTTP API.

---

## Scope And Worktree Rules

- Work in the current shared worktree and preserve unrelated changes.
- Do not modify TurnEngine, Conversation persistence, permissions, model routing, ASR providers, or audio encoding.
- Browser input uses豆包 ASR; Tauri continues to use local Whisper.
- Voice transcripts remain editable Composer drafts and are never sent automatically.
- Every production behavior change must follow RED → GREEN.

## File Map

- Create `surfaces/gui/src/useConversationVoice.ts`
  - Browser capture, state machine, ASR, errors, cleanup.
- Create `surfaces/gui/src/useConversationVoice.test.tsx`
  - Hook state transitions and cleanup.
- Create `surfaces/gui/src/components/ConversationVoiceControl.tsx`
  - Visible browser voice controls and status text.
- Create `surfaces/gui/src/components/ConversationVoiceControl.test.tsx`
  - Starting, recording, transcribing, unsupported, and error rendering.
- Modify `surfaces/gui/src/components/Composer.tsx`
  - Rename the interview-only slot to a general browser voice slot and align Tauri feedback.
- Modify `surfaces/gui/src/components/Composer.voice.test.tsx`
  - Verify all Persona variants accept voice controls and Tauri status is immediate Chinese text.
- Modify `surfaces/gui/src/App.tsx`
  - Instantiate one global browser voice controller and pass it to every Composer.
- Modify `surfaces/gui/src/App.interview.test.tsx`
  - Verify interview TTS/replay are gone and global voice remains available.
- Modify `surfaces/gui/src/components/ConversationInterviewBar.tsx`
  - Remove replay prop and button.
- Modify `surfaces/gui/src/components/ConversationInterviewBar.test.tsx`
  - Assert replay is absent while finish/report actions remain.
- Modify `docs/11_DEVELOPMENT_LOG.md`
- Modify `docs/12_TONIGHT_PROGRESS.md`

### Task 1: Browser Conversation Voice State Machine

**Files:**
- Create: `surfaces/gui/src/useConversationVoice.ts`
- Create: `surfaces/gui/src/useConversationVoice.test.tsx`

- [ ] **Step 1: Write the starting-state RED**

Create a deferred capture start and assert the hook changes state before it resolves:

```tsx
it("shows starting immediately while microphone permission is pending", async () => {
  let resolveStart!: () => void;
  capture.start.mockReturnValue(
    new Promise<void>((resolve) => {
      resolveStart = resolve;
    }),
  );

  render(<Harness conversationId="conversation-1" />);
  fireEvent.click(screen.getByRole("button", { name: "开始" }));

  expect(screen.getByText("starting")).toBeTruthy();
  resolveStart();
  await waitFor(() => expect(screen.getByText("recording")).toBeTruthy());
});
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/useConversationVoice.test.tsx
```

Expected: FAIL because `useConversationVoice` does not exist.

- [ ] **Step 3: Implement the minimal state API**

Create:

```typescript
export type ConversationVoiceStatus =
  | "idle"
  | "starting"
  | "recording"
  | "transcribing";

export function useConversationVoice({
  conversationId,
  onTranscript,
}: {
  conversationId: string;
  onTranscript: (text: string) => void;
}) {
  const [status, setStatus] =
    useState<ConversationVoiceStatus>("idle");
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");
  const capture = useRef<InterviewAudioCapture | null>(null);
  const epoch = useRef(0);
  const supported = interviewAudioCaptureSupported();

  const start = async () => {
    const currentEpoch = epoch.current + 1;
    epoch.current = currentEpoch;
    setError("");
    setLevel(0);
    setStatus("starting");
    try {
      capture.current ??= createInterviewAudioCapture();
      await capture.current.start(setLevel);
      if (epoch.current !== currentEpoch) {
        await capture.current.cancel();
        return;
      }
      setStatus("recording");
    } catch (caught) {
      if (epoch.current !== currentEpoch) return;
      setStatus("idle");
      setError(microphoneStartError(caught));
    }
  };

  return { supported, status, level, error, start };
}
```

- [ ] **Step 4: Add stop, transcript, and no-auto-send RED**

Add:

```tsx
it("transcribes into a draft callback without sending", async () => {
  api.transcribeInterviewAudio.mockResolvedValue({
    ok: true,
    transcript: "识别后的草稿",
  });
  const onTranscript = vi.fn();
  const onSend = vi.fn();

  render(
    <Harness
      conversationId="conversation-1"
      onTranscript={onTranscript}
      onSend={onSend}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "开始" }));
  await screen.findByText("recording");
  fireEvent.click(screen.getByRole("button", { name: "停止" }));

  expect(screen.getByText("transcribing")).toBeTruthy();
  await waitFor(() =>
    expect(onTranscript).toHaveBeenCalledWith("识别后的草稿"),
  );
  expect(onSend).not.toHaveBeenCalled();
  expect(screen.getByText("idle")).toBeTruthy();
});
```

- [ ] **Step 5: Implement stop and cancel**

Add:

```typescript
const stop = async () => {
  const current = capture.current;
  if (!current || status !== "recording") return;
  setStatus("transcribing");
  setLevel(0);
  try {
    const result = await transcribeInterviewAudio(
      await current.stop(),
    );
    const transcript = result.transcript?.trim();
    if (!result.ok || !transcript) throw new Error("empty transcript");
    onTranscript(transcript);
  } catch {
    await current.cancel().catch(() => undefined);
    setError("语音识别失败，请直接输入文字。");
  } finally {
    setStatus("idle");
  }
};

const cancel = async () => {
  epoch.current += 1;
  setStatus("idle");
  setLevel(0);
  await capture.current?.cancel().catch(() => undefined);
};
```

- [ ] **Step 6: Add cleanup and error RED**

Cover `NotAllowedError`, `NotFoundError`, cancel without ASR, Conversation change, and unmount:

```tsx
it("cancels capture when the conversation changes", async () => {
  const rendered = render(
    <Harness conversationId="conversation-1" />,
  );
  fireEvent.click(screen.getByRole("button", { name: "开始" }));
  await screen.findByText("recording");

  rendered.rerender(
    <Harness conversationId="conversation-2" />,
  );

  await waitFor(() => expect(capture.cancel).toHaveBeenCalled());
  expect(api.transcribeInterviewAudio).not.toHaveBeenCalled();
});
```

- [ ] **Step 7: Implement cleanup**

Add:

```typescript
useEffect(
  () => () => {
    epoch.current += 1;
    void capture.current?.cancel().catch(() => undefined);
  },
  [conversationId],
);
```

- [ ] **Step 8: Run GREEN**

Run the Task 1 command.

Expected: all hook tests pass.

### Task 2: Visible Browser Voice Control

**Files:**
- Create: `surfaces/gui/src/components/ConversationVoiceControl.tsx`
- Create: `surfaces/gui/src/components/ConversationVoiceControl.test.tsx`

- [ ] **Step 1: Write component RED**

Test each state:

```tsx
it("renders immediate and actionable Chinese states", () => {
  const { rerender } = render(
    <ConversationVoiceControl
      supported
      status="starting"
      level={0}
      error=""
      onStart={vi.fn()}
      onStop={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
  expect(screen.getByText("正在请求麦克风权限…")).toBeTruthy();

  rerender(
    <ConversationVoiceControl
      supported
      status="recording"
      level={0.5}
      error=""
      onStart={vi.fn()}
      onStop={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
  expect(screen.getByText("正在录音")).toBeTruthy();
  expect(screen.getByRole("button", { name: "停止录音" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "取消录音" })).toBeTruthy();
});
```

Also assert `transcribing` shows “正在识别…”, idle shows “开始语音输入”, and errors use
`role="alert"`.

- [ ] **Step 2: Run component RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/components/ConversationVoiceControl.test.tsx
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the control**

Use `VoiceRecordingMeter` for recording and fixed Chinese labels:

```tsx
if (!supported) {
  return (
    <button
      type="button"
      aria-label="当前环境不支持语音输入"
      disabled
    >
      <Icon name="mic" size={16} />
    </button>
  );
}

if (status === "starting") {
  return <span role="status">正在请求麦克风权限…</span>;
}

if (status === "transcribing") {
  return <span role="status">正在识别…</span>;
}

if (status === "recording") {
  return (
    <div>
      <VoiceRecordingMeter active level={level} />
      <span>正在录音</span>
      <button onClick={onCancel}>取消录音</button>
      <button onClick={onStop}>停止录音</button>
    </div>
  );
}

return (
  <button type="button" aria-label="开始语音输入" onClick={onStart}>
    <Icon name="mic" size={16} />
  </button>
);
```

- [ ] **Step 4: Run component GREEN**

Run the Task 2 command.

Expected: all component tests pass.

### Task 3: Global Composer Integration

**Files:**
- Modify: `surfaces/gui/src/components/Composer.tsx`
- Modify: `surfaces/gui/src/components/Composer.voice.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/App.interview.test.tsx`

- [ ] **Step 1: Write Composer RED**

Rename the prop expectation to `browserVoiceSlot` and cover multiple Personas:

```tsx
it.each(["career", "cowork", "code"])(
  "renders global voice input for %s",
  (personaId) => {
    render(
      <Composer
        {...props({
          personaId,
          browserVoiceSlot: (
            <button type="button">开始语音输入</button>
          ),
        })}
      />,
    );
    expect(
      screen.getByRole("button", { name: "开始语音输入" }),
    ).toBeTruthy();
  },
);
```

Add Tauri assertions for:

- Clicking immediately exposes “正在请求麦克风权限…”.
- Recording exposes “正在录音”.
- Stopping exposes “正在识别…”.
- Transcript is editable and `onSend` remains untouched.

- [ ] **Step 2: Run Composer RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/components/Composer.voice.test.tsx
```

Expected: FAIL because `browserVoiceSlot` is not supported and Tauri starting text is English/hidden.

- [ ] **Step 3: Implement Composer changes**

Replace:

```typescript
interviewVoiceSlot?: ReactNode;
```

with:

```typescript
browserVoiceSlot?: ReactNode;
```

Render browser controls for non-Tauri and keep native dictation for Tauri:

```tsx
{!isTauri() && props.browserVoiceSlot}
{isTauri() && (
  // existing local Whisper button
)}
```

Set Tauri state before awaiting:

```typescript
setDictationBusy("正在请求麦克风权限…");
const recording = await startDictation();
```

Use `正在识别…` while stopping and include dictation activity in the send-button disabled
condition.

- [ ] **Step 4: Write App RED**

Mock `useConversationVoice` as supported and assert a standard Career Conversation renders the
global control even when no InterviewSession is active. Assert changing `sessionId` is passed as
`conversationId`.

- [ ] **Step 5: Implement App integration**

Replace `useInterviewVoice` with:

```typescript
const conversationVoice = useConversationVoice({
  conversationId: sessionId,
  onTranscript: prefillComposer,
});
```

Pass:

```tsx
browserVoiceSlot={
  <ConversationVoiceControl
    supported={conversationVoice.supported}
    status={conversationVoice.status}
    level={conversationVoice.level}
    error={conversationVoice.error}
    onStart={conversationVoice.start}
    onStop={conversationVoice.stop}
    onCancel={conversationVoice.cancel}
  />
}
```

Do not guard it with InterviewSession state.

- [ ] **Step 6: Run integration GREEN**

Run:

```bash
cd surfaces/gui
npm test -- --run \
  src/components/Composer.voice.test.tsx \
  src/App.interview.test.tsx
```

Expected: all selected tests pass.

### Task 4: Remove Interview Question Playback

**Files:**
- Modify: `surfaces/gui/src/components/ConversationInterviewBar.tsx`
- Modify: `surfaces/gui/src/components/ConversationInterviewBar.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/App.interview.test.tsx`

- [ ] **Step 1: Write playback-removal RED**

Change the bar test to:

```tsx
expect(
  screen.queryByRole("button", { name: "重播问题" }),
).toBeNull();
```

In the App test, mock `synthesizeInterviewQuestion` and assert a waiting interview never calls it.

- [ ] **Step 2: Run RED**

Run:

```bash
cd surfaces/gui
npm test -- --run \
  src/components/ConversationInterviewBar.test.tsx \
  src/App.interview.test.tsx
```

Expected: FAIL because the bar still renders replay and App still creates `useInterviewVoice`.

- [ ] **Step 3: Remove playback wiring**

Delete `onReplay` from the bar props and remove:

```tsx
<button type="button" onClick={onReplay}>
  重播问题
</button>
```

Remove the `useInterviewVoice` import, invocation, and replay callback from `App.tsx`.

- [ ] **Step 4: Run GREEN**

Run the Task 4 command.

Expected: no replay UI and no TTS request.

### Task 5: Regression, Browser Gate, And Documentation

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Run focused regression**

```bash
cd surfaces/gui
npm test -- --run \
  src/useConversationVoice.test.tsx \
  src/components/ConversationVoiceControl.test.tsx \
  src/components/Composer.voice.test.tsx \
  src/components/ConversationInterviewBar.test.tsx \
  src/App.interview.test.tsx \
  src/browserAudioCapture.test.ts \
  src/interviewAudioCapture.test.ts
```

Expected: all pass.

- [ ] **Step 2: Run full GUI regression and build**

```bash
cd surfaces/gui
npm test -- --run
npm run build
```

Expected: all tests pass; only the existing Vite mixed-import and chunk-size warnings remain.

- [ ] **Step 3: Run browser acceptance**

Verify:

1. A normal Conversation shows “开始语音输入”.
2. Clicking immediately shows “正在请求麦克风权限…”.
3. Allowing permission shows waveform, timer, “正在录音”, stop, and cancel.
4. Stopping shows “正在识别…” and inserts an editable draft without sending.
5. A mock interview uses the same control and has no “重播问题”.
6. Network requests contain no `/voice/synthesize` call after a new interview question.
7. Switching Conversation releases the microphone.
8. Console has no new errors.

- [ ] **Step 4: Record evidence**

Append exact RED/GREEN results, full regression counts, browser evidence, and residual device
permission risks to both development logs.

- [ ] **Step 5: Final checks**

```bash
.venv/bin/python -m compileall -q coworker extensions/career_mcp
git diff --check
```

Expected: both commands exit 0.
