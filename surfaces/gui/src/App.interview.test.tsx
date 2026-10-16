import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { App } from "./App";

const mocked = vi.hoisted(() => ({
  bindCareerInterviewConversation: vi.fn(),
  createCareerInterview: vi.fn(),
  getCareerInterview: vi.fn(),
  getCareerInterviewByConversation: vi.fn(),
  renameSession: vi.fn(),
  synthesizeInterviewQuestion: vi.fn(),
  userMessage: vi.fn(),
  approve: vi.fn(),
  sessionEvents: [] as Array<(event: unknown) => void>,
  sessionOpens: [] as Array<{
    sessionId: string;
    open: () => void;
  }>,
  sessionIds: [] as string[],
  sessionMessages: [] as Array<{
    sessionId: string;
    args: unknown[];
  }>,
  sessionWorkspaces: [] as string[],
  sessionWorkspace: "/trusted/openworker-career",
  autoOpenSessions: true,
  conversationVoice: vi.fn(),
}));

vi.mock("./useConversationVoice", () => ({
  useConversationVoice: mocked.conversationVoice,
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  class FakeSession {
    private readonly sessionId: string;

    constructor(
      sessionId: string,
      _workspace: string,
      _agent: string,
      options: {
        onEvent: (event: unknown) => void;
        onOpen: () => void;
      },
    ) {
      this.sessionId = sessionId;
      mocked.sessionIds.push(sessionId);
      mocked.sessionWorkspaces.push(_workspace);
      mocked.sessionEvents.push(options.onEvent);
      mocked.sessionOpens.push({
        sessionId,
        open: options.onOpen,
      });
      if (mocked.autoOpenSessions) {
        window.setTimeout(options.onOpen, 0);
      }
    }

    close() {}
    setModel() {}
    approve(decision: unknown) {
      mocked.approve(decision);
    }
    userMessage(...args: unknown[]) {
      mocked.sessionMessages.push({
        sessionId: this.sessionId,
        args,
      });
      mocked.userMessage(...args);
    }
  }
  return {
    ...actual,
    Session: FakeSession,
    connectEvents: vi.fn(() => () => {}),
    bindCareerInterviewConversation:
      mocked.bindCareerInterviewConversation,
    createCareerInterview: mocked.createCareerInterview,
    getArtifacts: vi.fn(async () => []),
    getHealth: vi.fn(async () => ({
      status: "ok",
      default_workspace: null,
      model: "aiden:deepseek-v4-flash",
    })),
    getInbox: vi.fn(async () => []),
    getCareerInterview: mocked.getCareerInterview,
    getCareerInterviewByConversation:
      mocked.getCareerInterviewByConversation,
    getPersonas: vi.fn(async () => [
      {
        id: "career",
        name: "Career Agent",
        family: "code",
        needs_workspace: true,
      },
    ]),
    getRecentWorkspaces: vi.fn(async () => []),
    getSessionMessages: vi.fn(async () => []),
    getSessions: vi.fn(async () => [
      {
        session_id: "existing-career-session",
        agent: "career",
        workspace: mocked.sessionWorkspace,
        updated_at: "2026-08-11T00:00:00Z",
      },
    ]),
    getSettings: vi.fn(async () => ({
      models: ["aiden:deepseek-v4-flash"],
      model_labels: {},
      model_context_windows: {},
      surfaces: { cowork: true, chat: false, code: false },
      onboarded: true,
    })),
    getUnattended: vi.fn(async () => false),
    renameSession: mocked.renameSession,
    synthesizeInterviewQuestion:
      mocked.synthesizeInterviewQuestion,
  };
});

vi.mock("./components/Sidebar", () => ({
  Sidebar: ({
    onOpenCareerJobs,
    onSelectSession,
  }: {
    onOpenCareerJobs: () => void;
    onSelectSession: (
      id: string,
      workspace: string,
      agent: string,
    ) => void;
  }) => (
    <>
      <button onClick={onOpenCareerJobs}>打开岗位雷达</button>
      <button
        onClick={() =>
          onSelectSession(
            "existing-career-session",
            mocked.sessionWorkspace,
            "career",
          )
        }
      >
        打开最近面试
      </button>
    </>
  ),
}));

vi.mock("./components/CareerJobsView", () => ({
  CareerJobsView: ({
    onStartInterview,
    onStartResumeCoach,
  }: {
    onStartInterview: (payload: Record<string, unknown>) => void;
    onStartResumeCoach: (payload: {
      jobId: string;
      resumeId: string;
      companyName: string;
      position: string;
      jobSheet: string;
    }) => void;
  }) => (
    <>
      <button
        onClick={() =>
          onStartResumeCoach({
            jobId: "job-1",
            resumeId: "resume-1",
            companyName: "DeepSeek",
            position: "大模型算法工程师",
            jobSheet: "【岗位信息】\n- 岗位名称：大模型算法工程师\n【要求清单】\n- 要求1：熟悉 Python",
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
}));

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value: vi.fn(),
  });
  mocked.synthesizeInterviewQuestion.mockRejectedValue(
    new Error("question playback disabled in test"),
  );
  mocked.conversationVoice.mockReturnValue({
    supported: true,
    status: "idle",
    level: 0,
    error: "",
    start: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocked.sessionEvents.length = 0;
  mocked.sessionOpens.length = 0;
  mocked.sessionIds.length = 0;
  mocked.sessionMessages.length = 0;
  mocked.sessionWorkspaces.length = 0;
  mocked.sessionWorkspace = "/trusted/openworker-career";
  mocked.autoOpenSessions = true;
  vi.unstubAllGlobals();
});

const openSession = (sessionId: string) => {
  const connection = [...mocked.sessionOpens]
    .reverse()
    .find((candidate) => candidate.sessionId === sessionId);
  if (!connection) {
    throw new Error(`Session ${sessionId} was not created`);
  }
  act(connection.open);
};

const interviewSession = (
  id: string,
  conversationId: string,
  overrides: Record<string, unknown> = {},
) => ({
  id,
  job_id: "job-1",
  resume_id: "resume-1",
  conversation_id: conversationId,
  company: "DeepSeek",
  position: "大模型算法工程师",
  difficulty: "standard",
  duration_minutes: 15,
  question_budget: 8,
  status: "ready",
  phase: "idle",
  version: 1,
  turns: [],
  ...overrides,
});

describe("App conversation-native mock interview", () => {
  it("automatically sends one AI resume coaching turn", async () => {
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });
    const randomUUID = vi.fn(() => "initial");
    vi.stubGlobal("crypto", { randomUUID });

    render(<App />);
    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "打开岗位雷达" },
        { timeout: 2500 },
      ),
    );
    randomUUID.mockReturnValue("coach-target");
    fireEvent.click(
      await screen.findByRole("button", {
        name: "从岗位启动简历诊断",
      }),
    );

    await waitFor(() =>
      expect(mocked.userMessage).toHaveBeenCalledWith(
        expect.stringContaining("【岗位信息卡（系统脚本生成，编号以此为准）】"),
        undefined,
        "aiden:deepseek-v4-flash",
        "career-resume-coach",
        expect.stringContaining("【岗位信息】"),
      ),
    );
    expect(mocked.userMessage).toHaveBeenCalledTimes(1);
    const prompt = String(mocked.userMessage.mock.calls[0][0]);
    expect(prompt).toContain("resume_id=resume-1");
    expect(prompt).not.toContain("snapshot");
    expect(prompt).toContain("- 要求1：熟悉 Python");
    expect(
      mocked.sessionWorkspaces[
        mocked.sessionWorkspaces.length - 1
      ],
    ).toBe("/trusted/openworker-career");

    act(() => {
      mocked.sessionEvents[mocked.sessionEvents.length - 1]({
        type: "turn_start",
        data: { input: prompt, display: "开始 AI 简历诊断" },
      });
    });
    await waitFor(() =>
      expect(mocked.renameSession).toHaveBeenCalledWith(
        "coach-target",
        "DeepSeek · 大模型算法工程师",
      ),
    );
  });

  it("does not send queued resume coaching to a different session", async () => {
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });
    const randomUUID = vi.fn(() => "initial");
    vi.stubGlobal("crypto", { randomUUID });

    render(<App />);
    const openJobs = await screen.findByRole("button", {
      name: "打开岗位雷达",
    });
    mocked.autoOpenSessions = false;
    fireEvent.click(openJobs);
    randomUUID.mockReturnValue("coach-target");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动简历诊断" }),
    );
    await waitFor(() =>
      expect(mocked.sessionIds).toContain("coach-target"),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "打开最近面试" }),
    );
    await waitFor(() =>
      expect(mocked.sessionIds).toContain("existing-career-session"),
    );
    openSession("existing-career-session");

    await waitFor(() =>
      expect(
        mocked.sessionMessages.filter(
          (message) =>
            message.sessionId === "existing-career-session" &&
            message.args[3] === "career-resume-coach",
        ),
      ).toHaveLength(0),
    );
  });

  it("clears queued resume coaching when starting an interview", async () => {
    mocked.createCareerInterview.mockResolvedValue({
      ok: true,
      interview: { id: "interview-1" },
    });
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });
    const randomUUID = vi.fn(() => "initial");
    vi.stubGlobal("crypto", { randomUUID });

    render(<App />);
    const openJobs = await screen.findByRole("button", {
      name: "打开岗位雷达",
    });
    mocked.autoOpenSessions = false;
    fireEvent.click(openJobs);
    randomUUID.mockReturnValue("coach-target");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动简历诊断" }),
    );
    await waitFor(() =>
      expect(mocked.sessionIds).toContain("coach-target"),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "打开岗位雷达" }),
    );
    randomUUID.mockReturnValue("interview");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动面试" }),
    );
    await waitFor(() =>
      expect(mocked.sessionIds).toContain("interview"),
    );
    openSession("interview");

    await waitFor(() =>
      expect(
        mocked.sessionMessages.filter(
          (message) => message.sessionId === "interview",
        ).map((message) => message.args[3]),
      ).toEqual(["mock-interview"]),
    );
  });

  it("clears queued interview when starting resume coaching", async () => {
    mocked.createCareerInterview.mockResolvedValue({
      ok: true,
      interview: { id: "interview-1" },
    });
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });
    const randomUUID = vi.fn(() => "initial");
    vi.stubGlobal("crypto", { randomUUID });

    render(<App />);
    const openJobs = await screen.findByRole("button", {
      name: "打开岗位雷达",
    });
    mocked.autoOpenSessions = false;
    fireEvent.click(openJobs);
    randomUUID.mockReturnValue("interview");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动面试" }),
    );
    await waitFor(() =>
      expect(mocked.sessionIds).toContain("interview"),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "打开岗位雷达" }),
    );
    randomUUID.mockReturnValue("coach-target");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动简历诊断" }),
    );
    await waitFor(() =>
      expect(mocked.sessionIds).toContain("coach-target"),
    );
    openSession("coach-target");

    await waitFor(() =>
      expect(
        mocked.sessionMessages.filter(
          (message) => message.sessionId === "coach-target",
        ).map((message) => message.args[3]),
      ).toEqual(["career-resume-coach"]),
    );
  });

  it("does not create or send coaching without a trusted workspace", async () => {
    mocked.sessionWorkspace = "";
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });

    render(<App />);
    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "打开岗位雷达" },
        { timeout: 2500 },
      ),
    );
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

  it("shows voice input in a standard Career conversation", async () => {
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });

    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "打开最近面试",
      }),
    );

    expect(
      await screen.findByRole("button", {
        name: "开始语音输入",
      }),
    ).toBeTruthy();
    expect(mocked.conversationVoice).toHaveBeenLastCalledWith(
      expect.objectContaining({
        conversationId: "existing-career-session",
      }),
    );
  });

  it("keeps an Agent-created interview in the standard conversation", async () => {
    mocked.getCareerInterview.mockResolvedValue({
      ok: true,
      interview: {
        id: "01b29b0c-3b43-4dc7-8713-5cb7bc861165",
        version: 1,
        conversation_id: null,
      },
    });
    mocked.bindCareerInterviewConversation.mockResolvedValue({
      ok: true,
      interview: {
        id: "01b29b0c-3b43-4dc7-8713-5cb7bc861165",
        version: 2,
        conversation_id: "bound",
      },
    });
    mocked.getCareerInterviewByConversation.mockImplementation(
      async (conversationId: string) => ({
        ok: true,
        interview: interviewSession(
          "01b29b0c-3b43-4dc7-8713-5cb7bc861165",
          conversationId,
        ),
      }),
    );
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
    render(<App />);
    await screen.findByRole("button", { name: "打开岗位雷达" });
    await waitFor(() =>
      expect(mocked.sessionEvents.length).toBeGreaterThan(0),
    );

    act(() => {
      mocked.sessionEvents[mocked.sessionEvents.length - 1]({
        type: "tool_finished",
        data: {
          name: "mcp__career__create_interview_session",
          status: "ok",
          result_preview:
            '{"ok": true, "data": {"id": ' +
            '"01b29b0c-3b43-4dc7-8713-5cb7bc861165"}}',
        },
      });
    });

    expect(
      await screen.findByTestId("conversation-interview-bar"),
    ).toBeTruthy();
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(screen.queryByText(/面试页面/)).toBeNull();
    expect(
      mocked.bindCareerInterviewConversation,
    ).toHaveBeenCalledWith(
      "01b29b0c-3b43-4dc7-8713-5cb7bc861165",
      expect.objectContaining({
        conversation_id:
          mocked.sessionIds[mocked.sessionIds.length - 1],
      }),
    );
  });

  it("starts a job interview in the standard conversation", async () => {
    mocked.createCareerInterview.mockResolvedValue({
      ok: true,
      interview: { id: "interview-1" },
    });
    mocked.getCareerInterviewByConversation.mockImplementation(
      async (conversationId: string) => ({
        ok: true,
        interview:
          conversationId === "career-conve"
            ? interviewSession("interview-1", conversationId)
            : null,
      }),
    );
    const randomUUID = vi.fn(() => "initial-session");
    vi.stubGlobal("crypto", { randomUUID });

    render(<App />);
    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "打开岗位雷达" },
        { timeout: 2500 },
      ),
    );
    randomUUID.mockReturnValue("career-conversation");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动面试" }),
    );

    expect(
      await screen.findByTestId("conversation-interview-bar"),
    ).toBeTruthy();
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(screen.queryByText(/面试页面/)).toBeNull();
    expect(mocked.createCareerInterview).toHaveBeenCalledWith(
      expect.objectContaining({
        conversation_id: "career-conve",
      }),
    );
    await waitFor(() =>
      expect(mocked.userMessage).toHaveBeenCalledWith(
        expect.stringContaining("interview_session_id=interview-1"),
        undefined,
        "aiden:deepseek-v4-flash",
        "mock-interview",
        "开始模拟面试",
      ),
    );
    expect(
      mocked.sessionWorkspaces[
        mocked.sessionWorkspaces.length - 1
      ],
    ).toBe("/trusted/openworker-career");

    act(() => {
      mocked.sessionEvents[mocked.sessionEvents.length - 1]({
        type: "turn_start",
        data: { input: "开始模拟面试", display: "开始模拟面试" },
      });
    });
    await waitFor(() =>
      expect(mocked.renameSession).toHaveBeenCalledWith(
        "career-conve",
        "模拟面试 · 大模型算法工程师",
      ),
    );
  });

  it("shows only the original answer while sending the internal prompt", async () => {
    mocked.createCareerInterview.mockResolvedValue({
      ok: true,
      interview: { id: "interview-1" },
    });
    mocked.getCareerInterviewByConversation.mockImplementation(
      async (conversationId: string) => ({
        ok: true,
        interview:
          conversationId === "career-conve"
            ? interviewSession("interview-1", conversationId, {
                status: "in_progress",
                phase: "waiting_for_answer",
                turns: [
                  {
                    id: "turn-1",
                    turn_index: 1,
                    question_text: "请说明你的个人贡献。",
                    question_refs: ["project[0]"],
                    answer_text: null,
                    evaluation: null,
                    next_action: null,
                    probe_dimension: "personal_contribution",
                  },
                ],
              })
            : null,
      }),
    );
    const randomUUID = vi.fn(() => "initial-session");
    vi.stubGlobal("crypto", { randomUUID });

    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: "打开岗位雷达" }),
    );
    randomUUID.mockReturnValue("career-conversation");
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动面试" }),
    );
    const textbox = await screen.findByPlaceholderText(
      "输入回答，或使用语音回答…",
    );
    expect(
      mocked.synthesizeInterviewQuestion,
    ).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(mocked.userMessage).toHaveBeenCalled(),
    );
    mocked.userMessage.mockClear();

    fireEvent.change(textbox, {
      target: { value: "我负责核心推理链路。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() =>
      expect(mocked.userMessage).toHaveBeenCalledWith(
        expect.stringContaining("turn_id=turn-1"),
        undefined,
        "aiden:deepseek-v4-flash",
        "mock-interview",
        "我负责核心推理链路。",
      ),
    );
    expect(screen.getByText("我负责核心推理链路。")).toBeTruthy();
    expect(
      screen.queryByText(/interview_session_id=interview-1/),
    ).toBeNull();
  });

  it("restores the interview bar from a recent conversation", async () => {
    mocked.getCareerInterviewByConversation.mockImplementation(
      async (conversationId: string) => ({
        ok: true,
        interview:
          conversationId === "existing-career-session"
            ? interviewSession(
                "interview-restored",
                conversationId,
                {
                  status: "in_progress",
                  phase: "waiting_for_answer",
                },
              )
            : null,
      }),
    );

    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "打开最近面试",
      }),
    );

    expect(
      await screen.findByTestId("conversation-interview-bar"),
    ).toBeTruthy();
    expect(screen.getByRole("textbox")).toBeTruthy();
  });

  it("rejects a job interview before creation without a workspace", async () => {
    mocked.sessionWorkspace = "";
    mocked.createCareerInterview.mockResolvedValue({
      ok: true,
      interview: { id: "interview-should-not-exist" },
    });

    render(<App />);
    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "打开岗位雷达" },
        { timeout: 2500 },
      ),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动面试" }),
    );

    expect(
      await screen.findByText(
        "模拟面试需要可信工作区，请先打开 OpenCareer 项目工作区。",
      ),
    ).toBeTruthy();
    expect(mocked.createCareerInterview).not.toHaveBeenCalled();
  });

  it("shows interview permission approval above the standard composer", async () => {
    mocked.createCareerInterview.mockResolvedValue({
      ok: true,
      interview: { id: "interview-approval" },
    });
    mocked.getCareerInterviewByConversation.mockImplementation(
      async (conversationId: string) => ({
        ok: true,
        interview: interviewSession(
          "interview-approval",
          conversationId,
        ),
      }),
    );

    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: "打开岗位雷达" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "从岗位启动面试" }),
    );
    await screen.findByTestId("conversation-interview-bar");

    act(() => {
      mocked.sessionEvents[mocked.sessionEvents.length - 1]({
        type: "permission_required",
        data: {
          name: "load_skill",
          arguments: { skill: "mock-interview" },
          reason: "requires approval",
          category: "skill",
        },
      });
    });

    fireEvent.click(
      await screen.findByRole("button", { name: "仅允许本次" }),
    );
    expect(mocked.approve).toHaveBeenCalledWith("once");
  });

  it("uses dismissible side panels on a narrow viewport", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        media: "(max-width: 768px)",
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    mocked.getCareerInterviewByConversation.mockResolvedValue({
      ok: true,
      interview: null,
    });

    const { container } = render(<App />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "打开最近面试",
      }),
    );

    expect(container.querySelector(".app")?.className).toContain(
      "mobile-narrow",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "显示侧边栏" }),
    );
    expect(container.querySelector(".app")?.className).toContain(
      "mobile-nav-open",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "关闭侧边栏" }),
    );
    expect(container.querySelector(".app")?.className).not.toContain(
      "mobile-nav-open",
    );

    fireEvent.click(
      screen.getByRole("button", { name: "显示侧边面板" }),
    );
    expect(container.querySelector(".main")?.className).toContain(
      "rail-open",
    );
  });
});
