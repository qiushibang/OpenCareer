import { useEffect, useState } from "react";
import { Markdown } from "./Markdown";
import type { Item } from "../types";
import { careerCatalogRequest, getCareerJob, isLocal, type CatalogQuery, type CatalogResult } from "../api";

import { careerJobTypeLabel, careerJobTypeTone } from "../careerJobLabels";
import { Tag } from "./OcSelect";
import { Icon } from "./Icon";

const CARD_LIMIT = 10;
type Tool=Extract<Item,{kind:"tool"}>;
const KEYS=["condition","today","include_inactive","semantic_query","semantic_offset"];
// Only style a clearly marked list, leaving the assistant's prose and links intact.
function representativeJobs(text: string) {
  const lines = text.split(/\r?\n/);
  const heading = /^(?:#{1,6}\s+)?(?:\*\*)?代表岗位(?:[（(][^）)]*[）)])?(?:\*\*)?[：:]?$/;
  const item = /^\s{0,3}(?:\d+[.)]|[-*+])\s+/;
  let fence: string | undefined;
  for (let i = 0; i < lines.length; i++) {
    const marker = lines[i].match(/^\s{0,3}(`{3,}|~{3,})/)?.[1];
    if (marker) {
      if (!fence) fence = marker;
      else if (marker[0] === fence[0] && marker.length >= fence.length) fence = undefined;
      continue;
    }
    if (fence || !heading.test(lines[i].trim())) continue;
    let start = i + 1;
    while (start < lines.length && !lines[start].trim()) start++;
    let end = start;
    while (end < lines.length && item.test(lines[end])) {
      end++;
      if (!lines[end]?.trim() && item.test(lines[end + 1] ?? "")) end++;
    }
    if (end === start || lines[end]?.trim()) continue;
    return {
      before: lines.slice(0, i).join("\n").trim(),
      items: lines.slice(start, end).filter(line => item.test(line)).map(line => line.replace(item, "")),
      after: lines.slice(end).join("\n").trim(),
    };
  }
}

function toolArgs(tool?: Tool): Record<string, unknown> {
  try {
    const raw = typeof tool?.args === "string" ? JSON.parse(tool.args) : tool?.args;
    return raw && typeof raw === "object" ? raw : {};
  } catch { return {}; }
}

function catalogQuery(args: Record<string, unknown>): CatalogQuery {
  return Object.fromEntries(KEYS.filter(key => args[key] !== undefined).map(key => [key, args[key]]));
}

type CardRead<T> = {promise: Promise<T>; expires: number};
const catalogReads = new Map<string, CardRead<CatalogResult>>();
let pendingCatalogSearch: Promise<unknown> = Promise.resolve();
const detailReads = new Map<string, CardRead<Awaited<ReturnType<typeof getCareerJob>>>>();

// Navigation remounts the transcript. Reuse recent reads and coalesce concurrent
// requests so opening a historical answer does not crowd out interactive searches.
function readForCard<T>(cache: Map<string, CardRead<T>>, key: string, read: () => Promise<T>): Promise<T> {
  const cached = cache.get(key);
  if (cached && cached.expires > Date.now()) return cached.promise;
  const promise = read().catch(error => {
    if (cache.get(key)?.promise === promise) cache.delete(key);
    throw error;
  });
  cache.delete(key);
  cache.set(key, {promise, expires: Date.now() + 120_000});
  if (cache.size > 128) cache.delete(cache.keys().next().value!);
  return promise;
}

function loadCatalogCard(path: string, query?: CatalogQuery) {
  return readForCard(catalogReads, JSON.stringify([path,query]), () => {
    if (!query) return careerCatalogRequest<CatalogResult>(path);
    // Leave a request slot free for the interactive Radar and subscription UI.
    const next = pendingCatalogSearch.then(() => careerCatalogRequest<CatalogResult>(path,query));
    pendingCatalogSearch = next.catch(() => {});
    return next;
  });
}

function useJobCardResult(searches: Tool[], text?: string) {
  const [snapshot, setSnapshot] = useState<{tool: Tool; result: CatalogResult}>();
  const last = searches[0];
  useEffect(() => {
    if (!last) return;
    const listed = representativeJobs(text || "");
    const answerCount = listed?.before.match(/(?:[=＝]|共(?:找到|匹配)?|匹配到|找到)\s*(\d+)\s*(?:个|条|项)/)?.[1];
    const links = new Set(listed?.items.flatMap(item => [...item.matchAll(/\]\((https?:\/\/[^)\s]+)\)/g)].map(match => match[1])));
    let active = true;
    const read = async (tool: Tool) => {
      const preview = (tool.preview || "").replace(/\\"/g, '"');
      const id = preview.match(/"result_id"\s*:\s*"([a-f0-9]{32})"/)?.[1];
      const args = toolArgs(tool);
      const query = catalogQuery(args);
      let result = id ? await loadCatalogCard(`catalog/results/${id}`).catch(() => undefined) : undefined;
      // Never repeat a semantic search from the UI because it can call the model.
      if (!args.semantic_query && (id || args.condition) &&
          (!result || result.offset !== 0 || result.jobs.length < Math.min(result.total ?? 0, CARD_LIMIT))) {
        result = await loadCatalogCard("catalog/search", {...query, limit: CARD_LIMIT, offset: 0}).catch(() => result);
      }
      return {tool, result};
    };
    const load = async () => {
      const candidates = await Promise.all((links.size || answerCount ? searches : [last]).map(read));
      const available = candidates.flatMap(({tool,result}) => result ? [{
        tool, result,
        score: (answerCount && Number(answerCount) === result.total ? links.size + 1 : 0) +
          result.jobs.filter(job => links.has(job.source_url)).length,
      }] : []);
      const best = available.sort((a,b) => b.score - a.score)[0];
      if (!active || !best || (available.length > 1 && !best.score && listed)) return;
      if (links.size && !best.result.semantic_query && !toolArgs(best.tool).semantic_query &&
          best.result.has_more && [...links].some(url => !best.result.jobs.some(job => job.source_url === url))) {
        const page = await loadCatalogCard("catalog/search", {
          ...catalogQuery(toolArgs(best.tool)), ...best.result.query, limit: 100, offset: 0,
        }).catch(() => undefined);
        if (page?.total === best.result.total && page?.jobs.length) best.result = page;
      }
      if (!active) return;
      const order = new Map([...links].map((url, index) => [url, index]));
      const jobs = [...best.result.jobs].sort((a, b) =>
        (order.get(a.source_url) ?? Infinity) - (order.get(b.source_url) ?? Infinity)
      );
      setSnapshot({tool: best.tool, result: {...best.result, jobs}});
    };
    void load();
    return () => { active = false; };
  // The tool objects come from the transcript. The last tool identifies a completed turn.
  }, [last, text]);
  return snapshot && searches.includes(snapshot.tool) ? snapshot : undefined;
}

function jobExcerpt(detail?: Awaited<ReturnType<typeof getCareerJob>>["job"]) {
  const raw = detail?.description_raw || "";
  const duties = raw.split(/(?:职位|岗位|任职|任用|资格)要求[：:]?/)[0].split(/\r?\n/);
  const duty = duties.map(line => line.trim()).find(line => /^\d{1,2}[、.．)]\s*(?:负责|协助|参与|支持|主导|推动|开展|进行|跟进|制定|设计|搭建|建设|基于|与)/.test(line));
  const excerpt = (detail?.responsibilities?.find(line => line.trim()) || duty || raw)
    .replace(/^\s*(?:\d{1,2}[、.．)]\s*|职位描述[：:]\s*)/, "")
    .replace(/\s+/g, " ").trim();
  return excerpt.length > 140 ? excerpt.slice(0, 139) + "…" : excerpt;
}

function JobCardRow({job}: {job: CatalogResult["jobs"][number]}) {
  const [summary, setSummary] = useState("");
  useEffect(() => {
    let active = true;
    void readForCard(detailReads, job.id, () => getCareerJob(job.id)).then(({job: detail}) => {
      if (active) setSummary(jobExcerpt(detail));
    }).catch(() => {});
    return () => { active = false; };
  }, [job.id]);
  const location = job.locations.join("、") || job.location_raw;
  return <li className="career-job-row">
    <div className="career-job-row-main">
      <h4>{job.title || "未命名岗位"}</h4>
      <p className="career-job-meta">
        {location && <span className="career-job-location"><Icon name="target" size={12} />{location}</span>}
        {careerJobTypeTone(job.recruitment_type) && <Tag tone={careerJobTypeTone(job.recruitment_type)!}>{careerJobTypeLabel(job.recruitment_type)}</Tag>}
      </p>
      {summary && <p className="career-job-summary">{summary}</p>}
    </div>
    {/^https?:\/\//i.test(job.source_url) && <a className="career-job-apply" href={job.source_url} target="_blank" rel="noopener noreferrer">官网投递<Icon name="external" size={12} /></a>}
  </li>;
}

export function CareerQueryActions({tools, text}:{tools:Tool[]; text?:string}) {
  const [error,setError]=useState("");
  const searches=[...tools].reverse().filter(t=>t.name.endsWith("search_job_catalog")&&!["error","failed","running","pending"].includes(t.status)&&!(/"ok"\s*:\s*false/.test(t.preview||"")));
  const draft=[...tools].reverse().find(t=>t.name.endsWith("draft_job_subscription")&&!["error","failed","running","pending"].includes(t.status)&&!(/"ok"\s*:\s*false/.test(t.preview||"")));
  const subscription=draft||[...tools].reverse().find(t=>t.name.endsWith("list_job_subscriptions")&&!["error","failed","running","pending"].includes(t.status)&&!(/"ok"\s*:\s*false/.test(t.preview||"")));
  const snapshot = useJobCardResult(isLocal() ? searches : [], text);
  const search = snapshot?.tool ?? searches[0];
  const result = snapshot?.result;
  if(!isLocal() || (!search&&!subscription))return text ? <Markdown text={text}/> : null;
  const open=(subscribe:boolean)=>{
    try{
      // A draft states the user's complete intent. Later channel-list calls or
      // narrower example searches must not silently replace it in either link.
      const raw=toolArgs(subscribe ? draft || search : search);
      const query = !subscribe || !draft ? result?.query || catalogQuery(raw) : catalogQuery(raw);
      if(JSON.stringify(query).length>20000)throw new Error("筛选条件过长，请缩小范围后重试。");
      sessionStorage.setItem("opencareer-catalog-query",JSON.stringify(query));
      if(subscribe){
        let savedId=raw.subscription_id;
        // A tool-created draft already exists: reopen it instead of duplicating
        // it when the user confirms its delivery channel and time in the UI.
        if(subscription?.name.endsWith("draft_job_subscription")){
          try{const result=JSON.parse(subscription.preview||"{}");savedId=(result.data||result).id||savedId;}catch{/* Truncated previews cannot supply an identifier. */}
        }
        sessionStorage.setItem("opencareer-subscription-query",JSON.stringify({title:raw.title,send_time:raw.send_time,subscription_id:savedId,channel_ids:raw.channel_ids}));
      }
      window.dispatchEvent(new Event("opencareer:catalog-open"));
    }catch(e){setError((e as Error).message||"无法打开岗位雷达，请重试。");}
  };
  const jobs = search && text ? representativeJobs(text) : undefined;
  const count = result?.total ?? result?.evaluated_matches;
  const more = !!search && (count !== undefined ? count > CARD_LIMIT : (jobs?.items.length ?? 0) > CARD_LIMIT);
  const hasRows = result ? result.jobs.length > 0 : !!jobs;
  return <>
    {jobs?.before ? <Markdown text={jobs.before}/> : !jobs && text ? <Markdown text={text}/> : null}
    <section className="career-query-card" aria-label={hasRows ? "代表岗位" : "岗位查询操作"}>
      {hasRows && <>
        <div className="career-query-heading">
          <h3>{more || result?.semantic?.partial ? "代表岗位" : "匹配岗位"}</h3>
          {count !== undefined && <span>{result?.semantic?.partial ? "已评估匹配 " : "共 "}{count} 个</span>}
        </div>
        {result ? <ul className="career-query-list">{result.jobs.slice(0, CARD_LIMIT).map(job => <JobCardRow key={job.id} job={job}/>)}</ul>
          : <div className="career-query-list"><Markdown text={jobs!.items.slice(0, CARD_LIMIT).map(item => `- ${item}`).join("\n")}/></div>}
      </>}
      <div className="career-query-footer flex flex-wrap gap-2 items-center">
        {more && <button className="oc-btn oc-btn-primary oc-btn-sm" onClick={() => open(false)}>查看更多岗位<Icon name="chevronRight" size={13}/></button>}
        <button className="oc-btn oc-btn-sm" onClick={() => open(true)}><Icon name="bell" size={13}/>配置岗位订阅</button>
        {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      </div>
    </section>
    {jobs?.after && <Markdown text={jobs.after}/>}
  </>;
}
