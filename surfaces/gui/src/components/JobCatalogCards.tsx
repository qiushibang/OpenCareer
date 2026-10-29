import { useEffect, useState } from "react";
import { careerCatalogRequest, type CatalogResult } from "../api";

export function JobCatalogCards({preview}: {preview?: string}) {
  const [result, setResult] = useState<CatalogResult | null>(null);
  const [error, setError] = useState("");
  const cleaned = (preview || "").replace(/\\"/g, '"');
  const resultId = cleaned.match(/"result_id"\s*:\s*"([a-f0-9]{32})"/)?.[1];
  useEffect(() => {
    let live = true;
    if (resultId) careerCatalogRequest<CatalogResult>(`catalog/results/${resultId}`).then(r => { if (live) setResult(r); }).catch(e => { if (live) setError(e.message); });
    return () => {live = false;};
  }, [resultId]);
  if (!resultId) return null;
  if (error) return <p role="status" className="text-xs text-muted">{error}</p>;
  if (!result) return <p className="text-xs text-muted">正在读取岗位卡片…</p>;
  const openRadar = () => {
    sessionStorage.setItem("opencareer-catalog-query", JSON.stringify(result.query || {condition:result.applied_condition,semantic_query:result.semantic_query,include_inactive:result.include_inactive}));
    window.dispatchEvent(new CustomEvent("opencareer:catalog-open"));
  };
  return <section className="my-3 border border-line rounded-xl p-3 space-y-2" aria-label="对话岗位查询结果">
    <div className="flex items-center justify-between gap-2"><strong className="text-sm">{result.total === null ? `部分评估 · 已匹配 ${result.evaluated_matches}` : `匹配 ${result.total} 个岗位`}</strong><button className="text-accent text-sm" onClick={openRadar}>在岗位雷达查看</button></div>
    {result.warnings.map(w => <p key={w} className="text-xs text-warnInk">{w}</p>)}
    {result.jobs.map(j => <article key={j.id} className="rounded-lg bg-paper p-3 space-y-1">
      <strong className="text-sm">{j.title}</strong><p className="text-xs text-muted">{j.company.name} · {j.locations.join("、")} · 首次发现 {new Date(j.first_seen_at).toLocaleDateString("zh-CN", {timeZone:"Asia/Shanghai"})}</p>
      {j.reopened_at && <p className="text-xs text-muted">重新开放：{new Date(j.reopened_at).toLocaleDateString("zh-CN", {timeZone:"Asia/Shanghai"})}（本机观察，不算首次新增）</p>}
      <p className="text-xs text-muted">{j.match_evidence.slice(0,3).map(e => `${e.origin === "official" ? "官网" : e.origin === "model" ? "模型判断" : "规则识别"}：${e.text}`).join("；") || "按数据库字段匹配"}</p>
      {/^https:\/\//.test(j.source_url) && <a className="text-accent text-xs" href={j.source_url} target="_blank" rel="noreferrer">查看官网完整职位描述</a>}
    </article>)}
    {result.has_more && <button className="text-accent text-xs" onClick={openRadar}>更多结果与完整详情</button>}
  </section>;
}
