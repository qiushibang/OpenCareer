import { careerCatalogRequest } from "./api";

export const APPLICATION_STATUS: Record<string,string> = {not_started:"未开始",preparing:"准备投递",applied:"已投递",assessment:"笔试／测评中",interviewing:"面试中",offer:"已获 Offer",accepted:"已接受 Offer",rejected:"未通过",withdrawn:"已撤回"};
export const STAGES: Record<string,string> = {"":"未记录", "准备投递":"准备投递", "已投递":"已投递", "笔试":"笔试／测评", "一面":"一面", "二面":"二面", "三面":"三面", "四面":"四面", "待反馈":"待反馈", "Offer沟通":"Offer沟通", "已结束":"已结束"};
export const ROUNDS: Record<string,string> = {"一面":"一面", "二面":"二面", "三面":"三面", "四面":"四面"};
export function interviewNotes(record: Record<string,unknown>): string {
  if (typeof record.experience_notes === "string") return record.experience_notes;
  return [["questions","面试问题"],["answers","回答要点"],["review","面试复盘"],["knowledge_gaps","待补知识"],["next_step","下一步"]].filter(([key])=>record[key]).map(([key,label])=>`${label}\n${record[key]}`).join("\n\n");
}
export const PRIORITY: Record<string,string> = {high:"优先",normal:"普通",low:"备选"};
export const RECRUITMENT: Record<string,string> = {"":"未记录",experienced:"社会招聘",campus:"校园招聘",internship:"实习"};
export const ARRANGEMENT: Record<string,string> = {unscheduled:"待安排",scheduled:"已约时间",completed:"已完成",cancelled:"已取消"};
export const ROUND_RESULT: Record<string,string> = {pending:"待反馈",passed:"通过",failed:"未通过",unknown:"未记录"};
export const ROUND_KIND: Record<string,string> = {business:"业务面",technical:"技术面",hr:"HR面",final:"终面",extra:"加面",group:"群面",other:"其他"};
export const INTERVIEW_FORMAT: Record<string,string> = {video:"视频",phone:"电话",onsite:"现场",other:"其他"};
export interface Application {
  [key:string]: unknown;
  id: string; version: number; job_id: string|null; company: string; title: string; location: string;
  status: string; stage: string; priority: string; recruitment_type: string; batch: string;
  jd?: string; notes?: string; source_url: string; channel: string; department: string; business_line: string;
  salary_months: number|null; annual_salary: string; monthly_salary: string; salary_advertised: string; salary_expected: string; salary_offer: string;
  offer_currency: string; offer_period: string; offer_months: number|null;
  applied_on: string|null; next_action: string; next_at: string|null; deadline_on: string|null; next_done: boolean;
  tags: string[]; archived: boolean; resume_import_id: string|null; resume_label: string; resume_sha256: string;
  created_at: string; updated_at: string; interviews?: ApplicationInterview[];
  history?: {id:string;summary:string;occurred_at:string}[];
}
export interface ApplicationInterview {
  [key:string]:unknown;
  id: string; application_id: string; version: number; round_name: string; round_number: number|null;
  kind: string; format: string; scheduled_at: string|null; arrangement: string; result: string;
  questions: string; answers: string; review: string; knowledge_gaps: string; next_step: string;
}
export interface ApplicationPage {records: Application[];total:number;limit:number;offset:number;summary:{active:number;interviewing:number;offer:number}}
export interface ApplicationExport {applications:Application[];interviews:ApplicationInterview[];generated_at:string;timezone:string;total:number}
export type ApplicationFilters = Record<string,string|boolean>;
export const applicationsRequest = async <T>(path = "", body?: unknown, method?: string): Promise<T> => {
  try { return await careerCatalogRequest<T>("applications"+path,body,method); }
  catch (error) { throw new Error((error as Error).message.replace(/^[A-Z_]+：/,"")); }
};
export function chinaDate(value: unknown, dateOnly = false): string {
  if (!value) return "";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const date = new Date(String(value));
  if (Number.isNaN(date.valueOf())) return String(value);
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(date).map(p=>[p.type,p.value]));
  return `${parts.year}-${parts.month}-${parts.day}${dateOnly ? "" : ` ${parts.hour}:${parts.minute}`}`;
}
export const localDateTime = (value: unknown) => chinaDate(value).replace(" ","T");
export const fromLocalDateTime = (value: string) => value ? value+":00+08:00" : null;

export function estimatedAnnualSalary(monthly:string,months:number|null):string {
  if(!months||!Number.isInteger(months)||months<1||months>24)return "";
  const found=monthly.replace(/[,，]/g,"").match(/^\s*(\d+(?:\.\d{1,2})?)\s*(k|K|千|万|w|W)?\s*(?:元)?\s*(?:[／/]月)?\s*$/);
  if(!found)return "";
  const cents=Math.round(Number(found[1])*100)*({k:1000,K:1000,千:1000,万:10000,w:10000,W:10000}[found[2]||""]||1)*months;
  return Number.isFinite(cents)&&cents<=1e13?(cents/100).toFixed(2).replace(/\.00$/,""):"";
}
