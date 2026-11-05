import type { CatalogCondition } from "./api";

export interface SubscriptionChatContext {
  condition: CatalogCondition;
  today?: boolean;
  include_inactive?: boolean;
  semantic_query?: string | null;
  subscription_id?: string;
  title?: string;
  send_time?: string;
  channel_ids?: string[];
}

// Reuse skill messages' existing model-content / visible-display separation.
// This is attached only after the user sends a real request, never on entry.
export function subscriptionChatTurn(text: string, context: SubscriptionChatContext) {
  return {
    skill: "career-catalog-query",
    display: text,
    prompt: `用户正在${context.subscription_id ? "修改" : "创建"}每日岗位订阅。请以用户本次描述为准，确认缺少的公司、城市、岗位方向、是否仅新增及发送时间，不自行添加条件。未指定时间时默认北京时间09:00。查询岗位验证条件，查询已连接渠道后生成停用草稿，由用户核对并启用；缺少渠道时引导页面扫码，不索要凭据。\n页面带入的筛选参考（可根据用户描述修改）：${JSON.stringify(context)}\n用户本次描述：\n${text}`,
  };
}
