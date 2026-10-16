import { useEffect, useRef, useState } from "react";
import { getHostedAuthSession, isAlpha, supportRequest, type SupportFeedback } from "../api";
import { SUPPORT_FAULT, SUPPORT_OPEN, SUPPORT_RESET, safeDiagnosticId } from "../supportFault";
import { SupportAdmin } from "./SupportAdmin";

const nonce = () => crypto.randomUUID().replace(/-/g, "");
const statuses: Record<string, string> = { open: "待处理", in_progress: "处理中", resolved: "已修复", declined: "不采纳", merged: "已合并" };

export function SupportPortal() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("new");
  const [authenticated, setAuthenticated] = useState(!isAlpha());
  const [admin, setAdmin] = useState(false);
  const [authReady, setAuthReady] = useState(!isAlpha());
  const [kind, setKind] = useState<"bug" | "suggestion" | "other">("bug");
  const [description, setDescription] = useState("");
  const [requestId, setRequestId] = useState<string>();
  const [candidateId, setCandidateId] = useState<string>();
  const lastFault = useRef<string>();
  const draftNonce = useRef(nonce());
  const generation = useRef(0);
  const identity = useRef<string>();
  const dialog = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<SupportFeedback[]>([]);
  const [offset, setOffset] = useState(0);
  const listSequence = useRef(0);

  useEffect(() => {
    const onFault = (event: Event) => { lastFault.current = safeDiagnosticId((event as CustomEvent).detail?.requestId); };
    const onOpen = (event: Event) => {
      setRequestId(undefined); setCandidateId(safeDiagnosticId((event as CustomEvent).detail?.requestId) || lastFault.current);
      setTab("new"); setAuthReady(!isAlpha()); setOpen(true);
    };
    const reset = () => {
      generation.current += 1; setOpen(false); setDescription(""); setItems([]);
      setMessage(""); setBusy(false); setRequestId(undefined); lastFault.current = undefined;
      setCandidateId(undefined);
      identity.current = undefined; draftNonce.current = nonce(); setAuthenticated(!isAlpha());
      setAdmin(false); setAuthReady(!isAlpha());
    };
    window.addEventListener(SUPPORT_FAULT, onFault);
    window.addEventListener(SUPPORT_OPEN, onOpen);
    window.addEventListener(SUPPORT_RESET, reset);
    return () => {
      window.removeEventListener(SUPPORT_FAULT, onFault); window.removeEventListener(SUPPORT_OPEN, onOpen);
      window.removeEventListener(SUPPORT_RESET, reset);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const focused = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    const current = generation.current;
    const capabilities = async () => {
      const capabilityGeneration = generation.current;
      try {
        const data = await supportRequest<{ admin: boolean }>("capabilities");
        if (generation.current === capabilityGeneration) setAdmin(data.admin === true);
      } catch { if (generation.current === capabilityGeneration) setAdmin(false); }
    };
    if (isAlpha()) void getHostedAuthSession().then((session) => {
      if (current !== generation.current) return;
      const next = session.user?.id || "anonymous";
      if (identity.current && identity.current !== next) {
        generation.current += 1;
        setDescription(""); setItems([]); setMessage(""); setRequestId(undefined); lastFault.current = undefined; draftNonce.current = nonce();
        setCandidateId(undefined);
        setAdmin(false); setBusy(false); setTab("new");
      }
      identity.current = next; setAuthenticated(session.authenticated); setAuthReady(true);
      if (session.authenticated) void capabilities();
    }).catch(() => { if (current === generation.current) { setAuthenticated(false); setAuthReady(true); setAdmin(false); } });
    else void capabilities();
    return () => focused?.focus();
  }, [open]);

  useEffect(() => {
    if (!open || !authReady || !authenticated || !candidateId) return;
    const current = generation.current;
    let cancelled = false;
    void supportRequest<{ diagnostic: { request_id: string } }>(`diagnostics/${candidateId}`).then((data) => {
      if (!cancelled && current === generation.current && data.diagnostic?.request_id === candidateId) setRequestId(candidateId);
    }).catch(() => { if (!cancelled && current === generation.current) setRequestId(undefined); });
    return () => { cancelled = true; };
  }, [open, authReady, authenticated, candidateId]);

  const loadItems = async (pageOffset = 0) => {
    const current = generation.current;
    const sequence = ++listSequence.current;
    try {
      const data = await supportRequest<{ feedback: SupportFeedback[] }>(`feedback?offset=${pageOffset}`);
      if (current === generation.current && sequence === listSequence.current) { setItems(data.feedback); setOffset(pageOffset); }
    } catch { if (current === generation.current) setMessage("暂时无法读取反馈，请重试。"); }
  };
  const submit = async () => {
    if (busy || !authReady) return;
    const current = generation.current;
    setBusy(true); setMessage("");
    try {
      const body = { kind, description, nonce: draftNonce.current, ui_release: import.meta.env.VITE_OPENCAR_RELEASE || "unknown", ...(authenticated && requestId ? { request_id: requestId } : {}) };
      const data = await supportRequest<{ feedback: SupportFeedback }>(authenticated ? "feedback" : "anonymous-feedback", body);
      if (current !== generation.current) return;
      setMessage(`反馈已收到，编号：${data.feedback.id}`); setDescription(""); draftNonce.current = nonce();
    } catch { if (current === generation.current) setMessage("提交未成功，草稿仍保留，请稍后重试。若附带排查编号已过期，可以移除后再提交。"); }
    finally { if (current === generation.current) setBusy(false); }
  };

  return <>
    <button className="support-launcher btn" onClick={() => { setRequestId(undefined); setCandidateId(lastFault.current); setAuthReady(!isAlpha()); setOpen(true); }}>帮助与反馈</button>
    {open && <div className="support-backdrop" onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <div ref={dialog} role="dialog" aria-modal="true" aria-label="帮助与反馈" tabIndex={-1} className="support-dialog" onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
        if (event.key === "Tab") {
          const nodes = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),textarea:not(:disabled),select:not(:disabled),input:not(:disabled),a[href]');
          if (!nodes?.length) return;
          const first = nodes[0], last = nodes[nodes.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      }}>
        <div className="flex items-center justify-between gap-3 mb-4"><h2 className="text-lg">帮助与反馈</h2><button className="btn" aria-label="关闭反馈" onClick={() => setOpen(false)}>关闭</button></div>
        <div className="flex gap-2 mb-4"><button className="btn" onClick={() => setTab("new")}>提交问题</button>
          {authenticated && authReady && <button className="btn" onClick={() => { setTab("mine"); setMessage(""); void loadItems(); }}>我的反馈</button>}
          {admin && authReady && <button className="btn" onClick={() => setTab("admin")}>问题中心</button>}
        </div>
        {tab === "new" ? <>
          <p className="text-sm text-muted mb-4">请描述操作步骤、实际结果与期望结果。不要填写密钥、验证码、完整简历或私密对话；不会自动采集这些内容。</p>
          {!authenticated && <p className="text-sm text-muted mb-3">未登录也可以提交，但匿名反馈不会绑定账号，也无法在账号内追踪回复。</p>}
          <label className="block mb-3">反馈类型<select className="input w-full mt-1" disabled={busy} value={kind} onChange={(event) => { setKind(event.target.value as typeof kind); draftNonce.current = nonce(); }}><option value="bug">功能故障</option><option value="suggestion">体验建议</option><option value="other">其他</option></select></label>
          <label className="block">问题描述<textarea className="input w-full mt-1 min-h-36" maxLength={2000} disabled={busy} value={description} onChange={(event) => { setDescription(event.target.value); draftNonce.current = nonce(); }} /></label>
          <p className="text-xs text-muted text-right mt-1">{description.length} / 2000</p>
          {authenticated && requestId && <div className="text-xs text-muted mt-3 break-all">附带脱敏排查编号：{requestId}<button className="btn ml-2" onClick={() => { setCandidateId(undefined); setRequestId(undefined); }}>移除</button></div>}
          <button className="btn primary mt-4" disabled={busy || !authReady || description.trim().length < 5} onClick={() => void submit()}>{busy ? "正在提交…" : "提交反馈"}</button>
        </> : tab === "admin" && admin && authReady ? <SupportAdmin /> : <div className="space-y-3"><button className="btn" onClick={() => void loadItems(offset)}>刷新反馈</button>
          {items.length === 0 && <p className="text-sm text-muted">暂无反馈。</p>}
          {items.map((item) => <article key={item.id} className="rounded-xl border border-line p-4"><p className="text-xs text-muted mb-2">{statuses[item.status] || "待处理"} · {new Date(item.created_at / 1000).toLocaleDateString()}</p><p className="whitespace-pre-wrap break-words">{item.description}</p>{item.reply && <p className="mt-3 pt-3 border-t border-line whitespace-pre-wrap break-words">回复：{item.reply}</p>}<p className="text-xs text-muted mt-2 break-all">编号：{item.id}</p></article>)}
          <div className="flex gap-2"><button className="btn" disabled={offset === 0} onClick={() => void loadItems(Math.max(0, offset - 50))}>上一页</button><button className="btn" disabled={items.length < 50 || offset >= 450} onClick={() => void loadItems(offset + 50)}>下一页</button></div>
        </div>}
        {message && <p role="status" className="text-sm mt-4 break-all">{message}</p>}
      </div>
    </div>}
  </>;
}
