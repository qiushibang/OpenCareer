import { useEffect, useState } from "react";

export function VoiceRecordingMeter({
  active,
  level,
}: {
  active: boolean;
  level: number;
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>([]);

  useEffect(() => {
    if (!active) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(
        Math.floor((Date.now() - startedAt) / 1_000),
      );
    }, 250);
    return () => window.clearInterval(timer);
  }, [active]);

  useEffect(() => {
    if (!active) {
      setLevels([]);
      return;
    }
    const safeLevel = Number.isFinite(level) ? level : 0;
    setLevels((current) => [
      ...current.slice(-13),
      Math.max(0, Math.min(1, safeLevel)),
    ]);
  }, [active, level]);

  if (!active) return null;
  const elapsed = `${Math.floor(elapsedSeconds / 60)}:${String(
    elapsedSeconds % 60,
  ).padStart(2, "0")}`;

  return (
    <div
      className="voice-wave-row flex items-center gap-2"
      aria-label="正在录音"
    >
      <span className="voice-wave-line" aria-hidden="true" />
      <span className="voice-wave-bars" aria-hidden="true">
        {Array.from({ length: 14 }, (_, index) => {
          const level = levels[levels.length - 14 + index] ?? 0;
          return (
            <i
              key={index}
              style={{ height: Math.round(4 + level * 24) }}
            />
          );
        })}
      </span>
      <span
        className="text-[12px] text-muted tabular-nums"
        role="timer"
      >
        {elapsed}
      </span>
    </div>
  );
}
