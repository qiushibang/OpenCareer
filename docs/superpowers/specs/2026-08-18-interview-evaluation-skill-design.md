# 面试回答评价 Skill 设计

> 日期：2026-08-18
>
> 状态：方案已批准，待书面规格审阅

## 1. 目标

为每道模拟面试回答生成可审计的训练反馈：

- 一个 0–100 单题综合分。
- 一个主要痛点。
- 基于回答原文和本题标准的原因。
- 一个不改变候选人事实的优化策略。

后台保留动态激活维度、行为锚点和证据，用户界面不再展示固定五维评分。

## 2. Skill 边界

新增：

```text
.coworker/skills/career-interview-evaluation/SKILL.md
```

名称：`career-interview-evaluation`

触发条件：模拟面试用户提交回答后、决定下一步动作前，或用户要求复盘某道面试回答时。

它只负责评价建议，不负责：

- 创建或结束 InterviewSession。
- 生成、保存或切换问题。
- 直接写数据库或生成报告文件。
- 绕过简历确认、版本冲突或问题门禁。

`mock-interview` 仍负责编排工具调用。面试开始时加载两个 Skill；后续轮次从 Conversation
历史复用已加载指令，不重复调用 `load_skill`。

## 3. 输入

每次评价必须使用当前 `get_interview_session` 返回的：

- 精确问题、题型标签和用户回答。
- `probe_target`、`probe_dimension`、`depth_level`。
- Blueprint 中本题关联的 JD 要求和已确认简历证据。
- 当前题此前的追问和评价，避免重复询问同一缺口。

缺少问题、回答或目标时，不生成分数，返回评价输入不完整。

## 4. Prompt 执行顺序

Skill 要求模型严格执行：

1. 识别本题类型和目标胜任力。
2. 从题型模板中选择允许的评价维度。
3. 只激活与本题目标直接相关的维度。
4. 为每个维度摘录回答原文证据；没有证据时明确记录缺失。
5. 按 0–4 行为锚点评级，不直接编造总分。
6. 选择最妨碍面试官判断的一个主痛点。
7. 用“观察、标准、影响”解释原因。
8. 给出一个不增加新事实的优化动作。
9. 根据关键缺口建议下一动作，但最终动作由 `mock-interview` 和领域校验决定。

禁止项：

- 不使用未经确认的简历事实。
- 不生成候选人没说过的数字、职责、成果或困难。
- 不奖励没有样本、基线、口径和个人贡献的孤立百分比。
- 不因回答未使用 STAR 格式而机械扣分。
- 不使用口音、语速、停顿、人格或文化契合作为评价依据。
- 不把分数解释成录用概率或候选人总体能力。
- 关键证据仍可追问时，不建议 `SWITCH_TOPIC`。

## 5. 动态评价模板

通用候选维度：

| 维度 | 观察内容 |
|---|---|
| `relevance` | 是否直接回答本题目标和关键约束 |
| `specificity` | 是否提供具体、可核查的事实 |
| `ownership` | 本人的职责、决策、动作和团队边界 |
| `reasoning` | 假设、备选方案、选择依据和因果链 |
| `outcome` | 结果、基线、口径、验证和副作用 |
| `clarity` | 信息是否足以理解和评分 |
| `reflection` | 局限、纠偏和后续改变，仅适用时启用 |

题型模板：

| 题型 | 必选维度 | 可选维度 |
|---|---|---|
| 过去行为题 | relevance、specificity、ownership、outcome | reasoning、reflection、clarity |
| 产品 Case | relevance、product_problem、reasoning、prioritization、validation | tradeoff、clarity |
| 技术知识题 | relevance、technical_correctness、clarity | boundary、tradeoff |
| 编码题 | relevance、technical_correctness、testing、boundary | complexity、clarity |
| 系统设计题 | relevance、architecture、tradeoff、reliability | scale、evolution、clarity |
| AI/ML Case | relevance、problem_formulation、data、evaluation | baseline、error_analysis、deployment |
| 失败/复盘题 | relevance、ownership、diagnosis、reflection | outcome、clarity |

权重由领域代码中的题型模板决定，模型不能自由设置。目标胜任力和题型核心维度权重为 2，
其他激活维度权重为 1。

## 6. 行为锚点与计分

| 等级 | 行为锚点 |
|---:|---|
| 0 | 偏题、矛盾或完全没有可评分证据 |
| 1 | 只有抽象主张，关键事实缺失 |
| 2 | 有相关经历或思路，但证据链不完整 |
| 3 | 证据具体，主要判断成立，仍有一个次要缺口 |
| 4 | 证据充分、可核查，且与本题目标一致 |

后端确定性计算：

```text
score = round(sum(level * weight) / sum(4 * weight) * 100)
```

未激活维度不进入分母。用户解释：

- 85–100：证据充分。
- 70–84：主体成立，存在一处关键缺口。
- 50–69：相关但不足以稳定判断。
- 0–49：偏题、过度抽象、关键事实缺失或明显矛盾。

## 7. 存储契约

复用现有 `interview_turns.evaluation_json`，不增加 schema 迁移。新评价使用版本化对象：

```json
{
  "version": 2,
  "question_type": "past_behavior",
  "target_competency": "product_judgment",
  "active_dimensions": [
    {
      "name": "ownership",
      "level": 2,
      "evidence": ["我们最后选择了灰度发布"],
      "missing_evidence": "本人负责的判断和交付边界"
    }
  ],
  "question_score": 63,
  "primary_pain": "个人贡献不清",
  "reason": "回答说明了团队方案，但没有说明本人的决策、动作和交付边界。",
  "improvement": "按团队目标、我的职责、关键动作和结果重组回答。",
  "fact_refs": ["experience.projects[0]"]
}
```

领域代码负责：

- 校验题型、维度枚举、等级和文本长度。
- 根据模板补充权重并计算 `question_score`。
- 校验 `fact_refs` 属于 Blueprint。
- 拒绝敏感信息和禁用结论。

现有 v1 对象继续可读；新提交只接受 v2。报告编译器按 `version` 分流，旧历史不改写。

## 8. 下一动作

评价结果只提供建议，领域状态机仍是最终门禁：

- 缺少具体事实：`FOLLOW_UP`。
- 数字、归因或结果口径可疑：`VERIFY_CLAIM`。
- 当前 target 仍有更深证据：`DEEP_DIVE`。
- 当前 target 已达到锚点或深度用尽：`SWITCH_TOPIC`。
- 五题完成：`WRAP_UP`。

当主痛点属于低证据、指标定义、验证方法或个人贡献时，只要当前 target 还有深度，就不得
切换主题。

## 9. 用户可见报告

逐题只显示：

```text
本题得分：76/100
主要痛点：个人贡献不清
原因：回答说明了团队方案和结果，但没有交代本人决策和动作。
优化策略：按团队目标、我的职责、关键动作和结果重组回答。
```

删除固定五维均分、STAR 完整度统计和“出现数字次数即更好”的推断。跨题总结按 Blueprint
目标覆盖情况汇总，不计算不同题型之间的机械平均维度分。

## 10. 实施文件

- 新增 `.coworker/skills/career-interview-evaluation/SKILL.md`。
- 修改 `.coworker/skills/mock-interview/SKILL.md`。
- 修改 `extensions/career_mcp/domain/interviews.py`。
- 按需最小修改 `services/interviews.py` 和 `database/interview_repository.py`。
- 修改 `tests/test_skills.py`。
- 修改现有面试领域、服务、Repository 和报告测试。

不修改数据库 schema，不新增依赖。

## 11. 验收

- 高质量回答得到高行为等级，并保留对应原文证据。
- 模糊回答只评价已有信息，主痛点指向缺失证据。
- 孤立百分比不会自动提高 outcome。
- 技术知识题不因缺少 STAR、个人贡献或业务结果被扣分。
- 产品 Case 不要求虚构历史结果。
- 低证据回答建议停留在同一 target。
- 服务端忽略模型提供的总分，使用确定性公式重算。
- 非法维度、未知引用、敏感信息和伪造结论被拒绝。
- v1 历史报告仍可读取，v2 报告使用新格式。
- 面试开始后只加载一次评价 Skill。
