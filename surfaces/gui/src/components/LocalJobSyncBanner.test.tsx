import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { LocalJobSyncBanner } from "./LocalJobSyncBanner";

const api = vi.hoisted(() => ({ isLocal: vi.fn(() => true), getLocalJobSync: vi.fn(), refreshLocalJobs: vi.fn() }));
vi.mock("../api", () => api);
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); api.isLocal.mockReturnValue(true); });

it("shows progress, refreshes jobs after a source completes, and retries failures", async () => {
  vi.useFakeTimers();
  const source = { slug: "one", name: "测试官方招聘", checked_at: 0, status: "running" };
  api.getLocalJobSync.mockResolvedValueOnce({ ok: true, state: "running", completed: 0, total_sources: 2, failed: 0, updated_at: Date.now() / 1000, sources: [source] })
    .mockResolvedValue({ ok: true, state: "partial", completed: 1, total_sources: 2, failed: 1, updated_at: Date.now() / 1000, sources: [{ ...source, status: "succeeded", checked_at: 1 }, { ...source, slug: "bad", status: "failed" }] });
  api.refreshLocalJobs.mockResolvedValue({ ok: true, queued: true });
  const updated = vi.fn();
  await act(async () => { render(<LocalJobSyncBanner onUpdated={updated} />); });
  expect(screen.getByRole("status").textContent).toContain("已完成 0/2");
  expect((screen.getByRole("button", { name: "更新岗位" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(updated).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status").textContent).toContain("1 个来源成功");
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "重试采集" })); });
  expect(api.refreshLocalJobs).toHaveBeenCalledTimes(1);
  expect(screen.getByText("已请求更新，后台将开始处理。")).toBeTruthy();
});

it("does not poll or offer local crawling on the hosted build", () => {
  api.isLocal.mockReturnValue(false);
  render(<LocalJobSyncBanner onUpdated={vi.fn()} />);
  expect(api.getLocalJobSync).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("官方岗位采集")).toBeNull();
});

it("distinguishes shared snapshots from the last upstream crawl result", async () => {
  api.getLocalJobSync.mockResolvedValue({ ok: true, mode: "shared", state: "completed", completed: 1,
    total_sources: 1, failed: 0, updated_at: Date.now() / 1000, published_at: "2026-10-29T00:00:00Z",
    sources: [{ slug: "one", name: "测试来源", status: "succeeded", checked_at: 1, upstream_status: "failed" }] });
  await act(async () => { render(<LocalJobSyncBanner onUpdated={vi.fn()} />); });
  expect(screen.getByRole("status").textContent).toContain("公共岗位目录已同步");
  expect(screen.getByText(/每 24 小时/)).toBeTruthy();
  expect(screen.getByText(/服务器与本机仍保留/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "重试同步" })).toBeTruthy();
});
