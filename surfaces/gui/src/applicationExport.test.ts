import { expect, it } from "vitest";
import * as XLSX from "xlsx";
import { buildApplicationWorkbook, splitExcelText } from "./applicationExport";
import type { ApplicationExport } from "./applications";

it("writes a real four-sheet workbook and preserves long text as text rather than formulas", () => {
  const text = "面试复盘😀\n".repeat(9000);
  const payload = {applications:[{id:"application-1",company:"示例公司",title:"=HYPERLINK(\"https://example.com\")",jd:text,tags:["产品"],status:"interviewing",notes:"原进度备注"}],interviews:[{id:"interview-1",application_id:"application-1",round_name:"业务二面",result:"pending",review:text}],generated_at:"2026-10-30T00:00:00Z",timezone:"Asia/Shanghai",total:1} as unknown as ApplicationExport;
  const book = buildApplicationWorkbook(payload);
  const reread = XLSX.read(XLSX.write(book,{type:"array",bookType:"xlsx"}),{type:"array"});
  expect(reread.SheetNames).toEqual(["申请总表","面试记录","职位描述与面经","字段说明"]);
  expect(reread.Sheets["申请总表"]["C2"].v).toBe('=HYPERLINK("https://example.com")');
  expect(reread.Sheets["申请总表"]["C2"].f).toBeUndefined();
  const rows = XLSX.utils.sheet_to_json<Record<string,unknown>>(reread.Sheets["职位描述与面经"]);
  expect(rows.filter(row=>row["字段"]==="职位描述").map(row=>row["正文"]).join("")).toBe(text);
  expect(rows.filter(row=>row["字段"]==="面试复盘").map(row=>row["正文"]).join("")).toBe(text);
});

it("preserves newlines and Unicode within Excel cell limits", () => {
  const raw = "A😀\r\n".repeat(20000);
  const parts = splitExcelText(raw);
  expect(parts.join("")).toBe(raw);
  expect(parts.every(part=>part.length<=30000 && (part.match(/\n/g)||[]).length<=250)).toBe(true);
});

it("exports the simplified monthly salary and interview notes alongside preserved historical records", () => {
  const payload={applications:[{id:"a",company:"示例",title:"产品",monthly_salary:"25000",salary_expected:"旧期望",tags:[]}],interviews:[{id:"r",application_id:"a",round_name:"二面",experience_notes:"新的自由面经",questions:"旧问题"}],generated_at:"2026-10-30T00:00:00Z",timezone:"Asia/Shanghai",total:1} as unknown as ApplicationExport;
  const book=buildApplicationWorkbook(payload);
  const rows=XLSX.utils.sheet_to_json<Record<string,unknown>>(book.Sheets["申请总表"]);
  expect(rows[0]["月薪酬"]).toBe("25000");
  expect(rows[0]["个人期望薪资"]).toBe("旧期望");
  const notes=XLSX.utils.sheet_to_json<Record<string,unknown>>(book.Sheets["职位描述与面经"]);
  expect(notes.some(row=>row["字段"]==="面经"&&row["正文"]==="新的自由面经")).toBe(true);
  expect(notes.some(row=>row["正文"]==="旧问题")).toBe(true);
});
