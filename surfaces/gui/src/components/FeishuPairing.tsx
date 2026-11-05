import { useEffect, useRef, useState } from "react";
import { careerCatalogRequest, type JobChannel } from "../api";
interface Pairing {session_id:string;qr_image:string;verification_url:string;interval:number;expires_in:number}
export function FeishuPairing({onConnected,hasConnected=false}:{hasConnected?:boolean;onConnected:(channel:JobChannel)=>void}) {
  const [pair,setPair]=useState<Pairing|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const active=useRef(true),current=useRef<string|null>(null),generation=useRef(0),connected=useRef(onConnected);connected.current=onConnected;
  useEffect(()=>{active.current=true;return()=>{active.current=false;generation.current++;if(current.current)void careerCatalogRequest(`job-subscriptions/feishu-pairing/${current.current}`,undefined,"DELETE").catch(()=>{});};},[]);
  const cancel=()=>{generation.current++;if(current.current)void careerCatalogRequest(`job-subscriptions/feishu-pairing/${current.current}`,undefined,"DELETE").catch(()=>{});current.current=null;setPair(null);setMessage("扫码已取消，未启用订阅。");};
  const begin=async()=>{
    setBusy(true);setMessage("");const token=++generation.current;
    try{
      const result=await careerCatalogRequest<Pairing>("job-subscriptions/feishu-pairing",{});
      if(!active.current||token!==generation.current){void careerCatalogRequest(`job-subscriptions/feishu-pairing/${result.session_id}`,undefined,"DELETE").catch(()=>{});return;}
      current.current=result.session_id;setPair(result);setMessage("请用飞书扫描二维码，在飞书内确认创建及权限；完成后会自动连接。");
    }catch(e){if(active.current)setMessage((e as Error).message);}finally{if(active.current)setBusy(false);}
  };
  useEffect(()=>{
    if(!pair)return;let live=true;let timer:ReturnType<typeof setTimeout>;const deadline=Date.now()+pair.expires_in*1000;
    const poll=async()=>{
      if(!live||Date.now()>deadline){if(live){current.current=null;setPair(null);setMessage("二维码已过期，请重新生成。");}return;}
      try{
        const result=await careerCatalogRequest<{state:string;channel?:JobChannel;interval?:number}>(`job-subscriptions/feishu-pairing/${pair.session_id}/poll`,{});
        if(!live)return;
        if(result.state==="connected"&&result.channel){current.current=null;setPair(null);setMessage("飞书扫码配置已保存，尚未验证发送能力。请先检查连接，再发送测试消息确认。");connected.current(result.channel);return;}
        if(["expired","cancelled"].includes(result.state)){current.current=null;setPair(null);setMessage("二维码已过期或授权取消，请重新生成。");return;}
        timer=setTimeout(()=>void poll(),Math.max(5,result.interval||pair.interval)*1000);
      }catch(e){if(live){void careerCatalogRequest(`job-subscriptions/feishu-pairing/${pair.session_id}`,undefined,"DELETE").catch(()=>{});current.current=null;setPair(null);setMessage((e as Error).message);}}
    };
    timer=setTimeout(()=>void poll(),Math.max(5,pair.interval)*1000);return()=>{live=false;clearTimeout(timer);};
  },[pair]);
  return <div className="rounded-xl bg-paper p-4 space-y-3"><h4 className="font-medium">飞书扫码接入</h4><p className="text-xs text-muted">{/* 产品说明移至代码：使用飞书官方扫码创建机器人，免填应用密钥。请在飞书内核对并确认授权，连接后仍须确认启用订阅。 */}请在飞书确认授权；扫码不会启用订阅。</p>{pair?<div className="space-y-3"><img src={pair.qr_image} alt="飞书官方授权二维码" className="w-60 h-60 bg-white p-2"/><a className="text-sm text-accent underline block" href={pair.verification_url} target="_blank" rel="noreferrer">也可在飞书官方页面继续</a><button className="rounded-lg border border-line px-3 py-2 text-sm" onClick={cancel}>取消扫码</button></div>:<button className="rounded-lg bg-accent text-white px-4 py-2 text-sm disabled:opacity-50" disabled={busy} onClick={()=>void begin()}>{busy?"正在获取二维码…":hasConnected?"连接另一个飞书账号":"生成飞书授权二维码"}</button>}{message&&<p role="status" className="text-sm text-muted">{message}</p>}</div>;
}
