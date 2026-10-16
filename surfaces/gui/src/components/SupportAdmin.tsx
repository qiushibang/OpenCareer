import { useEffect, useState } from "react";
import { supportRequest, type SupportFeedback } from "../api";
import { SupportOperations } from "./SupportOperations";

type Issue = SupportFeedback & { user_id?: string | null };
const states: Record<string, string> = { open: "待处理", in_progress: "处理中", resolved: "已修复", declined: "不采纳", merged: "已合并" };

export function SupportAdmin() {
  const [operations, setOperations] = useState(false);
  const [filter, setFilter] = useState("");
  const [kind, setKind] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<Issue[]>([]);
  const [selected, setSelected] = useState<Issue>();
  const [diagnostic, setDiagnostic] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState("open");
  const [reply, setReply] = useState("");
  const [target, setTarget] = useState("");
  const [confirmMerge, setConfirmMerge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const load = async () => {
    try {
      const query = new URLSearchParams({ offset: String(offset), ...(filter ? { status: filter } : {}), ...(kind ? { kind } : {}) });
      const data = await supportRequest<{ feedback: Issue[] }>(`admin/feedback?${query}`);
      setItems(data.feedback);
    } catch { setItems([]); setMessage("无法读取问题中心，请检查权限或稍后重试。"); }
  };
  useEffect(() => { void load(); }, [filter, kind, offset]);
  const view = async (id: string) => {
    try {
      const data = await supportRequest<{ feedback: Issue; diagnostic: Record<string, unknown> | null }>(`admin/feedback/${id}`);
      setSelected(data.feedback); setStatus(data.feedback.status); setReply(data.feedback.reply);
      setDiagnostic(data.diagnostic); setTarget(""); setConfirmMerge(false); setMessage("");
    } catch { setMessage("无法读取此问题，请刷新后重试。"); }
  };
  const save = async (merge = false) => {
    if (!selected || busy) return;
    setBusy(true); setMessage("");
    try {
      const data = await supportRequest<{ feedback: Issue }>(`admin/feedback/${selected.id}${merge ? "/merge" : ""}`,
        merge ? { target_id: target, expected_updated_at: selected.updated_at } : { status, reply, expected_updated_at: selected.updated_at }, merge ? "POST" : "PATCH");
      setSelected({ ...selected, ...data.feedback }); setStatus(data.feedback.status); setReply(data.feedback.reply);
      setMessage(merge ? "重复问题已合并。" : "处理结果已保存。"); setConfirmMerge(false); await load();
    } catch { setMessage("保存未成功，内容仍保留。请刷新确认是否已由其他管理员处理，再重试。"); }
    finally { setBusy(false); }
  };
  return <div className="space-y-4">
    <div className="flex gap-2"><button className="btn" onClick={() => setOperations(false)}>反馈问题</button><button className="btn" onClick={() => setOperations(true)}>系统提醒与管理记录</button></div>
    {operations ? <SupportOperations /> : <>
    <p className="text-sm text-muted">仅支持反馈与脱敏诊断，不提供用户简历、私密对话或服务器文件访问。回复会展示给用户，请勿包含其他用户信息。</p>
    <div className="flex flex-wrap gap-2"><label>状态<select className="input ml-2" value={filter} onChange={(e) => { setOffset(0); setFilter(e.target.value); }}><option value="">全部</option>{Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>类型<select className="input ml-2" value={kind} onChange={(e) => { setOffset(0); setKind(e.target.value); }}><option value="">全部</option><option value="bug">功能故障</option><option value="suggestion">体验建议</option><option value="other">其他</option></select></label>
      <button className="btn" onClick={() => void load()}>刷新问题</button></div>
    {selected ? <section className="border border-line rounded-xl p-4 space-y-3">
      <button className="btn" onClick={() => setSelected(undefined)}>返回列表</button>
      <p className="text-xs break-all text-muted">编号：{selected.id} · {selected.user_id || "匿名反馈"}</p>
      <p className="whitespace-pre-wrap break-words">{selected.description}</p>
      {diagnostic ? <dl className="text-xs grid grid-cols-2 gap-2 border-y border-line py-3">{["kind", "page", "status", "source", "release", "duration_ms"].map((key) => <div key={key}><dt className="text-muted">{key}</dt><dd>{String(diagnostic[key] ?? "—")}</dd></div>)}</dl> : <p className="text-xs text-muted">未关联诊断或记录已过期。</p>}
      <label className="block">处理状态<select className="input ml-2" value={status} disabled={busy || status === "merged"} onChange={(e) => setStatus(e.target.value)}>{Object.entries(states).map(([value, label]) => <option key={value} value={value} disabled={value === "merged"}>{label}</option>)}</select></label>
      <label className="block">回复用户<textarea className="input w-full mt-1 min-h-24" maxLength={1200} value={reply} disabled={busy || status === "merged"} onChange={(e) => setReply(e.target.value)} /></label>
      <button className="btn primary" disabled={busy || status === "merged"} onClick={() => void save()}>保存处理结果</button>
      <div className="border-t border-line pt-3"><label className="block text-sm">重复问题的主编号<input className="input w-full mt-1" maxLength={32} value={target} disabled={busy} onChange={(e) => { setTarget(e.target.value.trim()); setConfirmMerge(false); }} /></label>
        {confirmMerge ? <div className="mt-2 text-sm"><p>合并后在主问题中统一处理，不向用户显示另一条反馈正文。</p><button className="btn mt-2" disabled={busy} onClick={() => void save(true)}>确认合并</button></div> : <button className="btn mt-2" disabled={busy || !/^[0-9a-f]{32}$/.test(target) || target === selected.id || status === "merged"} onClick={() => setConfirmMerge(true)}>合并重复问题</button>}
      </div>
    </section> : <>
      {items.length === 0 && <p className="text-sm text-muted">暂无符合条件的问题。</p>}
      {items.map((item) => <article key={item.id} className="rounded-xl border border-line p-4"><p className="text-xs text-muted mb-2">{states[item.status]} · {item.user_id || "匿名反馈"}</p><p className="whitespace-pre-wrap break-words">{item.description}</p><button className="btn mt-3" onClick={() => void view(item.id)}>查看问题</button></article>)}
      <div className="flex gap-2"><button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>上一页</button><button className="btn" disabled={items.length < 50} onClick={() => setOffset(offset + 50)}>下一页</button></div>
    </>}
    {message && <p role="status" className="text-sm break-words">{message}</p>}
    </>}
  </div>;
}
