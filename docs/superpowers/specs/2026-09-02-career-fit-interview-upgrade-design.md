# 岗位评估与面试准备升级（设计规格）

日期：2026-09-02
状态：已批准
来源：对 career-ops（69.8k，Agent Skill 架构）、ai-job-search（39.9k，Claude Code
框架）、Reactive Resume、Resume-Matcher 等高星项目的源码实证调研。AIHawk 仓库已
404 且在"不自动投递"红线内，剔除；Reactive Resume 无申请跟踪功能，仅按渲染
基础设施记为产品备忘。

## 问题

四个单薄点：①"这个岗位值得投吗"无结构化判断（career-resume-coach 是自由文本
诊断）；② 面试前准备完全空白（mock-interview 只做面试本身）；③ 岗位雷达无批量
初筛视角；④ 面试复盘教训不回流下一轮准备。

## 方案（全部 Skill/Persona 层，零 Python/TS 代码、零 DB、零新依赖）

### P1 新建 `.coworker/skills/career-job-fit/SKILL.md`

触发意图："值得投吗/评估匹配度"。固定输出契约：岗位画像（含原型归类，本土化
career-ops 六原型）→ 五维匹配（能力/经历/方向/硬门槛/风险信号）→ 真实缺口表
（"matched or honestly gapped, never silently omitted"，ai-job-search 原则）→
JD 可信度（独立于匹配结论，career-ops Block G）→ 四档结论（强烈推荐/值得/
补充后再判断/不建议）。数据只来自 get_job + get_confirmed_resume；硬门槛不过
直接出结论不做润色建议；结论经用户确认可写 update_job_tracking note。

### P3 新建 `.coworker/skills/career-interview-prep/SKILL.md`

触发意图："帮我准备面试"。六章节准备包（吸收 ai-job-search /interview）：
①可能的问题（优先级：复盘被质疑点 > 评估短板 > JD 逐项 > 阶段类型）②STAR
映射（"no claim in the room that isn't on the paper"）③一致性简报（简历量化
主张逐条深挖预演 + 经不起追问清单）④刁钻问题（空窗/转方向，只基于真实经历）
⑤反问清单 ⑥引导衔接既有 mock-interview。闭环：复盘后提示用户把"撑不住追问的
表述"沉淀为确认事实，下一轮准备包优先读取。

### P2 增强 `career-job-search/SKILL.md`

已有确认简历时，检索结果按 对口/疑似对口/缺口明显 三档粗标（每条一句依据），
深度评估引导到 career-job-fit；不自动批量深评。

### P4 Persona `career.md` 真实性红线（跨 Skill 通用）

- 用过 ≠ 做过（"uses X → built X" 是最常见造假模式，禁止）
- 关键词只能重组措辞，不能发明（reformulated, never fabricated）
- 宁可不提，不编细节（silence beats manufactured detail）
- 换重点可以，改事实和夸数字不行（reframed emphasis fine; changed facts
  and escalated numbers are not）

## 边界

- 不恢复简历文件生成（8-24 下线决策不变）；RenderCV/Reactive Resume 记为
  产品备忘，未批准不实施。
- 不做自动申请、海外源、薪资基准、自动批量深评。
- 新 Skill 目录随 Dockerfile `COPY .coworker/skills` 自动进镜像；entrypoint
  manifest 同步已有测试覆盖（tests/test_deploy_entrypoint.py）。

## 验收

本地 alpha 真实浏览器三场景：① 对已确认简历+岗位发起评估，输出完整契约且硬
门槛场景直接"不建议投递"；② 面试准备输出六章节并成功衔接模拟面试；③ 岗位
检索出现三档粗标。部署后线上复测匿名边界与登录流程不变。
