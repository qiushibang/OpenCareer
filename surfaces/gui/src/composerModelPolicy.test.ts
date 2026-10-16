import { describe, expect, it } from "vitest";

import {
  AIDEN_MODEL,
  byokModelsFromProviders,
  composerModelPolicy,
} from "./composerModelPolicy";

describe("composerModelPolicy", () => {
  it("only exposes Aiden when other configured models exist", () => {
    expect(
      composerModelPolicy([
        "ep-20260806151220-8km7l",
        AIDEN_MODEL,
        "gpt-5.6-sol",
      ]),
    ).toEqual({
      model: AIDEN_MODEL,
      models: [AIDEN_MODEL],
      modelReady: true,
    });
  });

  it("does not fall back when Aiden is unavailable", () => {
    expect(composerModelPolicy(["gpt-5.6-sol"])).toEqual({
      model: AIDEN_MODEL,
      models: [],
      modelReady: false,
    });
  });

  // 云端 Alpha：模型由后端启动参数挂载，/v1/settings 被 403。前端必须信任 health
  // 返回的后端模型，不能回退到桌面专用的 Aiden provider。
  it("uses the backend health model in alpha mode", () => {
    expect(
      composerModelPolicy([], true, "deepseek:deepseek-v4-flash"),
    ).toEqual({
      model: "deepseek:deepseek-v4-flash",
      models: ["deepseek:deepseek-v4-flash"],
      modelReady: true,
    });
  });

  // 云端 BYOK：已配置 provider 推导出用户模型列表，backendModel（服务器默认或
  // 用户刚保存的默认模型）保持首位，不重复。
  it("offers byok models after the backend model in alpha mode", () => {
    expect(
      composerModelPolicy(
        ["deepseek:deepseek-chat", "kimi:kimi-latest"],
        true,
        "deepseek:deepseek-v4-flash",
      ),
    ).toEqual({
      model: "deepseek:deepseek-v4-flash",
      models: [
        "deepseek:deepseek-v4-flash",
        "deepseek:deepseek-chat",
        "kimi:kimi-latest",
      ],
      modelReady: true,
    });
  });

  it("falls back to the first byok model when health has no model yet", () => {
    expect(composerModelPolicy(["deepseek:deepseek-chat"], true, "")).toEqual({
      model: "deepseek:deepseek-chat",
      models: ["deepseek:deepseek-chat"],
      modelReady: true,
    });
    expect(composerModelPolicy([], true, "")).toEqual({
      model: "",
      models: [],
      modelReady: false,
    });
  });

  it("derives byok model ids from configured providers", () => {
    expect(
      byokModelsFromProviders([
        { name: "openai", configured: true, suggested_models: ["gpt-4.1-mini", "gpt-4.1"] },
        { name: "deepseek", configured: true, suggested_models: ["deepseek-chat"] },
        { name: "kimi", configured: false, suggested_models: ["kimi-latest"] },
      ]),
    ).toEqual(["gpt-4.1-mini", "gpt-4.1", "deepseek:deepseek-chat"]);
  });
});
