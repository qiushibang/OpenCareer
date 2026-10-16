import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bindCareerInterviewConversation,
  createCareerInterview,
  downloadCareerInterviewArtifact,
  finishCareerInterview,
  getInterviewVoiceProvider,
  generateCareerInterviewReport,
  getCareerInterview,
  getCareerInterviewByConversation,
  getNextCareerInterviewQuestion,
  removeInterviewVoiceProvider,
  saveInterviewVoiceProvider,
  startCareerInterview,
  submitCareerInterviewAnswer,
  synthesizeInterviewQuestion,
  transcribeInterviewAudio,
} from "./api";
import {
  bindCreatedCareerInterview,
  createLinkedCareerInterview,
  interviewIdFromToolResult,
  interviewAnswerMessage,
  interviewAnswerPrompt,
  interviewStartPrompt,
} from "./careerInterview";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("career interview prompts", () => {
  it("frames start and answer turns for the mock-interview Skill", () => {
    expect(interviewStartPrompt("session/one")).toBe(
      "开始这场模拟面试。interview_session_id=session/one。" +
        "加载 mock-interview Skill，根据当前 JD、已确认简历和 " +
        "Blueprint 提出并保存一道针对性问题。",
    );
    expect(
      interviewAnswerPrompt("session/one", "turn/two", 7, "我的回答"),
    ).toBe(
      "提交模拟面试回答。interview_session_id=session/one；" +
        "turn_id=turn/two；expected_version=7。" +
        "\n\n候选人回答：\n我的回答",
    );
  });

  it("rejects empty and oversized answers", () => {
    expect(() =>
      interviewAnswerPrompt("session-1", "turn-1", 2, "   "),
    ).toThrow("回答不能为空");
    expect(() =>
      interviewAnswerPrompt(
        "session-1",
        "turn-1",
        2,
        "答".repeat(20_001),
      ),
    ).toThrow("回答不能超过 20000 个字符");
  });

  it("separates an interview answer from its visible text", () => {
    expect(
      interviewAnswerMessage(
        "interview-1",
        "turn-1",
        3,
        "  我的回答  ",
      ),
    ).toEqual({
      prompt: expect.stringContaining(
        "expected_version=3",
      ),
      display: "我的回答",
    });
  });
});

describe("linked career interview launch", () => {
  it("accepts only a successful Career create tool UUID", () => {
    const preview =
      '{"ok": true, "data": {"id": ' +
      '"01b29b0c-3b43-4dc7-8713-5cb7bc861165", "version": 1}}';

    expect(
      interviewIdFromToolResult(
        "mcp__career__create_interview_session",
        "ok",
        preview,
      ),
    ).toBe("01b29b0c-3b43-4dc7-8713-5cb7bc861165");
    expect(
      interviewIdFromToolResult("write_file", "ok", preview),
    ).toBeNull();
    expect(
      interviewIdFromToolResult(
        "mcp__career__create_interview_session",
        "error",
        preview,
      ),
    ).toBeNull();
    expect(
      interviewIdFromToolResult(
        "mcp__career__create_interview_session",
        "ok",
        '{"id":"not-a-uuid"}',
      ),
    ).toBeNull();
  });

  it("binds one new Career conversation to the interview session", async () => {
    const create = vi.fn().mockResolvedValue({
      ok: true,
      interview: { id: "interview-1" },
    });

    const result = await createLinkedCareerInterview(
      {
        jobId: "job-1",
        resumeId: "resume-1",
        durationMinutes: 15,
        difficulty: "standard",
      },
      "career-conversation-1",
      create,
    );

    expect(create).toHaveBeenCalledWith({
      job_id: "job-1",
      resume_id: "resume-1",
      conversation_id: "career-conversation-1",
      duration_minutes: 15,
      difficulty: "standard",
    });
    expect(result).toEqual({
      interviewId: "interview-1",
      conversationId: "career-conversation-1",
      startRequired: true,
    });
  });

  it("resumes the conversation returned by an active interview", async () => {
    const create = vi.fn().mockResolvedValue({
      ok: true,
      interview: {
        id: "interview-1",
        conversation_id: "existing-conversation",
        status: "in_progress",
      },
    });

    const result = await createLinkedCareerInterview(
      {
        jobId: "job-1",
        resumeId: "resume-1",
        durationMinutes: 15,
        difficulty: "standard",
      },
      "new-conversation",
      create,
    );

    expect(result).toEqual({
      interviewId: "interview-1",
      conversationId: "existing-conversation",
      startRequired: false,
    });
  });

  it("binds an Agent-created session to the real GUI conversation", async () => {
    const get = vi.fn().mockResolvedValue({
      ok: true,
      interview: {
        id: "interview-1",
        version: 1,
        conversation_id: null,
      },
    });
    const bind = vi.fn().mockResolvedValue({
      ok: true,
      interview: {
        id: "interview-1",
        version: 2,
        conversation_id: "career-session-real",
      },
    });

    await bindCreatedCareerInterview(
      "interview-1",
      "career-session-real",
      get,
      bind,
    );

    expect(bind).toHaveBeenCalledWith("interview-1", {
      expected_version: 1,
      conversation_id: "career-session-real",
    });
  });

  it("refreshes once after a conversation bind version conflict", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        interview: {
          id: "interview-1",
          version: 1,
          conversation_id: null,
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        interview: {
          id: "interview-1",
          version: 2,
          conversation_id: null,
        },
      });
    const bind = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        error: {
          code: "VERSION_CONFLICT",
          message: "conflict",
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        interview: {
          id: "interview-1",
          version: 3,
          conversation_id: "career-session-real",
        },
      });

    await bindCreatedCareerInterview(
      "interview-1",
      "career-session-real",
      get,
      bind,
    );

    expect(get).toHaveBeenCalledTimes(2);
    expect(bind).toHaveBeenNthCalledWith(2, "interview-1", {
      expected_version: 2,
      conversation_id: "career-session-real",
    });
  });
});

describe("career interview API", () => {
  it("queries an interview by encoded conversation id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({ ok: true, interview: null }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCareerInterviewByConversation("conversation/one");

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/v1/career/interviews?conversation_id=conversation%2Fone",
    );
  });

  it("encodes identifiers and sends versioned JSON bodies", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await createCareerInterview({
      job_id: "job/one",
      resume_id: "resume/one",
      conversation_id: "conversation/one",
      difficulty: "standard",
      duration_minutes: 15,
    });
    await bindCareerInterviewConversation("session/one", {
      expected_version: 1,
      conversation_id: "conversation/one",
    });
    await getCareerInterview("session/one");
    await startCareerInterview("session/one", {
      expected_version: 1,
      question: { question: "请介绍自己？", refs: ["INTRO"] },
    });
    await submitCareerInterviewAnswer("session/one", {
      turn_id: "turn/one",
      expected_version: 2,
      answer_text: "回答",
    });
    await getNextCareerInterviewQuestion("session/one", {
      turn_id: "turn/one",
      expected_version: 3,
      evaluation: { relevance: 8 },
      next_action: "FOLLOW_UP",
      next_reason: "继续追问",
      next_question: {
        question: "你的个人贡献是什么？",
        refs: ["project[0]"],
      },
    });
    await finishCareerInterview("session/one", {
      expected_version: 4,
      user_requested: true,
    });
    await generateCareerInterviewReport("session/one", {
      expected_version: 5,
    });

    expect(fetchMock.mock.calls[0][1].body).toBe(
      JSON.stringify({
        job_id: "job/one",
        resume_id: "resume/one",
        conversation_id: "conversation/one",
        difficulty: "standard",
        duration_minutes: 15,
      }),
    );
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      "/interviews/session%2Fone/conversation",
    );
    expect(fetchMock.mock.calls[1][1].body).toBe(
      JSON.stringify({
        expected_version: 1,
        conversation_id: "conversation/one",
      }),
    );
    for (const index of [2, 3, 4, 5, 6, 7]) {
      expect(String(fetchMock.mock.calls[index][0])).toContain(
        "/interviews/session%2Fone",
      );
    }
    expect(fetchMock.mock.calls[4][1].body).toBe(
      JSON.stringify({
        turn_id: "turn/one",
        expected_version: 2,
        answer_text: "回答",
      }),
    );
    expect(String(fetchMock.mock.calls[5][0])).toContain("/next");
    expect(String(fetchMock.mock.calls[6][0])).toContain("/finish");
    expect(String(fetchMock.mock.calls[7][0])).toContain("/report");
  });

  it("downloads artifacts through the authenticated API client", async () => {
    const click = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["report"]),
    });
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:report"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(document, "createElement").mockReturnValue({
      click,
      href: "",
      download: "",
    } as unknown as HTMLAnchorElement);

    await downloadCareerInterviewArtifact("session/one", "report");

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/interviews/session%2Fone/artifacts/report",
    );
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("configures and invokes interview voice endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        configured: true,
        transcript: "识别文本",
      }),
      blob: async () => new Blob(["mp3"]),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getInterviewVoiceProvider();
    await saveInterviewVoiceProvider({
      api_key: "secret",
      app_id: "",
      access_token: "",
      asr_resource_id: "asr",
      tts_resource_id: "tts",
      speaker: "speaker",
    });
    await removeInterviewVoiceProvider();
    await transcribeInterviewAudio({
      mime: "audio/wav",
      data_base64: "UklGRg==",
    });
    await synthesizeInterviewQuestion("请介绍你的项目经历。");

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/v1/settings/voice-provider",
    );
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
    expect(fetchMock.mock.calls[1][1].body).toContain('"api_key":"secret"');
    expect(fetchMock.mock.calls[2][1]).toMatchObject({
      method: "DELETE",
    });
    expect(String(fetchMock.mock.calls[3][0])).toContain(
      "/voice/transcribe",
    );
    expect(String(fetchMock.mock.calls[4][0])).toContain(
      "/voice/synthesize",
    );
  });
});
