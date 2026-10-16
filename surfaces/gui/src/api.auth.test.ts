import { afterEach, expect, it, vi } from "vitest";
import { getHealth, getInbox, redirectToHostedLogin, Session } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("authenticates REST and session WebSocket calls with the launch token", async () => {
  vi.stubGlobal("__COWORKER_API_TOKEN__", "launch-token");
  const request = vi.fn(async (_url: string, init?: RequestInit) => {
    expect(new Headers(init?.headers).get("X-OpenWorker-Token")).toBe("launch-token");
    return {
      ok: true,
      json: async () => ({
        status: "ok",
        default_workspace: null,
        model: "test-model",
      }),
    } as Response;
  });
  vi.stubGlobal("fetch", request);

  class FakeWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    readyState = FakeWebSocket.CONNECTING;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    send = vi.fn();

    constructor(
      public readonly url: string,
      public readonly protocols?: string | string[],
    ) {}
  }
  vi.stubGlobal("WebSocket", FakeWebSocket);

  await getHealth();
  expect(request).toHaveBeenCalledOnce();

  const session = new Session("s1", "/workspace", "code", { onEvent: vi.fn() });
  const socket = (session as unknown as { ws: FakeWebSocket }).ws;
  expect(socket.protocols).toEqual(["openworker", "launch-token"]);
});

it("rejects a redacted health response without a model", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: "ok" }),
    })),
  );

  await expect(getHealth()).rejects.toThrow("missing model");
});

it("normalizes an inbox response without items to an empty list", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      json: async () => ({ detail: "Unauthorized" }),
    })),
  );

  await expect(getInbox("session-1", "pending")).resolves.toEqual([]);
});

it("redirects hosted logout to the login flow with a safe return path", () => {
  const replace = vi.fn();
  vi.stubGlobal("location", { replace });

  redirectToHostedLogin("/career/jobs?tab=favorites");

  expect(replace).toHaveBeenCalledWith(
    "http://127.0.0.1:8765/auth/login?return_to=%2Fcareer%2Fjobs%3Ftab%3Dfavorites&prompt=login",
  );
});
