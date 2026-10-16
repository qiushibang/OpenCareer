# Browser Interview Audio Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure, in-memory browser microphone capture to simulated interviews while preserving the existing Tauri capture path and editable ASR draft workflow.

**Architecture:** Pure audio helpers resample device Float32 samples and encode 16 kHz mono PCM16 WAV. A browser capture object owns `getUserMedia`, `AudioContext`, `AudioWorkletNode`, memory buffers, timeout, and cleanup; a small runtime adapter selects it or the existing Tauri bridge so `InterviewView` has one interface.

**Tech Stack:** React 18, TypeScript, Web Audio API, AudioWorklet, Vitest, Testing Library, existing Volcengine ASR HTTP API.

---

## File Map

- Create `surfaces/gui/src/browserAudioCapture.ts`: pure resampling/WAV helpers, browser capability gate, browser capture lifecycle.
- Create `surfaces/gui/src/browserAudioCapture.test.ts`: deterministic audio format and fake Web Audio lifecycle tests.
- Create `surfaces/gui/src/interviewAudioCapture.ts`: common capture contract and Browser/Tauri runtime selection.
- Create `surfaces/gui/src/interviewAudioCapture.test.ts`: runtime selection and Tauri level polling tests.
- Modify `surfaces/gui/src/components/VoiceRecordingMeter.tsx`: accept an external level and retain only display history/timing.
- Modify `surfaces/gui/src/components/VoiceRecordingMeter.test.tsx`: drive levels through props instead of mocking Tauri.
- Modify `surfaces/gui/src/components/InterviewView.tsx`: use one capture instance, expose browser controls, auto-stop, map errors, and clean up.
- Modify `surfaces/gui/src/components/InterviewView.test.tsx`: cover Browser and Tauri recording behavior.
- Modify `docs/11_DEVELOPMENT_LOG.md` and `docs/12_TONIGHT_PROGRESS.md`: record tests and acceptance evidence.

### Task 1: Pure Audio Conversion

- [x] Add failing tests for 48 kHz and 44.1 kHz linear resampling, PCM16 clamping, RIFF fields, and WAV data length in `browserAudioCapture.test.ts`.
- [x] Run `npm test -- src/browserAudioCapture.test.ts` from `surfaces/gui`; expect failure because `browserAudioCapture` does not exist.
- [x] Implement and export:

```ts
export function resampleLinear(
  input: Float32Array,
  inputRate: number,
  outputRate = 16_000,
): Float32Array;

export function encodePcm16Wav(
  samples: Float32Array,
  sampleRate = 16_000,
): Uint8Array;
```

The encoder writes PCM format `1`, mono channel `1`, byte rate `sampleRate * 2`, block align `2`, bits `16`, and clamps samples to `[-1, 1]`.

- [x] Re-run the test and expect all pure conversion cases to pass.

### Task 2: Browser Capture Lifecycle

- [x] Add fake `MediaStream`, `AudioContext`, and `AudioWorkletNode` tests proving that `start()` requests the microphone only when called, forwards level samples, `stop()` returns WAV and releases every resource, and `cancel()` releases resources without returning audio.
- [x] Add failing cases for permission denial, missing microphone, repeated `start()`, `stop()` before start, empty audio, and the 300-second automatic stop callback.
- [x] Run `npm test -- src/browserAudioCapture.test.ts`; confirm each new behavior fails for the missing lifecycle implementation.
- [x] Implement:

```ts
export type CapturedAudio = {
  mime: "audio/wav";
  data_base64: string;
};

export interface InterviewAudioCapture {
  start(
    onLevel: (level: number) => void,
    onLimitReached?: () => void,
  ): Promise<void>;
  stop(): Promise<CapturedAudio>;
  cancel(): Promise<void>;
}

export function browserInterviewCaptureSupported(): boolean;
export function createBrowserInterviewCapture(): InterviewAudioCapture;
```

Use an inline `Blob` only as the transient `audioWorklet.addModule()` source, revoke that module URL immediately after loading, keep microphone audio only in `Float32Array` chunks, and clear tracks, nodes, context, callbacks, chunks, and timeout on every terminal path.

- [x] Run the browser capture tests and expect them to pass with no unhandled rejection.

### Task 3: Runtime Adapter and Meter Decoupling

- [x] Add failing adapter tests proving Tauri wraps the existing bridge and polls `getDictationLevel`, while Browser delegates to `createBrowserInterviewCapture`.
- [x] Implement `createInterviewAudioCapture()` and `interviewAudioCaptureSupported()` in `interviewAudioCapture.ts`; do not move or alter the Tauri commands.
- [x] Rewrite `VoiceRecordingMeter.test.tsx` so rerendering `level={0.75}` changes bar history and fake timers advance `0:00` to `0:01`.
- [x] Run the meter test and confirm RED because the component does not accept `level`.
- [x] Change the component contract to:

```tsx
export function VoiceRecordingMeter({
  active,
  level,
}: {
  active: boolean;
  level: number;
})
```

Clamp the prop to `0..1`, append it while active, and remove all Tauri imports and polling.

- [x] Run adapter and meter tests and expect all cases to pass.

### Task 4: InterviewView Browser Integration

- [x] Replace the test-wide fixed Tauri runtime with a mocked common adapter that can exercise Browser and Tauri through the same UI.
- [x] Add failing tests for browser recording visibility, ASR draft population, cancel without ASR, auto-stop at five minutes, unsupported-environment guidance, Chinese permission/device errors, and unmount cleanup.
- [x] Run `npm test -- src/components/InterviewView.test.tsx`; verify the browser cases fail because the view still gates controls with `isTauri()`.
- [x] In `InterviewView`, create one capture instance per mounted view, pass its level callback into state, remove direct Tauri imports and `isTauri()` checks, and render controls whenever `interviewAudioCaptureSupported()` is true.
- [x] On limit callback call the same stop-and-transcribe path as the stop button. Preserve the current draft on all failures, never submit automatically, and show:

```text
未获得麦克风权限，请在浏览器地址栏允许后重试。
未检测到可用麦克风，请连接设备后重试。
当前浏览器环境不支持安全录音，请使用 HTTPS 或直接输入文字回答。
语音识别失败，请直接输入文字回答。
```

- [x] Cancel active capture when the question changes, the interview ends, or the view unmounts.
- [x] Run `InterviewView.test.tsx`, `VoiceRecordingMeter.test.tsx`, adapter tests, and browser capture tests; expect all to pass.

### Task 5: Regression, Build, and Real Acceptance

- [x] Run `npm test` in `surfaces/gui`; expect the full GUI suite to pass.
- [x] Run `npm run build`; expect TypeScript and Vite production build to pass.
- [x] Start or reuse Server `127.0.0.1:8765` and GUI `localhost:1420`, then enter an active simulated interview.
- [ ] In the real browser, allow microphone access, speak Chinese, verify moving waveform/timer, stop, and confirm the transcript enters the editable answer field without submission.
- [ ] Start a second recording, cancel it, and confirm no ASR request is sent; inspect browser console for zero errors.
- [x] Update `docs/11_DEVELOPMENT_LOG.md` and `docs/12_TONIGHT_PROGRESS.md` with exact commands, pass counts, browser/runtime details, and any residual HTTPS deployment risk.

## Self-Review

- Spec coverage: capability gate, PCM format, 300-second limit, Chinese errors, privacy cleanup, editable transcript, Browser/Tauri compatibility, tests, build, and real acceptance are each assigned above.
- Scope: no backend, provider, Composer, persistence, FFmpeg, dependency, authentication, or cloud architecture changes.
- Type consistency: both runtime implementations use the same `InterviewAudioCapture` and `CapturedAudio` contracts; `VoiceRecordingMeter` receives `active` and `level`.
- Placeholder scan: no implementation step is deferred.
