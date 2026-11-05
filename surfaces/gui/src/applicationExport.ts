import * as XLSX from "xlsx";
import { APPLICATION_STATUS, PRIORITY, RECRUITMENT, ARRANGEMENT, ROUND_RESULT, ROUND_KIND, INTERVIEW_FORMAT, chinaDate, type ApplicationExport } from "./applications";

/** Preserve every code point and newline; reserve room below Excel's hard limits. */
export function splitExcelText(text: string): string[] {
  const parts: string[] = [];
  let current = "", lines = 0;
  for (const char of text) {
    if (current.length + char.length > 30000 || lines + (char === "\n" ? 1 : 0) > 250) {
      parts.push(current); current = ""; lines = 0;
    }
    current += char;
    if (char === "\n") lines++;
  }
  if (current || !parts.length) parts.push(current);
  return parts;
}

type Column = [string,string];
const APP_COLUMNS: Column[] = [["id","申请编号"],["company","公司"],["title","岗位名称"],["location","工作地点"],["recruitment_type","招聘类型"],["batch","招聘批次"],["status","申请状态"],["stage","当前阶段"],["priority","优先级"],["applied_on","投递日期"],["applied_date_source","投递日期来源"],["next_action","下一步"],["next_at","下次时间（北京时间）"],["deadline_on","截止日期"],["next_done","下一步已完成"],["monthly_salary","月薪酬"],["salary_months","发薪月数"],["annual_salary","预计年薪酬（元／年）"],["salary_advertised","历史岗位公布薪资"],["salary_expected","个人期望薪资"],["salary_offer","实际Offer报价"],["offer_currency","Offer币种"],["offer_period","Offer计薪周期"],["offer_months","Offer发薪月数"],["resume_label","投出简历版本"],["resume_sha256","简历版本指纹"],["source_url","原始链接"],["channel","来源渠道"],["department","部门"],["business_line","业务线"],["tags","标签"],["notes","申请备注"],["jd","职位描述"],["archived","已归档"],["created_at","创建时间（北京时间）"],["updated_at","更新时间（北京时间）"]];
const ROUND_COLUMNS: Column[] = [["application_id","申请编号"],["id","面试编号"],["round_name","轮次名称"],["round_number","轮次序号"],["kind","面试类型"],["format","面试形式"],["scheduled_at","面试日期（北京时间）"],["arrangement","安排状态"],["result","本轮结果"],["questions","面试问题"],["answers","回答要点"],["experience_notes","面经"],["review","面试复盘"],["knowledge_gaps","待补知识"],["next_step","面试后下一步"]];
const MAPS: Record<string,Record<string,string>> = {applied_date_source:{legacy_tracking:"旧系统记录，待核对",user_confirmed:"用户填写",unknown:"未记录"},status:APPLICATION_STATUS,priority:PRIORITY,recruitment_type:RECRUITMENT,arrangement:ARRANGEMENT,result:ROUND_RESULT,kind:ROUND_KIND,format:INTERVIEW_FORMAT,offer_period:{month:"月薪",year:"年薪",day:"日薪",unknown:"未记录"}};

export function buildApplicationWorkbook(payload: ApplicationExport): XLSX.WorkBook {
  const book = XLSX.utils.book_new();
  const longRows: unknown[][] = [["申请编号","面试编号","字段","段号","正文"]];
  function text(value: unknown, key: string): string {
    if (value === null || value === undefined) return "";
    if (typeof value === "boolean") return value ? "是" : "否";
    if (Array.isArray(value)) return value.join("、");
    if (key==="scheduled_at") return chinaDate(value,true);
    if (["next_at","created_at","updated_at"].includes(key)) return chinaDate(value);
    return MAPS[key]?.[String(value)] ?? String(value);
  }
  function table(records: Record<string,unknown>[], columns: Column[], interview: boolean): unknown[][] {
    return [columns.map(column=>column[1]), ...records.map(record=>columns.map(([key,label])=>{
      const value = text(record[key],key);
      const parts = splitExcelText(value);
      const full = ["jd","questions","answers","experience_notes","review","knowledge_gaps","next_step"].includes(key);
      if (value && (full || parts.length>1)) {
        parts.forEach((part,index)=>longRows.push([interview ? record.application_id : record.id,interview ? record.id : "",label,index+1,part]));
        return `全文见「职位描述与面经」：${label}（${parts.length}段）`;
      }
      return value;
    }))];
  }
  function sheet(name: string, rows: unknown[][]): void {
    // Explicit text cells, never formulas or external workbook references.
    const data = rows.map(row=>row.map(value=>({t:"s" as const,v:String(value ?? "")})));
    const result = XLSX.utils.aoa_to_sheet(data);
    result["!cols"] = rows[0].map((_,i)=>({wch: name === "职位描述与面经" && i===4 ? 100 : i===0 ? 38 : 24}));
    if (rows.length>1) result["!autofilter"] = {ref:XLSX.utils.encode_range({s:{r:0,c:0},e:{r:rows.length-1,c:rows[0].length-1}})};
    XLSX.utils.book_append_sheet(book,result,name);
  }
  sheet("申请总表",table(payload.applications,APP_COLUMNS,false));
  const sourceColumn = APP_COLUMNS.findIndex(([key])=>key==="source_url");
  payload.applications.forEach((application,index)=>{
    try {
      const url = new URL(application.source_url);
      if (["http:","https:"].includes(url.protocol) && !url.username && !url.password) {
        book.Sheets["申请总表"][XLSX.utils.encode_cell({r:index+1,c:sourceColumn})].l = {Target:url.href};
      }
    } catch {/* Invalid or absent links remain ordinary text. */}
  });
  sheet("面试记录",table(payload.interviews,ROUND_COLUMNS,true));
  sheet("职位描述与面经",longRows);
  sheet("字段说明",[["项目","说明"],["导出时间",chinaDate(payload.generated_at)],["导出申请数量",payload.total],["时间口径","所有时间按北京时间（Asia/Shanghai）显示；日期未知保持空白"],["数据范围","仅本人选择的申请及关联真实面试；包括筛选范围的所有分页"],["长文本","按申请编号、面试编号、字段及段号拼接正文，可还原完整JD和面经；不静默截断"],["阶段与结果","一面完成不代表通过，真实招聘面试与模拟面试分开"],["薪资","岗位公布、个人期望与实际Offer分别保存，金额与单位以本人记录为准"],["简历版本","保存版本名称与指纹，不包含简历原件；原件移除后不会偷偷保留副本"],["文件用途","可携带的求职记录；不包含软件视图、模型密钥或会话凭据，完整备份仍需保留本地数据目录"]]);
  return book;
}

export function downloadApplicationWorkbook(payload: ApplicationExport): void {
  XLSX.writeFileXLSX(buildApplicationWorkbook(payload),`OpenCareer求职进度_${chinaDate(payload.generated_at,true)}.xlsx`);
}
