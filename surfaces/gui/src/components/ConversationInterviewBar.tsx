import type { CareerInterviewSession } from "../api";

const DIMENSION_LABELS: Record<string, string> = {
  context: "项目背景",
  personal_contribution: "个人贡献",
  implementation: "技术实现",
  architecture: "系统架构",
  performance: "性能优化",
  evaluation: "评测验证",
  metrics: "成功指标",
  strategy: "产品策略",
  inference: "推理优化",
};

type ArtifactKind = "transcript" | "report" | "session";

export function ConversationInterviewBar({
  interview,
  error,
  busy,
  onStart,
  onRetry,
  onDownload,
  onReviewPrompt,
}: {
  interview: CareerInterviewSession;
  error: string;
  busy: boolean;
  onStart: () => void;
  onRetry: () => void;
  onDownload: (kind: ArtifactKind) => void;
  onReviewPrompt: (prompt: string) => void;
}) {
  const currentTurn = [...interview.turns]
    .reverse()
    .find((turn) => turn.answer_text === null);
  const answered = interview.turns.filter(
    (turn) => turn.answer_text !== null,
  ).length;
  const currentNumber = Math.min(
    currentTurn?.turn_index || answered + 1,
    interview.question_budget,
  );
  const dimension = currentTurn?.probe_dimension
    ? DIMENSION_LABELS[currentTurn.probe_dimension] || "岗位能力"
    : "岗位能力";
  const completed = interview.status === "completed";
  const generating = interview.phase === "generating_report";
  const ready = interview.status === "ready";

  return (
    <section
      data-testid="conversation-interview-bar"
      className="mx-4 mt-3 rounded-lg border border-line bg-accentSoft px-4 py-3 text-sm text-muted"
      aria-label="模拟面试状态"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-ink">
            {interview.company ? `${interview.company} · ` : ""}
            {interview.position}
          </div>
          {ready ? (
            <div className="mt-1 text-muted">
              {interview.duration_minutes} 分钟 ·{" "}
              {interview.question_budget} 题
            </div>
          ) : generating ? (
            <div className="mt-1 text-muted">
              正在生成面试复盘…
            </div>
          ) : completed ? (
            <div className="mt-1 text-muted">复盘已生成</div>
          ) : (
            <div className="mt-1 text-muted">
              第 {currentNumber} / {interview.question_budget} 题 ·{" "}
              {dimension}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {ready && (
            <button
              type="button"
              className="rounded-md bg-accent px-3 py-1.5 font-medium text-white disabled:opacity-50"
              disabled={busy}
              onClick={onStart}
            >
              开始面试
            </button>
          )}
          {completed && (
            <>
              <button
                type="button"
                className="rounded-md border border-line bg-panel px-3 py-1.5"
                onClick={() => onDownload("report")}
              >
                下载报告
              </button>
              <button
                type="button"
                className="rounded-md border border-line bg-panel px-3 py-1.5"
                onClick={() => onDownload("transcript")}
              >
                下载逐字稿
              </button>
              <button
                type="button"
                className="rounded-md bg-accent px-3 py-1.5 font-medium text-white"
                onClick={() =>
                  onReviewPrompt("第三题怎样回答更好")
                }
              >
                第三题怎样回答更好
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-2 flex items-center gap-2 text-red-700">
          <span>{error}</span>
          <button
            type="button"
            className="font-medium underline"
            onClick={onRetry}
          >
            重试
          </button>
        </div>
      )}
    </section>
  );
}
