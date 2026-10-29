import { useEffect, useState, type FormEvent } from "react";
import { careerCatalogRequest, type CatalogCondition, type CatalogQuery, type CatalogSchema } from "../api";

export function describeCondition(condition: CatalogCondition): string {
  const values: Record<string,string> = {bytedance:"字节跳动",xiaomi:"小米",tencent:"腾讯",alibaba:"阿里巴巴",deepseek:"DeepSeek",meituan:"美团",kuaishou:"快手",xiaohongshu:"小红书",moonshot:"月之暗面",zhipu:"智谱 AI",didi:"滴滴出行",product:"产品",algorithm:"算法",engineering:"研发",operations:"运营",design:"设计",other:"其他",strategy_product:"策略产品",evaluation_product:"评测产品",commercial_product:"商业化产品",growth_product:"增长产品",platform_product:"平台产品",ai_product:"AI 产品",recommendation:"推荐算法",search:"搜索算法",advertising:"广告算法",nlp:"自然语言算法",multimodal:"多模态算法",llm_training:"大模型训练",llm_inference:"大模型推理",active:"在招",inactive:"已下线",experienced:"社会招聘",campus:"校园招聘",internship:"实习"};
  const labels: Record<string,string> = { company: "公司", locations: "城市", recruitment_type: "招聘类型", job_family: "岗位职能", directions: "细分方向", business_lines: "官方业务线", business_line_candidates: "业务方向（规则推断）", official_department: "官网部门", title: "岗位标题", text: "职位原文", first_seen_at: "首次发现", published_at: "官网发布日期", status: "岗位状态" };
  if (Array.isArray(condition.all)) return condition.all.map(c => describeCondition(c as CatalogCondition)).join("；") || "全部在招岗位";
  if (Array.isArray(condition.any)) return "满足任一：" + condition.any.map(c => describeCondition(c as CatalogCondition)).join(" / ");
  if (condition.not) return "排除（" + describeCondition(condition.not as CatalogCondition) + "）";
  return `${labels[String(condition.field)] || condition.field}：${Array.isArray(condition.values) ? condition.values.map(v => values[String(v)] || v).join("、") : "未知"}`;
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
      conditions.push({field: values.date_field || "first_seen_at", op:"between",values:[values.date_from+"T00:00:00+08:00",end.toISOString().slice(0,10)+"T00:00:00+08:00"]});
    }
    setError("");
    onSubmit({condition: {all: conditions}, today, semantic_query: values.semantic?.trim() || null});
  };
  const inputClass = "rounded-lg border border-line bg-panel px-3 py-2 text-sm w-full";
  return <form onSubmit={submit} className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-4 border border-line rounded-xl bg-paper" aria-label="组合岗位筛选">
    <label>公司<select aria-label="公司" className={inputClass} value={values.company || ""} onChange={e => update("company", e.target.value)}><option value="">全部公司</option>{schema?.companies.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
    <label>工作城市<input className={inputClass} value={values.locations || ""} placeholder="北京、上海" onChange={e => update("locations", e.target.value)} /></label>
    <label>招聘类型<select aria-label="招聘类型" className={inputClass} value={values.recruitment_type || ""} onChange={e => update("recruitment_type", e.target.value)}><option value="">实习／校招／社招均可</option>{schema?.recruitment_types?.map(t => <option key={t.value} value={t.value}>{{internship:"实习",campus:"校园招聘",experienced:"社会招聘",social:"社会招聘"}[t.value] || t.value}</option>)}</select></label>
    <label>岗位职能<select aria-label="岗位职能" className={inputClass} value={values.job_family || ""} onChange={e => update("job_family", e.target.value)}><option value="">全部职能</option>{Object.entries(schema?.job_families || {}).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label>细分方向<select aria-label="细分方向" className={inputClass} value={values.directions || ""} onChange={e => update("directions", e.target.value)}><option value="">全部方向</option>{Object.entries(schema?.directions || {}).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label>官方业务线<input className={inputClass} placeholder="未知不会推测" value={values.business_lines || ""} onChange={e => update("business_lines", e.target.value)} /></label>
    <label>业务方向（规则推断）<input className={inputClass} placeholder="例如抖音、飞书；不是官方归属" value={values.business_line_candidates || ""} onChange={e => update("business_line_candidates", e.target.value)} /></label>
    <label>官网部门<input className={inputClass} value={values.official_department || ""} onChange={e => update("official_department", e.target.value)} /></label>
    <label>包含关键词<input className={inputClass} value={values.text || ""} onChange={e => update("text", e.target.value)} /></label>
    <label>排除关键词<input className={inputClass} value={values.exclude || ""} onChange={e => update("exclude", e.target.value)} /></label>
    <label>按需语义判断<input className={inputClass} placeholder="可选，会调用已配置的模型" value={values.semantic || ""} onChange={e => update("semantic", e.target.value)} /></label>
    <label>日期口径<select aria-label="日期口径" className={inputClass} value={values.date_field || "first_seen_at"} onChange={e => update("date_field", e.target.value)}><option value="first_seen_at">公共目录首次发现</option><option value="published_at">官网发布日期（可能未知）</option></select></label>
    <label>开始日期<input className={inputClass} type="date" value={values.date_from || ""} onChange={e => {update("date_from",e.target.value);setToday(false);}} /></label>
    <label>结束日期（含当天）<input className={inputClass} type="date" value={values.date_to || ""} onChange={e => {update("date_to",e.target.value);setToday(false);}} /></label>
    <label className="col-span-2 text-xs flex gap-2 items-center"><input type="checkbox" checked={today} onChange={e => {setToday(e.target.checked);setValues(p => ({...p,date_from:"",date_to:""}));}} />仅今天首次发现（北京时间）；不是首次下载时间</label>
    {error && <p role="alert" className="col-span-full text-danger text-sm">{error}</p>}
    <button type="submit" className="rounded-lg bg-accent text-white px-4 py-2">应用筛选</button>
    <p className="col-span-full text-xs text-muted">业务线仅采用明确字段；规则分类和模型判断会标注依据。语义判断每次最多100个候选，结果可能不完整。</p>
  </form>;
}
