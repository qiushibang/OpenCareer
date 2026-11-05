import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {CareerQueryActions} from "./CareerQueryActions";
vi.mock("../api",()=>({isLocal:()=>true}));
afterEach(()=>{cleanup();sessionStorage.clear();});
it("carries the same complex query and subscription time into local radar without sending",()=>{
 const query={condition:{all:[{field:"company",op:"in",values:["bytedance"]},{not:{field:"recruitment_type",op:"in",values:["internship"]}}]},today:true,semantic_query:null};
 const opened=vi.fn();window.addEventListener("opencareer:catalog-open",opened);
 render(<CareerQueryActions tools={[{kind:"tool",id:"one",name:"mcp__career__search_job_catalog",status:"ok",args:query},{kind:"tool",id:"two",name:"mcp__career__draft_job_subscription",status:"ok",args:{...query,title:"产品日报",send_time:"08:30"}}]}/>);
 fireEvent.click(screen.getByRole("button",{name:"在岗位雷达查看"}));expect(JSON.parse(sessionStorage.getItem("opencareer-catalog-query")!)).toEqual(query);
 fireEvent.click(screen.getByRole("button",{name:"配置岗位订阅"}));expect(JSON.parse(sessionStorage.getItem("opencareer-subscription-query")!)).toEqual({title:"产品日报",send_time:"08:30"});expect(opened).toHaveBeenCalledTimes(2);
 window.removeEventListener("opencareer:catalog-open",opened);
});

it("reopens a saved tool draft by its identifier without creating a duplicate",()=>{
 render(<CareerQueryActions tools={[{kind:"tool",id:"draft",name:"mcp__career__draft_job_subscription",status:"ok",args:{condition:{all:[]},title:"日报",channel_ids:["channel"]},preview:JSON.stringify({ok:true,data:{id:"existing-draft"}})}]}/>);
 fireEvent.click(screen.getByRole("button",{name:"配置岗位订阅"}));
 expect(JSON.parse(sessionStorage.getItem("opencareer-subscription-query")!)).toEqual({title:"日报",channel_ids:["channel"],subscription_id:"existing-draft"});
});
