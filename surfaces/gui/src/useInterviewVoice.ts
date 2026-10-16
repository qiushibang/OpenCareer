import { useEffect, useRef, useState } from "react";

import {
  synthesizeInterviewQuestion,
  transcribeInterviewAudio,
} from "./api";
import {
  createInterviewAudioCapture,
  interviewAudioCaptureSupported,
  type InterviewAudioCapture,
} from "./interviewAudioCapture";

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

export function useInterviewVoice({
  questionId,
  question,
  onTranscript,
}: {
  questionId?: string;
  question?: string;
  onTranscript: (text: string) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [recordingLevel, setRecordingLevel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [questionAudioReady, setQuestionAudioReady] =
    useState(false);
  const capture = useRef<InterviewAudioCapture | null>(null);
  const captureEpoch = useRef(0);
  const stopping = useRef(false);
  const stopRef = useRef<() => Promise<void>>(
    async () => undefined,
  );
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrl = useRef("");
  const supported = interviewAudioCaptureSupported();

  useEffect(() => {
    if (!questionId || !question) return;
    let active = true;
    setError("");
    setQuestionAudioReady(false);
    void synthesizeInterviewQuestion(question)
      .then((blob) => {
        if (!active) return;
        const url = URL.createObjectURL(blob);
        const next = new Audio(url);
        audio.current = next;
        audioUrl.current = url;
        setQuestionAudioReady(true);
        return next.play();
      })
      .catch(() => {
        if (active) {
          setError("问题语音不可用，请直接阅读文字问题。");
        }
      });
    return () => {
      active = false;
      audio.current?.pause();
      audio.current = null;
      setQuestionAudioReady(false);
      if (audioUrl.current) {
        URL.revokeObjectURL(audioUrl.current);
        audioUrl.current = "";
      }
    };
  }, [questionId, question]);

  const stopRecording = async () => {
    const current = capture.current;
    if (stopping.current || !current) return;
    stopping.current = true;
    setBusy(true);
    setError("");
    setRecording(false);
    setRecordingLevel(0);
    try {
      const captured = await current.stop();
      const result = await transcribeInterviewAudio(captured);
      const transcript = result.transcript?.trim();
      if (!result.ok || !transcript) {
        throw new Error("empty transcript");
      }
      onTranscript(transcript);
    } catch {
      await current.cancel().catch(() => undefined);
      setError("语音识别失败，请直接输入文字回答。");
    } finally {
      stopping.current = false;
      setBusy(false);
    }
  };
  stopRef.current = stopRecording;

  const startRecording = async () => {
    const epoch = captureEpoch.current + 1;
    captureEpoch.current = epoch;
    setError("");
    setRecordingLevel(0);
    try {
      if (!capture.current) {
        capture.current = createInterviewAudioCapture();
      }
      await capture.current.start(
        setRecordingLevel,
        () => void stopRef.current(),
      );
      if (captureEpoch.current !== epoch) {
        await capture.current.cancel();
        return;
      }
      setRecording(true);
    } catch (caught) {
      if (captureEpoch.current !== epoch) return;
      setRecording(false);
      setError(microphoneStartError(caught));
    }
  };

  const cancelRecording = async () => {
    captureEpoch.current += 1;
    setRecording(false);
    setRecordingLevel(0);
    try {
      await capture.current?.cancel();
    } finally {
      setBusy(false);
    }
  };

  const replayQuestion = () => {
    if (!audio.current) return;
    audio.current.currentTime = 0;
    void audio.current.play().catch(() => {
      setError("问题语音不可用，请直接阅读文字问题。");
    });
  };

  useEffect(
    () => () => {
      captureEpoch.current += 1;
      void capture.current?.cancel().catch(() => undefined);
    },
    [questionId],
  );

  return {
    supported,
    recording,
    recordingLevel,
    busy,
    error,
    questionAudioReady,
    startRecording,
    stopRecording,
    cancelRecording,
    replayQuestion,
  };
}
