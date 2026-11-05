import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { DateInput } from "./DateInput";
import { Icon } from "./Icon";
import { InterviewDateInput } from "./InterviewDateInput";
import { estimatedAnnualSalary, APPLICATION_STATUS, PRIORITY, RECRUITMENT, STAGES, ROUNDS, interviewNotes, ROUND_RESULT, ROUND_KIND, applicationsRequest, chinaDate, localDateTime, fromLocalDateTime, type Application, type ApplicationInterview, type ApplicationPage, type ApplicationFilters, type ApplicationExport } from "../applications";

const INPUT = "w-full rounded-lg border border-line bg-panel px-2.5 py-2 text-[13px] text-ink outline-none focus:border-accent";
const BUTTON = "rounded-lg border border-line bg-panel px-3 py-2 text-[12px] hover:bg-paper disabled:opacity-40";
const LABEL = "text-xs text-muted space-y-1 block";
const VIEWS: Record<string,string> = {all:"全部申请",preparing:"准备投递",interviewing:"面试中",offer:"Offer",closed:"已结束",archived:"已归档"};
const COLUMNS: [string,string][] = [["company","公司"],["title","岗位名称"],["location","工作地点"],["status","申请状态"],["stage","当前阶段"],["applied_on","投递日期"],["monthly_salary","月薪酬"],["salary_months","发薪月数"],["annual_salary","预计年薪酬"],["priority","优先级"],["recruitment_type","招聘类型"],["batch","招聘批次"],["department","部门"],["business_line","业务线"],["channel","来源渠道"],["resume_label","简历版本"]];
const DEFAULT_COLUMNS = COLUMNS.slice(0,10).map(c=>c[0]);
// One sizing source for colgroup, table width and frozen offsets. Auto table sizing
// would expand the company cell while leaving the next sticky offset unchanged.
const SELECTION_WIDTH = 40;
const COMPANY_WIDTH = 120;
const COLUMN_WIDTHS:Record<string,number> = {company:COMPANY_WIDTH,title:260,location:110,status:120,stage:110,applied_on:168,monthly_salary:100,salary_months:84,annual_salary:118,priority:90};
function columnWidth(key:string):number { return COLUMN_WIDTHS[key] ?? 140; }
function frozenOffset(key:string):number|undefined { return key === "company" ? SELECTION_WIDTH : key === "title" ? SELECTION_WIDTH + COMPANY_WIDTH : undefined; }

const APP_FIELDS = ["company","title","location","status","stage","priority","recruitment_type","batch","department","business_line","channel","source_url","jd","notes","applied_on","next_action","next_at","deadline_on","next_done","tags","archived","salary_months","monthly_salary","salary_advertised","salary_expected","salary_offer","offer_currency","offer_period","offer_months","resume_import_id","resume_label"];
const ROUND_FIELDS = ["experience_notes","round_name","round_number","kind","format","scheduled_at","arrangement","result","questions","answers","review","knowledge_gaps","next_step"];
const EMPTY_ROUND = {experience_notes:"",round_name:"一面",round_number:null,kind:"business",format:"video",scheduled_at:null,arrangement:"unscheduled",result:"pending",questions:"",answers:"",review:"",knowledge_gaps:"",next_step:""};
const OFFICIAL_FIELDS = new Set(["company","title","location","recruitment_type","department","business_line","source_url","jd"]);
const PREF_KEY = "opencareer-applications-view-v3";
function preferences(): {filters:ApplicationFilters;columns:string[];group:string} {
  try { const saved = JSON.parse(localStorage.getItem(PREF_KEY)||"{}"); // Ignore retired filters so old preferences cannot silently hide records.
    const old=saved.filters||{};
    return {filters:{view:Object.prototype.hasOwnProperty.call(VIEWS,old.view)?old.view:"all",q:old.q||"",sort:old.sort,descending:old.descending},columns:Array.isArray(saved.columns)?saved.columns:DEFAULT_COLUMNS,group:""}; }
  catch { return {filters:{view:"all"},columns:DEFAULT_COLUMNS,group:""}; }
}
function pick(record: Record<string,unknown>, keys: string[]): Record<string,unknown> { return Object.fromEntries(keys.map(key=>[key,record[key]])); }
function Options({values}:{values:Record<string,string>}) { return <>{Object.entries(values).map(([key,label])=><option key={key} value={key}>{label}</option>)}</>; }

function useModalKeys(active:boolean,label:string,onClose:()=>void) {
  const close=useRef(onClose);close.current=onClose;
  useEffect(()=>{
    if(!active)return;
    const dialog=document.querySelector<HTMLElement>(`[role="dialog"][aria-label="${label}"]`);
    if(!dialog)return;
    const before=document.activeElement as HTMLElement|null;
    const controls=()=>Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],summary')).filter(node=>node.getClientRects().length>0);
    controls()[0]?.focus({preventScroll:true});
    const key=(event:KeyboardEvent)=>{
      if(event.key==="Escape"){event.preventDefault();close.current();}
      if(event.key!=="Tab")return;
      const values=controls(),first=values[0],last=values[values.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    };
    dialog.addEventListener("keydown",key);
    return()=>{dialog.removeEventListener("keydown",key);if(before?.isConnected&&dialog.contains(document.activeElement))before.focus({preventScroll:true});};
  },[active,label]);
}

function InlineCell({record,field,save}:{record:Application;field:string;save:(record:Application,patch:Record<string,unknown>)=>Promise<void>}) {
  const value = field === "next_at" ? localDateTime(record[field]) : String(record[field]??"");
  const [draft,setDraft] = useState(value), [busy,setBusy] = useState(false), [error,setError] = useState("");
  const focused = useRef(false), dirty = useRef(false);
  useEffect(()=>{ if (!focused.current && !dirty.current) setDraft(value); },[value]);
  const persist = async (text:string) => {
    if (text===value) {dirty.current=false;return;}
    if (busy) return;
    setBusy(true); setError("");
    try { await save(record,{[field]:field==="salary_months"?(text?Number(text):null):field==="next_at"?fromLocalDateTime(text):["applied_on","deadline_on"].includes(field)?text||null:text}); dirty.current=false; }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const choices = field==="status"?APPLICATION_STATUS:field==="priority"?PRIORITY:field==="recruitment_type"?RECRUITMENT:field==="stage"?STAGES:null;
  if(field==="annual_salary")return <span className="px-1.5 text-muted">{record.annual_salary?Number(record.annual_salary).toLocaleString("zh-CN")+" 元／年":"待填写薪酬"}</span>;
  if(record.job_id&&OFFICIAL_FIELDS.has(field))return <span className="px-1.5 text-muted">{field==="recruitment_type"?(RECRUITMENT[value]||value):value||"官网未提供"}</span>;
  return <div className="application-inline-cell min-w-0">
    {choices ? <span className="application-select"><select aria-label={`${COLUMNS.find(c=>c[0]===field)?.[1]}：${record.title}`} value={draft} disabled={busy} style={{width:`${Math.max(6,Array.from(choices[draft]||draft||"未记录").length*2)+4}ch`}} onChange={e=>{setDraft(e.target.value);dirty.current=true;void persist(e.target.value);}}>{draft&&!Object.prototype.hasOwnProperty.call(choices,draft)&&<option value={draft}>{draft}（原记录）</option>}<Options values={choices}/></select><Icon name="chevronDown" size={14}/></span>
      : ["applied_on","deadline_on"].includes(field) ? <DateInput compact label={`${COLUMNS.find(c=>c[0]===field)?.[1]}：${record.title}`} value={draft} disabled={busy} onFocus={()=>{focused.current=true;}} onDirty={()=>{dirty.current=true;}} onChange={date=>setDraft(date||"")} onCommit={date=>{focused.current=false;void persist(date||"");}}/>
      : <input aria-label={`${COLUMNS.find(c=>c[0]===field)?.[1]}：${record.title}`} className={"w-full rounded-md border bg-transparent px-1.5 py-1.5 focus:border-accent "+(error?"border-red-400":"border-transparent")} type={field==="next_at"?"datetime-local":"text"} value={draft} disabled={busy} onFocus={()=>{focused.current=true;}} onChange={e=>{setDraft(e.target.value);dirty.current=true;}} onBlur={()=>{focused.current=false;void persist(draft);}} onKeyDown={e=>{if(e.key==="Enter")e.currentTarget.blur();}}/>}
    {error && <p role="alert" className="text-xs text-danger max-w-[230px]">{error}（草稿保留，刷新记录后重试）</p>}
  </div>;
}

export function ApplicationsView({initialId}:{initialId?:string|null}) {
  const [pref] = useState(preferences);
  const [filters,setFilters] = useState<ApplicationFilters>(pref.filters), [columns,setColumns] = useState(pref.columns), [group] = useState(pref.group);
  const [page,setPage] = useState<ApplicationPage|null>(null), [offset,setOffset] = useState(0), [loading,setLoading] = useState(false), [error,setError] = useState("");
  const [selected,setSelected] = useState<Set<string>>(new Set()), [selectedId,setSelectedId] = useState<string|null>(initialId||null);
  const [detail,setDetail] = useState<Application|null>(null), [draft,setDraft] = useState<Application|null>(null), [dirty,setDirty] = useState(false), [panelNotice,setPanelNotice] = useState("");
  const [busy,setBusy] = useState(false);
  const [newRecord,setNewRecord] = useState<Record<string,string>|null>(null);
  const [round,setRound] = useState<Record<string,unknown>|null>(null), [roundDirty,setRoundDirty] = useState(false);
  const [exportScope,setExportScope] = useState("filtered"), [exportBusy,setExportBusy] = useState(false), [exportNotice,setExportNotice] = useState("");
  const requestNumber = useRef(0), exportNumber = useRef(0);
  const draftBase = useRef<Record<string,unknown>|null>(null);
  const filterKey = JSON.stringify(filters);
  const load = useCallback(async () => {
    const number = ++requestNumber.current;setLoading(true);
    try { const result = await applicationsRequest<ApplicationPage>("/query",{filters,limit:50,offset}); if(number===requestNumber.current){setPage(result);setError("");} }
    catch(e){if(number===requestNumber.current)setError((e as Error).message);}
    finally{if(number===requestNumber.current)setLoading(false);}
  },[filterKey,offset]);
  useEffect(()=>{requestNumber.current++;setLoading(true);const timer=setTimeout(()=>{void load();},180);return()=>{clearTimeout(timer);requestNumber.current++;};},[load]);
  useEffect(()=>{setOffset(0);setSelected(new Set());},[filterKey]);
  useEffect(()=>{try{localStorage.setItem(PREF_KEY,JSON.stringify({filters,columns,group}));}catch{/* preferences are optional */}},[filterKey,columns,group]);
  useEffect(()=>{if(initialId)setSelectedId(initialId);},[initialId]);
  useEffect(()=>{
    if(!selectedId){setDetail(null);setDraft(null);return;}
    let live=true;setDetail(null);setDraft(null);setRound(null);setDirty(false);setPanelNotice("");
    applicationsRequest<Application>("/"+encodeURIComponent(selectedId)).then(record=>{
      if(!live)return;setDetail(record);draftBase.current=pick(record,APP_FIELDS);
      try { const saved=JSON.parse(sessionStorage.getItem("application-draft:"+selectedId)||"null");if(saved){draftBase.current=saved._base||pick(record,APP_FIELDS);setDraft({...record,...Object.fromEntries(Object.entries(saved).filter(([key])=>!record.job_id||!OFFICIAL_FIELDS.has(key)))});setDirty(true);setPanelNotice("已恢复未保存的申请草稿，请检查后保存。");return;} } catch{/* no draft */}
      setDraft(record);
    }).catch(e=>{if(live)setPanelNotice(e.message);});
    return()=>{live=false;};
  },[selectedId]);
  useEffect(()=>{if(dirty&&draft){try{sessionStorage.setItem("application-draft:"+draft.id,JSON.stringify({...pick(draft,APP_FIELDS),version:draft.version,_base:draftBase.current}));}catch{setPanelNotice("浏览器无法暂存草稿，请及时保存申请信息。");}}},[draft,dirty]);
  useEffect(()=>{if(roundDirty&&round&&selectedId){try{sessionStorage.setItem("application-round-draft:"+selectedId+":"+(round.id||"new"),JSON.stringify(round));}catch{setPanelNotice("请及时保存本轮面经，浏览器暂存空间不足。");}}},[round,roundDirty,selectedId]);
  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(dirty||roundDirty)event.preventDefault();};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty,roundDirty]);
  const filter = (key:string,value:string|boolean) => setFilters(previous=>({...previous,[key]:value}));
  const change = (key:string,value:unknown) => {setDraft(previous=>previous?{...previous,[key]:value}:previous);setDirty(true);};
  const open = (id:string|null) => {if(busy)return;if((dirty||roundDirty)&&!window.confirm("有未保存内容，已暂存在本机浏览器。仍要切换吗？"))return;setSelectedId(id);setRoundDirty(false);};
  useModalKeys(!!selectedId||!!newRecord,newRecord?"新建申请":"申请详情",()=>{
    if(busy)return;
    if(newRecord){if(Object.values(newRecord).some(Boolean)&&!window.confirm("新申请尚未保存，确定取消吗？"))return;setNewRecord(null);}
    else open(null);
  });
  const readLatest = async () => {
    if(!draft||busy)return;setBusy(true);
    try {
      const fresh=await applicationsRequest<Application>("/"+draft.id);
      const base=draftBase.current||detail||{};
      const edits=Object.fromEntries(APP_FIELDS.filter(key=>(!fresh.job_id||!OFFICIAL_FIELDS.has(key))&&JSON.stringify(draft[key])!==JSON.stringify(base[key])).map(key=>[key,draft[key]]));
      setDetail(fresh);setDraft({...fresh,...edits});draftBase.current=pick(fresh,APP_FIELDS);setDirty(Object.keys(edits).length>0);if(!Object.keys(edits).length)sessionStorage.removeItem("application-draft:"+draft.id);
      if(round?.id){const current=fresh.interviews?.find(value=>value.id===round.id);if(current)setRound(previous=>({...previous,version:current.version}));}
      setPanelNotice("已读取最新记录并保留你的修改草稿，请核对后再次保存；未自动覆盖服务器内容。");
    }catch(e){setPanelNotice((e as Error).message);}finally{setBusy(false);}
  };
  const inlineSave = async (record:Application,patch:Record<string,unknown>) => {
    if(selectedId===record.id&&dirty)throw new Error("请先保存右侧申请草稿，再编辑这条记录。");
    const saved = await applicationsRequest<Application>("/"+record.id,{expected_version:record.version,...patch},"PATCH");
    if(selectedId===record.id){setDetail(previous=>({...previous,...saved}));setDraft(previous=>({...previous,...saved}));}
    await load();
  };
  const saveApplication = async (event:FormEvent) => {
    event.preventDefault();if(!draft)return;setBusy(true);setPanelNotice("");
    try{
      await applicationsRequest<Application>("/"+draft.id,{expected_version:draft.version,...pick(draft,APP_FIELDS.filter(key=>!draft.job_id||!OFFICIAL_FIELDS.has(key)))},"PATCH");
      const saved=await applicationsRequest<Application>("/"+draft.id);setDetail(saved);setDraft(saved);draftBase.current=pick(saved,APP_FIELDS);setDirty(false);sessionStorage.removeItem("application-draft:"+draft.id);setPanelNotice("申请已保存");await load();
    }catch(e){setPanelNotice((e as Error).message);}finally{setBusy(false);}
  };
  const beginRound = (existing?:ApplicationInterview) => {
    if(dirty){setPanelNotice("请先保存申请信息，再编辑面试，避免覆盖未保存的草稿。");return;}
    if(roundDirty&&!window.confirm("当前面经尚未保存，已暂存草稿。仍要切换吗？"))return;
    let data:Record<string,unknown> = existing?{...existing}:{...EMPTY_ROUND};
    try{data=JSON.parse(sessionStorage.getItem("application-round-draft:"+selectedId+":"+(existing?.id||"new"))||"null")||data;}catch{/* no draft */}
    setRound({...data,experience_notes:interviewNotes(data)});setRoundDirty(false);setPanelNotice("");
  };
  const saveRound = async (event:FormEvent) => {
    event.preventDefault();if(!round||!detail)return;if(dirty){setPanelNotice("请先保存申请信息，再保存面试；两份草稿均保留。");return;}setBusy(true);setPanelNotice("");
    try{
      await applicationsRequest("/"+detail.id+"/interviews"+(round.id?"/"+round.id:""),{...pick(round,ROUND_FIELDS),arrangement:round.arrangement==="scheduled"&&!round.scheduled_at?"unscheduled":round.arrangement,...(round.id?{expected_version:round.version}:{}),set_current_stage:false},round.id?"PATCH":"POST");
      sessionStorage.removeItem("application-round-draft:"+detail.id+":"+(round.id||"new"));
      const saved=await applicationsRequest<Application>("/"+detail.id);setDetail(saved);setDraft(saved);draftBase.current=pick(saved,APP_FIELDS);setRound(null);setRoundDirty(false);setPanelNotice("面试已保存，面试完成不自动视为通过。");await load();
    }catch(e){setPanelNotice((e as Error).message);}finally{setBusy(false);}
  };
  const deleteRound = async (interview:ApplicationInterview) => {
    if(busy||dirty||roundDirty){setPanelNotice("请先保存或取消当前编辑，再删除面试。");return;}
    if(!window.confirm(`确定删除${interview.round_name}及本轮面经吗？其他面试与申请备注会保留。`))return;
    setBusy(true);
    try {
      await applicationsRequest("/"+selectedId+"/interviews/"+interview.id,{expected_version:interview.version},"DELETE");
      sessionStorage.removeItem("application-round-draft:"+selectedId+":"+interview.id);
      const saved=await applicationsRequest<Application>("/"+selectedId);setDetail(saved);setDraft(saved);draftBase.current=pick(saved,APP_FIELDS);
      if(round?.id===interview.id)setRound(null);
      setPanelNotice("本轮面试已删除，申请状态与阶段保留。");await load();
    }catch(e){setPanelNotice((e as Error).message);}finally{setBusy(false);}
  };
  const cancelRound = () => {
    sessionStorage.removeItem("application-round-draft:"+selectedId+":"+(round?.id||"new"));setRound(null);setRoundDirty(false);
  };
  const create = async (event:FormEvent) => {
    event.preventDefault();if(!newRecord)return;setBusy(true);setError("");
    try{const saved=await applicationsRequest<Application>("",newRecord);setNewRecord(null);setFilters({view:"all"});setSelectedId(saved.id);await load();}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  };
  const exportFile = async () => {
    const number=++exportNumber.current;setExportBusy(true);setExportNotice("正在准备完整申请与面试记录…");
    try{
      const body=exportScope==="all"?{filters:{include_archived:true}}:{filters,...(exportScope==="selected"?{ids:[...selected]}:{})};
      if(exportScope==="selected"&&!selected.size)throw new Error("请先勾选要导出的记录。");
      const payload=await applicationsRequest<ApplicationExport>("/export",body);
      if(number!==exportNumber.current)return;
      const module=await import("../applicationExport");
      if(number!==exportNumber.current)return;
      module.downloadApplicationWorkbook(payload);setExportNotice(`已准备 ${payload.total} 条申请及 ${payload.interviews.length} 场面试的Excel下载，请在浏览器下载列表查看。`);
    }catch(e){if(number===exportNumber.current)setExportNotice((e as Error).message);}finally{if(number===exportNumber.current)setExportBusy(false);}
  };
  const visible=COLUMNS.filter(([key])=>columns.includes(key)||key==="company"||key==="title");
  const grouped = new Map<string,Application[]>();
  for(const record of page?.records||[]){const key=group?String(record[group]||"未记录"):"";grouped.set(key,[...(grouped.get(key)||[]),record]);}
  const field = (key:string,label:string,type="text",options?:Record<string,string>) => {
    const value=String(draft?.[key]??"");
    if(draft?.job_id&&OFFICIAL_FIELDS.has(key))return <div className={LABEL} key={key}><span>{label}</span><p className="text-[13px] text-ink py-2 break-words" aria-label={label}>{options?(options[value]||value||"官网未提供"):value||"官网未提供"}</p></div>;
    return <label className={LABEL} key={key}><span>{label}</span>{options?<select aria-label={label} className={INPUT} value={value} onChange={e=>change(key,e.target.value)}>{value&&!Object.prototype.hasOwnProperty.call(options,value)&&<option value={value}>{value}（原记录）</option>}<Options values={options}/></select>:type==="date"?<DateInput label={label} value={value} onChange={date=>change(key,date)}/>:<input aria-label={label} className={INPUT} placeholder={key==="monthly_salary"?"例如 25000 或 25k":undefined} type={type} value={type==="datetime-local"?localDateTime(draft?.[key]):value} onChange={e=>change(key,type==="datetime-local"?fromLocalDateTime(e.target.value):type==="date"?e.target.value||null:e.target.value)}/>}</label>;
  };

  return <main className="oc-page oc-applications flex-1 min-w-0 flex flex-col bg-panel text-ink" aria-label="求职进度工作台">
    <header className="border-b border-line px-6 pt-6 pb-4 space-y-4">
      <div className="application-heading">
        <h1 className="text-xl font-semibold">求职进度</h1>
        <div className="application-actions">
          <button className={BUTTON} disabled={loading} onClick={()=>void load()}>刷新记录</button>
          <button className={BUTTON} disabled={exportBusy||!page} onClick={()=>void exportFile()}>导出 Excel</button>
          {exportBusy&&<button className={BUTTON} onClick={()=>{exportNumber.current++;setExportBusy(false);setExportNotice("已取消本次导出准备。");}}>取消导出</button>}
          <button className="rounded-lg bg-accent px-4 py-2 text-sm text-white" onClick={()=>setNewRecord({company:"",title:"",location:"",jd:"",notes:""})}>新建申请</button>
        </div>
      </div>
      <div className="application-summary flex gap-5 text-xs text-muted"><span>未归档 <strong className="text-ink">{page?.summary.active||0}</strong></span><span>面试中 <strong className="text-ink">{page?.summary.interviewing||0}</strong></span><span>Offer <strong className="text-ink">{page?.summary.offer||0}</strong></span><span className="ml-auto">{page?.total??0} 条申请</span></div>
      {/* Common filtering uses one status view plus a single keyword. Column and export
          preferences live separately; retired filters never remain active invisibly. */}
      <div className="application-controls">
        <div className="flex gap-1" role="group" aria-label="申请视图">{Object.entries(VIEWS).map(([key,label])=><button key={key} className={"rounded-md px-3 py-1.5 text-xs "+((filters.view||"all")===key?"bg-accent text-white":"hover:bg-paper text-muted")} onClick={()=>filter("view",key)}>{label}</button>)}</div>
        <input aria-label="搜索求职申请" placeholder="搜索公司、岗位或备注" className={INPUT+" application-search"} value={String(filters.q||"")} onChange={e=>filter("q",e.target.value)}/>
        <details className="relative application-table-settings"><summary className={BUTTON+" cursor-pointer list-none"}>表格设置</summary><div className="application-settings-menu absolute right-0 top-11 z-30 w-80 border border-line rounded-xl bg-panel p-4 shadow-lg space-y-4">
          <fieldset><legend className="text-xs font-medium mb-3">显示列</legend><div className="grid grid-cols-2 gap-2">{COLUMNS.map(([key,label])=><label className="text-xs flex gap-2" key={key}><input type="checkbox" disabled={["company","title"].includes(key)} checked={columns.includes(key)||["company","title"].includes(key)} onChange={e=>setColumns(previous=>e.target.checked?[...previous,key]:previous.filter(v=>v!==key))}/>{label}</label>)}</div></fieldset>
          <label className={LABEL}><span>Excel 导出范围</span><select aria-label="Excel导出范围" className={INPUT} value={exportScope} onChange={e=>setExportScope(e.target.value)}><option value="filtered">当前列表（所有分页）</option><option value="all">全部申请（含归档）</option><option value="selected">勾选记录（{selected.size}）</option></select></label>
        </div></details>
      </div>
      {exportNotice&&<p role="status" className="text-xs text-muted">{exportNotice}</p>}{error&&<p role="alert" className="text-sm text-danger">{error}<button onClick={()=>void load()} className="ml-2 underline">重试</button></p>}
    </header>
    <div className="flex-1 overflow-auto relative">
      <table className="application-table table-fixed border-separate border-spacing-0 text-xs" style={{width:SELECTION_WIDTH+visible.reduce((width,[key])=>width+columnWidth(key),0)}} aria-label="求职申请总表"><colgroup><col style={{width:SELECTION_WIDTH}}/>{visible.map(([key])=><col key={key} style={{width:columnWidth(key)}}/>)}</colgroup><thead className="sticky top-0 z-20 bg-paper"><tr><th className="application-frozen px-3 py-3" style={{left:0}}><input aria-label="勾选本页申请" type="checkbox" checked={!!page?.records.length&&page.records.every(row=>selected.has(row.id))} onChange={e=>setSelected(previous=>{const next=new Set(previous);for(const row of page?.records||[]){if(e.target.checked)next.add(row.id);else next.delete(row.id);}return next;})}/></th>{visible.map(([key,label])=><th key={key} data-application-column={key} style={{left:frozenOffset(key)}} className={"border-b border-line px-3 py-3 text-left font-medium "+(frozenOffset(key)!==undefined?"application-frozen":"")}><button onClick={()=>setFilters(previous=>({...previous,sort:key,descending:previous.sort===key?!previous.descending:false}))}>{label} {filters.sort===key?(filters.descending?"↓":"↑"):""}</button></th>)}</tr></thead><tbody>
        {[...grouped].map(([name,records])=><GroupRows key={name} name={name} group={group} records={records} columns={visible} selected={selected} setSelected={setSelected} open={open} save={inlineSave}/>)}
      </tbody></table>
      {!loading&&!page?.records.length&&<div className="py-20 text-center"><p className="text-sm">{filters.q||filters.status||filters.view!=="all"?"当前条件没有申请记录":"从一个心仪岗位开始"}</p><p className="mt-2 text-xs text-muted">{/* 产品说明移至代码：在岗位雷达加入求职进度，或手动记录内推、招聘网站和其他机会。 */}从岗位雷达加入，或手动新建。</p></div>}
      {loading&&<p role="status" className="px-6 py-3 text-xs text-muted">正在读取申请…</p>}
    </div>
    <footer className="border-t border-line px-6 py-3 flex justify-between items-center text-xs text-muted"><span>{page?.total?`${offset+1}–${Math.min(offset+50,page.total)} / ${page.total}`:"0 条申请"}</span>{/* 表内修改后离开单元格即可保存；状态和错误在编辑单元格旁显示。 */}<div className="flex gap-2"><button className={BUTTON} disabled={!offset||loading} onClick={()=>setOffset(n=>Math.max(0,n-50))}>上一页</button><button className={BUTTON} disabled={!page||offset+50>=page.total||loading} onClick={()=>setOffset(n=>n+50)}>下一页</button></div></footer>

    {newRecord&&<div className="fixed inset-0 z-40 bg-black/20 flex justify-center items-center p-5"><section role="dialog" aria-modal="true" aria-label="新建申请" className="bg-panel rounded-2xl shadow-xl p-6 w-full max-w-xl max-h-[90vh] overflow-auto"><h2 className="font-semibold text-lg mb-4">手动新建申请</h2><form onSubmit={e=>void create(e)} className="space-y-3">{([['company','公司名称'],['title','岗位名称'],['location','工作地点']] as const).map(([key,label])=><label className={LABEL} key={key}>{label}<input required={key!=="location"} className={INPUT} value={newRecord[key]} onChange={e=>setNewRecord(previous=>({...previous,[key]:e.target.value}))}/></label>)}<label className={LABEL}>职位描述<textarea aria-label="职位描述" className={INPUT+" h-28"} value={newRecord.jd} onChange={e=>setNewRecord(previous=>({...previous,jd:e.target.value}))}/></label><label className={LABEL}>申请备注<textarea aria-label="申请备注" className={INPUT} value={newRecord.notes} onChange={e=>setNewRecord(previous=>({...previous,notes:e.target.value}))}/></label><p className="text-xs text-muted">先加入个人计划，尚未代表已在招聘网站投递。</p>{error&&<p role="alert" className="text-danger text-sm">{error}</p>}<div className="flex gap-2 justify-end"><button type="button" className={BUTTON} onClick={()=>setNewRecord(null)}>取消</button><button className="rounded-lg bg-accent text-white px-4 py-2 text-sm" disabled={busy}>创建申请</button></div></form></section></div>}

    {selectedId&&<div className="fixed inset-0 z-40 bg-black/10 flex justify-end"><section role="dialog" aria-modal="true" aria-label="申请详情" className="oc-drawer w-full max-w-[760px] h-full overflow-y-auto bg-panel border-l border-line shadow-xl">
      <div className="sticky top-0 z-20 border-b border-line bg-panel px-6 py-4 flex items-start justify-between"><div><h2 className="font-semibold text-lg">{detail?.title||"申请详情"}</h2><p className="text-xs text-muted mt-1">{detail?.company} · {detail?.location||"地点未记录"}</p></div><button className={BUTTON} aria-label="关闭详情" disabled={busy} onClick={()=>open(null)}>关闭</button></div>
      <div className="px-6 py-2 border-b border-line bg-panel flex gap-3 sticky top-[85px] z-20">{[["application-fields","申请信息"],["application-interviews","面试与面经"],["application-history","进度历史"]].map(([id,label])=><button key={id} className="text-xs text-muted hover:text-accent" onClick={()=>document.getElementById(id)?.scrollIntoView({block:"start"})}>{label}</button>)}</div>
      <div className="p-6 space-y-6">{panelNotice&&<p role="status" className="rounded-lg bg-paper p-3 text-xs whitespace-pre-wrap">{panelNotice}<button className="ml-2 underline text-accent" type="button" disabled={busy} onClick={()=>void readLatest()}>读取最新记录并保留草稿</button></p>}
      {draft?<><form id="application-fields" onSubmit={e=>void saveApplication(e)} className="space-y-4" aria-label="申请信息">
        {draft.applied_date_source==="legacy_tracking"&&<p className="text-xs text-muted">{/* 产品说明移至代码：投递日期沿用旧系统记录，可能是当时更新进度的时间；请按实际情况核对。 */}旧投递日期，请按实际核对。</p>}
        <div className="grid grid-cols-2 gap-3">{field("company","公司名称")}{field("title","岗位名称")}{field("location","工作地点")}{field("status","申请状态","text",APPLICATION_STATUS)}{field("stage","当前阶段","text",STAGES)}{field("priority","优先级","text",PRIORITY)}{field("recruitment_type","招聘类型","text",RECRUITMENT)}{field("batch","招聘批次")}{field("applied_on","投递日期","date")}{field("channel","来源渠道")}{field("department","部门")}{field("business_line","业务线")}</div>
        {field("source_url","原始链接","url")}
        {draft.source_url&&/^https?:\/\//i.test(draft.source_url)&&<a className="inline-flex items-center rounded-lg border border-accent/30 px-4 py-2.5 text-sm font-medium text-accent hover:bg-paper" href={draft.source_url} target="_blank" rel="noreferrer">打开原始岗位链接</a>}
        <div className="rounded-xl bg-paper p-4 space-y-3"><div className="grid grid-cols-2 gap-3">{field("monthly_salary","月薪酬（元／月）")}<label className={LABEL}>发薪月数<input aria-label="发薪月数" type="number" min={1} max={24} step={1} placeholder="例如 13、14、16" className={INPUT} value={draft.salary_months??""} onChange={e=>change("salary_months",e.target.value?Number(e.target.value):null)}/></label></div>{/* 产品说明移至代码：例如：25000 元／月 × 14 薪，预计年薪酬 350000 元。奖金、股票等另记备注。 */}<p aria-label="预计年薪酬" className="text-sm font-medium">预计年薪酬：{estimatedAnnualSalary(draft.monthly_salary,draft.salary_months)?Number(estimatedAnnualSalary(draft.monthly_salary,draft.salary_months)).toLocaleString("zh-CN")+" 元／年":"填写明确月薪和发薪月数后自动计算"}</p></div>
        <label className={LABEL}>标签（逗号分隔）<input className={INPUT} value={String(draft.tags_text??draft.tags.join("，"))} onChange={e=>{change("tags",e.target.value.split(/[,，、]/).filter(Boolean));setDraft(previous=>previous?{...previous,tags_text:e.target.value}:previous);}}/></label>
        <section aria-label="职位描述" className="space-y-2"><h3 className="text-xs text-muted">职位描述{draft.job_id?"（官网信息）":""}</h3><div className="whitespace-pre-wrap text-[13px] leading-6 max-h-72 overflow-auto rounded-xl bg-paper p-4">{draft.jd||"暂无职位描述"}</div></section>
        <label className={LABEL}>申请备注<textarea aria-label="申请备注" className={INPUT+" min-h-28"} value={draft.notes||""} onChange={e=>change("notes",e.target.value)}/></label>
        <div className="flex justify-between items-center"><label className="text-xs text-muted flex gap-2"><input type="checkbox" checked={draft.archived} onChange={e=>change("archived",e.target.checked)}/>归档此申请（记录仍保留）</label><button className="rounded-lg bg-accent text-white px-4 py-2 text-sm" disabled={busy}>保存申请信息</button></div>
      </form>
      <section id="application-interviews" className="border-t border-line pt-5 space-y-3 scroll-mt-36"><div className="flex justify-between items-center"><h3 className="font-semibold text-sm">真实面试与面经</h3><button className={BUTTON} onClick={()=>beginRound()}>新增面试</button></div>{/* 产品说明移至代码：每轮分别记录时间、结果和复盘；一面完成不代表通过。模拟面试不会自动写成真实招聘进展。 */}
      {(detail?.interviews||[]).map(interview=><article key={interview.id} className="rounded-xl bg-paper p-4"><div className="flex justify-between items-start"><div><h4 className="font-medium text-sm">{interview.round_name}</h4><p className="text-xs text-muted mt-1">{chinaDate(interview.scheduled_at,true)||"时间未记录"} · {ROUND_RESULT[interview.result]}</p></div><div className="flex gap-4"><button className="text-sm text-accent" aria-label={`编辑${interview.round_name}`} onClick={()=>beginRound(interview)}>编辑</button><button className="text-sm text-danger" aria-label={`删除${interview.round_name}`} disabled={busy} onClick={()=>void deleteRound(interview)}>删除</button></div></div><p className="mt-3 text-[13px] leading-6 whitespace-pre-wrap">{interviewNotes(interview)||"尚未填写面经"}</p></article>)}
      {!detail?.interviews?.length&&!round&&<p className="text-xs text-muted py-3">尚未记录真实面试，点击新增面试开始记录。</p>}
      {round&&<form aria-label="真实面试记录" className="rounded-xl border border-line p-4 space-y-3" onSubmit={e=>void saveRound(e)}>
        <div className="grid grid-cols-2 gap-3"><label className={LABEL}>面试轮次<select aria-label="面试轮次" className={INPUT} value={String(round.round_name)} onChange={e=>{setRound(previous=>({...previous,round_name:e.target.value}));setRoundDirty(true);}}>{!!round.round_name&&!Object.prototype.hasOwnProperty.call(ROUNDS,String(round.round_name))&&<option value={String(round.round_name)}>{String(round.round_name)}（原记录）</option>}<Options values={ROUNDS}/></select></label>
        {([['kind','面试类型',ROUND_KIND],['result','本轮结果',ROUND_RESULT]] as const).map(([key,label,values])=><label className={LABEL} key={key}>{label}<select aria-label={label} className={INPUT} value={String(round[key])} onChange={e=>{setRound(previous=>({...previous,[key]:e.target.value}));setRoundDirty(true);}}><Options values={values}/></select></label>)}<InterviewDateInput key={String(round.id||"new")} value={round.scheduled_at} onChange={value=>{setRound(previous=>({...previous,scheduled_at:value}));setRoundDirty(true);}}/></div>
        <label className={LABEL}>面经<textarea aria-label="面经" className={INPUT+" min-h-44"} placeholder="自由记录本轮问题、回答和心得…" value={String(round.experience_notes||"")} onChange={e=>{setRound(previous=>({...previous,experience_notes:e.target.value}));setRoundDirty(true);}}/></label>
        <div className="flex gap-2 justify-end"><button className={BUTTON} type="button" onClick={cancelRound}>取消</button><button className="rounded-lg bg-accent text-white px-4 py-2 text-sm" disabled={busy}>保存</button></div>
      </form>}

      </section>
      <details id="application-history" className="border-t border-line pt-4 text-xs scroll-mt-36"><summary className="text-muted cursor-pointer">查看进度历史</summary><ol className="mt-3 space-y-2">{detail?.history?.map(event=><li key={event.id}>{chinaDate(event.occurred_at)} · {event.summary}</li>)}</ol></details>
      </>:<p className="text-sm text-muted">正在读取申请详情…</p>}</div>
    </section></div>}
  </main>;
}

function GroupRows({name,group,records,columns,selected,setSelected,open,save}:{name:string;group:string;records:Application[];columns:[string,string][];selected:Set<string>;setSelected:React.Dispatch<React.SetStateAction<Set<string>>>;open:(id:string)=>void;save:(record:Application,patch:Record<string,unknown>)=>Promise<void>}) {
  return <>{group&&<tr><td colSpan={columns.length+1} className="bg-paper px-4 py-2 font-medium">{APPLICATION_STATUS[name]||PRIORITY[name]||name} · 本页{records.length}条</td></tr>}{records.map(record=><tr key={record.id} className="border-b border-line hover:bg-paper/50"><td className="application-frozen px-3 py-2" style={{left:0}}><input aria-label={`勾选申请：${record.title}`} type="checkbox" checked={selected.has(record.id)} onChange={e=>setSelected(previous=>{const next=new Set(previous);if(e.target.checked)next.add(record.id);else next.delete(record.id);return next;})}/></td>{columns.map(([key])=><td key={key} data-application-column={key} style={{left:frozenOffset(key)}} className={"px-2 py-2 "+(frozenOffset(key)!==undefined?"application-frozen":"")}>{key==="title"?<button className="text-left text-accent font-medium max-w-[260px]" onClick={()=>open(record.id)}>{record.title}</button>:key==="company"?<span className="font-medium px-1.5">{record.company}</span>:<InlineCell record={record} field={key} save={save}/>}</td>)}</tr>)}</>;
}
