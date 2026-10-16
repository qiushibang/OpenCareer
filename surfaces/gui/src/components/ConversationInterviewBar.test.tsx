import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ConversationInterviewBar } from "./ConversationInterviewBar";

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: "interview-1",
    job_id: "job-1",
    resume_id: "resume-1",
    conversation_id: "career-conversation-1",
    company: "DeepSeek",
    position: "大模型算法工程师",
    difficulty: "standard" as const,
    duration_minutes: 15 as const,
    question_budget: 8 as const,
    status: "in_progress" as const,
    phase: "waiting_for_answer",
    version: 2,
    turns: [
      {
        id: "turn-1",
        turn_index: 1,
        question_text: "请说明你在项目中的个人职责。",
        question_refs: ["project[0].highlights[0]"],
        answer_text: null,
        evaluation: null,
        next_action: null,
        probe_target: "project[0]",
        probe_dimension: "personal_contribution",
        depth_level: 2,
      },
    ],
    ...overrides,
  };
}

const handlers = () => ({
  onStart: vi.fn(),
  onRetry: vi.fn(),
  onDownload: vi.fn(),
  onReviewPrompt: vi.fn(),
});

afterEach(cleanup);

it("shows user-facing progress without internal ids", () => {
  render(
    <ConversationInterviewBar
      interview={session()}
      error=""
      busy={false}
      {...handlers()}
    />,
  );

  expect(screen.getByText(/第 1 \/ 8 题/)).toBeTruthy();
  expect(screen.getByText(/个人贡献/)).toBeTruthy();
  expect(
    screen.queryByText(/project\[0\]|turn-1|depth/i),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "提前结束" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "重播问题" }),
  ).toBeNull();
});

it("supports ready, report generation, and completed review actions", () => {
  const readyHandlers = handlers();
  const { rerender } = render(
    <ConversationInterviewBar
      interview={session({
        status: "ready",
        phase: "idle",
        turns: [],
      })}
      error=""
      busy={false}
      {...readyHandlers}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "开始面试" }));
  expect(readyHandlers.onStart).toHaveBeenCalledTimes(1);

  rerender(
    <ConversationInterviewBar
      interview={session({ phase: "generating_report" })}
      error=""
      busy={true}
      {...handlers()}
    />,
  );
  expect(screen.getByText("正在生成面试复盘…")).toBeTruthy();

  const completedHandlers = handlers();
  rerender(
    <ConversationInterviewBar
      interview={session({
        status: "completed",
        phase: "completed",
      })}
      error=""
      busy={false}
      {...completedHandlers}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "下载报告" }));
  fireEvent.click(
    screen.getByRole("button", { name: "第三题怎样回答更好" }),
  );
  expect(completedHandlers.onDownload).toHaveBeenCalledWith("report");
  expect(completedHandlers.onReviewPrompt).toHaveBeenCalledWith(
    "第三题怎样回答更好",
  );
});

it("offers retry when interview state cannot be refreshed", () => {
  const actions = handlers();
  render(
    <ConversationInterviewBar
      interview={session()}
      error="无法读取模拟面试状态。"
      busy={false}
      {...actions}
    />,
  );

  expect(screen.getByText("无法读取模拟面试状态。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(actions.onRetry).toHaveBeenCalledTimes(1);
});
