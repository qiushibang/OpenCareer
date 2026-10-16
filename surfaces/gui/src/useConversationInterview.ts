import { useCallback, useEffect, useState } from "react";

import {
  getCareerInterviewByConversation,
  type CareerInterviewSession,
} from "./api";

const POLL_PHASES = new Set([
  "asking",
  "evaluating",
  "generating_report",
]);

export function useConversationInterview(
  conversationId: string,
  enabled: boolean,
) {
  const [interview, setInterview] =
    useState<CareerInterviewSession | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!enabled || !conversationId) {
      setInterview(null);
      setError("");
      return;
    }
    try {
      const response = await getCareerInterviewByConversation(
        conversationId,
      );
      if (!response.ok) {
        setError(
          response.error?.message || "无法读取模拟面试状态。",
        );
        return;
      }
      setInterview(response.interview || null);
      setError("");
    } catch {
      setError("无法连接模拟面试服务，可稍后重试。");
    }
  }, [conversationId, enabled]);

  useEffect(() => {
    setInterview(null);
    setError("");
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!interview || !POLL_PHASES.has(interview.phase)) return;
    const timer = window.setTimeout(() => void refresh(), 1_000);
    return () => window.clearTimeout(timer);
  }, [interview, refresh]);

  return { interview, error, refresh };
}
