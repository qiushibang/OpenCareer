import { afterEach, expect, it, vi } from "vitest";
import { getCareerJobs } from "./api";

afterEach(()=>vi.unstubAllGlobals());

it("distinguishes throttling from an empty catalog and retains the server retry interval",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>new Response(JSON.stringify({error:"Too many requests"}),{
    status:429,headers:{"Retry-After":"3"},
  })));
  await expect(getCareerJobs()).rejects.toMatchObject({message:"请求较多，请稍后重试。",retryAfterMs:3000});
});

it("bounds invalid retry intervals instead of creating a tight retry loop",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>new Response("{}",{status:429,headers:{"Retry-After":"invalid"}})));
  await expect(getCareerJobs()).rejects.toMatchObject({retryAfterMs:60000});
});
