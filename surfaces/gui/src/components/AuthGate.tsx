import { useCallback, useEffect, useState, type ReactNode } from "react";

import {
  getHostedAuthSession,
  hostedLoginUrl,
  isAlpha,
  isLocal,
  logoutHostedAuth,
  redirectToHostedLogin,
  type HostedAuthSession,
} from "../api";

function FilingFooter() {
  const filingNumber = String(
    (import.meta as any).env?.VITE_ICP_NUMBER || "",
  ).trim();
  if (!filingNumber) return null;
  return (
    <a
      href="https://beian.miit.gov.cn/"
      target="_blank"
      rel="noreferrer"
      className="fixed bottom-3 right-4 z-50 text-[11px] text-faint hover:text-ink"
    >
      {filingNumber}
    </a>
  );
}

function FullPage({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-paper text-ink flex items-center justify-center px-5 py-10">
      <section className="w-full max-w-[430px] rounded-[28px] border border-line bg-panel px-8 py-9 shadow-[0_22px_70px_rgba(21,31,48,0.10)]">
        {children}
      </section>
      <FilingFooter />
    </main>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const hosted = isAlpha() && !isLocal();
  const [session, setSession] = useState<HostedAuthSession | null>(null);
  const [failed, setFailed] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);

  const refresh = useCallback(async () => {
    setFailed(false);
    try {
      setSession(await getHostedAuthSession());
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    if (hosted) void refresh();
  }, [hosted, refresh]);

  if (!hosted) return <>{children}</>;
  const callbackFailed = new URLSearchParams(window.location.search).get("auth_error") === "login_failed";
  const returnTo = callbackFailed
    ? `${window.location.pathname}${window.location.hash}`
    : `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (session?.authenticated) {
    const logout = async () => {
      setLogoutBusy(true);
      setLogoutFailed(false);
      try {
        await logoutHostedAuth();
        setSession({ configured: true, authenticated: false, user: null });
        redirectToHostedLogin(returnTo);
      } catch {
        setLogoutFailed(true);
      } finally {
        setLogoutBusy(false);
      }
    };
    return (
      <>
        {children}
        <div className="fixed right-4 top-3 z-50 flex items-center gap-2 rounded-xl border border-line bg-panel/95 px-3 py-2 text-xs shadow-xs backdrop-blur">
          <span className="max-w-40 truncate text-muted">
            {session.user?.display_name || session.user?.email || "已登录"}
          </span>
          <button
            type="button"
            onClick={() => void logout()}
            disabled={logoutBusy}
            className="font-semibold text-ink hover:text-accent disabled:opacity-50"
          >
            {logoutBusy ? "正在退出…" : logoutFailed ? "退出失败，请重试" : "退出登录"}
          </button>
        </div>
        <FilingFooter />
      </>
    );
  }

  if (failed) {
    return (
      <FullPage>
        <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">
          OpenCareer
        </p>
        <h1 className="mt-4 text-2xl font-semibold">暂时无法确认登录状态</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          请检查网络连接后重试。你的对话和简历不会因此被修改。
        </p>
        <button
          type="button"
          onClick={() => void refresh()}
          className="mt-7 w-full rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-paper"
        >
          重新检查
        </button>
      </FullPage>
    );
  }

  if (session === null) {
    return (
      <FullPage>
        <p className="text-center text-sm text-muted">正在检查登录状态…</p>
      </FullPage>
    );
  }

  if (!session.configured) {
    return (
      <FullPage>
        <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">
          OpenCareer
        </p>
        <h1 className="mt-4 text-2xl font-semibold">登录服务正在准备中</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          当前入口尚未开放，请稍后再来。现有内测数据仍保持隔离保存。
        </p>
      </FullPage>
    );
  }

  if (callbackFailed) {
    return (
      <FullPage>
        <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">
          OpenCareer
        </p>
        <h1 className="mt-4 text-2xl font-semibold">登录没有完成</h1>
        <p className="mt-3 text-sm leading-6 text-muted">
          本次登录凭据可能已过期，或者回调页面被重复打开。请重新登录；你的账号数据没有被修改。
        </p>
        <a
          href={hostedLoginUrl(returnTo)}
          className="mt-7 flex w-full items-center justify-center rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-paper transition-opacity hover:opacity-90"
        >
          重新登录
        </a>
      </FullPage>
    );
  }

  return (
    <FullPage>
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-xl font-bold text-white">
        OC
      </div>
      <p className="mt-7 text-xs font-semibold tracking-[0.16em] text-accent uppercase">
        OpenCareer
      </p>
      <h1 className="mt-3 text-[28px] font-semibold leading-tight">你的 AI 求职工作台</h1>
      <p className="mt-4 text-sm leading-6 text-muted">
        登录后继续管理你的对话、简历、收藏岗位与申请进度。每位用户的数据独立保存。
      </p>
      <a
        href={hostedLoginUrl(returnTo)}
        className="mt-8 flex w-full items-center justify-center rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-paper transition-opacity hover:opacity-90"
      >
        登录 OpenCareer
      </a>
      <p className="mt-4 text-center text-[11px] leading-5 text-faint">
        登录过程由 Authing 提供身份认证，OpenCareer 不保存你的登录密码。
      </p>
    </FullPage>
  );
}
