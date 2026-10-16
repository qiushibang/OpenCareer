import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useInterviewVoice } from "./useInterviewVoice";

const api = vi.hoisted(() => ({
  synthesizeInterviewQuestion: vi.fn(),
  transcribeInterviewAudio: vi.fn(),
}));

const capture = vi.hoisted(() => ({
  supported: true,
  start: vi.fn(),
  stop: vi.fn(),
  cancel: vi.fn(),
}));

vi.mock("./api", () => api);
vi.mock("./interviewAudioCapture", () => ({
  interviewAudioCaptureSupported: () => capture.supported,
  createInterviewAudioCapture: () => capture,
}));

function Harness({
  questionId = "turn-1",
  question = "请介绍项目背景",
  onTranscript,
}: {
  questionId?: string;
  question?: string;
  onTranscript: (text: string) => void;
}) {
  const voice = useInterviewVoice({
    questionId,
    question,
    onTranscript,
  });
  return (
    <>
      <button onClick={() => void voice.startRecording()}>
        开始录音
      </button>
      <button onClick={() => void voice.stopRecording()}>
        停止录音
      </button>
      <button onClick={() => void voice.cancelRecording()}>
        取消录音
      </button>
      <button onClick={voice.replayQuestion}>重播问题</button>
      <span>{voice.error}</span>
    </>
  );
}

beforeEach(() => {
  capture.supported = true;
  capture.start.mockResolvedValue(undefined);
  capture.stop.mockResolvedValue({
    mime: "audio/wav",
    data_base64: "UklGRg==",
  });
  capture.cancel.mockResolvedValue(undefined);
  api.synthesizeInterviewQuestion.mockRejectedValue(
    new Error("tts unavailable"),
  );
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

it("transcribes into an editable draft without sending", async () => {
  api.transcribeInterviewAudio.mockResolvedValue({
    ok: true,
    transcript: "识别后的回答",
  });
  const onTranscript = vi.fn();

  render(<Harness onTranscript={onTranscript} />);
  fireEvent.click(screen.getByRole("button", { name: "开始录音" }));
  await waitFor(() => expect(capture.start).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "停止录音" }));

  await waitFor(() =>
    expect(onTranscript).toHaveBeenCalledWith("识别后的回答"),
  );
  expect(api.transcribeInterviewAudio).toHaveBeenCalledWith({
    mime: "audio/wav",
    data_base64: "UklGRg==",
  });
});

it("autoplays, replays, and revokes question audio", async () => {
  const play = vi.fn(async () => undefined);
  const pause = vi.fn();
  const revoke = vi.fn();
  vi.stubGlobal(
    "Audio",
    vi.fn(function () { return { play, pause, currentTime: 0 }; }),
  );
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:question"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revoke,
  });
  api.synthesizeInterviewQuestion.mockResolvedValue(
    new Blob(["mp3"]),
  );

  const rendered = render(<Harness onTranscript={vi.fn()} />);
  await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "重播问题" }));
  expect(play).toHaveBeenCalledTimes(2);

  rendered.unmount();
  expect(pause).toHaveBeenCalled();
  expect(revoke).toHaveBeenCalledWith("blob:question");
});

it("cancels microphone capture on request and question change", async () => {
  const onTranscript = vi.fn();
  const rendered = render(<Harness onTranscript={onTranscript} />);
  fireEvent.click(screen.getByRole("button", { name: "开始录音" }));
  await waitFor(() => expect(capture.start).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "取消录音" }));
  await waitFor(() => expect(capture.cancel).toHaveBeenCalled());

  capture.cancel.mockClear();
  rendered.rerender(
    <Harness
      questionId="turn-2"
      question="请说明个人贡献"
      onTranscript={onTranscript}
    />,
  );
  await waitFor(() => expect(capture.cancel).toHaveBeenCalled());
});
