import { useEffect, useRef, useState } from "react";

import { transcribeInterviewAudio } from "./api";
import {
  createInterviewAudioCapture,
  interviewAudioCaptureSupported,
  type InterviewAudioCapture,
} from "./interviewAudioCapture";

export type ConversationVoiceStatus =
  | "idle"
  | "starting"
  | "recording"
  | "transcribing";

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
  return "无法启动麦克风，请直接输入文字。";
}

export function useConversationVoice({
  conversationId,
  onTranscript,
}: {
  conversationId: string;
  onTranscript: (text: string) => void;
}) {
  const [status, setStatusState] =
    useState<ConversationVoiceStatus>("idle");
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");
  const capture = useRef<InterviewAudioCapture | null>(null);
  const epoch = useRef(0);
  const statusRef = useRef<ConversationVoiceStatus>("idle");
  const stopRef = useRef<() => Promise<void>>(
    async () => undefined,
  );
  const supported = interviewAudioCaptureSupported();

  const setStatus = (next: ConversationVoiceStatus) => {
    statusRef.current = next;
    setStatusState(next);
  };

  const stop = async () => {
    const current = capture.current;
    if (!current || statusRef.current !== "recording") return;
    const currentEpoch = epoch.current;
    setStatus("transcribing");
    setLevel(0);
    setError("");
    try {
      const result = await transcribeInterviewAudio(
        await current.stop(),
      );
      const transcript = result.transcript?.trim();
      if (!result.ok || !transcript) {
        throw new Error("empty transcript");
      }
      if (epoch.current !== currentEpoch) return;
      onTranscript(transcript);
    } catch {
      if (epoch.current !== currentEpoch) return;
      await current.cancel().catch(() => undefined);
      setError("语音识别失败，请直接输入文字。");
    } finally {
      if (epoch.current === currentEpoch) {
        setStatus("idle");
      }
    }
  };
  stopRef.current = stop;

  const start = async () => {
    if (!supported || statusRef.current !== "idle") return;
    const currentEpoch = epoch.current + 1;
    epoch.current = currentEpoch;
    setError("");
    setLevel(0);
    setStatus("starting");
    try {
      capture.current ??= createInterviewAudioCapture();
      await capture.current.start(
        setLevel,
        () => void stopRef.current(),
      );
      if (epoch.current !== currentEpoch) {
        await capture.current.cancel();
        return;
      }
      setStatus("recording");
    } catch (caught) {
      if (epoch.current !== currentEpoch) return;
      setStatus("idle");
      setError(microphoneStartError(caught));
    }
  };

  const cancel = async () => {
    epoch.current += 1;
    setStatus("idle");
    setLevel(0);
    await capture.current?.cancel().catch(() => undefined);
  };

  useEffect(() => {
    setStatus("idle");
    setLevel(0);
    setError("");
    return () => {
      epoch.current += 1;
      void capture.current?.cancel().catch(() => undefined);
    };
  }, [conversationId]);

  return {
    supported,
    status,
    level,
    error,
    start,
    stop,
    cancel,
  };
}
