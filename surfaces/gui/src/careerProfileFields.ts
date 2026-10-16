const FIELD_LABELS: Record<string, string> = {
  name: "姓名",
  phone: "手机号",
  email: "邮箱",
  birth_date: "出生日期",
  location: "所在地",
  summary: "个人简介",
  github: "GitHub",
  school: "学校",
  degree: "学历",
  major: "专业",
  gpa: "GPA",
  ranking: "排名",
  start_date: "开始时间",
  end_date: "结束时间",
  company: "公司",
  title: "职位",
  description: "描述",
  responsibilities: "职责",
  achievements: "成果",
  project_name: "项目名称",
  role: "担任角色",
  technologies: "技术栈",
  skill: "技能",
  level: "熟练程度",
  evidence: "佐证",
};

export function careerProfileFieldLabel(key: string): string {
  const normalized = key.trim();
  return FIELD_LABELS[normalized] || normalized.replace(/[_-]+/g, " ");
}
