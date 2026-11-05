import {useEffect,useId,useLayoutEffect,useRef,useState} from "react";
import {createPortal} from "react-dom";
import {Icon} from "./Icon";

function validDate(parts:string[]):string|null {
  if(!/^\d{4}$/.test(parts[0]||"") || !/^\d{2}$/.test(parts[1]||"") || !/^\d{2}$/.test(parts[2]||""))return null;
  const iso=parts.join("-");const date=new Date(iso+"T00:00:00Z");
  return Number(parts[0])>=1900 && Number.isFinite(date.valueOf()) && date.toISOString().slice(0,10)===iso ? iso : null;
}
function dateParts(value:string|null|undefined):string[] {return /^\d{4}-\d{2}-\d{2}$/.test(value||"")?value!.split("-"):["","",""];}
function today():string {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}

// A shared, date-only input avoids native browser year/anchor inconsistencies.
// Only complete real calendar dates (or an explicitly empty date) leave this component.
export function DateInput({value,label,onChange,onCommit,onDirty,onFocus,disabled=false,compact=false}:{
  value:string|null|undefined;label:string;onChange:(value:string|null)=>void;
  onCommit?:(value:string|null)=>void;onDirty?:()=>void;onFocus?:()=>void;disabled?:boolean;compact?:boolean;
}) {
  const [parts,setParts]=useState(()=>dateParts(value));
  const [touched,setTouched]=useState(false);
  const [open,setOpen]=useState(false);
  const [month,setMonth]=useState(()=>(value||today()).slice(0,7));
  const [position,setPosition]=useState({top:0,left:0});
  const root=useRef<HTMLDivElement>(null),popup=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null);
  const inputs=useRef<(HTMLInputElement|null)[]>([]);
  const lastCommit=useRef<string|null|undefined>(undefined),commitLatest=useRef(()=>{});
  const id=useId();const iso=validDate(parts),empty=parts.every(v=>!v);
  const invalid=!empty&&!iso;
  const error=invalid&&(touched||parts.every((v,i)=>v.length===(i===0?4:2)))?"请填写有效日期：四位年、两位月和日。":"";
  useEffect(()=>{setParts(dateParts(value));setTouched(false);},[value]);
  useEffect(()=>{inputs.current.forEach((node,index)=>node?.setCustomValidity(index===2&&invalid?"请完整填写有效的年月日。":""));},[invalid]);
  useLayoutEffect(()=>{
    if(!open)return;
    const place=()=>{const rect=root.current?.getBoundingClientRect();if(!rect)return;const width=Math.min(288,window.innerWidth-24),height=popup.current?.getBoundingClientRect().height||332;setPosition({left:Math.max(12,Math.min(rect.left+width<=window.innerWidth-12?rect.left:rect.right-width,window.innerWidth-width-12)),top:Math.max(12,rect.bottom+height+8>window.innerHeight&&rect.top>height?rect.top-height-6:Math.min(rect.bottom+6,window.innerHeight-height-12))});};
    place();
    (popup.current?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')||popup.current?.querySelector<HTMLButtonElement>('[data-today="true"]')||popup.current?.querySelector<HTMLButtonElement>(".date-calendar-grid button"))?.focus({preventScroll:true});
    const outside=(event:PointerEvent)=>{const node=event.target as Node;if(!root.current?.contains(node)&&!popup.current?.contains(node)){commitLatest.current();setOpen(false);}};
    const escape=(event:KeyboardEvent)=>{if(event.key==="Escape"){event.stopPropagation();event.preventDefault();setOpen(false);trigger.current?.focus();}};
    const anchorLeft=root.current?.getBoundingClientRect().left;
    const scroll=(event:Event)=>{
      if(popup.current?.contains(event.target as Node))return;
      const rect=root.current?.getBoundingClientRect();
      // Horizontal table motion can hide the field behind frozen columns. Vertical
      // drawer scrolling instead keeps the popup attached, including focus scrolling.
      if(!rect||Math.abs(rect.left-(anchorLeft??rect.left))>1||rect.bottom<0||rect.top>window.innerHeight)setOpen(false);
      else place();
    };
    document.addEventListener("pointerdown",outside);document.addEventListener("keydown",escape,true);
    window.addEventListener("resize",place);window.addEventListener("scroll",scroll,true);
    return()=>{document.removeEventListener("pointerdown",outside);document.removeEventListener("keydown",escape,true);window.removeEventListener("resize",place);window.removeEventListener("scroll",scroll,true);};
  },[open]);
  const update=(index:number,raw:string)=>{
    lastCommit.current=undefined;onDirty?.();const next=[...parts];next[index]=raw.replace(/\D/g,"").slice(0,index===0?4:2);setParts(next);setTouched(false);
    const date=validDate(next);if(date||next.every(v=>!v))onChange(date);
    if(next[index].length===(index===0?4:2)&&index<2){inputs.current[index+1]?.focus();inputs.current[index+1]?.select();}
  };
  const emitCommit=(date:string|null)=>{if(lastCommit.current!==date){lastCommit.current=date;onCommit?.(date);}};
  const choose=(date:string|null)=>{setParts(dateParts(date));setTouched(false);if(date!==value||invalid)onDirty?.();onChange(date);emitCommit(date);setOpen(false);trigger.current?.focus();};
  const commit=()=>{setTouched(true);if(iso||empty)emitCommit(iso);};
  commitLatest.current=commit;
  const [year,mon]=month.split("-").map(Number);
  const first=new Date(year,mon-1,1);const leading=(first.getDay()+6)%7,days=new Date(year,mon,0).getDate();
  const moveMonth=(delta:number)=>{const next=new Date(year,mon-1+delta,1);if(next.getFullYear()>=1900&&next.getFullYear()<=9999)setMonth(`${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,"0")}`);};
  return <div className={"date-input "+(compact?"date-input-compact":"")} ref={root} role="group" aria-label={label} onBlur={event=>{
    const next=event.relatedTarget as Node|null;if(root.current?.contains(next)||popup.current?.contains(next))return;
    commit();
  }}>
    <div className="date-input-fields" data-invalid={!!error}>
      {["年","月","日"].map((unit,index)=><span className="date-input-segment" key={unit}>
        {index>0&&<span aria-hidden="true" className="date-input-divider">/</span>}
        <input ref={node=>{inputs.current[index]=node;}} aria-label={`${label}${unit}`} aria-invalid={invalid} aria-describedby={error?id+"-error":undefined} type="text" inputMode="numeric" autoComplete="off" placeholder={index===0?"YYYY":index===1?"MM":"DD"} pattern={index===0?"[0-9]{4}":"[0-9]{2}"} maxLength={index===0?4:2} disabled={disabled} value={parts[index]} onFocus={()=>{lastCommit.current=undefined;onFocus?.();}} onChange={event=>update(index,event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();commit();}if(event.key==="Backspace"&&!parts[index]&&index>0)inputs.current[index-1]?.focus();}} onPaste={event=>{
          const match=event.clipboardData.getData("text").trim().match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?$/);if(!match)return;
          event.preventDefault();const next=[match[1],match[2].padStart(2,"0"),match[3].padStart(2,"0")];setParts(next);setTouched(true);lastCommit.current=undefined;onDirty?.();const date=validDate(next);if(date)onChange(date);
        }}/>
      </span>)}
      <button ref={trigger} type="button" disabled={disabled} className="date-input-trigger" aria-label={`${label}选择日期`} aria-expanded={open} aria-controls={open?id:undefined} onClick={()=>{if(!open)setMonth((iso||today()).slice(0,7));setOpen(v=>!v);}}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18"/></svg>
      </button>
    </div>
    {error&&<p id={id+"-error"} role="alert" className="date-input-error">{error}</p>}
    {open&&createPortal(<div ref={popup} id={id} role="dialog" aria-label={`${label}日历`} className="date-calendar" style={position} onKeyDown={event=>{if(event.key!=="Tab")return;const buttons=Array.from(popup.current?.querySelectorAll<HTMLButtonElement>("button:not([disabled])")||[]);const first=buttons[0],last=buttons[buttons.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}}>
      <div className="date-calendar-heading"><button type="button" aria-label="上个月" onClick={()=>moveMonth(-1)}><Icon name="chevronRight" size={16} className="rotate-180"/></button><strong>{year} 年 {mon} 月</strong><button type="button" aria-label="下个月" onClick={()=>moveMonth(1)}><Icon name="chevronRight" size={16}/></button></div>
      <div className="date-calendar-grid">{["一","二","三","四","五","六","日"].map(d=><span className="date-calendar-weekday" key={d}>{d}</span>)}
        {Array.from({length:leading},(_,i)=><span key={"blank"+i}/>)}
        {Array.from({length:days},(_,i)=>{const date=`${month}-${String(i+1).padStart(2,"0")}`;return <button key={date} type="button" aria-label={date} aria-pressed={date===iso} data-today={date===today()} onClick={()=>choose(date)}>{i+1}</button>;})}
      </div>
      <div className="date-calendar-footer"><button type="button" onClick={()=>choose(null)}>清空日期</button><button type="button" onClick={()=>choose(today())}>今天</button><button type="button" onClick={()=>{setOpen(false);trigger.current?.focus();}}>关闭</button></div>
    </div>,document.body)}
  </div>;
}
