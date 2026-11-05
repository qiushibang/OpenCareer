import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { subscriptionChatTurn } from "./subscriptionChat";
import { SubscriptionChatIntro } from "./components/SubscriptionChatIntro";

afterEach(cleanup);

it("shows a conversational guide and editable examples without exposing the query",()=>{
  const onExample=vi.fn();const condition={all:[{not:{field:"text",op:"contains",values:["销售"]}}]};
  const {container}=render(<SubscriptionChatIntro context={{condition,today:true}} onExample={onExample}/>);
  expect(screen.getByRole("heading",{name:"想每天收到哪些岗位？"})).toBeTruthy();
  expect(container.textContent).not.toContain(JSON.stringify(condition));
  expect(onExample).not.toHaveBeenCalled();
  const example="每天早上9点，把字节跳动北京的产品岗发到我的飞书。";
  fireEvent.click(screen.getByRole("button",{name:example}));
  expect(onExample).toHaveBeenCalledWith(example);
});

it("keeps the user's visible message natural while preserving the full editing context for the skill",()=>{
  const context={condition:{any:[{field:"locations",op:"in",values:["北京"]},{not:{field:"text",op:"contains",values:["销售"]}}]},subscription_id:"existing",today:true,channel_ids:["configured-channel"]};
  const turn=subscriptionChatTurn("改成每天晚上八点，其他不变。",context);
  expect(turn.display).toBe("改成每天晚上八点，其他不变。");
  expect(turn.skill).toBe("career-catalog-query");
  expect(turn.prompt).toContain(JSON.stringify(context));
  expect(turn.prompt).toContain(turn.display);
  expect(turn.display).not.toContain("condition");
});
