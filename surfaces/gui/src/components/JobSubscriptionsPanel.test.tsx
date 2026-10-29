import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobSubscriptionsPanel } from "./JobSubscriptionsPanel";
const request = vi.fn(async (path: string) => path.endsWith("channels") ? [{id: "channel",name: "测试群",kind: "wecom"}] : path === "job-subscriptions" ? [{id: "sub",title: "北京产品",condition: {all: []},channel_ids: ["channel"],send_time: "09:00",version: 1,enabled: false}] : {});
vi.mock("../api", () => ({ careerCatalogRequest: (...args: [string]) => request(...args) }));
describe("job subscriptions", () => {
  it("shows destination and time before explicit activation", async () => {
    render(<JobSubscriptionsPanel condition={{all: []}} onClose={() => {}} />);
    expect(await screen.findByText("北京产品")).toBeTruthy();
    expect(screen.getByText(/09:00/)).toBeTruthy();
    expect(screen.getAllByText(/测试群/).length).toBeGreaterThan(0);
    expect(request.mock.calls.some(c => c[0].includes("activate"))).toBe(false);
    fireEvent.click(screen.getByRole("button", {name: "确认启用"}));
    expect(request).toHaveBeenCalledWith("job-subscriptions/sub/activate", {version: 1, confirmed: true});
  });
});
