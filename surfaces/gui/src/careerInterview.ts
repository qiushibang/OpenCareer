import {
  bindCareerInterviewConversation,
  createCareerInterview,
  getCareerInterview,
  type CareerInterviewResult,
} from "./api";

const MAX_ANSWER_CHARS = 20_000;
const INTERVIEW_CREATE_TOOL =
  "mcp__career__create_interview_session";
const UUID_PATTERN =
  /"id"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"/i;

export type InterviewAgentMessage = {
  prompt: string;
  display: string;
};

export function interviewIdFromToolResult(
  name: unknown,
  status: unknown,
  preview: unknown,
): string | null {
  if (
    name !== INTERVIEW_CREATE_TOOL ||
    status !== "ok" ||
    typeof preview !== "string"
  ) {
    return null;
  }
  return preview.match(UUID_PATTERN)?.[1] || null;
}

export async function bindCreatedCareerInterview(
  interviewId: string,
  conversationId: string,
  get: typeof getCareerInterview = getCareerInterview,
  bind: typeof bindCareerInterviewConversation =
    bindCareerInterviewConversation,
): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const current = await get(interviewId);
    if (!current.ok || !current.interview) {
      throw new Error(
        current.error?.message || "无法读取模拟面试。",
      );
    }
    if (current.interview.conversation_id === conversationId) {
      return;
    }
    if (current.interview.conversation_id) {
      throw new Error("该模拟面试已绑定其他对话。");
    }
    const response = await bind(interviewId, {
      expected_version: current.interview.version,
      conversation_id: conversationId,
    });
    if (response.ok) return;
    if (
      response.error?.code !== "VERSION_CONFLICT" ||
      attempt === 1
    ) {
      throw new Error(
        response.error?.message || "无法绑定模拟面试对话。",
      );
    }
  }
}

export async function createLinkedCareerInterview(
  payload: {
    jobId: string;
    resumeId: string;
    durationMinutes: 10 | 15 | 20;
    difficulty: "simple" | "standard" | "deep";
  },
  conversationId: string,
  create: typeof createCareerInterview = createCareerInterview,
): Promise<{
  interviewId: string;
  conversationId: string;
  startRequired: boolean;
}> {
  const response: CareerInterviewResult = await create({
    job_id: payload.jobId,
    resume_id: payload.resumeId,
    conversation_id: conversationId,
    duration_minutes: payload.durationMinutes,
    difficulty: payload.difficulty,
  });
  if (!response.ok || !response.interview?.id) {
    throw new Error(
      response.error?.message || "无法创建模拟面试。",
    );
  }
  return {
    interviewId: response.interview.id,
    conversationId:
      response.interview.conversation_id || conversationId,
    startRequired: response.interview.status !== "in_progress",
  };
}

export const interviewStartPrompt = (sessionId: string) =>
  `开始这场模拟面试。interview_session_id=${sessionId}。` +
  "加载 mock-interview Skill，根据当前 JD、已确认简历和 " +
  "Blueprint 提出并保存一道针对性问题。";

const normalizeInterviewAnswer = (answer: string) => {
  const normalized = answer.trim();
  if (!normalized) throw new Error("回答不能为空");
  if (normalized.length > MAX_ANSWER_CHARS) {
    throw new Error("回答不能超过 20000 个字符");
  }
  return normalized;
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
  expectedVersion: number,
  answer: string,
): InterviewAgentMessage => {
  const normalized = normalizeInterviewAnswer(answer);
  return {
    prompt:
    `提交模拟面试回答。interview_session_id=${sessionId}；` +
      `turn_id=${turnId}；expected_version=${expectedVersion}。` +
      `\n\n候选人回答：\n${normalized}`,
    display: normalized,
  };
};

export const interviewAnswerPrompt = (
  sessionId: string,
  turnId: string,
  expectedVersion: number,
  answer: string,
) => interviewAnswerMessage(
  sessionId,
  turnId,
  expectedVersion,
  answer,
).prompt;

export const interviewFinishPrompt = (sessionId: string) =>
  `结束模拟面试。interview_session_id=${sessionId}。` +
  "加载 mock-interview Skill，完成评价并生成面试报告。";
