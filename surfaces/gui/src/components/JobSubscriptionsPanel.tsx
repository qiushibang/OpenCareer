import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { careerCatalogRequest, type CatalogCondition, type CatalogResult, type JobChannel, type JobDigestRun, type JobSubscription } from "../api";
import type { SubscriptionChatContext } from "../subscriptionChat";
import { FeishuPairing } from "./FeishuPairing";
import { describeCondition } from "./CatalogQueryForm";

const fieldClass = "rounded-lg border border-line bg-panel px-3 py-2 text-sm w-full";
const buttonClass = "rounded-lg border border-line px-3 py-2 text-sm hover:bg-paper disabled:opacity-50";
type ChannelCheck={status:string;diagnostic?:{message:string;http_status?:number;platform_code?:number;request_id?:string}};
function channelNotice(result:ChannelCheck):string {const d=result.diagnostic;return d?`${d.message}${d.platform_code!==undefined?`（错误码 ${d.platform_code}）`:""}${d.request_id?` 排查编号：${d.request_id}`:""}`:labels[result.status]||result.status;}
const labels: Record<string,string> = { sent: "已发送", failed: "失败", uncertain: "待确认（未自动重发）", running: "运行中", retryable: "等待重试", sending: "发送结果待确认" };

export function JobSubscriptionsPanel({condition, semanticQuery, today=false, includeInactive=false, onClose, initialDraft, onConfigureInChat}: {onConfigureInChat?: (context:SubscriptionChatContext)=>void;initialDraft?:{title?:string;send_time?:string;subscription_id?:string;channel_ids?:string[]};condition: CatalogCondition; semanticQuery?: string | null; today?: boolean; includeInactive?: boolean; onClose: () => void}) {
  const [channels, setChannels] = useState<JobChannel[]>([]);
  const [subscriptions, setSubscriptions] = useState<JobSubscription[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(initialDraft?.title||"我的岗位日报");
  const [sendTime, setSendTime] = useState(initialDraft?.send_time||"09:00");
  const [chosen, setChosen] = useState<string[]>(initialDraft?.channel_ids || []);
  const [kind, setKind] = useState("feishu");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [manual,setManual]=useState(false);
  const [channelsOpen,setChannelsOpen]=useState(false);
  const channelsInitialized=useRef(false);
  const [runs, setRuns] = useState<JobDigestRun[]>([]);
  const [preview, setPreview] = useState<CatalogResult | null>(null);
  const [editing, setEditing] = useState<string | null>(initialDraft?.subscription_id || null);
  const [editFilters, setEditFilters] = useState({condition,today,include_inactive:includeInactive,semantic_query:semanticQuery || null});
  const [confirming, setConfirming] = useState(!!initialDraft);
  const restored = useRef(false);
  const configureInChat = (subscription?: JobSubscription) => {
    const filters = subscription || {condition, today, include_inactive:includeInactive, semantic_query:semanticQuery};
    const context = {condition:filters.condition,today:filters.today,include_inactive:filters.include_inactive,semantic_query:filters.semantic_query,
      ...(subscription ? {subscription_id:subscription.id,title:subscription.title,send_time:subscription.send_time,channel_ids:subscription.channel_ids} : {})};
    onConfigureInChat?.(context);
  };
  const load = useCallback(async () => {
    const [c,s] = await Promise.all([careerCatalogRequest<JobChannel[]>("job-subscriptions/channels"), careerCatalogRequest<JobSubscription[]>("job-subscriptions")]);
    setChannels(c); setSubscriptions(s);
    if(!channelsInitialized.current){channelsInitialized.current=true;setChannelsOpen(!c.length);}
    const draft=s.find(item=>item.id===initialDraft?.subscription_id);
    if(draft && !restored.current){
      restored.current=true;setEditing(draft.id);setTitle(draft.title);setSendTime(draft.send_time);setChosen(draft.channel_ids);
      setEditFilters({condition:draft.condition,today:!!draft.today,include_inactive:!!draft.include_inactive,semantic_query:draft.semantic_query||null});
      setConfirming(!draft.enabled);
    }
    if(c.length===1)setChosen(previous=>previous.length?previous:[c[0].id]);
  }, [initialDraft?.subscription_id]);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  const action = async (task: () => Promise<unknown>) => {
    setBusy(true); setError(""); setNotice("");
    try { await task(); await load(); } catch (e) { setError(e instanceof Error ? e.message : "操作失败"); } finally { setBusy(false); }
  };
  const saveChannel = (e: FormEvent) => {
    e.preventDefault(); void action(async () => {
      const saved=await careerCatalogRequest<JobChannel>("job-subscriptions/channels", {name:name.trim()||({feishu:"我的飞书群",dingtalk:"我的钉钉群",wecom:"我的企业微信群"}[kind]||"我的求职群"),kind,url:url.trim(),secret:secret.trim()});
      setChosen([saved.id]);setManual(false);
      setUrl(""); setSecret(""); setName(""); setNotice("渠道已保存。只有启用订阅或点击发送测试消息才会外发。");
    });
  };
  return <section role="dialog" aria-label="岗位订阅" aria-modal="true" className="oc-modal-backdrop oc-subscription-backdrop fixed inset-0 z-50">
    <div className="oc-modal oc-subscription-panel max-w-4xl mx-auto bg-panel border border-line rounded-2xl shadow-xl p-5 space-y-5">
      <div className="flex justify-between"><h2 className="text-lg font-semibold">岗位订阅</h2><button className={buttonClass} onClick={onClose}>关闭</button></div>
      <p className="text-sm text-muted">{/* 产品说明移至代码：每天先刷新岗位，再发送匹配结果。无新增和零匹配也发送，新岗位单独标记。仅在本机服务运行时执行；重启后补查一次。 */}每天推送，零匹配也发送。本地服务需保持运行。</p>
      {error && <p role="alert" className="text-danger">{error}</p>}{notice && <p role="status" className="text-ink rounded-lg bg-paper p-3">{notice}</p>}
      {onConfigureInChat && <section className="rounded-xl bg-paper p-4 flex flex-wrap items-center justify-between gap-4"><div><h3 className="font-medium">告诉 AI，你想每天收到什么岗位</h3><p className="text-sm text-muted mt-1">例如：每天早上 9 点，把字节跳动北京的产品岗发给我。</p></div><button className="rounded-lg bg-accent text-white px-4 py-2 text-sm" onClick={()=>configureInChat()}>在对话中创建订阅</button></section>}
      <details open={channelsOpen} onToggle={e=>setChannelsOpen(e.currentTarget.open)} className="border border-line rounded-xl p-4"><summary className="cursor-pointer font-medium">接收渠道{channels.length ? ` · 已连接 ${channels.length} 个` : " · 尚未连接"}</summary><div className="space-y-3 mt-3">
        <FeishuPairing hasConnected={channels.some(channel=>channel.kind==="feishu_app")} onConnected={channel=>{setChosen([channel.id]);void load().catch(e=>setError(e.message));setNotice("飞书扫码配置已保存，尚未验证发送能力。请先检查连接，再发送测试消息。");}}/>
        <details open={manual} onToggle={e=>setManual(e.currentTarget.open)}><summary className="cursor-pointer text-sm text-accent">其他平台／已有群机器人</summary><form onSubmit={saveChannel} className="grid sm:grid-cols-2 gap-3 mt-3">
          <label>机器人平台<select aria-label="机器人平台" className={fieldClass} value={kind} onChange={e=>setKind(e.target.value)}><option value="feishu">飞书群机器人</option><option value="dingtalk">钉钉群机器人</option><option value="wecom">企业微信群机器人</option></select></label>
          <div className="text-xs text-muted sm:col-span-2 space-y-1"><p>{/* 产品说明移至代码：① 打开目标群设置，添加自定义机器人。② 复制机器人地址，粘贴到下方即可；配置只需一次。 */}添加群机器人后，粘贴官方地址。</p><a className="text-accent underline" target="_blank" rel="noreferrer" href={{feishu:"https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot",dingtalk:"https://open.dingtalk.com/document/robots/custom-robot-access",wecom:"https://developer.work.weixin.qq.com/document/path/91770"}[kind]}>查看所选平台的官方配置图解</a>{/* 产品说明移至代码：企业微信与普通微信不同；当前不提供普通微信扫码绑定。钉钉暂使用官方群机器人地址。 */}</div>
          <label className="sm:col-span-2">官方 Webhook 地址<input aria-label="官方 Webhook 地址" className={fieldClass} type="password" autoComplete="off" required value={url} onChange={e=>setUrl(e.target.value)}/></label>
          <details className="sm:col-span-2"><summary className="cursor-pointer text-xs text-muted">名称与安全设置（按平台要求填写）</summary><div className="space-y-3 mt-3"><label>渠道名称（可选）<input className={fieldClass} value={name} onChange={e=>setName(e.target.value)} placeholder="不填则自动命名"/></label>{kind!=="wecom"&&<label>签名密钥<input className={fieldClass} type="password" autoComplete="new-password" value={secret} onChange={e=>setSecret(e.target.value)}/></label>}<p className="text-xs text-muted">{/* 产品说明移至代码：签名校验已开启时请填写密钥；地址和密钥仅在此录入，不发送到对话。 */}按平台要求填写；密钥仅存本机。</p></div></details>
          <button className={buttonClass} disabled={busy} type="submit">保存渠道</button>
        </form></details>
        {channels.map(c => <div key={c.id} className="flex gap-2 items-center text-sm"><span className="flex-1">{c.name} · {({feishu_app:"飞书扫码",feishu:"飞书群",dingtalk:"钉钉群",wecom:"企业微信群"}[c.kind]||c.kind)}</span>{c.kind==="feishu_app"&&<button className={buttonClass} disabled={busy} onClick={()=>void action(async()=>{setNotice(channelNotice(await careerCatalogRequest<ChannelCheck>(`job-subscriptions/channels/${c.id}/check`,{})));})}>检查连接（不发消息）</button>}<button className={buttonClass} disabled={busy} onClick={() => void action(async () => { const result = await careerCatalogRequest<ChannelCheck>(`job-subscriptions/channels/${c.id}/test`, {confirmed:true}); setNotice(channelNotice(result)); })}>发送测试消息</button><button className={buttonClass} disabled={busy} onClick={() => void action(() => careerCatalogRequest(`job-subscriptions/channels/${c.id}`, undefined, "DELETE"))}>移除渠道</button></div>)}
      </div></details>
      {confirming && <section className="border border-line rounded-xl p-4 space-y-3"><h3 className="font-medium">确认 AI 整理的订阅</h3>
        <p className="text-sm">{describeCondition(editFilters.condition)}{editFilters.today ? "；每天当天新增" : ""}</p>{editFilters.semantic_query && <p className="text-sm">语义判断：{editFilters.semantic_query}（每次最多100个候选）</p>}
        {onConfigureInChat && <button className={buttonClass} onClick={()=>configureInChat(editing ? subscriptions.find(s=>s.id===editing) : undefined)}>在对话中调整条件</button>}
        <div className="grid sm:grid-cols-2 gap-3"><label>订阅名称<input className={fieldClass} value={title} onChange={e => setTitle(e.target.value)} /></label><label>每日发送时间（北京时间）<input className={fieldClass} type="time" value={sendTime} onChange={e => setSendTime(e.target.value)} /></label></div>
        <fieldset><legend className="text-sm">发送到</legend>{channels.map(c => <label key={c.id} className="mr-4 text-sm"><input type="checkbox" checked={chosen.includes(c.id)} onChange={e => setChosen(p => e.target.checked ? [...p,c.id] : p.filter(id => id !== c.id))} /> {c.name}</label>)}</fieldset>
        <button className={buttonClass} disabled={busy || !chosen.length} onClick={() => void action(async () => { await careerCatalogRequest("job-subscriptions", {title,...editFilters,channel_ids:chosen,send_time:sendTime,...(editing ? {subscription_id:editing} : {})});setEditing(null);setConfirming(false); setNotice("已保存订阅条件，请在下方预览并确认启用。"); })}>保存订阅草稿</button>
      </section>}
      <section className="space-y-3"><h3 className="font-medium">我的订阅</h3>{!subscriptions.length && <p className="text-sm text-muted">{/* 产品说明移至代码：暂无订阅。也可以在对话里说“每天早上9点把北京产品岗位发到我的求职群”。 */}暂无订阅</p>}
        {subscriptions.map(s => <article key={s.id} className="border border-line rounded-xl p-4 space-y-2">
          <h4 className="font-medium">{s.title}</h4><p className="text-sm">{describeCondition(s.condition)}{s.today ? "；仅每天当天新增" : ""}{s.include_inactive ? "；包含已下线岗位" : ""}</p>
          <p className="text-sm">每天 {s.send_time} · 北京时间 · {s.channel_ids.map(id => channels.find(c => c.id === id)?.name || "渠道已移除").join("、")} · {s.enabled ? "已启用" : "未启用"}</p>
          {s.next_run && s.enabled && <p className="text-xs text-muted">下次：{new Date(s.next_run).toLocaleString("zh-CN", {timeZone:"Asia/Shanghai"})}</p>}
          {s.semantic_query && <p className="text-xs text-muted">语义：{s.semantic_query}，候选超过上限时会明确提示不完整。</p>}
          <div className="flex flex-wrap gap-2"><button className={buttonClass} disabled={busy} onClick={() => void action(async () => setPreview(await careerCatalogRequest<CatalogResult>(`job-subscriptions/${s.id}/preview`, {})))}>预览匹配结果</button>
            {onConfigureInChat && <button className={buttonClass} disabled={busy} onClick={()=>configureInChat(s)}>在对话中修改</button>}
            {s.enabled ? <button className={buttonClass} disabled={busy} onClick={() => void action(() => careerCatalogRequest(`job-subscriptions/${s.id}/pause`, {}))}>暂停</button> : <button className={buttonClass} disabled={busy} onClick={() => void action(() => careerCatalogRequest(`job-subscriptions/${s.id}/activate`, {version:s.version,confirmed:true}))}>确认启用</button>}
            <button className={buttonClass} disabled={busy} onClick={() => void action(async () => setRuns(await careerCatalogRequest<JobDigestRun[]>(`job-subscriptions/${s.id}/runs`)))}>运行记录</button></div>
        </article>)}
      </section>
      {preview && <section className="rounded-xl bg-paper p-3"><h3>匹配预览：{preview.total ?? `部分评估，已匹配 ${preview.evaluated_matches}`} 项</h3>{preview.jobs.map(j => <p key={j.id} className="text-sm py-1">{j.company.name} · {j.title} · {j.locations.join("、")}</p>)}</section>}
      {runs.map(r => <details key={r.id} className="rounded-xl bg-paper p-3"><summary>{new Date(r.started_at).toLocaleString("zh-CN")} · {labels[r.status] || r.status}</summary><p className="text-sm text-warnInk">{r.result.warning || r.result.error}</p><p className="text-xs">{r.result.partial ? "部分语义评估" : "完整匹配"} · 共 {r.result.jobs?.length || 0} 项</p>{r.deliveries.map(d => <p key={d.channel_id+d.part} className="text-xs">第 {d.part+1} 条 · {labels[d.status] || d.status}</p>)}<div className="max-h-80 overflow-auto">{r.result.jobs?.map(j => <p className="text-sm py-1" key={j.id}>{j.company.name} · {j.title} · {/^https:\/\//.test(j.source_url) && <a href={j.source_url} target="_blank" rel="noreferrer" className="text-accent">官网</a>}</p>)}</div></details>)}
    </div>
  </section>;
}
