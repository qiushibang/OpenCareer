import type { SubscriptionChatContext } from "../subscriptionChat";

const EXAMPLES = [
  "每天早上9点，把字节跳动北京的产品岗发到我的飞书。",
  "每天晚上8点，推送上海当天新增的 AI 产品实习岗。",
  "订阅北京和深圳的推荐算法岗，排除实习。",
];

export function SubscriptionChatIntro({ context, onExample }: {
  context: SubscriptionChatContext;
  onExample: (text: string) => void;
}) {
  return <section className="transcript pt-8 sm:pt-14" aria-label="订阅创建引导">
    <div className="bubble-assistant">
      <div className="who">岗位订阅助手</div>
      <h1 className="text-2xl font-semibold mt-3 mb-4">{context.subscription_id ? "这次想调整哪些订阅条件？" : "想每天收到哪些岗位？"}</h1>
      <p className="text-sm leading-7 text-muted">告诉我你关注的公司、城市和岗位方向，是否只要新增岗位，以及每天几点接收。我会帮你查询、整理成订阅，最后由你确认。</p>
      <p className="text-xs text-muted mt-2">不指定时间时，默认每天北京时间 09:00。</p>
      <div className="mt-6 space-y-2">
        <p className="text-xs text-muted mb-3">可以这样说</p>
        {EXAMPLES.map(example=><button key={example} type="button" onClick={()=>onExample(example)} className="block w-full text-left rounded-xl border border-line bg-panel px-4 py-3 text-sm leading-6 hover:border-accent hover:bg-paper">{example}</button>)}
      </div>
    </div>
  </section>;
}
