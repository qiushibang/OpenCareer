import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { SettingsView } from "./SettingsView";

const api = vi.hoisted(() => ({
  getInterviewVoiceProvider: vi.fn(),
  saveInterviewVoiceProvider: vi.fn(),
  removeInterviewVoiceProvider: vi.fn(),
}));

vi.mock("../api", () => ({
  ...api,
  getSettings: vi.fn(async () => ({})),
  getTrustedWorkspaces: vi.fn(async () => []),
}));
vi.mock("../tauri", () => ({
  isTauri: () => false,
}));
vi.mock("./ManageTabs", () => ({ ModelsTab: () => null }));
vi.mock("./GalleryModal", () => ({ GalleryModal: () => null }));
vi.mock("./PersonasTab", () => ({ PersonasTab: () => null }));
vi.mock("./SkillsTab", () => ({ SkillsTab: () => null }));
vi.mock("./IntegrationsView", () => ({
  PanelHead: ({ title }: { title: string }) => <h2>{title}</h2>,
}));
vi.mock("./Icon", () => ({ Icon: () => null }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SettingsView interview voice provider", () => {
  it("prefills public IDs, keeps secrets blank, saves and removes", async () => {
    api.getInterviewVoiceProvider.mockResolvedValue({
      configured: true,
      auth_mode: "api_key",
      asr_resource_id: "asr-resource",
      tts_resource_id: "tts-resource",
      speaker: "speaker-id",
    });
    api.saveInterviewVoiceProvider.mockResolvedValue({
      configured: true,
      auth_mode: "api_key",
      asr_resource_id: "asr-resource",
      tts_resource_id: "tts-resource",
      speaker: "speaker-id",
    });
    api.removeInterviewVoiceProvider.mockResolvedValue({
      configured: false,
      auth_mode: null,
      asr_resource_id: "",
      tts_resource_id: "",
      speaker: "",
    });

    render(<SettingsView initialTab="voice" />);

    expect(
      await screen.findByText("火山引擎模拟面试语音"),
    ).toBeTruthy();
    expect(screen.getByLabelText("语音 API Key")).toHaveProperty(
      "value",
      "",
    );
    expect(screen.getByLabelText("ASR Resource ID")).toHaveProperty(
      "value",
      "asr-resource",
    );
    fireEvent.change(screen.getByLabelText("语音 API Key"), {
      target: { value: "new-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存云语音" }));

    await waitFor(() =>
      expect(api.saveInterviewVoiceProvider).toHaveBeenCalledWith(
        expect.objectContaining({
          api_key: "new-secret",
          asr_resource_id: "asr-resource",
          tts_resource_id: "tts-resource",
          speaker: "speaker-id",
        }),
      ),
    );
    expect(screen.getByLabelText("语音 API Key")).toHaveProperty(
      "value",
      "",
    );

    fireEvent.click(screen.getByRole("button", { name: "删除云语音配置" }));
    await waitFor(() =>
      expect(api.removeInterviewVoiceProvider).toHaveBeenCalled(),
    );
  });
});
