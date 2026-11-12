import {cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {CareerQueryActions} from "./CareerQueryActions";
const { request, getJob } = vi.hoisted(() => ({request: vi.fn(), getJob: vi.fn()}));
vi.mock("../api",()=>({isLocal:()=>true, careerCatalogRequest:request, getCareerJob:getJob}));
afterEach(()=>{cleanup();sessionStorage.clear();vi.resetAllMocks();});
it("carries the same complex query and subscription time into the draft without sending",async()=>{
 request.mockResolvedValue(undefined);
 const query={condition:{all:[{field:"company",op:"in",values:["bytedance"]},{not:{field:"recruitment_type",op:"in",values:["internship"]}}]},today:true,semantic_query:null};
 const opened=vi.fn();window.addEventListener("opencareer:catalog-open",opened);
 render(<CareerQueryActions tools={[{kind:"tool",id:"one",name:"mcp__career__search_job_catalog",status:"ok",args:query},{kind:"tool",id:"two",name:"mcp__career__draft_job_subscription",status:"ok",args:{...query,title:"产品日报",send_time:"08:30"}}]}/>);
 fireEvent.click(screen.getByRole("button",{name:"配置岗位订阅"}));expect(JSON.parse(sessionStorage.getItem("opencareer-subscription-query")!)).toEqual({title:"产品日报",send_time:"08:30"});expect(JSON.parse(sessionStorage.getItem("opencareer-catalog-query")!)).toEqual(query);expect(opened).toHaveBeenCalledTimes(1);
 window.removeEventListener("opencareer:catalog-open",opened);
});

it("reopens a saved tool draft by its identifier without creating a duplicate",()=>{
 render(<CareerQueryActions tools={[{kind:"tool",id:"draft",name:"mcp__career__draft_job_subscription",status:"ok",args:{condition:{all:[]},title:"日报",channel_ids:["channel"]},preview:JSON.stringify({ok:true,data:{id:"existing-draft"}})}]}/>);
 fireEvent.click(screen.getByRole("button",{name:"配置岗位订阅"}));
 expect(JSON.parse(sessionStorage.getItem("opencareer-subscription-query")!)).toEqual({title:"日报",channel_ids:["channel"],subscription_id:"existing-draft"});
});

it("keeps the authoritative draft when example searches and a later list call use different conditions",()=>{
 request.mockResolvedValue(undefined);
 const query={condition:{all:[{field:"company",op:"in",values:["bytedance"]},{field:"locations",op:"in",values:["北京"]},{field:"job_family",op:"in",values:["product"]}]},today:false};
 const sample={condition:{all:[...query.condition.all,{field:"recruitment_type",op:"in",values:["internship"]}]}};
 render(<CareerQueryActions tools={[
  {kind:"tool",id:"all",name:"mcp__career__search_job_catalog",status:"ok",args:query},
  {kind:"tool",id:"sample",name:"mcp__career__search_job_catalog",status:"ok",args:sample},
  {kind:"tool",id:"draft",name:"mcp__career__draft_job_subscription",status:"ok",args:{...query,title:"三种招聘类型",send_time:"09:00",channel_ids:[]}},
  {kind:"tool",id:"list",name:"mcp__career__list_job_subscriptions",status:"ok",args:{}},
 ]}/>);
 fireEvent.click(screen.getByRole("button",{name:"配置岗位订阅"}));
 expect(JSON.parse(sessionStorage.getItem("opencareer-catalog-query")!)).toEqual(query);
 expect(JSON.parse(sessionStorage.getItem("opencareer-subscription-query")!)).toEqual({title:"三种招聘类型",send_time:"09:00",channel_ids:[]});
});

it("preserves legacy links and hides the more action for a short list", () => {
  const text = [
    "共找到两个岗位。", "", "**代表岗位（官网可直达）**", "",
    "1. **策略产品** | 北京 | [官网](https://jobs.example/one)",
    "2. **评测产品** | 北京 | [官网](https://jobs.example/two)",
    "", "请以官网状态为准。",
  ].join("\n");
  render(<CareerQueryActions text={text} tools={[
    {kind:"tool",id:"search",name:"mcp__career__search_job_catalog",status:"ok",args:{}},
  ]}/>);
  const card = within(screen.getByRole("region", {name:"代表岗位"}));
  expect(card.getAllByRole("listitem")).toHaveLength(2);
  expect(card.getAllByRole("link").map(link => link.getAttribute("href"))).toEqual([
    "https://jobs.example/one", "https://jobs.example/two",
  ]);
  expect(card.queryByRole("button", {name:"查看更多岗位"})).toBeNull();
  expect(card.getByRole("button", {name:"配置岗位订阅"})).toBeTruthy();
  expect(screen.getByText("请以官网状态为准。")).toBeTruthy();
});

it.each([9, 10, 11])("renders up to ten structured jobs for %i matches", async total => {
  const id = total.toString(16).repeat(32);
  const query = {condition:{all:[]},today:true};
  const jobs = Array.from({length:total}, (_, i) => ({
    id: `case-${total}-${i}`, title: `产品岗位 ${i+1}`, locations:["北京"], recruitment_type:"internship", source_url:`https://jobs.example/${i}`,
  }));
  request.mockResolvedValue({total,jobs,offset:0});
  getJob.mockResolvedValue({job:{responsibilities:["负责岗位产品策略和评测。"]}});
  render(<CareerQueryActions text="查询完成。" tools={[
    {kind:"tool",id:"search",name:"mcp__career__search_job_catalog",status:"ok",args:query,preview:`{"result_id":"${id}"`},
  ]}/>);
  const card = within(await screen.findByRole("region",{name:"代表岗位"}));
  expect(card.getAllByRole("listitem")).toHaveLength(Math.min(total,10));
  expect(card.getAllByRole("link",{name:"官网投递"})).toHaveLength(Math.min(total,10));
  expect(await card.findAllByText("负责岗位产品策略和评测。")).toHaveLength(Math.min(total,10));
  const more = card.queryByRole("button",{name:"查看更多岗位"});
  if (total > 10) {
    fireEvent.click(more!);
    expect(JSON.parse(sessionStorage.getItem("opencareer-catalog-query")!)).toEqual(query);
  } else expect(more).toBeNull();
});

it("uses the search referenced by the answer when a later search covers only a subset", async () => {
  const fullId = "d".repeat(32);
  const subsetId = "e".repeat(32);
  const fullQuery = {condition:{all:[]}};
  const subsetQuery = {condition:{field:"recruitment_type",op:"in",values:["internship"]}};
  const fullJobs = Array.from({length:10}, (_, i) => ({
    id: String(i), title: `岗位 ${i+1}`, locations:["北京"], recruitment_type:"campus", source_url:`https://jobs.example/${i}`,
  }));
  request.mockImplementation(async (path: string) => ({
    jobs:fullJobs,total:path.endsWith(fullId) ? 46 : 12,offset:0,
  }));
  getJob.mockResolvedValue({});
  render(<CareerQueryActions text={"查询结果 = 46 个岗位。\n\n**代表岗位**\n\n1. [官网](https://jobs.example/9)"} tools={[
    {kind:"tool",id:"full",name:"search_job_catalog",status:"ok",args:fullQuery,preview:JSON.stringify({result_id:fullId})},
    {kind:"tool",id:"subset",name:"search_job_catalog",status:"ok",args:subsetQuery,preview:JSON.stringify({result_id:subsetId})},
  ]}/>);
  expect(await screen.findByText("共 46 个")).toBeTruthy();
  expect(screen.getAllByRole("link",{name:"官网投递"})[0].getAttribute("href")).toBe("https://jobs.example/9");
  fireEvent.click(screen.getByRole("button",{name:"查看更多岗位"}));
  expect(JSON.parse(sessionStorage.getItem("opencareer-catalog-query")!)).toEqual(fullQuery);
});
