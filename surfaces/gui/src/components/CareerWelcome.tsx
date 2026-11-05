import { useId } from "react";
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
    description: "导入简历、确认经历，整理你的求职资料。",
    action: "import-resume",
  },
  {
    icon: "search",
    title: "发现合适岗位",
    description: "按公司、城市和方向，找到值得投递的岗位。",
    prompt: "我想搜索合适岗位。请先询问我的求职目标，包括目标公司、城市和职位方向。",
  },
  {
    icon: "fileCode",
    title: "分析一份 JD",
    description: "粘贴职位描述，梳理岗位要求、匹配点与准备方向。",
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
  const descriptionId = useId();
  return (
    <div className="career-welcome">
      <div className="career-eyebrow">你的求职 Agent</div>
      <h1>今天从哪里开始？</h1>
      {/* 基于已确认经历提供岗位发现、匹配与申请准备；不在首页重复产品说明。 */}
      <div className="career-actions">
        {ACTIONS.map((action,index) => (
          <button
            key={action.title}
            type="button"
            aria-label={action.title}
            aria-describedby={`${descriptionId}-${index}`}
            onClick={() =>
              action.action === "import-resume"
                ? onImportResume()
                : action.prompt && onPrefill(action.prompt)
            }
          >
            <span className="career-action-index" aria-hidden="true">0{index+1}</span>
            <span className="career-action-icon">
              <Icon name={action.icon} size={18} />
            </span>
            <span>
              <strong>{action.title}</strong>
              <small id={`${descriptionId}-${index}`}>{action.description}</small>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
