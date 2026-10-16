import {
  browserInterviewCaptureSupported,
  createBrowserInterviewCapture,
  type InterviewAudioCapture,
} from "./browserAudioCapture";
import {
  cancelInterviewCapture,
  getDictationLevel,
  isTauri,
  startInterviewCapture,
  stopInterviewCapture,
} from "./tauri";

export type { InterviewAudioCapture } from "./browserAudioCapture";

export function interviewAudioCaptureSupported(): boolean {
  return isTauri() || browserInterviewCaptureSupported();
}

export function createInterviewAudioCapture(): InterviewAudioCapture {
  if (!isTauri()) return createBrowserInterviewCapture();

  let levelTimer: number | null = null;
  const clearLevelTimer = () => {
    if (levelTimer !== null) {
      window.clearInterval(levelTimer);
      levelTimer = null;
    }
  };

  return {
    async start(onLevel) {
      await startInterviewCapture();
      levelTimer = window.setInterval(() => {
        void getDictationLevel()
          .then((level) => {
            if (typeof level === "number") {
              onLevel(Math.max(0, Math.min(1, level)));
            }
          })
          .catch(() => undefined);
      }, 100);
    },

    async stop() {
      clearLevelTimer();
      return stopInterviewCapture();
    },

    async cancel() {
      clearLevelTimer();
      await cancelInterviewCapture();
    },
  };
}
