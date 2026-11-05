import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobSubscriptionsPanel } from "./JobSubscriptionsPanel";
const request = vi.fn(async (path: string) => path.endsWith("channels") ? [{id: "channel",name: "测试群",kind: "wecom"}] : path === "job-subscriptions" ? [{id: "sub",title: "北京产品",condition: {all: []},channel_ids: ["channel"],send_time: "09:00",version: 1,enabled: false}] : {});
vi.mock("../api", () => ({ careerCatalogRequest: (...args: [string]) => request(...args) }));
describe("job subscriptions", () => {
  it("shows destination and time before explicit activation", async () => {
    render(<JobSubscriptionsPanel condition={{all: []}} onClose={() => {}} />);
    expect(await screen.findByText("北京产品")).toBeTruthy();
    expect(screen.getByText(/09:00/)).toBeTruthy();
    expect(screen.getAllByText(/测试群/).length).toBeGreaterThan(0);
    expect(request.mock.calls.some(c => c[0].includes("activate"))).toBe(false);
    fireEvent.click(screen.getByRole("button", {name: "确认启用"}));
    expect(request).toHaveBeenCalledWith("job-subscriptions/sub/activate", {version: 1, confirmed: true});
  });
});

it("shows a policy diagnosis without sending when the user checks the connection",async()=>{
 request.mockClear();
 request.mockImplementation(async(path:string)=>path.endsWith("/check")?{status:"failed",diagnostic:{message:"飞书访问控制策略拒绝了当前应用",platform_code:21001}}:path.endsWith("channels")?[{id:"scan-channel",name:"扫码账号",kind:"feishu_app"}]:[]);
 render(<JobSubscriptionsPanel condition={{all:[]}} onClose={()=>{}}/>);
 fireEvent.click(await screen.findByRole("button",{name:"检查连接（不发消息）"}));
 expect(await screen.findByText(/飞书访问控制策略拒绝了当前应用.*21001/)).toBeTruthy();
 expect(request).toHaveBeenCalledWith("job-subscriptions/channels/scan-channel/check",{});
 expect(request.mock.calls.some(c=>c[0].endsWith("/test"))).toBe(false);
});

it("guides configuration into chat with the exact current condition and no task write", async()=>{
 request.mockClear();request.mockImplementation(async(path:string)=>path.endsWith("channels")?[]:[]);
 const onChat=vi.fn();const condition={all:[{field:"company",op:"in",values:["bytedance"]},{not:{field:"text",op:"contains",values:["销售"]}}]};
 render(<JobSubscriptionsPanel condition={condition} today onConfigureInChat={onChat} onClose={()=>{}}/>);
 fireEvent.click(screen.getByRole("button",{name:"在对话中创建订阅"}));
 expect(onChat).toHaveBeenCalledWith(expect.objectContaining({condition,today:true,include_inactive:false}));
 expect(screen.queryByRole("button",{name:"保存订阅草稿"})).toBeNull();
 expect(request.mock.calls.every(c=>c.length===1)).toBe(true);
});

it("saves the AI conditions, daily-new flag, time and channel as a disabled draft",async()=>{
 request.mockClear();request.mockImplementation(async(path:string)=>path.endsWith("channels")?[{id:"channel",name:"测试群",kind:"wecom"}]:[]);
 const condition={any:[{field:"locations",op:"in",values:["北京"]},{field:"locations",op:"in",values:["上海"]}]};
 render(<JobSubscriptionsPanel condition={condition} today initialDraft={{title:"产品日报",send_time:"08:30"}} onClose={()=>{}}/>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"保存订阅草稿"}).hasAttribute("disabled")).toBe(false));
 fireEvent.click(screen.getByRole("button",{name:"保存订阅草稿"}));
 await waitFor(()=>expect(request).toHaveBeenCalledWith("job-subscriptions",{title:"产品日报",condition,today:true,include_inactive:false,semantic_query:null,channel_ids:["channel"],send_time:"08:30"}));
 expect(request.mock.calls.some(c=>c[0].includes("activate")||c[0].endsWith("/test"))).toBe(false);
});

it("loads an existing tool draft's saved filters and updates the same subscription",async()=>{
 const condition={field:"company",op:"in",values:["bytedance"]};
 request.mockClear();request.mockImplementation(async(path:string)=>path.endsWith("channels")?[{id:"channel",name:"测试群",kind:"wecom"}]:[{id:"existing",title:"已保存条件",condition,today:true,include_inactive:false,channel_ids:["channel"],send_time:"08:30",version:2,enabled:false}]);
 render(<JobSubscriptionsPanel condition={{all:[]}} initialDraft={{subscription_id:"existing"}} onClose={()=>{}}/>);
 await waitFor(()=>expect((screen.getByLabelText("订阅名称") as HTMLInputElement).value).toBe("已保存条件"));
 fireEvent.click(screen.getByRole("button",{name:"保存订阅草稿"}));
 await waitFor(()=>expect(request).toHaveBeenCalledWith("job-subscriptions",expect.objectContaining({subscription_id:"existing",condition,today:true,send_time:"08:30"})));
});
