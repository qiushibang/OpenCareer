import { careerJobTypeLabel } from "./careerJobLabels";

export interface ResumeCoachLaunchPayload {
  jobId: string;
  resumeId: string;
  companyName: string;
  position: string;
  /** 脚本从岗位记录生成的结构化信息卡（非 AI 生成），作为对话第一条消息展示。 */
  jobSheet: string;
}

export interface ResumeCoachTurn {
  prompt: string;
  display: string;
  skill: "career-resume-coach";
}

export interface CareerJobSheetSource {
  title?: string | null;
  companyName?: string | null;
  locationRaw?: string | null;
  recruitmentType?: string | null;
  sourceUrl?: string | null;
  jobId?: string | null;
  descriptionRaw?: string | null;
  responsibilities?: string[] | null;
  requirements?: string[] | null;
}

const splitItems = (segment: string): string[] =>
  segment
    .split(/[\n;；]/)
    .flatMap((item) =>
      // 中文 JD 常见 "1、… 2、…" 连排：按枚举标记再切一刀，避免整段塞进一条。
      item.split(/(?<=[^0-9])\s*(?=\d{1,2}[、.．]\s*[^\s])/),
    )
    .map((item) =>
      item
        // 去掉条目自带的枚举前缀，避免与"要求N"双重编号。
        .replace(/^(?:\d{1,2}[、.．]|[(（]\d{1,2}[)）]|[①②③④⑤⑥⑦⑧⑨⑩])\s*/, "")
        .replace(/^[、,.\s]+|[。.\s]+$/g, "")
        .trim(),
    )
    .filter((item) => item.length > 1);

/** 从 JD 原文的「职责：… / 要求：…」段落确定性提取编号条目。解析不出结构时
 * 返回空数组，由调用方回退到逐行编号，绝不靠模型补全。 */
export function parseJdSections(
  descriptionRaw: string | null | undefined,
): { responsibilities: string[]; requirements: string[] } {
  const text = (descriptionRaw || "").replace(/\r/g, "");
  if (!text.trim()) return { responsibilities: [], requirements: [] };
  const grab = (labels: string[]): string[] => {
    for (const label of labels) {
      const inline = text.match(new RegExp(`${label}[：:]\\s*([^\\n]+)`));
      if (inline?.[1]?.trim()) return splitItems(inline[1]);
      const block = text.match(
        new RegExp(`${label}[：:]\\s*\\n([\\s\\S]*?)(?=\\n[^\\n：\\n]{0,8}[：:]|\\n*$)`),
      );
      if (block?.[1]?.trim()) return splitItems(block[1]);
    }
    return [];
  };
  return {
    responsibilities: grab(["职责", "岗位职责", "工作职责", "工作内容"]),
    requirements: grab(["要求", "任职要求", "岗位要求", "任职资格"]),
  };
}

const numbered = (label: string, items: string[]): string =>
  items.map((item, index) => `- ${label}${index + 1}：${item}`).join("\n");

/** 脚本确定性生成岗位信息卡：岗位元数据 + 编号要求/职责清单。全部字段来自
 * 岗位记录原文，不经任何模型处理；对话第一条消息即此卡，后文"要求 N"引用
 * 以这里的编号为准。 */
export function buildCareerJobSheet(job: CareerJobSheetSource): string {
  const lines: string[] = ["【岗位信息】"];
  lines.push(`- 岗位名称：${(job.title || "").trim() || "未命名岗位"}`);
  lines.push(`- 公司：${(job.companyName || "").trim() || "未知公司"}`);
  if (job.locationRaw?.trim()) lines.push(`- 地点：${job.locationRaw.trim()}`);
  if (job.recruitmentType?.trim())
    lines.push(`- 招聘类型：${careerJobTypeLabel(job.recruitmentType.trim())}`);
  if (job.sourceUrl?.trim()) lines.push(`- 官网链接：${job.sourceUrl.trim()}`);
  if (job.jobId?.trim()) lines.push(`- 记录：job_id=${job.jobId.trim()}`);

  // 结构化数组与原文解析都过同一条归一化管线：数组元素可能只是整段文本
  // （爬虫常见），需要按枚举标记拆分并剥掉自带编号，避免与"要求N"双重编号。
  const normalize = (items: string[]): string[] => splitItems(items.join("\n"));
  const parsed = parseJdSections(job.descriptionRaw);
  // JD 无「要求：」标签但正文自带 1、2、3 枚举行时，把这些行作为要求候选。
  const numberedLines = splitItems(
    (job.descriptionRaw || "")
      .split("\n")
      .filter((line) => /^\s*\d{1,2}[、.．]/.test(line))
      .join("\n"),
  );
  // 取条目最多的来源，保证清单条数贴近 JD 实际内容。
  const longest = (...lists: string[][]): string[] =>
    lists.reduce((best, current) => (current.length > best.length ? current : best));
  const finalRequirements = longest(
    normalize(job.requirements || []),
    parsed.requirements,
    numberedLines,
  );
  const finalResponsibilities = longest(
    normalize(job.responsibilities || []),
    parsed.responsibilities,
  );

  lines.push("");
  if (finalRequirements.length > 0) {
    lines.push("【要求清单】");
    lines.push(numbered("要求", finalRequirements));
  } else {
    lines.push("【要求清单】（JD 未解析出结构化要求，原文附后）");
  }

  if (finalResponsibilities.length > 0) {
    lines.push("");
    lines.push("【职责清单】");
    lines.push(numbered("职责", finalResponsibilities));
  }

  if (finalRequirements.length === 0 && finalResponsibilities.length === 0) {
    lines.push("");
    lines.push("【JD 原文】");
    const fallback = (job.descriptionRaw || "").trim();
    if (fallback) {
      fallback.split(/\n+/).forEach((line, index) => {
        if (line.trim()) lines.push(`- 原文${index + 1}：${line.trim()}`);
      });
    } else {
      lines.push("（岗位记录未包含 JD 文本）");
    }
  }
  return lines.join("\n");
}

export function careerResumeCoachMessage(
  payload: ResumeCoachLaunchPayload,
): ResumeCoachTurn {
  const prompt = [
    "【岗位信息卡（系统脚本生成，编号以此为准）】",
    payload.jobSheet,
    "",
    "请使用 career-resume-coach Skill 分析目标岗位与已确认简历。",
    `job_id=${payload.jobId}`,
    `resume_id=${payload.resumeId}`,
    "诊断与改写中的「要求 N / 加分项 N」编号必须与上方【要求清单】一致，不得重新编号。",
    "先输出诊断并追问缺失事实；用户确认后再给出逐段改写与面试准备。",
    "全部分析由 AI 完成，不要调用岗位匹配、申请材料包或文件导出工具。",
  ].join("\n");
  return {
    prompt,
    display: payload.jobSheet,
    skill: "career-resume-coach",
  };
}
