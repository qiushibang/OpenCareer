import { Icon, type IconName } from "./Icon";

const ACTIONS: {
  icon: IconName;
  title: string;
  description: string;
  prompt?: string;
  action?: "import-resume";
}[] = [
  {
    icon: "file",
    title: "建立求职档案",
    description: "导入简历并逐项确认经历",
    action: "import-resume",
  },
  {
    icon: "search",
    title: "发现合适岗位",
    description: "从官网岗位中按目标公司、城市和方向搜索",
    prompt: "我想搜索合适岗位。请先询问我的求职目标，包括目标公司、城市和职位方向。",
  },
  {
    icon: "fileCode",
    title: "分析一份 JD",
    description: "粘贴职位描述，查看要求、匹配点和风险",
    prompt: "我想分析一份 JD。请等我粘贴职位描述后再开始分析。",
  },
];

export function CareerWelcome({
  onPrefill,
  onImportResume,
}: {
  onPrefill: (text: string) => void;
  onImportResume: () => void;
}) {
  return (
    <div className="career-welcome">
      <div className="career-eyebrow">你的求职 Agent</div>
      <h1>今天从哪里开始？</h1>
      <p>我会基于已确认的真实经历，帮你发现岗位、判断匹配并准备申请材料。</p>
      <div className="career-actions">
        {ACTIONS.map((action) => (
          <button
            key={action.title}
            type="button"
            onClick={() =>
              action.action === "import-resume"
                ? onImportResume()
                : action.prompt && onPrefill(action.prompt)
            }
          >
            <span className="career-action-icon">
              <Icon name={action.icon} size={18} />
            </span>
            <span>
              <strong>{action.title}</strong>
              <small>{action.description}</small>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
