import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { QuickModelSetup } from "./QuickModelSetup";

const api = vi.hoisted(() => ({
  getProviders: vi.fn(),
  setProvider: vi.fn(),
  verifyProvider: vi.fn(),
}));

vi.mock("../api", () => ({
  ...api,
}));

vi.mock("../tauri", () => ({
  openExternal: vi.fn(),
}));

const PROVIDERS = [
  {
    name: "deepseek",
    title: "DeepSeek（深度求索）",
    needs_key: true,
    configured: true,
    source: "env",
    values: {},
    suggested_models: ["deepseek-chat", "deepseek-reasoner"],
    recommended_model: "deepseek-chat",
    fields: [
      { key: "api_key", label: "API Key", secret: true, required: true, help: "", placeholder: "sk-…" },
      { key: "base_url", label: "自定义接口地址（可选）", secret: false, required: false, help: "", placeholder: "" },
    ],
  },
  {
    name: "kimi",
    title: "Kimi（月之暗面）",
    needs_key: true,
    configured: false,
    source: "env",
    values: {},
    suggested_models: ["kimi-latest"],
    recommended_model: "kimi-latest",
    fields: [
      { key: "api_key", label: "API Key", secret: true, required: true, help: "", placeholder: "sk-…" },
    ],
  },
];

function renderModal(overrides: Partial<Parameters<typeof QuickModelSetup>[0]> = {}) {
  const props = {
    onClose: vi.fn(),
    onOpenSettings: vi.fn(),
    onSaved: vi.fn(),
    onUseModel: vi.fn(),
    ...overrides,
  };
  render(<QuickModelSetup {...props} />);
  return props;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("QuickModelSetup（配置自定义模型弹窗）", () => {
  it("shows the curated gallery with status, and the form opens from a card", async () => {
    api.getProviders.mockResolvedValue(PROVIDERS);
    renderModal();

    await waitFor(() => expect(screen.getByText("DeepSeek（深度求索）")).toBeTruthy());
    // 服务器内置的 DeepSeek 标明来源；未配置的 Kimi 标为未配置。
    expect(screen.getByText("✓ 服务器提供")).toBeTruthy();
    expect(screen.getAllByText("未配置").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId("qm-provider-kimi"));
    expect(await screen.findByTestId("qm-field-api_key")).toBeTruthy();
    // 返回画廊的面包屑在弹窗内可用。
    fireEvent.click(screen.getByTestId("qm-back"));
    expect(await screen.findByTestId("qm-provider-deepseek")).toBeTruthy();
  });

  it("test-and-save persists, selects the recommended model, and notifies the host", async () => {
    api.getProviders.mockResolvedValue(PROVIDERS);
    api.verifyProvider.mockResolvedValue({ ok: true });
    api.setProvider.mockResolvedValue({ ok: true });
    const props = renderModal();

    fireEvent.click(await screen.findByTestId("qm-provider-kimi"));
    const keyInput = await screen.findByTestId("qm-field-api_key");
    fireEvent.change(keyInput, { target: { value: "sk-kimi-key" } });
    fireEvent.click(screen.getByTestId("qm-test"));

    await waitFor(() => {
      expect(api.setProvider).toHaveBeenCalledWith("kimi", { api_key: "sk-kimi-key" });
    });
    // 测试通过 → 推荐模型立即选中（回到对话即可用），宿主收到刷新通知。
    await waitFor(() => {
      expect(props.onUseModel).toHaveBeenCalledWith("kimi:kimi-latest");
      expect(props.onSaved).toHaveBeenCalled();
    });
  });

  it("a failed test shows the error inline and does not save or switch", async () => {
    api.getProviders.mockResolvedValue(PROVIDERS);
    api.verifyProvider.mockResolvedValue({ ok: false, error: "invalid api key" });
    const props = renderModal();

    fireEvent.click(await screen.findByTestId("qm-provider-kimi"));
    fireEvent.change(await screen.findByTestId("qm-field-api_key"), { target: { value: "sk-bad" } });
    fireEvent.click(screen.getByTestId("qm-test"));

    expect(await screen.findByText(/测试失败：invalid api key/)).toBeTruthy();
    await waitFor(() => expect(api.verifyProvider).toHaveBeenCalled());
    expect(api.setProvider).not.toHaveBeenCalled();
    expect(props.onUseModel).not.toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("links to the full management page and closes", async () => {
    api.getProviders.mockResolvedValue(PROVIDERS);
    const props = renderModal();

    fireEvent.click(await screen.findByTestId("quick-setup-manage"));
    expect(props.onOpenSettings).toHaveBeenCalledOnce();
    expect(props.onClose).toHaveBeenCalledOnce();
  });
});
