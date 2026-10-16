import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ConversationVoiceControl } from "./ConversationVoiceControl";

const props = () => ({
  supported: true,
  status: "idle" as const,
  level: 0,
  error: "",
  onStart: vi.fn(),
  onStop: vi.fn(),
  onCancel: vi.fn(),
});

afterEach(cleanup);

it("renders immediate and actionable Chinese states", () => {
  const actions = props();
  const { rerender } = render(
    <ConversationVoiceControl
      {...actions}
      status="starting"
    />,
  );
  expect(screen.getByText("正在请求麦克风权限…")).toBeTruthy();

  rerender(
    <ConversationVoiceControl
      {...actions}
      status="recording"
      level={0.5}
    />,
  );
  expect(screen.getByText("正在录音")).toBeTruthy();
  expect(document.querySelector(".voice-wave-bars")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "停止录音" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "取消录音" }),
  );
  expect(actions.onStop).toHaveBeenCalledTimes(1);
  expect(actions.onCancel).toHaveBeenCalledTimes(1);

  rerender(
    <ConversationVoiceControl
      {...actions}
      status="transcribing"
    />,
  );
  expect(screen.getByText("正在识别…")).toBeTruthy();
});

it("starts from an explicit microphone button", () => {
  const actions = props();
  render(<ConversationVoiceControl {...actions} />);

  fireEvent.click(
    screen.getByRole("button", { name: "开始语音输入" }),
  );

  expect(actions.onStart).toHaveBeenCalledTimes(1);
});

it("shows unsupported and error feedback", () => {
  const actions = props();
  const { rerender } = render(
    <ConversationVoiceControl
      {...actions}
      supported={false}
    />,
  );
  expect(
    screen.getByRole("button", {
      name: "当前环境不支持语音输入",
    }),
  ).toHaveProperty("disabled", true);

  rerender(
    <ConversationVoiceControl
      {...actions}
      error="未获得麦克风权限"
    />,
  );
  expect(screen.getByRole("alert").textContent).toContain(
    "未获得麦克风权限",
  );
});
