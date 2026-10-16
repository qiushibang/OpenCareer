import type { ConversationVoiceStatus } from "../useConversationVoice";
import { Icon } from "./Icon";
import { VoiceRecordingMeter } from "./VoiceRecordingMeter";

export function ConversationVoiceControl({
  supported,
  status,
  level,
  error,
  onStart,
  onStop,
  onCancel,
}: {
  supported: boolean;
  status: ConversationVoiceStatus;
  level: number;
  error: string;
  onStart: () => void | Promise<void>;
  onStop: () => void | Promise<void>;
  onCancel: () => void | Promise<void>;
}) {
  const iconButton =
    "w-7 h-7 grid place-items-center rounded-md text-muted hover:text-ink hover:bg-paper shrink-0";

  if (!supported) {
    return (
      <button
        type="button"
        className={`${iconButton} opacity-40`}
        aria-label="当前环境不支持语音输入"
        title="当前环境不支持语音输入"
        disabled
      >
        <Icon name="mic" size={16} />
      </button>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      {status === "starting" && (
        <span className="text-[11.5px] text-accent" role="status">
          正在请求麦克风权限…
        </span>
      )}

      {status === "transcribing" && (
        <span className="text-[11.5px] text-accent" role="status">
          正在识别…
        </span>
      )}

      {status === "recording" && (
        <>
          <div className="min-w-[120px]">
            <VoiceRecordingMeter active level={level} />
          </div>
          <span className="text-[11.5px] text-red-600">
            正在录音
          </span>
          <button
            type="button"
            className="text-[11.5px] text-muted hover:text-ink"
            onClick={() => void onCancel()}
          >
            取消录音
          </button>
          <button
            type="button"
            className="text-[11.5px] text-red-700 hover:text-red-800"
            onClick={() => void onStop()}
          >
            停止录音
          </button>
        </>
      )}

      {status === "idle" && (
        <button
          type="button"
          className={iconButton}
          aria-label="开始语音输入"
          title="开始语音输入"
          onClick={() => void onStart()}
        >
          <Icon name="mic" size={16} />
        </button>
      )}

      {error && (
        <span
          className="max-w-[240px] truncate text-[11.5px] text-red-600"
          role="alert"
          title={error}
        >
          {error}
        </span>
      )}
    </div>
  );
}
