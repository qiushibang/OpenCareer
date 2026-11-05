import {useState} from "react";
import {chinaDate} from "../applications";
import {DateInput} from "./DateInput";

// Interview storage retains its existing Shanghai timestamp; the shared UI is date-only.
export function InterviewDateInput({value,onChange}:{value:unknown;onChange:(value:string|null)=>void}) {
  const [reset,setReset]=useState(0);
  return <fieldset className="text-xs text-muted space-y-1"><legend>面试日期</legend><div className="flex items-center gap-2"><DateInput key={reset} label="面试日期" value={chinaDate(value,true)} onChange={date=>onChange(date?date+"T00:00:00+08:00":null)}/><button type="button" className="text-accent shrink-0" onClick={()=>{setReset(n=>n+1);onChange(null);}}>清空日期</button></div></fieldset>;
}
