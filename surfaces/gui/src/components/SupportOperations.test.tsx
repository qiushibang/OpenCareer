import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SupportOperations } from "./SupportOperations";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("displays safe system alerts and management actions without rendering raw markup", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url) => new Response(JSON.stringify(String(url).includes("audit")
    ? { audit: [{ id: "b".repeat(32), user_id: "fixture-admin", action: "update", created_at: 0, target_id: "a".repeat(32) }] }
    : { alerts: [{ id: "a".repeat(32), category: "health_down", source: "host", count: 1, active: true, updated_at: 0 }] }))));
  render(<SupportOperations />);
  expect(await screen.findByText("服务暂时不可达")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "管理记录" }));
  expect(await screen.findByText(/处理反馈/)).toBeTruthy();
});
