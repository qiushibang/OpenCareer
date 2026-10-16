import { describe, expect, it } from "vitest";

import {
  buildCareerJobSheet,
  careerResumeCoachMessage,
  parseJdSections,
} from "./careerResumeCoach";

const SHEET_JOB = {
  jobId: "job-1",
  resumeId: "resume-1",
  companyName: "示例算法公司",
  position: "算法工程师",
  jobSheet: buildCareerJobSheet({
    title: "算法工程师",
    companyName: "示例算法公司",
    locationRaw: "北京。",
    recruitmentType: null,
    sourceUrl: "https://example.invalid/jobs/ms-gate",
    jobId: "job-1",
    descriptionRaw: [
      "示例算法公司招聘算法工程师。",
      "",
      "职责：负责推荐算法的设计、离线评估与在线调优。",
      "要求：硕士研究生及以上学历，计算机相关专业；熟悉 Python 与机器学习。",
      "地点：北京。",
    ].join("\n"),
    responsibilities: [],
    requirements: [],
  }),
};

describe("buildCareerJobSheet", () => {
  it("prefers the structured requirement/responsibility arrays", () => {
    const sheet = buildCareerJobSheet({
      title: "Agent 工程师",
      companyName: "某公司",
      sourceUrl: "https://jobs.example.com/1",
      jobId: "job-9",
      responsibilities: ["设计 Agent 工作流", "搭建评测集"],
      requirements: ["熟悉 Python", "有 LLM 项目经验"],
    });

    expect(sheet).toContain("- 岗位名称：Agent 工程师");
    expect(sheet).toContain("- 官网链接：https://jobs.example.com/1");
    expect(sheet).toContain("- 要求1：熟悉 Python");
    expect(sheet).toContain("- 要求2：有 LLM 项目经验");
    expect(sheet).toContain("- 职责1：设计 Agent 工作流");
    expect(sheet).not.toContain("JD 原文");
  });

  it("parses 职责/要求 sections from raw JD text and numbers them", () => {
    const parsed = parseJdSections(
      [
        "示例算法公司招聘算法工程师。",
        "职责：负责推荐算法的设计、离线评估与在线调优。",
        "要求：硕士研究生及以上学历，计算机相关专业；熟悉 Python 与机器学习。",
        "地点：北京。",
      ].join("\n"),
    );
    expect(parsed.responsibilities).toEqual(["负责推荐算法的设计、离线评估与在线调优"]);
    expect(parsed.requirements).toEqual([
      "硕士研究生及以上学历，计算机相关专业",
      "熟悉 Python 与机器学习",
    ]);
  });

it("reparses the raw JD when the structured array holds a single blob", () => {
    // 爬虫常见形态：requirements 只有一个元素装下整段，原文里才有 1、2、3 编号。
    const sheet = buildCareerJobSheet({
      title: "AI产品经理（AI创新产品）（杭州/北京） - 飞书 AI Friendly",
      companyName: "字节跳动",
      locationRaw: "杭州",
      recruitmentType: "experienced",
      sourceUrl: "https://jobs.bytedance.com/experienced/position/754/detail",
      jobId: "job-bytedance",
      descriptionRaw: [
        "字节跳动招聘AI产品经理。",
        "1、对未来人机协作办公有充分思考，你看过大量材料、想过很多轮，有自己的判断，不是跟风做AI",
        "2、熟悉大模型与Agent产品形态，能独立完成产品方案设计",
        "3、有跨团队协作经验，能推动工程团队落地",
      ].join("\n"),
      responsibilities: [],
      requirements: [
        "1、对未来人机协作办公有充分思考，你看过大量材料、想过很多轮，有自己的判断，不是跟风做AI",
      ],
    });

    // 原文解析出 3 条，多于结构化数组的 1 条 → 以原文为准。
    expect(sheet).toContain("- 要求1：对未来人机协作办公有充分思考");
    expect(sheet).toContain("- 要求2：熟悉大模型与Agent产品形态");
    expect(sheet).toContain("- 要求3：有跨团队协作经验");
    // 条目自带的"1、"前缀被剥掉，不与"要求N"双重编号。
    expect(sheet).not.toContain("- 要求1：1、");
    // 招聘类型走中文标签映射。
    expect(sheet).toContain("- 招聘类型：社会招聘");
  });

  it("falls back to numbered raw lines when no sections parse", () => {
    const sheet = buildCareerJobSheet({
      title: "神秘岗位",
      companyName: "某公司",
      jobId: "job-2",
      descriptionRaw: "第一行描述。\n第二行描述。",
    });
    expect(sheet).toContain("【要求清单】（JD 未解析出结构化要求，原文附后）");
    expect(sheet).toContain("- 原文1：第一行描述。");
    expect(sheet).toContain("- 原文2：第二行描述。");
  });
});

describe("careerResumeCoachMessage", () => {
  it("leads with the script-generated job sheet in both prompt and display", () => {
    const message = careerResumeCoachMessage(SHEET_JOB);

    // 第一句就是脚本生成的结构化信息卡（对话里第一条可见内容）。
    expect(message.display).toContain("【岗位信息】");
    expect(message.display).toContain("- 岗位名称：算法工程师");
    expect(message.display).toContain("- 官网链接：https://example.invalid/jobs/ms-gate");
    expect(message.display).toContain("- 要求1：硕士研究生及以上学历，计算机相关专业");
    expect(message.display).toContain("- 要求2：熟悉 Python 与机器学习");
    // 编号来自脚本，模型只被要求沿用。
    expect(message.prompt).toContain("【岗位信息卡（系统脚本生成，编号以此为准）】");
    expect(message.prompt).toContain("编号必须与上方【要求清单】一致");
    expect(message.prompt).toContain("job_id=job-1");
    expect(message.prompt).toContain("resume_id=resume-1");
  });

  it("never includes private resume material", () => {
    const message = careerResumeCoachMessage(SHEET_JOB);
    expect(message.prompt).not.toMatch(
      /snapshot|private_path|upload_token|include_sensitive=true|@|138\d{8}/,
    );
  });
});
