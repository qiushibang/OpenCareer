import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useConversationInterview } from "./useConversationInterview";

const api = vi.hoisted(() => ({
  getCareerInterviewByConversation: vi.fn(),
}));

vi.mock("./api", () => api);

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
    phase: "evaluating",
    version: 2,
    turns: [],
    ...overrides,
  };
}

function Harness({
  conversationId,
  enabled = true,
}: {
  conversationId: string;
  enabled?: boolean;
}) {
  const state = useConversationInterview(conversationId, enabled);
  return (
    <>
      <span>{state.interview?.id || "none"}</span>
      <span>{state.error || "ok"}</span>
      <button onClick={() => void state.refresh()}>重试</button>
    </>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("restores and polls the interview for the active conversation", async () => {
  api.getCareerInterviewByConversation
    .mockResolvedValueOnce({
      ok: true,
      interview: session(),
    })
    .mockResolvedValueOnce({
      ok: true,
      interview: session({ phase: "waiting_for_answer" }),
    });

  render(<Harness conversationId="career-conversation-1" />);
  await act(async () => Promise.resolve());

  expect(screen.getByText("interview-1")).toBeTruthy();
  await act(async () => vi.advanceTimersByTimeAsync(1_000));
  expect(api.getCareerInterviewByConversation).toHaveBeenCalledTimes(2);
});

it("returns no active state for an ordinary conversation", async () => {
  api.getCareerInterviewByConversation.mockResolvedValue({
    ok: true,
    interview: null,
  });

  render(<Harness conversationId="ordinary-conversation" />);
  await act(async () => Promise.resolve());

  expect(screen.getByText("none")).toBeTruthy();
  expect(screen.getByText("ok")).toBeTruthy();
});

it("preserves the last interview when refresh fails", async () => {
  api.getCareerInterviewByConversation
    .mockResolvedValueOnce({
      ok: true,
      interview: session({ phase: "waiting_for_answer" }),
    })
    .mockRejectedValueOnce(new Error("offline"));

  render(<Harness conversationId="career-conversation-1" />);
  await act(async () => Promise.resolve());
  screen.getByRole("button", { name: "重试" }).click();
  await act(async () => Promise.resolve());

  expect(screen.getByText("interview-1")).toBeTruthy();
  expect(
    screen.getByText("无法连接模拟面试服务，可稍后重试。"),
  ).toBeTruthy();
});
