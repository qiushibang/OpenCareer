import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { InterviewView } from "./InterviewView";

const api = vi.hoisted(() => ({
  downloadCareerInterviewArtifact: vi.fn(),
  getCareerInterview: vi.fn(),
  synthesizeInterviewQuestion: vi.fn(),
  transcribeInterviewAudio: vi.fn(),
}));

const capture = vi.hoisted(() => ({
  supported: true,
  start: vi.fn(),
  stop: vi.fn(),
  cancel: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../interviewAudioCapture", () => ({
  interviewAudioCaptureSupported: () => capture.supported,
  createInterviewAudioCapture: () => capture,
}));

const firstTurn = {
  id: "turn-1",
  turn_index: 1,
  question_text: "请介绍与你申请岗位最相关的一段经历？",
  question_refs: ["INTRO"],
  answer_text: null,
  evaluation: {
    relevance: 8,
    clarity: 7,
    structure: 6,
    depth: 8,
    evidence: 5,
  },
  next_action: null,
};

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: "interview-1",
    job_id: "job-1",
    resume_id: "resume-1",
    conversation_id: "career-conversation-1",
    company: "DeepSeek",
    position: "大模型算法工程师",
    difficulty: "standard",
    duration_minutes: 15,
    question_budget: 8,
    status: "in_progress",
    phase: "waiting_for_answer",
    version: 2,
    turns: [firstTurn],
    ...overrides,
  };
}

beforeEach(() => {
  api.synthesizeInterviewQuestion.mockRejectedValue(
    new Error("voice not configured"),
  );
  capture.supported = true;
  capture.start.mockResolvedValue(undefined);
  capture.stop.mockResolvedValue({
    mime: "audio/wav",
    data_base64: "UklGRg==",
  });
  capture.cancel.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("InterviewView", () => {
  it("shows immediate feedback while the first question is pending", async () => {
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session({
        status: "ready",
        phase: "idle",
        turns: [],
      }),
    });
    const onAgentTurn = vi.fn();

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={onAgentTurn}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始面试" }),
    );

    expect(onAgentTurn).toHaveBeenCalledWith(
      expect.stringContaining("interview_session_id=interview-1"),
      "mock-interview",
    );
    expect(
      screen.getByRole("button", {
        name: "面试官正在准备第一题…",
      }),
    ).toHaveProperty("disabled", true);
  });

  it("keeps polling from ready until the first question appears", async () => {
    const ready = session({
      status: "ready",
      phase: "idle",
      turns: [],
    });
    api.getCareerInterview
      .mockResolvedValueOnce({ ok: true, interview: ready })
      .mockResolvedValueOnce({ ok: true, interview: ready })
      .mockResolvedValue({
        ok: true,
        interview: session(),
      });

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始面试" }),
    );

    expect(
      await screen.findByText(
        "请介绍与你申请岗位最相关的一段经历？",
        {},
        { timeout: 2500 },
      ),
    ).toBeTruthy();
  });

  it("shows one current question and keeps hidden scores private", async () => {
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      await screen.findByText("请介绍与你申请岗位最相关的一段经历？"),
    ).toBeTruthy();
    expect(screen.queryByText(/relevance|相关性得分|8 分/)).toBeNull();
    expect(screen.getByLabelText("回答")).toHaveProperty("disabled", false);
  });

  it("submits one linked Agent turn and refreshes to the next question", async () => {
    const next = {
      ...firstTurn,
      id: "turn-2",
      turn_index: 2,
      question_text: "你在这个项目中的个人贡献是什么？",
      question_refs: ["project[0]"],
    };
    api.getCareerInterview
      .mockResolvedValueOnce({ ok: true, interview: session() })
      .mockResolvedValue({
        ok: true,
        interview: session({ version: 4, turns: [firstTurn, next] }),
      });
    const onAgentTurn = vi.fn();

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={onAgentTurn}
        onClose={vi.fn()}
      />,
    );
    fireEvent.change(await screen.findByLabelText("回答"), {
      target: { value: "我负责数据清洗、检索链路和离线评测。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交回答" }));

    expect(onAgentTurn).toHaveBeenCalledTimes(1);
    expect(onAgentTurn).toHaveBeenCalledWith(
      expect.stringContaining("turn_id=turn-1"),
      "mock-interview",
    );
    expect(
      await screen.findByText("你在这个项目中的个人贡献是什么？"),
    ).toBeTruthy();
    expect(screen.getByLabelText("回答")).toHaveProperty("value", "");
  });

  it("exposes finish after five answers and preserves drafts on conflict", async () => {
    const answeredTurns = Array.from({ length: 5 }, (_, index) => ({
      ...firstTurn,
      id: `turn-${index + 1}`,
      turn_index: index + 1,
      question_text: `问题 ${index + 1}`,
      answer_text: `回答 ${index + 1}`,
    }));
    const current = {
      ...firstTurn,
      id: "turn-6",
      turn_index: 6,
      question_text: "最后一个问题",
    };
    api.getCareerInterview
      .mockResolvedValueOnce({
        ok: true,
        interview: session({ turns: [...answeredTurns, current] }),
      })
      .mockResolvedValueOnce({
        ok: false,
        error: { code: "VERSION_CONFLICT", message: "conflict" },
      });

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.change(await screen.findByLabelText("回答"), {
      target: { value: "尚未提交的草稿" },
    });
    expect(
      screen.getByRole("button", { name: "结束并生成报告" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() =>
      expect(api.getCareerInterview).toHaveBeenCalledTimes(2),
    );
    expect(screen.getByLabelText("回答")).toHaveProperty(
      "value",
      "尚未提交的草稿",
    );
    expect(screen.getByText("面试状态已变化，已保留当前草稿。")).toBeTruthy();
  });

  it("lets the user finish after one completed turn", async () => {
    const answered = {
      ...firstTurn,
      answer_text: "第一轮回答",
      evaluation: {
        relevance: 8,
        clarity: 7,
        structure: 6,
        depth: 7,
        evidence: 6,
      },
    };
    const current = {
      ...firstTurn,
      id: "turn-2",
      turn_index: 2,
      question_text: "第二题",
    };
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session({ turns: [answered, current], version: 4 }),
    });
    const onAgentTurn = vi.fn();

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={onAgentTurn}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: "提前结束并生成报告",
      }),
    );
    expect(onAgentTurn).toHaveBeenCalledWith(
      expect.stringContaining("结束模拟面试"),
      "mock-interview",
    );
  });

  it("captures audio and leaves the ASR transcript editable", async () => {
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });
    api.synthesizeInterviewQuestion.mockRejectedValue(
      new Error("tts unavailable"),
    );
    api.transcribeInterviewAudio.mockResolvedValue({
      ok: true,
      transcript: "这是尚未提交的语音草稿",
    });
    const onAgentTurn = vi.fn();

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={onAgentTurn}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始录音" }),
    );
    expect(
      await screen.findByRole("button", { name: "停止录音" }),
    ).toBeTruthy();
    expect(document.querySelector(".voice-wave-bars")).toBeTruthy();
    expect(screen.getByRole("timer").textContent).toBe("0:00");
    fireEvent.click(screen.getByRole("button", { name: "停止录音" }));

    await waitFor(() =>
      expect(api.transcribeInterviewAudio).toHaveBeenCalledWith({
        mime: "audio/wav",
        data_base64: "UklGRg==",
      }),
    );
    expect(screen.getByLabelText("回答")).toHaveProperty(
      "value",
      "这是尚未提交的语音草稿",
    );
    expect(onAgentTurn).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("回答"), {
      target: { value: "用户确认后的文本" },
    });
    expect(screen.getByLabelText("回答")).toHaveProperty(
      "value",
      "用户确认后的文本",
    );
  });

  it("autoplays once, supports replay, and revokes question audio", async () => {
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
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });
    api.synthesizeInterviewQuestion.mockResolvedValue(
      new Blob(["mp3"]),
    );

    const rendered = render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "重播问题" }));
    expect(play).toHaveBeenCalledTimes(2);
    rendered.unmount();
    expect(pause).toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith("blob:question");
  });

  it("keeps text controls after ASR failure and can cancel capture", async () => {
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });
    api.synthesizeInterviewQuestion.mockRejectedValue(
      new Error("tts failed"),
    );
    capture.stop.mockRejectedValue(
      new Error("asr failed"),
    );

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始录音" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "取消录音" }),
    );
    expect(capture.cancel).toHaveBeenCalled();

    fireEvent.click(
      await screen.findByRole("button", { name: "开始录音" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "停止录音" }),
    );
    expect(
      await screen.findByText("语音识别失败，请直接输入文字回答。"),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("回答"), {
      target: { value: "仍可使用文字回答" },
    });
    expect(
      screen.getByRole("button", { name: "提交回答" }),
    ).toHaveProperty("disabled", false);
  });

  it("keeps text mode and explains unsupported browser recording", async () => {
    capture.supported = false;
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      await screen.findByText(
        "当前浏览器环境不支持安全录音，请使用 HTTPS 或直接输入文字回答。",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "开始录音" }),
    ).toBeNull();
    expect(screen.getByLabelText("回答")).toHaveProperty(
      "disabled",
      false,
    );
  });

  it.each([
    [
      "NotAllowedError",
      "未获得麦克风权限，请在浏览器地址栏允许后重试。",
    ],
    [
      "SecurityError",
      "未获得麦克风权限，请在浏览器地址栏允许后重试。",
    ],
    [
      "NotFoundError",
      "未检测到可用麦克风，请连接设备后重试。",
    ],
  ])("maps %s microphone errors to Chinese guidance", async (name, message) => {
    capture.start.mockRejectedValueOnce(
      new DOMException("microphone failed", name),
    );
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始录音" }),
    );

    expect(await screen.findByText(message)).toBeTruthy();
  });

  it("auto-stops and transcribes when the capture limit is reached", async () => {
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });
    api.transcribeInterviewAudio.mockResolvedValue({
      ok: true,
      transcript: "五分钟自动停止后的草稿",
    });

    render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始录音" }),
    );
    const onLimitReached = capture.start.mock.calls[0][1] as () => void;
    onLimitReached();

    expect(
      await screen.findByDisplayValue("五分钟自动停止后的草稿"),
    ).toBeTruthy();
    expect(capture.stop).toHaveBeenCalledTimes(1);
  });

  it("cancels active capture on unmount without calling ASR", async () => {
    api.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: session(),
    });
    const rendered = render(
      <InterviewView
        interviewId="interview-1"
        onAgentTurn={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "开始录音" }),
    );

    rendered.unmount();

    await waitFor(() => expect(capture.cancel).toHaveBeenCalled());
    expect(api.transcribeInterviewAudio).not.toHaveBeenCalled();
  });
});
