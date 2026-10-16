// §37 voice input — the composer's side of the contract, driven through a mocked
// __TAURI__ global (the mic is native-only; the browser build renders no mic at all).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Composer } from "./Composer";

const READY = {
  recording: false,
  model_installed: true,
  model_verified: true,
  test_passed: true,
  download_in_progress: false,
  model_name: "Whisper Base English (local)",
  model_bytes: 147964211,
  supported: true,
  device_summary: "macOS 15 · Apple Silicon",
  compatibility_reason: null,
};
const NOT_READY = { ...READY, model_verified: false, test_passed: false };
const RECORDING = { ...READY, recording: true };

let invoke: ReturnType<typeof vi.fn>;

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive",
  model: "gpt-5.6-sol",
  running: false,
  connected: true,
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

beforeEach(() => {
  invoke = vi.fn(async (cmd: string) => {
    if (cmd === "get_dictation_status") return READY;
    if (cmd === "start_dictation") return RECORDING;
    if (cmd === "stop_dictation") return "hello from the mic";
    if (cmd === "dictation_level") return 0.75;
    return null;
  });
  (globalThis as any).__TAURI__ = { core: { invoke }, event: { listen: async () => () => {} } };
});

afterEach(() => {
  cleanup();
  delete (globalThis as any).__TAURI__;
});

describe("Composer voice input (§37)", () => {
  it.each(["career", "cowork", "code"])(
    "renders global browser voice input for %s",
    (personaId) => {
      delete (globalThis as any).__TAURI__;
      render(
        <Composer
          {...props({
            personaId,
            browserVoiceSlot: (
              <button type="button">开始语音输入</button>
            ),
          })}
        />,
      );

      expect(
        screen.getByRole("button", { name: "开始语音输入" }),
      ).toBeTruthy();
      expect(screen.getByRole("button", { name: "发送" })).toBeTruthy();
    },
  );

  it("shows microphone permission feedback before desktop capture resolves", async () => {
    let resolveStart!: (status: typeof RECORDING) => void;
    invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "get_dictation_status") return READY;
      if (cmd === "start_dictation") {
        return new Promise<typeof RECORDING>((resolve) => {
          resolveStart = resolve;
        });
      }
      return null;
    });
    render(
      <Composer {...props()} />,
    );

    fireEvent.click(await screen.findByLabelText("开始语音输入"));
    expect(
      screen.getByText("正在请求麦克风权限…"),
    ).toBeTruthy();
    resolveStart(RECORDING);
    await screen.findByText("正在录音");
  });

  it("renders no mic at all outside the desktop app", () => {
    delete (globalThis as any).__TAURI__;
    render(<Composer {...props()} />);
    expect(screen.queryByLabelText(/语音输入/)).toBeNull();
  });

  it("not ready → muted mic deep-links to Settings instead of recording", async () => {
    invoke.mockImplementation(async (cmd: string) =>
      cmd === "get_dictation_status" ? NOT_READY : null,
    );
    const onConfigureVoiceInput = vi.fn();
    render(<Composer {...props({ onConfigureVoiceInput })} />);

    const mic = await screen.findByLabelText("在设置中配置语音输入");
    expect(mic.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(mic);
    await waitFor(() => expect(onConfigureVoiceInput).toHaveBeenCalled());
    expect(invoke).not.toHaveBeenCalledWith("start_dictation", undefined);
  });

  it("ready → record shows the waveform and protects Send; stop inserts an editable draft", async () => {
    render(<Composer {...props()} />);

    fireEvent.click(await screen.findByLabelText("开始语音输入"));
    const stop = await screen.findByLabelText("停止语音输入");
    expect(document.querySelector(".voice-wave-bars")).toBeTruthy();
    await waitFor(() => {
      const bars = document.querySelectorAll(".voice-wave-bars i");
      expect(
        (bars[bars.length - 1] as HTMLElement).style.height,
      ).toBe("22px");
    });
    expect(screen.getByLabelText("发送").hasAttribute("disabled")).toBe(true);

    invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "stop_dictation") return "hello from the mic";
      if (cmd === "get_dictation_status") return READY;
      return null;
    });
    fireEvent.click(stop);
    await screen.findByLabelText("开始语音输入"); // recording UI wound down
    const box = screen.getByPlaceholderText(/向 Agent 提问/) as HTMLTextAreaElement;
    expect(box.value).toBe("hello from the mic"); // a DRAFT — nothing auto-sent
    expect(document.querySelector(".voice-wave-bars")).toBeNull();
  });

  it("a start failure surfaces the error and never wedges the mic", async () => {
    invoke.mockImplementation(async (cmd: string) => {
      if (cmd === "get_dictation_status") return READY;
      if (cmd === "start_dictation") throw new Error("No microphone is available.");
      return null;
    });
    render(<Composer {...props()} />);

    fireEvent.click(await screen.findByLabelText("开始语音输入"));
    expect((await screen.findByRole("alert")).textContent).toContain("No microphone is available.");
    expect(screen.getByLabelText("开始语音输入").hasAttribute("disabled")).toBe(false);
  });
});
