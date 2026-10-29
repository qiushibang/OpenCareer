import { useCallback, useEffect, useState, type FormEvent } from "react";
import { careerCatalogRequest, type CatalogCondition, type CatalogResult, type JobChannel, type JobDigestRun, type JobSubscription } from "../api";
import { CatalogQueryForm, describeCondition } from "./CatalogQueryForm";

const fieldClass = "rounded-lg border border-line bg-panel px-3 py-2 text-sm w-full";
const buttonClass = "rounded-lg border border-line px-3 py-2 text-sm hover:bg-paper disabled:opacity-50";
const labels: Record<string,string> = { sent: "已发送", failed: "失败", uncertain: "待确认（未自动重发）", running: "运行中", retryable: "等待重试", sending: "发送结果待确认" };

export function JobSubscriptionsPanel({condition, semanticQuery, today=false, includeInactive=false, onClose}: {condition: CatalogCondition; semanticQuery?: string | null; today?: boolean; includeInactive?: boolean; onClose: () => void}) {
  const [channels, setChannels] = useState<JobChannel[]>([]);
  const [subscriptions, setSubscriptions] = useState<JobSubscription[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("我的岗位日报");
  const [sendTime, setSendTime] = useState("09:00");
  const [chosen, setChosen] = useState<string[]>([]);
  const [kind, setKind] = useState("feishu");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [runs, setRuns] = useState<JobDigestRun[]>([]);
  const [preview, setPreview] = useState<CatalogResult | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editFilters, setEditFilters] = useState({condition,today,include_inactive:includeInactive,semantic_query:semanticQuery || null});
  const [showFilters, setShowFilters] = useState(false);
  const load = useCallback(async () => {
    const [c,s] = await Promise.all([careerCatalogRequest<JobChannel[]>("job-subscriptions/channels"), careerCatalogRequest<JobSubscription[]>("job-subscriptions")]);
    setChannels(c); setSubscriptions(s);
  }, []);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  const action = async (task: () => Promise<unknown>) => {
    setBusy(true); setError(""); setNotice("");
    try { await task(); await load(); } catch (e) { setError(e instanceof Error ? e.message : "操作失败"); } finally { setBusy(false); }
  };
  const saveChannel = (e: FormEvent) => {
    e.preventDefault(); void action(async () => {
      await careerCatalogRequest("job-subscriptions/channels", {name,kind,url,secret});
      setUrl(""); setSecret(""); setName(""); setNotice("渠道已保存。只有启用订阅或点击发送测试消息才会外发。");
    });
  };
  return <section role="dialog" aria-label="岗位订阅" aria-modal="true" className="fixed inset-0 z-50 bg-black/20 p-4 sm:p-10 overflow-auto">
    <div className="max-w-4xl mx-auto bg-panel border border-line rounded-2xl shadow-xl p-5 space-y-5">
      <div className="flex justify-between"><h2 className="text-lg font-semibold">岗位订阅</h2><button className={buttonClass} onClick={onClose}>关闭</button></div>
      <p className="text-sm text-muted">每天先刷新岗位，再发送匹配结果。无新增和零匹配也发送，新岗位单独标记。仅在本机服务运行时执行；重启后补查一次。</p>
      {error && <p role="alert" className="text-danger">{error}</p>}{notice && <p role="status" className="text-ok">{notice}</p>}
      <section className="border border-line rounded-xl p-4 space-y-3"><h3 className="font-medium">发送渠道</h3>
        <form onSubmit={saveChannel} className="grid sm:grid-cols-2 gap-3">
          <label>渠道名称<input className={fieldClass} required value={name} onChange={e => setName(e.target.value)} placeholder="例如：我的求职群" /></label>
          <label>机器人平台<select aria-label="机器人平台" className={fieldClass} value={kind} onChange={e => setKind(e.target.value)}><option value="feishu">飞书群机器人</option><option value="dingtalk">钉钉群机器人</option><option value="wecom">企业微信群机器人</option></select></label>
          <label>官方 Webhook 地址<input className={fieldClass} type="password" autoComplete="off" required value={url} onChange={e => setUrl(e.target.value)} /></label>
          {kind !== "wecom" ? <label>签名密钥（按机器人设置填写）<input className={fieldClass} type="password" autoComplete="new-password" value={secret} onChange={e => setSecret(e.target.value)} /></label> : <p className="text-xs text-muted">企业微信地址中的 key 即凭据，无须填写额外签名密钥。</p>}
          <button className={buttonClass} disabled={busy} type="submit">保存渠道</button>
          <p className="text-xs text-muted">凭据只保存在本机，不进入对话或公共岗位快照。请在平台启用官方安全校验。</p>
        </form>
        {channels.map(c => <div key={c.id} className="flex gap-2 items-center text-sm"><span className="flex-1">{c.name} · {c.kind}</span><button className={buttonClass} disabled={busy} onClick={() => void action(async () => { const result = await careerCatalogRequest<{status:string}>(`job-subscriptions/channels/${c.id}/test`, {confirmed:true}); setNotice(labels[result.status] || result.status); })}>发送测试消息</button><button className={buttonClass} disabled={busy} onClick={() => void action(() => careerCatalogRequest(`job-subscriptions/channels/${c.id}`, undefined, "DELETE"))}>移除渠道</button></div>)}
      </section>
      <section className="border border-line rounded-xl p-4 space-y-3"><h3 className="font-medium">{editing ? "修改订阅草稿" : "订阅当前筛选"}</h3>
        <p className="text-sm">{describeCondition(editFilters.condition)}{editFilters.today ? "；每天当天首次发现" : ""}</p>{editFilters.semantic_query && <p className="text-sm">语义判断：{editFilters.semantic_query}（每次最多100个候选）</p>}
        <button className={buttonClass} onClick={() => setShowFilters(v => !v)}>重新设置筛选条件</button>
        {showFilters && <CatalogQueryForm onSubmit={q => {setEditFilters({condition:q.condition || {all:[]},today:!!q.today,include_inactive:!!q.include_inactive,semantic_query:q.semantic_query || null});setShowFilters(false);}} />}
        <div className="grid sm:grid-cols-2 gap-3"><label>订阅名称<input className={fieldClass} value={title} onChange={e => setTitle(e.target.value)} /></label><label>每日发送时间（北京时间）<input className={fieldClass} type="time" value={sendTime} onChange={e => setSendTime(e.target.value)} /></label></div>
        <fieldset><legend className="text-sm">发送到</legend>{channels.map(c => <label key={c.id} className="mr-4 text-sm"><input type="checkbox" checked={chosen.includes(c.id)} onChange={e => setChosen(p => e.target.checked ? [...p,c.id] : p.filter(id => id !== c.id))} /> {c.name}</label>)}</fieldset>
        <button className={buttonClass} disabled={busy || !chosen.length} onClick={() => void action(async () => { await careerCatalogRequest("job-subscriptions", {title,...editFilters,channel_ids:chosen,send_time:sendTime,...(editing ? {subscription_id:editing} : {})});setEditing(null); setNotice("已生成停用草稿，请预览并确认启用。"); })}>保存订阅草稿</button>
      </section>
      <section className="space-y-3"><h3 className="font-medium">我的订阅</h3>{!subscriptions.length && <p className="text-sm text-muted">暂无订阅。也可以在对话里说“每天早上9点把北京产品岗位发到我的求职群”。</p>}
        {subscriptions.map(s => <article key={s.id} className="border border-line rounded-xl p-4 space-y-2">
          <h4 className="font-medium">{s.title}</h4><p className="text-sm">{describeCondition(s.condition)}</p>
          <p className="text-sm">每天 {s.send_time} · 北京时间 · {s.channel_ids.map(id => channels.find(c => c.id === id)?.name || "渠道已移除").join("、")} · {s.enabled ? "已启用" : "未启用"}</p>
          {s.next_run && s.enabled && <p className="text-xs text-muted">下次：{new Date(s.next_run).toLocaleString("zh-CN", {timeZone:"Asia/Shanghai"})}</p>}
          {s.semantic_query && <p className="text-xs text-muted">语义：{s.semantic_query}，候选超过上限时会明确提示不完整。</p>}
          <div className="flex flex-wrap gap-2"><button className={buttonClass} disabled={busy} onClick={() => void action(async () => setPreview(await careerCatalogRequest<CatalogResult>(`job-subscriptions/${s.id}/preview`, {})))}>预览匹配结果</button>
            <button className={buttonClass} disabled={busy} onClick={() => {setEditing(s.id);setTitle(s.title);setSendTime(s.send_time);setChosen(s.channel_ids);setEditFilters({condition:s.condition,today:!!s.today,include_inactive:!!s.include_inactive,semantic_query:s.semantic_query || null});setNotice("请修改上方草稿。保存修改会暂停原订阅，须重新确认启用。");}}>修改条件和时间</button>
            {s.enabled ? <button className={buttonClass} disabled={busy} onClick={() => void action(() => careerCatalogRequest(`job-subscriptions/${s.id}/pause`, {}))}>暂停</button> : <button className={buttonClass} disabled={busy} onClick={() => void action(() => careerCatalogRequest(`job-subscriptions/${s.id}/activate`, {version:s.version,confirmed:true}))}>确认启用</button>}
            <button className={buttonClass} disabled={busy} onClick={() => void action(async () => setRuns(await careerCatalogRequest<JobDigestRun[]>(`job-subscriptions/${s.id}/runs`)))}>运行记录</button></div>
        </article>)}
      </section>
      {preview && <section className="rounded-xl bg-paper p-3"><h3>匹配预览：{preview.total ?? `部分评估，已匹配 ${preview.evaluated_matches}`} 项</h3>{preview.jobs.map(j => <p key={j.id} className="text-sm py-1">{j.company.name} · {j.title} · {j.locations.join("、")}</p>)}</section>}
      {runs.map(r => <details key={r.id} className="rounded-xl bg-paper p-3"><summary>{new Date(r.started_at).toLocaleString("zh-CN")} · {labels[r.status] || r.status}</summary><p className="text-sm text-warnInk">{r.result.warning || r.result.error}</p><p className="text-xs">{r.result.partial ? "部分语义评估" : "完整匹配"} · 共 {r.result.jobs?.length || 0} 项</p>{r.deliveries.map(d => <p key={d.channel_id+d.part} className="text-xs">第 {d.part+1} 条 · {labels[d.status] || d.status}</p>)}<div className="max-h-80 overflow-auto">{r.result.jobs?.map(j => <p className="text-sm py-1" key={j.id}>{j.company.name} · {j.title} · {/^https:\/\//.test(j.source_url) && <a href={j.source_url} target="_blank" rel="noreferrer" className="text-accent">官网</a>}</p>)}</div></details>)}
    </div>
  </section>;
}
