import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SupportPortal } from "./SupportPortal";
import { publishFault } from "../supportFault";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("keeps the draft after a failed submission and displays feedback as plain text", async () => {
  let fail = true;
  const fetch = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (String(_input).includes("/v1/auth/session")) return new Response(JSON.stringify({ configured: true, authenticated: true, user: { id: "fixture-user" } }));
    if (init?.method === "POST") {
      if (fail) return new Response("{}", { status: 503 });
      return new Response(JSON.stringify({ feedback: { id: "f".repeat(32) } }), { status: 201 });
    }
    return new Response(JSON.stringify({ feedback: [{ id: "e".repeat(32), description: "<script>fictional text</script>", status: "open", reply: "", created_at: 0 }] }));
  });
  vi.stubGlobal("fetch", fetch);
  const { container } = render(<SupportPortal />);
  fireEvent.click(screen.getByRole("button", { name: "帮助与反馈" }));
  const description = await screen.findByLabelText("问题描述");
  fireEvent.change(description, { target: { value: "虚构问题：发送按钮无法点击" } });
  await waitFor(() => expect((screen.getByRole("button", { name: "提交反馈" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await screen.findByText(/提交未成功/);
  expect((description as HTMLTextAreaElement).value).toBe("虚构问题：发送按钮无法点击");
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await waitFor(() => expect(screen.getByText(/反馈已收到/)).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "我的反馈" }));
  expect(await screen.findByText("<script>fictional text</script>")).toBeTruthy();
  expect(container.querySelector("script")).toBeNull();
});

it("does not attach a missing diagnostic that would block feedback submission", async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes("/v1/auth/session")) return new Response(JSON.stringify({ authenticated: true, user: { id: "fixture-user" } }));
    if (String(input).includes("diagnostics/")) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(init?.method === "POST" ? { feedback: { id: "b".repeat(32) } } : { admin: false }));
  });
  vi.stubGlobal("fetch", fetch);
  render(<SupportPortal />);
  publishFault("a".repeat(32));
  fireEvent.click(screen.getByRole("button", { name: "帮助与反馈" }));
  fireEvent.change(await screen.findByLabelText("问题描述"), { target: { value: "虚构问题：网络连接失败" } });
  await waitFor(() => expect(screen.queryByText(/附带脱敏排查编号/)).toBeNull());
  await waitFor(() => expect((screen.getByRole("button", { name: "提交反馈" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  expect(await screen.findByText(/反馈已收到/)).toBeTruthy();
  expect(JSON.parse(String(fetch.mock.calls.find((call) => call[1]?.method === "POST")?.[1]?.body)).request_id).toBeUndefined();
});
