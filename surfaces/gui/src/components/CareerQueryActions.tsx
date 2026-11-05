import { useState } from "react";
import type { Item } from "../types";
import { isLocal, type CatalogQuery } from "../api";

type Tool=Extract<Item,{kind:"tool"}>;
const KEYS=["condition","today","include_inactive","semantic_query","semantic_offset"];
export function CareerQueryActions({tools}:{tools:Tool[]}) {
  const [error,setError]=useState("");
  if(!isLocal())return null;
  const search=[...tools].reverse().find(t=>t.name.endsWith("search_job_catalog")&&!["error","failed","running","pending"].includes(t.status)&&!(/"ok"\s*:\s*false/.test(t.preview||"")));
  const draft=[...tools].reverse().find(t=>t.name.endsWith("draft_job_subscription")&&!["error","failed","running","pending"].includes(t.status)&&!(/"ok"\s*:\s*false/.test(t.preview||"")));
  const subscription=draft||[...tools].reverse().find(t=>t.name.endsWith("list_job_subscriptions")&&!["error","failed","running","pending"].includes(t.status)&&!(/"ok"\s*:\s*false/.test(t.preview||"")));
  if(!search&&!subscription)return null;
  const args=(tool?:Tool)=>{try{const raw=typeof tool?.args==="string"?JSON.parse(tool.args):tool?.args;return raw&&typeof raw==="object"?raw:{};}catch{return {};}};
  const open=(subscribe:boolean)=>{
    try{
      // A draft states the user's complete intent. Later channel-list calls or
      // narrower example searches must not silently replace it in either link.
      const raw=args(draft||search);
      const query=Object.fromEntries(KEYS.filter(key=>raw[key]!==undefined).map(key=>[key,raw[key]])) as CatalogQuery;
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
  return <div className="flex flex-wrap gap-2 items-center" aria-label="岗位查询操作">{search&&<button className="rounded-lg border border-line px-3 py-2 text-sm text-accent hover:bg-paper" onClick={()=>open(false)}>在岗位雷达查看</button>}<button className="rounded-lg border border-line px-3 py-2 text-sm text-accent hover:bg-paper" onClick={()=>open(true)}>配置岗位订阅</button>{error&&<p role="alert" className="text-xs text-danger">{error}</p>}</div>;
}
