import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SupportErrorBoundary } from "./SupportDiagnostics";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("offers a safe diagnostic when the page crashes without uploading exception text", async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ request_id: "a".repeat(32) }), { status: 201 }));
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(console, "error").mockImplementation(() => {});
  function Broken(): never { throw new Error("fictional-private-api-key"); }
  render(<SupportErrorBoundary><Broken /></SupportErrorBoundary>);
  expect(screen.getByText("页面暂时遇到问题")).toBeTruthy();
  await waitFor(() => expect(screen.getByText(/排查编号：/)).toBeTruthy());
  expect(screen.queryByText(/fictional-private-api-key/)).toBeNull();
  expect(String(fetch.mock.calls)).not.toContain("fictional-private-api-key");
  expect(screen.getByRole("button", { name: "反馈此问题" })).toBeTruthy();
});
