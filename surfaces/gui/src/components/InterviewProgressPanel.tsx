import type {
  CareerInterviewSession,
  CareerInterviewTurn,
} from "../api";

const SLOT_COUNT = 5;

const DIMENSION_LABELS: Record<string, string> = {
  context: "项目背景",
  personal_contribution: "个人贡献",
  architecture: "系统架构",
  implementation: "技术实现",
  performance: "性能优化",
  strategy: "产品策略",
  metrics: "成功指标",
  evaluation: "效果验证",
  user_problem: "用户问题",
  prioritization: "产品优先级",
  tradeoff: "方案权衡",
  result: "项目结果",
};

function turnLabel(turn: CareerInterviewTurn): string {
  return (
    turn.question_topic?.trim() ||
    (turn.probe_dimension
      ? DIMENSION_LABELS[turn.probe_dimension]
      : "") ||
    "岗位能力"
  );
}

export function InterviewProgressPanel({
  interview,
}: {
  interview: CareerInterviewSession;
}) {
  const turns = new Map(
    interview.turns.map((turn) => [turn.turn_index, turn]),
  );

  return (
    <div className="space-y-2" aria-label="模拟面试题目进度">
      {Array.from({ length: SLOT_COUNT }, (_, offset) => {
        const index = offset + 1;
        const turn = turns.get(index);
        const state = turn?.evaluation
          ? "completed"
          : turn
            ? "current"
            : "pending";
        const color =
          state === "completed"
            ? "border-okLine bg-okSoft text-ok"
            : state === "current"
              ? "border-accent bg-accentSoft text-ink"
              : "border-line bg-paper text-faint";

        return (
          <div
            key={index}
            data-testid="interview-question-slot"
            id={`interview-slot-${index}`}
            data-state={state}
            className={`min-w-0 rounded-md border px-3 py-2 ${color}`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 text-xs font-semibold">
                Q{index}
              </span>
              <span className="min-w-0 truncate text-xs font-medium">
                {turn ? turnLabel(turn) : "待生成"}
              </span>
            </div>
            {turn && (
              <p
                className={
                  "mt-1 overflow-hidden text-xs leading-5 " +
                  (state === "current" ? "" : "line-clamp-2")
                }
              >
                {turn.question_text}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
