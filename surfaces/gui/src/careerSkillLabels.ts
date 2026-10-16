/** Career 技能的中文界面元数据：名称与一句话使用说明。后端 SKILL.md 的
 * name/description 是英文（供模型消费），这里给用户看中文；未收录的技能
 * 回退原名与原描述。 */

export interface SkillZhMeta {
  title: string;
  description: string;
}

export const SKILL_ZH: Record<string, SkillZhMeta> = {
  "career-jd-analysis": {
    title: "JD 岗位分析",
    description: "解析职位描述：职责、要求、地点与缺失信息，确认后存入岗位库",
  },
  "career-job-search": {
    title: "岗位检索",
    description: "在官方岗位库中按公司、城市、方向检索，并对结果做对口粗筛",
  },
  "career-job-fit": {
    title: "岗位匹配评估",
    description: "评估一个已入库岗位是否值得投递：硬门槛、五维匹配、真实缺口与明确结论",
  },
  "career-resume-coach": {
    title: "AI 简历诊断与改写",
    description: "对照岗位逐段诊断简历，给分级修改建议、投递结论与面试准备",
  },
  "career-resume-import": {
    title: "简历导入确认",
    description: "把上传的简历解析为待确认的档案事实，逐段确认后存入求职档案",
  },
  "career-interview-prep": {
    title: "面试准备包",
    description: "按面试阶段生成问题预测、STAR 映射、一致性简报与反问清单",
  },
  "mock-interview": {
    title: "模拟面试",
    description: "五轮自适应模拟面试：连续追问、项目深挖、严格评价与复盘",
  },
  "career-interview-evaluation": {
    title: "面试评价（内部）",
    description: "模拟面试的回答评价引擎，随模拟面试自动加载，无需单独调用",
  },
};

export function skillZhTitle(name: string): string {
  return SKILL_ZH[name]?.title ?? name;
}

export function skillZhDescription(name: string, fallback: string): string {
  return SKILL_ZH[name]?.description ?? fallback;
}
