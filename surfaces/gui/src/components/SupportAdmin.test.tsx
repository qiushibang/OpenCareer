import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SupportAdmin } from "./SupportAdmin";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("loads a support issue and submits the administrator's explicit reply", async () => {
  const item = { id: "a".repeat(32), kind: "bug", description: "虚构问题：页面无法打开", status: "open", reply: "", created_at: 0, updated_at: 123, user_id: "fixture-user" };
  const fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "PATCH") { const { user_id, ...updated } = item; return new Response(JSON.stringify({ feedback: { ...updated, status: "resolved" } })); }
    if (String(url).includes("admin/feedback/")) return new Response(JSON.stringify({ feedback: item, diagnostic: null }));
    return new Response(JSON.stringify({ feedback: [item] }));
  });
  vi.stubGlobal("fetch", fetch);
  render(<SupportAdmin />);
  fireEvent.click(await screen.findByRole("button", { name: "查看问题" }));
  fireEvent.change(await screen.findByLabelText("处理状态"), { target: { value: "resolved" } });
  fireEvent.change(screen.getByLabelText("回复用户"), { target: { value: "虚构回复：请刷新重试" } });
  fireEvent.click(screen.getByRole("button", { name: "保存处理结果" }));
  expect(await screen.findByText("处理结果已保存。")).toBeTruthy();
  expect(screen.getByText(/fixture-user/)).toBeTruthy();
  const patch = fetch.mock.calls.find((call) => call[1]?.method === "PATCH");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ status: "resolved", reply: "虚构回复：请刷新重试", expected_updated_at: 123 });
});
