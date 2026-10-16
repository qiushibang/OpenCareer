import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  downloadCareerInterviewArtifact,
  getCareerInterview,
  synthesizeInterviewQuestion,
  transcribeInterviewAudio,
  type CareerInterviewSession,
} from "../api";
import {
  interviewAnswerPrompt,
  interviewFinishPrompt,
  interviewStartPrompt,
} from "../careerInterview";
import {
  createInterviewAudioCapture,
  interviewAudioCaptureSupported,
  type InterviewAudioCapture,
} from "../interviewAudioCapture";
import { VoiceRecordingMeter } from "./VoiceRecordingMeter";

const POLL_PHASES = new Set([
  "asking",
  "evaluating",
  "generating_report",
]);

function microphoneStartError(error: unknown): string {
  const name =
    error && typeof error === "object" && "name" in error
      ? String(error.name)
      : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "未获得麦克风权限，请在浏览器地址栏允许后重试。";
  }
  if (name === "NotFoundError") {
    return "未检测到可用麦克风，请连接设备后重试。";
  }
  return "无法启动麦克风，请直接输入文字回答。";
}

export function InterviewView({
  interviewId,
  onAgentTurn,
  onClose,
}: {
  interviewId: string;
  onAgentTurn: (prompt: string, skill: "mock-interview") => void;
  onClose: () => void;
}) {
  const [interview, setInterview] =
    useState<CareerInterviewSession | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingTurnId, setPendingTurnId] = useState<string | null>(
    null,
  );
  const [recording, setRecording] = useState(false);
  const [recordingLevel, setRecordingLevel] = useState(0);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [questionAudioReady, setQuestionAudioReady] = useState(false);
  const questionAudio = useRef<HTMLAudioElement | null>(null);
  const questionAudioUrl = useRef("");
  const audioCapture = useRef<InterviewAudioCapture | null>(null);
  const recordingRef = useRef(false);
  const captureEpoch = useRef(0);
  const stoppingRef = useRef(false);
  const stopRecordingRef = useRef<() => Promise<void>>(
    async () => undefined,
  );
  const audioCaptureSupported = interviewAudioCaptureSupported();

  const refresh = useCallback(
    async (expectedTurnId?: string) => {
      try {
        const response = await getCareerInterview(interviewId);
        if (!response.ok || !response.interview) {
          if (response.error?.code === "VERSION_CONFLICT") {
            setError("面试状态已变化，已保留当前草稿。");
          } else {
            setError(response.error?.message || "无法读取模拟面试。");
          }
          return;
        }
        const updated = response.interview;
        setInterview(updated);
        setError("");
        if (expectedTurnId) {
          const latest = updated.turns[updated.turns.length - 1];
          const completed = [
            "completed",
            "cancelled",
            "failed",
          ].includes(updated.status);
          const advanced =
            expectedTurnId === "start"
              ? Boolean(latest)
              : latest?.id !== expectedTurnId;
          if (completed || advanced) {
            setPendingTurnId(null);
            if (expectedTurnId !== "start") setDraft("");
          }
        }
      } catch {
        setError("无法连接本地模拟面试服务。");
      } finally {
        setLoading(false);
      }
    },
    [interviewId],
  );

  useEffect(() => {
    setLoading(true);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (
      !pendingTurnId &&
      (!interview || !POLL_PHASES.has(interview.phase))
    ) {
      return;
    }
    const timer = window.setTimeout(
      () => void refresh(pendingTurnId || undefined),
      1_000,
    );
    return () => window.clearTimeout(timer);
  }, [interview, pendingTurnId, refresh]);

  const currentTurn = useMemo(
    () =>
      [...(interview?.turns || [])]
        .reverse()
        .find((turn) => turn.answer_text === null),
    [interview],
  );
  const answeredTurns =
    interview?.turns.filter((turn) => turn.answer_text !== null).length ||
    0;

  useEffect(() => {
    const question = currentTurn?.question_text;
    if (!currentTurn?.id || !question) return;
    let active = true;
    setVoiceError("");
    setQuestionAudioReady(false);
    void Promise.resolve(synthesizeInterviewQuestion(question))
      .then((blob) => {
        if (!active) return;
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        questionAudio.current = audio;
        questionAudioUrl.current = url;
        setQuestionAudioReady(true);
        return audio.play();
      })
      .catch(() => {
        if (active) {
          setVoiceError("问题语音不可用，请直接阅读文字问题。");
        }
      });
    return () => {
      active = false;
      questionAudio.current?.pause();
      questionAudio.current = null;
      setQuestionAudioReady(false);
      if (questionAudioUrl.current) {
        URL.revokeObjectURL(questionAudioUrl.current);
        questionAudioUrl.current = "";
      }
    };
  }, [currentTurn?.id, currentTurn?.question_text]);

  const startRecording = async () => {
    const epoch = captureEpoch.current + 1;
    captureEpoch.current = epoch;
    setVoiceError("");
    setRecordingLevel(0);
    try {
      if (!audioCapture.current) {
        audioCapture.current = createInterviewAudioCapture();
      }
      await audioCapture.current.start(
        setRecordingLevel,
        () => void stopRecordingRef.current(),
      );
      if (captureEpoch.current !== epoch) {
        await audioCapture.current.cancel();
        return;
      }
      recordingRef.current = true;
      setRecording(true);
    } catch (exc) {
      if (captureEpoch.current !== epoch) return;
      recordingRef.current = false;
      setVoiceError(microphoneStartError(exc));
    }
  };

  const stopRecording = async () => {
    if (stoppingRef.current || !audioCapture.current) return;
    stoppingRef.current = true;
    setVoiceBusy(true);
    setVoiceError("");
    recordingRef.current = false;
    setRecording(false);
    setRecordingLevel(0);
    try {
      const captured = await audioCapture.current.stop();
      const result = await transcribeInterviewAudio(captured);
      if (!result.ok || !result.transcript?.trim()) {
        throw new Error("empty transcript");
      }
      setDraft(result.transcript.trim());
    } catch {
      await audioCapture.current.cancel().catch(() => undefined);
      setVoiceError("语音识别失败，请直接输入文字回答。");
    } finally {
      stoppingRef.current = false;
      setVoiceBusy(false);
    }
  };
  stopRecordingRef.current = stopRecording;

  const cancelRecording = async () => {
    captureEpoch.current += 1;
    recordingRef.current = false;
    setRecording(false);
    setRecordingLevel(0);
    try {
      await audioCapture.current?.cancel();
    } finally {
      setVoiceBusy(false);
    }
  };

  useEffect(
    () => () => {
      captureEpoch.current += 1;
      recordingRef.current = false;
      void audioCapture.current?.cancel().catch(() => undefined);
    },
    [currentTurn?.id],
  );

  const replayQuestion = () => {
    if (!questionAudio.current) return;
    questionAudio.current.currentTime = 0;
    void questionAudio.current.play().catch(() => {
      setVoiceError("问题语音不可用，请直接阅读文字问题。");
    });
  };

  const start = () => {
    if (!interview || pendingTurnId) return;
    setPendingTurnId("start");
    onAgentTurn(interviewStartPrompt(interview.id), "mock-interview");
    void refresh("start");
  };

  const submit = () => {
    if (!interview || !currentTurn || pendingTurnId) return;
    try {
      const prompt = interviewAnswerPrompt(
        interview.id,
        currentTurn.id,
        interview.version,
        draft,
      );
      setPendingTurnId(currentTurn.id);
      onAgentTurn(prompt, "mock-interview");
      void refresh(currentTurn.id);
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "模拟面试回答无效。",
      );
    }
  };

  const finish = () => {
    if (!interview || pendingTurnId) return;
    setPendingTurnId(currentTurn?.id || "finish");
    onAgentTurn(interviewFinishPrompt(interview.id), "mock-interview");
    void refresh(currentTurn?.id || "finish");
  };

  const download = async (
    kind: "transcript" | "report" | "session",
  ) => {
    setError("");
    try {
      await downloadCareerInterviewArtifact(interviewId, kind);
    } catch {
      setError("无法下载模拟面试文件。");
    }
  };

  if (loading && !interview) {
    return (
      <main className="grid h-full place-items-center text-sm text-muted">
        正在读取模拟面试…
      </main>
    );
  }

  if (!interview) {
    return (
      <main className="grid h-full place-items-center p-6">
        <div className="text-center">
          <p className="text-sm text-red-700">
            {error || "未找到这场模拟面试。"}
          </p>
          <button className="mt-4 text-sm text-accent" onClick={onClose}>
            返回岗位
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="h-full overflow-y-auto bg-paper p-5">
      <section className="mx-auto max-w-3xl rounded-2xl border border-line bg-panel p-5">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] text-muted">模拟面试</p>
            <h1 className="mt-1 text-lg font-semibold">
              {interview.position}
            </h1>
            <p className="mt-1 text-xs text-muted">
              {interview.company || "未知公司"} · 已回答 {answeredTurns}/
              {interview.question_budget} 题
            </p>
          </div>
          <button className="text-sm text-muted" onClick={onClose}>
            返回岗位
          </button>
        </header>

        {error && (
          <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {error}
          </p>
        )}

        {interview.status === "ready" && (
          <div className="mt-8 text-center">
            <p className="text-sm text-muted">
              每轮只会出现一道问题，评分将在面试结束后展示。
            </p>
            <button
              className="mt-4 rounded-lg bg-accent px-5 py-2.5 text-sm text-white disabled:opacity-40"
              disabled={Boolean(pendingTurnId)}
              onClick={start}
            >
              {pendingTurnId === "start"
                ? "面试官正在准备第一题…"
                : "开始面试"}
            </button>
          </div>
        )}

        {interview.status === "in_progress" && currentTurn && (
          <div className="mt-6">
            <article className="rounded-xl border border-line bg-paper p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-muted">
                  第 {currentTurn.turn_index} 题
                </p>
                {questionAudioReady && (
                  <button
                    className="text-xs text-accent"
                    onClick={replayQuestion}
                  >
                    重播问题
                  </button>
                )}
              </div>
              <p className="mt-2 text-base leading-7">
                {currentTurn.question_text}
              </p>
            </article>

            <label
              className="mt-5 block text-sm font-medium"
              htmlFor="interview-answer"
            >
              回答
            </label>
            <textarea
              id="interview-answer"
              aria-label="回答"
              className="mt-2 min-h-40 w-full rounded-xl border border-line bg-paper p-3 text-sm leading-6"
              maxLength={20_000}
              value={draft}
              disabled={Boolean(pendingTurnId)}
              onChange={(event) => setDraft(event.target.value)}
            />
            <p className="mt-2 text-xs text-muted">
              语音不可用时仍可编辑并提交文字回答。
            </p>
            {!audioCaptureSupported && (
              <p className="mt-2 text-xs text-amber-700">
                当前浏览器环境不支持安全录音，请使用 HTTPS
                或直接输入文字回答。
              </p>
            )}
            {voiceError && (
              <p className="mt-2 text-xs text-amber-700">
                {voiceError}
              </p>
            )}
            <div className="mt-3">
              <VoiceRecordingMeter
                active={recording}
                level={recordingLevel}
              />
              {recording && (
                <p className="mt-2 text-xs text-muted">
                  正在使用麦克风
                </p>
              )}
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              {audioCaptureSupported &&
                (recording ? (
                  <>
                    <button
                      className="rounded-lg border border-line px-4 py-2 text-sm"
                      disabled={voiceBusy}
                      onClick={() => void cancelRecording()}
                    >
                      取消录音
                    </button>
                    <button
                      className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-700"
                      disabled={voiceBusy}
                      onClick={() => void stopRecording()}
                    >
                      停止录音
                    </button>
                  </>
                ) : (
                  <button
                    className="rounded-lg border border-line px-4 py-2 text-sm"
                    disabled={voiceBusy || Boolean(pendingTurnId)}
                    onClick={() => void startRecording()}
                  >
                    {voiceBusy ? "正在识别…" : "开始录音"}
                  </button>
                ))}
              <button
                className="rounded-lg border border-line px-4 py-2 text-sm"
                onClick={() => void refresh()}
              >
                刷新
              </button>
              {answeredTurns >= 1 && (
                <button
                  className="rounded-lg border border-accent px-4 py-2 text-sm text-accent disabled:opacity-40"
                  disabled={
                    Boolean(pendingTurnId) || recording || voiceBusy
                  }
                  onClick={finish}
                >
                  {answeredTurns < 5
                    ? "提前结束并生成报告"
                    : "结束并生成报告"}
                </button>
              )}
              <button
                className="rounded-lg bg-accent px-4 py-2 text-sm text-white disabled:opacity-40"
                disabled={
                  !draft.trim() ||
                  Boolean(pendingTurnId) ||
                  recording ||
                  voiceBusy
                }
                onClick={submit}
              >
                提交回答
              </button>
            </div>
          </div>
        )}

        {pendingTurnId && (
          <p className="mt-5 text-center text-sm text-muted">
            Career Agent 正在处理本轮…
          </p>
        )}

        {interview.status === "completed" && (
          <div className="mt-6">
            <h2 className="text-base font-semibold">面试复盘已生成</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="rounded-lg bg-accent px-4 py-2 text-sm text-white"
                onClick={() => void download("report")}
              >
                下载面试报告
              </button>
              <button
                className="rounded-lg border border-line px-4 py-2 text-sm"
                onClick={() => void download("transcript")}
              >
                下载逐字稿
              </button>
            </div>
            <div className="mt-5 space-y-3">
              {interview.turns.map((turn) => (
                <article
                  key={turn.id}
                  className="rounded-lg border border-line p-3 text-sm"
                >
                  <p>{turn.question_text}</p>
                  {turn.evaluation && (
                    <p className="mt-2 text-xs text-muted">
                      本轮评价已写入复盘报告。
                    </p>
                  )}
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
