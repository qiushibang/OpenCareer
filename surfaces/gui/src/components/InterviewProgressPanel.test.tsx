import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CareerInterviewSession } from "../api";
import { InterviewProgressPanel } from "./InterviewProgressPanel";

const interview: CareerInterviewSession = {
  id: "interview-1",
  job_id: "job-1",
  resume_id: "resume-1",
  conversation_id: "conversation-1",
  company: "腾讯",
  position: "AI 产品经理",
  difficulty: "standard",
  duration_minutes: 10,
  question_budget: 5,
  status: "in_progress",
  phase: "evaluating",
  version: 4,
  turns: [
    {
      id: "turn-1",
      turn_index: 1,
      question_text: "请说明你如何定义目标用户？",
      question_refs: ["requirement-1"],
      answer_text: "我先分析核心使用场景。",
      evaluation: { version: 2 },
      next_action: "SWITCH_TOPIC",
      question_topic: "用户问题定义",
      probe_dimension: "user_problem",
    },
    {
      id: "turn-2",
      turn_index: 2,
      question_text: "你如何确定功能优先级？",
      question_refs: ["requirement-2"],
      answer_text: "我会比较用户价值和实现成本。",
      evaluation: null,
      next_action: null,
      question_topic: "产品优先级",
      probe_dimension: "prioritization",
    },
  ],
};

describe("InterviewProgressPanel", () => {
  it("renders five dynamic slots without workflow controls", () => {
    render(<InterviewProgressPanel interview={interview} />);

    expect(screen.getAllByTestId("interview-question-slot")).toHaveLength(5);
    expect(screen.getByText("用户问题定义")).toBeTruthy();
    expect(screen.getByText("产品优先级")).toBeTruthy();
    expect(screen.getAllByText("待生成")).toHaveLength(3);
    expect(screen.queryByText("重播问题")).toBeNull();
    expect(screen.queryByText("提前结束")).toBeNull();
    expect(screen.queryByText("流程状态")).toBeNull();
  });

  it("keeps an answered but unevaluated turn current", () => {
    render(<InterviewProgressPanel interview={interview} />);

    expect(document.getElementById("interview-slot-1")?.dataset.state).toBe(
      "completed",
    );
    expect(document.getElementById("interview-slot-2")?.dataset.state).toBe(
      "current",
    );
    expect(document.getElementById("interview-slot-3")?.dataset.state).toBe(
      "pending",
    );
  });
});
