import { afterEach, expect, it, vi } from "vitest";
import { getProviders, getSettings } from "./api";

// Career Alpha 把 /v1/providers、/v1/settings 等「本机控制类」接口一律 403，
// 响应体是 {"error": "..."} 对象而非数组/设置对象。这些 fetcher 必须把「接口不可用」
// 这个合法状态归一化成安全形状（空数组 / 空对象），否则调用方对返回值调用
// .find()/.map() 会抛未捕获 TypeError，把整棵 React 树冲垮 → 发消息即白屏。

afterEach(() => {
  vi.unstubAllGlobals();
});

const forbidden = () =>
  vi.fn(async () => ({
    ok: false,
    status: 403,
    json: async () => ({ error: "This local-machine control is disabled in Career Alpha." }),
  }));

it("normalizes a 403 providers response to an empty list", async () => {
  vi.stubGlobal("fetch", forbidden());
  const providers = await getProviders();
  expect(Array.isArray(providers)).toBe(true);
  // 调用方的真实用法：providers.find(...) 不得抛错。
  expect(() => providers.find((p) => p.name === "openai")).not.toThrow();
});

it("normalizes a 403 settings response to an object with an empty models list", async () => {
  vi.stubGlobal("fetch", forbidden());
  const settings = await getSettings();
  // 调用方会读 settings.models 并 .map(...)；必须是数组。
  expect(Array.isArray(settings.models)).toBe(true);
});
