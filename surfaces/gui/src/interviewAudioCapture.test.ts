import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

const runtime = vi.hoisted(() => ({
  tauri: true,
}));

const tauri = vi.hoisted(() => ({
  isTauri: vi.fn(() => runtime.tauri),
  getDictationLevel: vi.fn(),
  startInterviewCapture: vi.fn(),
  stopInterviewCapture: vi.fn(),
  cancelInterviewCapture: vi.fn(),
}));

const browserCapture = vi.hoisted(() => ({
  start: vi.fn(),
  stop: vi.fn(),
  cancel: vi.fn(),
}));

const browser = vi.hoisted(() => ({
  browserInterviewCaptureSupported: vi.fn(() => true),
  createBrowserInterviewCapture: vi.fn(() => browserCapture),
}));

vi.mock("./tauri", () => tauri);
vi.mock("./browserAudioCapture", () => browser);

import {
  createInterviewAudioCapture,
  interviewAudioCaptureSupported,
} from "./interviewAudioCapture";

beforeEach(() => {
  vi.useFakeTimers();
  runtime.tauri = true;
  tauri.startInterviewCapture.mockResolvedValue(undefined);
  tauri.stopInterviewCapture.mockResolvedValue({
    mime: "audio/wav",
    data_base64: "UklGRg==",
  });
  tauri.cancelInterviewCapture.mockResolvedValue(undefined);
  tauri.getDictationLevel.mockResolvedValue(0.4);
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("interview audio capture runtime adapter", () => {
  it("wraps Tauri capture and forwards polled microphone levels", async () => {
    const onLevel = vi.fn();
    const capture = createInterviewAudioCapture();

    await capture.start(onLevel);
    await vi.advanceTimersByTimeAsync(100);
    const audio = await capture.stop();

    expect(tauri.startInterviewCapture).toHaveBeenCalledTimes(1);
    expect(tauri.getDictationLevel).toHaveBeenCalled();
    expect(onLevel).toHaveBeenCalledWith(0.4);
    expect(tauri.stopInterviewCapture).toHaveBeenCalledTimes(1);
    expect(audio.data_base64).toBe("UklGRg==");
  });

  it("clears Tauri level polling when capture is cancelled", async () => {
    const capture = createInterviewAudioCapture();
    await capture.start(vi.fn());

    await capture.cancel();
    await vi.advanceTimersByTimeAsync(500);

    expect(tauri.cancelInterviewCapture).toHaveBeenCalledTimes(1);
    expect(tauri.getDictationLevel).not.toHaveBeenCalled();
  });

  it("delegates to browser capture outside Tauri", async () => {
    runtime.tauri = false;
    const onLevel = vi.fn();
    const onLimit = vi.fn();

    const capture = createInterviewAudioCapture();
    await capture.start(onLevel, onLimit);

    expect(browser.createBrowserInterviewCapture).toHaveBeenCalledTimes(1);
    expect(browserCapture.start).toHaveBeenCalledWith(onLevel, onLimit);
  });

  it("reports support from the active runtime", () => {
    expect(interviewAudioCaptureSupported()).toBe(true);

    runtime.tauri = false;
    browser.browserInterviewCaptureSupported.mockReturnValueOnce(false);
    expect(interviewAudioCaptureSupported()).toBe(false);
  });
});
