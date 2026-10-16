import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useConversationVoice } from "./useConversationVoice";

const api = vi.hoisted(() => ({
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
  conversationId,
  onTranscript = vi.fn(),
}: {
  conversationId: string;
  onTranscript?: (text: string) => void;
}) {
  const voice = useConversationVoice({
    conversationId,
    onTranscript,
  });
  return (
    <>
      <span>{voice.status}</span>
      <span>{voice.error}</span>
      <span>{voice.level}</span>
      <button onClick={() => void voice.start()}>开始</button>
      <button onClick={() => void voice.stop()}>停止</button>
      <button onClick={() => void voice.cancel()}>取消</button>
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
  api.transcribeInterviewAudio.mockResolvedValue({
    ok: true,
    transcript: "识别后的草稿",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

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

it("transcribes into a draft callback without sending", async () => {
  const onTranscript = vi.fn();
  render(
    <Harness
      conversationId="conversation-1"
      onTranscript={onTranscript}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "开始" }));
  await screen.findByText("recording");
  fireEvent.click(screen.getByRole("button", { name: "停止" }));

  expect(screen.getByText("transcribing")).toBeTruthy();
  await waitFor(() =>
    expect(onTranscript).toHaveBeenCalledWith("识别后的草稿"),
  );
  expect(screen.getByText("idle")).toBeTruthy();
});

it("cancels capture when the conversation changes", async () => {
  const rendered = render(
    <Harness conversationId="conversation-1" />,
  );
  fireEvent.click(screen.getByRole("button", { name: "开始" }));
  await screen.findByText("recording");

  capture.cancel.mockClear();
  rendered.rerender(
    <Harness conversationId="conversation-2" />,
  );

  await waitFor(() => expect(capture.cancel).toHaveBeenCalled());
  expect(api.transcribeInterviewAudio).not.toHaveBeenCalled();
});

it("drops a completed transcript after the conversation changes", async () => {
  let resolveTranscription!: (result: {
    ok: boolean;
    transcript: string;
  }) => void;
  const pendingTranscription = new Promise<{
    ok: boolean;
    transcript: string;
  }>((resolve) => {
    resolveTranscription = resolve;
  });
  api.transcribeInterviewAudio.mockReturnValue(
    pendingTranscription,
  );
  const onTranscript = vi.fn();
  const rendered = render(
    <Harness
      conversationId="conversation-1"
      onTranscript={onTranscript}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "开始" }));
  await screen.findByText("recording");
  fireEvent.click(screen.getByRole("button", { name: "停止" }));
  await screen.findByText("transcribing");

  rendered.rerender(
    <Harness
      conversationId="conversation-2"
      onTranscript={onTranscript}
    />,
  );
  await act(async () => {
    resolveTranscription({
      ok: true,
      transcript: "旧会话的识别结果",
    });
    await pendingTranscription;
  });

  expect(onTranscript).not.toHaveBeenCalled();
});

it("shows a Chinese permission error and returns to idle", async () => {
  capture.start.mockRejectedValue(
    Object.assign(new Error("denied"), {
      name: "NotAllowedError",
    }),
  );

  render(<Harness conversationId="conversation-1" />);
  fireEvent.click(screen.getByRole("button", { name: "开始" }));

  expect(
    await screen.findByText(
      "未获得麦克风权限，请在浏览器地址栏允许后重试。",
    ),
  ).toBeTruthy();
  expect(screen.getByText("idle")).toBeTruthy();
});
