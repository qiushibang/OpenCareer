import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it("reports transport failure using fixed metadata only and never recursively retries diagnostics", async () => {
  const request = vi.fn(async (url: RequestInfo | URL) => {
    if (String(url).includes("/v1/support/diagnostics")) throw new Error("fictional-private-report-secret");
    throw new Error("fictional-private-network-secret");
  });
  vi.stubGlobal("fetch", request);
  const { getHealth } = await import("./api");
  await expect(getHealth()).rejects.toThrow();
  await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
  const report = request.mock.calls[1] as unknown as [string, RequestInit];
  expect(JSON.parse(String(report[1].body))).toEqual({ kind: "network_error", page: "unknown" });
  expect(JSON.stringify(request.mock.calls)).not.toContain("fictional-private");
  await expect(getHealth()).rejects.toThrow();
  expect(request).toHaveBeenCalledTimes(3); // rate limited, no second report
});
