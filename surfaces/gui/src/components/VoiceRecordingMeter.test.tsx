import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VoiceRecordingMeter } from "./VoiceRecordingMeter";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("VoiceRecordingMeter", () => {
  it("uses provided microphone levels and elapsed recording time", async () => {
    const rendered = render(
      <VoiceRecordingMeter active level={0.25} />,
    );
    rendered.rerender(
      <VoiceRecordingMeter active level={0.75} />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_100);
    });

    expect(document.querySelector(".voice-wave-bars")).toBeTruthy();
    const bars = document.querySelectorAll(".voice-wave-bars i");
    expect((bars[bars.length - 1] as HTMLElement).style.height).toBe(
      "22px",
    );
    expect(screen.getByRole("timer").textContent).toBe("0:01");

    rendered.rerender(
      <VoiceRecordingMeter active level={Number.NaN} />,
    );
    const updatedBars = document.querySelectorAll(
      ".voice-wave-bars i",
    );
    expect(
      (updatedBars[updatedBars.length - 1] as HTMLElement).style.height,
    ).toBe("4px");

    rendered.rerender(
      <VoiceRecordingMeter active={false} level={0} />,
    );
    expect(screen.queryByRole("timer")).toBeNull();
  });
});
