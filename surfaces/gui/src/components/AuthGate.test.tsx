import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  alpha: true,
  local: false,
  logout: vi.fn(async () => undefined),
  redirectToLogin: vi.fn(),
  session: {
    configured: true,
    authenticated: false,
    user: null,
  } as any,
}));

vi.mock("../api", () => ({
  isAlpha: () => mocks.alpha,
  isLocal: () => mocks.local,
  getHostedAuthSession: vi.fn(async () => mocks.session),
  logoutHostedAuth: mocks.logout,
  redirectToHostedLogin: mocks.redirectToLogin,
  hostedLoginUrl: (returnTo: string) =>
    `/_openworker/auth/login?return_to=${encodeURIComponent(returnTo)}`,
}));

import { AuthGate } from "./AuthGate";

describe("AuthGate", () => {
  beforeEach(() => {
    mocks.alpha = true;
    mocks.local = false;
    mocks.session = {
      configured: true,
      authenticated: false,
      user: null,
    };
    mocks.logout.mockClear();
    mocks.redirectToLogin.mockClear();
    window.history.replaceState({}, "", "/career/jobs?tab=favorites");
  });

  afterEach(cleanup);

  it("shows the hosted sign-in page to an anonymous cloud visitor", async () => {
    render(
      <AuthGate>
        <div>private product</div>
      </AuthGate>,
    );

    const link = await screen.findByRole("link", { name: "登录 OpenCareer" });
    expect(link.getAttribute("href")).toContain("%2Fcareer%2Fjobs%3Ftab%3Dfavorites");
    expect(screen.queryByText("private product")).toBeNull();
  });

  it("recovers from a failed callback without returning to the error URL", async () => {
    window.history.replaceState({}, "", "/?auth_error=login_failed");

    render(
      <AuthGate>
        <div>private product</div>
      </AuthGate>,
    );

    const link = await screen.findByRole("link", { name: "重新登录" });
    expect(screen.getByText("登录没有完成")).toBeTruthy();
    expect(link.getAttribute("href")).toContain("return_to=%2F");
    expect(link.getAttribute("href")).not.toContain("auth_error");
    expect(screen.queryByText("private product")).toBeNull();
  });

  it("renders private product content after the server session is authenticated", async () => {
    mocks.session = {
      configured: true,
      authenticated: true,
      user: { id: "usr_1", email: "alice@example.com", display_name: "Alice" },
    };

    render(
      <AuthGate>
        <div>private product</div>
      </AuthGate>,
    );

    await waitFor(() => expect(screen.getByText("private product")).toBeTruthy());
    screen.getByRole("button", { name: "退出登录" }).click();
    await waitFor(() => expect(mocks.logout).toHaveBeenCalledOnce());
    expect(mocks.redirectToLogin).toHaveBeenCalledWith(
      "/career/jobs?tab=favorites",
    );
    expect(await screen.findByRole("link", { name: "登录 OpenCareer" })).toBeTruthy();
    expect(screen.queryByText("private product")).toBeNull();
  });

  it("does not add hosted login to the local desktop application", () => {
    mocks.alpha = false;
    render(
      <AuthGate>
        <div>desktop product</div>
      </AuthGate>,
    );

    expect(screen.getByText("desktop product")).toBeTruthy();
  });

  it("opens the isolated local web app without a hosted account", () => {
    mocks.local = true;
    mocks.session = { configured: false, authenticated: false, user: null };
    render(<AuthGate><div>local career workspace</div></AuthGate>);
    expect(screen.getByText("local career workspace")).toBeTruthy();
    expect(screen.queryByText("登录服务正在准备中")).toBeNull();
  });
});
