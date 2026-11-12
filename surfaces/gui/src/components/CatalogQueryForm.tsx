import {DateInput} from "./DateInput";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { OcSelect } from "./OcSelect";
import { careerJobTypeLabel, careerJobTypeTone } from "../careerJobLabels";
import { careerCatalogRequest, type CatalogCondition, type CatalogQuery, type CatalogSchema } from "../api";

const VALUE_LABELS: Record<string,string> = {bytedance:"字节跳动",xiaomi:"小米",tencent:"腾讯",alibaba:"阿里巴巴",deepseek:"DeepSeek",meituan:"美团",kuaishou:"快手",xiaohongshu:"小红书",moonshot:"月之暗面",zhipu:"智谱 AI",didi:"滴滴出行",product:"产品",algorithm:"算法",engineering:"研发",operations:"运营",design:"设计",other:"其他",strategy_product:"策略产品",evaluation_product:"评测产品",commercial_product:"商业化产品",growth_product:"增长产品",platform_product:"平台产品",ai_product:"AI 产品",recommendation:"推荐算法",search:"搜索算法",advertising:"广告算法",nlp:"自然语言算法",multimodal:"多模态算法",llm_training:"大模型训练",llm_inference:"大模型推理",active:"在招",inactive:"已下线",experienced:"社会招聘",campus:"校园招聘",internship:"实习"};
const FIELD_LABELS: Record<string,string> = { company: "公司", locations: "城市", recruitment_type: "招聘类型", job_family: "岗位职能", directions: "细分方向", business_lines: "官方业务线", business_line_candidates: "业务方向（规则推断）", official_department: "官网部门", title: "岗位标题", text: "职位原文", new_at: "新增", updated_at: "更新", reopened_at: "重新开放", backfilled_at: "历史补录", published_at: "官网发布日期", status: "岗位状态" };
const values = VALUE_LABELS, labels = FIELD_LABELS;

export function describeCondition(condition: CatalogCondition): string {
  if (Array.isArray(condition.all)) return condition.all.map(c => describeCondition(c as CatalogCondition)).join("；") || "全部在招岗位";
  if (Array.isArray(condition.any)) return "满足任一：" + condition.any.map(c => describeCondition(c as CatalogCondition)).join(" / ");
  if (condition.not) return "排除（" + describeCondition(condition.not as CatalogCondition) + "）";
  return `${labels[String(condition.field)] || condition.field}：${Array.isArray(condition.values) ? condition.values.map(v => values[String(v)] || v).join("、") : "未知"}`;
}

const DATE_FIELDS = new Set(["new_at","updated_at","reopened_at","backfilled_at","published_at"]);
function valueText(field: string, value: unknown): string {
  const text = String(value);
  if (DATE_FIELDS.has(field)) return text.slice(0, 10);
  return VALUE_LABELS[text] || text;
}
function leafText(condition: CatalogCondition): string {
  const field = String(condition.field);
  const items = Array.isArray(condition.values) ? condition.values.map(v => valueText(field, v)) : [];
  const joined = condition.op === "between" && items.length === 2 ? `${items[0]} 至 ${items[1]}` : items.join("、");
  return `${FIELD_LABELS[field] || field}：${joined}`;
}

/** Structured, scannable view of a catalog condition: one row per field with value tags. */
export function ConditionChips({ condition, today, semanticQuery, includeInactive, inline }: { condition: CatalogCondition; today?: boolean; semanticQuery?: string | null; includeInactive?: boolean; inline?: boolean }) {
  const rows: { label: string; node: ReactNode }[] = [];
  const add = (item: CatalogCondition) => {
    if (Array.isArray(item.all)) { item.all.forEach(child => add(child as CatalogCondition)); return; }
    if (Array.isArray(item.any)) {
      rows.push({ label: "满足任一", node: item.any.map((child, index) => <span key={index} className="contents">{index > 0 && <span className="oc-cond-or">或</span>}<span className="oc-cond-value">{Array.isArray((child as CatalogCondition).any) || Array.isArray((child as CatalogCondition).all) ? describeCondition(child as CatalogCondition) : leafText(child as CatalogCondition)}</span></span>) });
      return;
    }
    if (item.not) { rows.push({ label: "排除", node: <span className="oc-cond-value is-exclude">{describeCondition(item.not as CatalogCondition)}</span> }); return; }
    const field = String(item.field);
    const list = Array.isArray(item.values) ? item.values : [];
    const node = item.op === "between" && list.length === 2
      ? <span className="oc-cond-value">{valueText(field, list[0])} 至 {valueText(field, list[1])}</span>
      : list.map((value, index) => <span key={index} className="oc-cond-value">{valueText(field, value)}</span>);
    rows.push({ label: (FIELD_LABELS[field] || field) + (item.op === "contains" ? "包含" : ""), node });
  };
  add(condition);
  if (today) rows.push({ label: "时间", node: <span className="oc-cond-value">每天当天新增</span> });
  if (includeInactive) rows.push({ label: "岗位状态", node: <span className="oc-cond-value">包含已下线岗位</span> });
  if (semanticQuery) rows.push({ label: "语义判断", node: <span className="oc-cond-value">{semanticQuery}</span> });
  if (!rows.length) return <p className="text-[12.5px] text-muted">全部在招岗位</p>;
  return <dl className={"oc-cond" + (inline ? " is-inline" : "")}>{rows.map((row, index) => <div key={index} className="oc-cond-row"><dt>{row.label}</dt><dd>{row.node}</dd></div>)}</dl>;
}

export function CatalogQueryForm({ onSubmit }: { onSubmit: (query: CatalogQuery) => void }) {
  const [schema, setSchema] = useState<CatalogSchema | null>(null);
  const [values, setValues] = useState<Record<string,string>>({});
  const [today, setToday] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let live = true; careerCatalogRequest<CatalogSchema>("catalog/schema").then(s => { if (live) setSchema(s); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, []);
  const update = (key: string, value: string) => setValues(p => ({...p, [key]: value}));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const conditions: CatalogCondition[] = [];
    for (const field of ["company", "locations", "job_family", "directions", "business_lines", "business_line_candidates", "official_department", "text", "recruitment_type"]) {
      if (values[field]?.trim()) conditions.push({field, op: field === "text" || field === "official_department" ? "contains" : "in", values: values[field].split(/[、,，]/).map(v => v.trim()).filter(Boolean)});
    }
    if (values.exclude?.trim()) conditions.push({not: {field: "text", op: "contains", values: values.exclude.split(/[、,，]/).map(v => v.trim()).filter(Boolean)}});
    if (values.date_from || values.date_to) {
      if (!values.date_from || !values.date_to || values.date_from > values.date_to) { setError("请选择完整且有效的日期范围。"); return; }
      const end = new Date(values.date_to + "T00:00:00Z"); end.setUTCDate(end.getUTCDate()+1);
      conditions.push({field: values.date_field || "new_at", op:"between",values:[values.date_from+"T00:00:00+08:00",end.toISOString().slice(0,10)+"T00:00:00+08:00"]});
    }
    setError("");
    onSubmit({condition: {all: conditions}, today, semantic_query: values.semantic?.trim() || null});
  };
  const inputClass = "oc-field";
  return <form onSubmit={submit} className="oc-form-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3.5 p-4 sm:p-5 border border-line rounded-[14px] bg-[color-mix(in_srgb,var(--paper)_55%,var(--panel))]" aria-label="组合岗位筛选">
    <div className="oc-form-label">公司<OcSelect ariaLabel="公司" searchable value={values.company || ""} onChange={v => update("company", v)} options={[{value:"",label:"全部公司"},...(schema?.companies || []).map(c => ({value:c.slug,label:c.name}))]} /></div>
    <label>工作城市<input className={inputClass} value={values.locations || ""} placeholder="北京、上海" onChange={e => update("locations", e.target.value)} /></label>
    <div className="oc-form-label">招聘类型<OcSelect ariaLabel="招聘类型" value={values.recruitment_type || ""} onChange={v => update("recruitment_type", v)} options={[{value:"",label:"实习／校招／社招均可"},...(schema?.recruitment_types || []).map(t => ({value:t.value,label:careerJobTypeLabel(t.value) === "类型未标注" ? t.value : careerJobTypeLabel(t.value),tone:careerJobTypeTone(t.value) || undefined}))]} /></div>
    <div className="oc-form-label">岗位职能<OcSelect ariaLabel="岗位职能" value={values.job_family || ""} onChange={v => update("job_family", v)} options={[{value:"",label:"全部职能"},...Object.entries(schema?.job_families || {}).map(([k,v]) => ({value:k,label:v}))]} /></div>
    <div className="oc-form-label">细分方向<OcSelect ariaLabel="细分方向" value={values.directions || ""} onChange={v => update("directions", v)} options={[{value:"",label:"全部方向"},...Object.entries(schema?.directions || {}).map(([k,v]) => ({value:k,label:v}))]} /></div>
    <label>官方业务线<input className={inputClass} placeholder="未知不会推测" value={values.business_lines || ""} onChange={e => update("business_lines", e.target.value)} /></label>
    <label>业务方向（规则推断）<input className={inputClass} placeholder="例如抖音、飞书；不是官方归属" value={values.business_line_candidates || ""} onChange={e => update("business_line_candidates", e.target.value)} /></label>
    <label>官网部门<input className={inputClass} value={values.official_department || ""} onChange={e => update("official_department", e.target.value)} /></label>
    <label>包含关键词<input className={inputClass} value={values.text || ""} onChange={e => update("text", e.target.value)} /></label>
    <label>排除关键词<input className={inputClass} value={values.exclude || ""} onChange={e => update("exclude", e.target.value)} /></label>
    <label>按需语义判断<input className={inputClass} placeholder="可选，会调用已配置的模型" value={values.semantic || ""} onChange={e => update("semantic", e.target.value)} /></label>
    <div className="oc-form-label">日期口径<OcSelect ariaLabel="日期口径" value={values.date_field || "new_at"} onChange={v => update("date_field", v)} options={[{value:"new_at",label:"新增岗位",hint:"连续采集中首次出现"},{value:"updated_at",label:"岗位内容更新"},{value:"reopened_at",label:"重新开放"},{value:"backfilled_at",label:"历史补录"},{value:"published_at",label:"官网发布日期",hint:"部分来源可能未知"}]} /></div>
    <label>开始日期<DateInput label="开始日期" value={values.date_from || ""} onChange={date => {update("date_from",date||"");setToday(false);}} /></label>
    <label>结束日期（含当天）<DateInput label="结束日期（含当天）" value={values.date_to || ""} onChange={date => {update("date_to",date||"");setToday(false);}} /></label>
    <label className="oc-inline sm:col-span-2 lg:col-span-3 text-xs"><input type="checkbox" checked={today} onChange={e => {setToday(e.target.checked);setValues(p => ({...p,date_from:"",date_to:""}));}} />仅今天新增（北京时间）；初次同步与中断补录不计为新增</label>
    {error && <p role="alert" className="col-span-full text-danger text-sm">{error}</p>}
    <div className="col-span-full flex flex-wrap items-center justify-between gap-3 pt-1">
    <p className="text-xs text-muted">{/* 产品说明移至代码：业务线仅采用明确字段；规则分类和模型判断会标注依据。语义判断每次最多100个候选，结果可能不完整。 */}语义评估每次最多100个候选。</p>
    <button type="submit" className="oc-btn oc-btn-primary">应用筛选</button>
    </div>
  </form>;
}
