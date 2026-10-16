# JD/简历驱动的面试智能设计

## 目标

让 AI 面试官真正读取目标 JD 和已确认简历事实，按岗位类型对最相关项目进行可追溯、
多轮、差异化深挖。

本规格只实现面试智能内核。对话式 UI、历史中心和实时语音分别在后续子规格实现。

## 当前问题

### 模型只看到路径

当前 Blueprint 保存：

- `requirement_id`
- 要求原文
- evidence status
- `project[0].highlights[0]` 等 evidence path

但不保存 path 对应的 excerpt。`get_interview_session` 返回 Blueprint 时，模型不知道
该项目的名称、行动和结果。

### 首题被硬编码

`mock-interview` Skill 的 Start Workflow 强制使用：

```json
{
  "question": "请简单介绍一下你自己。",
  "topic": "自我介绍",
  "refs": ["INTRO"]
}
```

因此首题不会结合岗位或简历。

### 深挖没有持久化状态

当前 Turn 只保存问题文字和 refs。`topic` 在 validation 后丢失，也没有 probe target、
dimension 或 depth。模型只能从历史文本猜测是否应该继续深挖。

## 成功标准

1. 新 InterviewSession 使用 Blueprint v2。
2. 模型能看到有限、脱敏、可引用的简历事实摘要。
3. 存在 evidence card 时，首题引用岗位要求和最相关简历经历；完全无证据时只引用
   岗位要求，并明确使用知识/场景问题。
4. 每个问题都绑定合法 probe target、dimension、depth 和 refs。
5. 标准难度对核心项目完成至少两层连续追问。
6. 算法、研发、产品采用不同维度。
7. 混合岗位可以同时启用多个 role track。
8. 不确定岗位回退 `general`。
9. v1 历史 Session 仍可读取；新 Session 不再生成 v1。
10. 不泄露敏感字段，不虚构用户经历。

## Blueprint v2

```json
{
  "version": 2,
  "company": "DeepSeek",
  "position": "大模型算法工程师",
  "difficulty": "standard",
  "duration_minutes": 15,
  "question_budget": 8,
  "role_tracks": ["algorithm", "engineering"],
  "job_requirements": [
    {
      "requirement_id": "requirement-1",
      "requirement": "熟悉模型训练和推理优化",
      "category": "hard",
      "evidence_status": "direct",
      "evidence_paths": ["project[0].highlights[0]"]
    }
  ],
  "evidence_cards": [
    {
      "fact_path": "project[0].highlights[0]",
      "section": "project",
      "group_path": "project[0]",
      "excerpt": "负责模型推理服务和性能优化",
      "requirement_ids": ["requirement-1"]
    }
  ],
  "probe_plan": [
    {
      "target_id": "project[0]",
      "target_type": "resume_project",
      "priority": 100,
      "refs": [
        "requirement-1",
        "project[0].highlights[0]"
      ],
      "dimensions": [
        "personal_contribution",
        "implementation",
        "performance",
        "evaluation",
        "tradeoff"
      ],
      "max_depth": 3
    }
  ],
  "candidate_strengths": ["project[0].highlights[0]"],
  "candidate_risks": ["requirement-2"],
  "must_probe": ["requirement-2"]
}
```

## 岗位 track 分类

新增纯函数：

```python
classify_role_tracks(
    title: str,
    requirements: list[str],
) -> list[str]
```

输入只来自当前保存的 JD。分类使用确定性词典和归一化，不调用模型。

### `algorithm`

示例信号：

- 算法、模型、机器学习、深度学习、NLP、CV、推荐、训练、推理。

### `engineering`

示例信号：

- 开发、工程师、后端、前端、客户端、架构、平台、基础设施、SRE。

### `product`

示例信号：

- 产品经理、产品策划、产品运营、策略产品、商业产品。

规则：

- title 信号优先于 requirement 信号。
- 可以返回多个 track。
- 无信号时只返回 `general`。
- 词典和优先级必须有独立 fixture 测试。
- 分类结果不输出伪造置信度。

## Evidence Card

### 来源

InterviewService 在创建 Session 时读取所选 resume 的
`get_resume_match_input()`，只使用已确认 sections。

复用 `build_evidence_entries()` 的脱敏逻辑：

- 跳过敏感 key。
- 跳过包含敏感 value 的文本。
- 保留原始 `fact_path`。

### 选择和排序

最多返回 16 张 card：

1. 被 hard requirement 匹配的 evidence。
2. 被其他 JD requirement 匹配的 evidence。
3. project/work 中能组成可面试项目的其他事实。
4. basic summary 和 education 只在仍有预算时补充。

同一 path 只出现一次。每个 excerpt：

- 去除多余空白。
- 最长 300 字。
- 不做模型改写。
- 不拼接未确认事实。

### 分组

`group_path` 取可面试经历根路径，例如：

- `project[0]`
- `work[1]`

Probe plan 以 group 为深挖 target，具体问题仍引用一个或多个 fact path。

## Probe Plan

新增纯函数：

```python
build_probe_plan(
    *,
    role_tracks: list[str],
    requirements: list[dict],
    evidence_cards: list[dict],
    difficulty: str,
    question_budget: int,
) -> list[dict]
```

### target 类型

- `resume_project`
- `resume_work`
- `job_requirement`
- `role_scenario`
- `reflection`

### 优先级

从高到低：

1. hard requirement 对应的相关项目。
2. 与多个 requirement 相关的核心项目。
3. hard/important requirement 的 `none` 或 `related` 缺口。
4. 其他简历经历。
5. role scenario。
6. reflection。

`none` 只允许询问知识、方法或相似经验，不得暗示简历中存在该经历。

### 维度

公共维度：

- `context`
- `personal_contribution`
- `result`
- `evidence`
- `tradeoff`
- `failure`
- `reflection`

算法维度：

- `data`
- `model_choice`
- `training`
- `inference`
- `experiment`
- `evaluation`
- `error_analysis`
- `optimization`

研发维度：

- `architecture`
- `implementation`
- `interface`
- `data_structure`
- `concurrency`
- `consistency`
- `performance`
- `reliability`
- `observability`
- `security`

产品维度：

- `user_problem`
- `strategy`
- `feature_design`
- `workflow`
- `evaluation`
- `metrics`
- `experiment`
- `iteration`
- `prioritization`
- `business_tradeoff`

### 深度

- simple：`max_depth=1`
- standard：核心 target `max_depth=3`，其他 target `max_depth=2`
- deep：核心 target `max_depth=4`，其他 target `max_depth=3`

深度表示连续探查层级，不等同于已回答问题总数。

## InterviewTurn v2

schema v11 新增 nullable 字段：

```text
question_topic    TEXT
probe_target      TEXT
probe_dimension   TEXT
depth_level       INTEGER
```

旧 Turn 字段为 null。新 Session 的每道题必须填写。

问题 proposal：

```json
{
  "question": "你如何设计该推理服务的核心数据结构？",
  "topic": "技术实现",
  "refs": [
    "requirement-1",
    "project[0].highlights[0]"
  ],
  "probe_target": "project[0]",
  "probe_dimension": "data_structure",
  "depth_level": 2
}
```

## 问题校验

Blueprint v2 的 `validate_question()` 必须校验：

- question、topic 和单问题规则。
- refs 全部属于 Blueprint。
- probe target 属于 probe plan。
- dimension 属于该 target。
- `1 <= depth_level <= max_depth`。
- 存在 evidence card 时，首题必须同时包含 requirement ref 和 resume evidence
  ref；无 evidence card 时必须只使用 requirement ref 和 `job_requirement`
  target。
- FOLLOW_UP/VERIFY_CLAIM/DEEP_DIVE 的 target 必须与上一题相同。
- 同一 target 的 depth 不得回退或跳过超过一层。
- SWITCH_TOPIC 必须切换 target。
- 不得重复标准化后的问题。

Blueprint v1 继续使用旧 validator，保证历史兼容。

## 首题策略

不再使用固定 INTRO。

选择：

1. 最高优先级且具有 resume evidence 的 target。
2. 该 target 关联的最高优先级 requirement。
3. `personal_contribution` 或 `context` 维度。

存在 evidence card 时，首题要求：

- 提及目标岗位。
- 提及可安全展示的项目/经历摘要。
- 只提出一个主问题。
- refs 至少包含一个 requirement 和一个 fact path。

完全无 evidence card 时，选择最高优先级的 job requirement，使用
`job_requirement` target 和岗位知识/场景维度。问题不得出现“你在项目中”
“结合你的经历”等暗示已有相关经历的措辞。

示例：

```text
你正在应聘大模型算法工程师。请结合简历中负责模型推理服务的经历，
介绍你在其中承担的个人职责。
```

## 每轮决策

Agent 读取完整 Blueprint 和 Previous Turns 后按以下顺序决策：

1. 若回答含糊、主要使用“我们”、没有个人行动或缺少证据，继续当前 target。
2. 若当前 target 未达到目标 depth，选择下一个未覆盖 dimension。
3. 若当前 target 已有充分证据，切换到下一优先 target。
4. 问题预算不足时优先覆盖 hard requirement 和核心项目。
5. 达到预算或满足 WRAP_UP 条件时结束。

Agent 必须先生成 evaluation，再选择 next action 和 question。

## Prompt 分层

### Career Persona

只增加全局原则：

- 真实面试官角色。
- JD + confirmed resume grounding。
- 一次一个问题。
- 面试中不辅导。
- 不虚构、不泄露隐藏评价。
- 回答不是 Career Vault 事实。

不得在 Persona 中复制 MCP schema 或完整工作流。

### `mock-interview` Skill

重写 Start/Answer Workflow：

- 必须读取 Blueprint v2 的 excerpt、role tracks 和 probe plan。
- 首题由最高优先 target 生成。
- 不再硬编码问题。
- 每轮显式提交 topic/target/dimension/depth。
- 按 role track 使用对应问题维度。
- 只有 Service 接受的问题才能返回给用户。

### GUI task prompt

GUI prompt 只表达自然任务和内部标识：

```text
开始这场模拟面试，并根据当前 JD、已确认简历和 Blueprint 提出第一题。
```

回答 prompt 必须让用户可见消息保持自然文本。ID/version 等控制信息由面试对话适配层
传递或在渲染层隐藏，不显示成用户消息正文。

### 不修改

- Agent Loop。
- Provider Router。
- MCP Client。
- 权限审批。
- 核心 Conversation 存储。

## 错误处理

- 无已确认 resume：`RESUME_NOT_FOUND`。
- stale snapshot：`STALE_MATCH`。
- 无 requirements：沿用 `INSUFFICIENT_JOB_DATA`。
- 无 evidence card：允许创建岗位知识型面试，但首题不得声称候选人有相关经历。
- role classifier 无结果：`general`。
- 非法 target/dimension/depth/ref：`QUESTION_VALIDATION_FAILED`。
- 旧 Session：使用 v1 兼容路径，不原地迁移 Blueprint。
- 新 Session 不允许回退生成 v1。

## 隐私

- Blueprint 不保存完整 resume。
- evidence excerpt 不超过 300 字。
- card 总数不超过 16。
- 敏感 key/value 过滤复用现有 Domain 规则。
- Artifact 中可以保存 Blueprint v2，但仍必须通过 `contains_sensitive_value`。
- 日志不得输出完整 Blueprint 或 resume sections。

## TDD

### Domain

- algorithm/engineering/product/general 分类。
- 混合岗位多 track。
- evidence card 排序、去重、长度和敏感过滤。
- probe plan 优先级、维度和深度。
- v1/v2 question validator。
- 首题有证据时的双引用要求，以及无证据时的安全退化。
- target/depth 转换约束。

### Service/Repository

- create 生成 Blueprint v2。
- 新 Turn 持久化四个元数据字段。
- v1 历史记录可读取。
- stale 和 CAS 行为不变。
- transaction failure 不留下部分 Turn。

### Skill

静态契约测试要求：

- 不再出现固定首题。
- 明确读取 excerpt。
- 三类 role track 均有具体维度。
- 明确连续深挖和切换条件。
- 不允许未引用问题。

### 真实 TurnEngine Gate

使用本地 fixture 和真实模型各完成一场：

1. 算法岗位。
2. 研发岗位。
3. 产品岗位。

每场至少 5 轮；标准难度使用 8 轮更优。

验收：

- fixture 提供 evidence card 时，首题包含岗位和真实简历经历。
- 核心项目至少两层连续追问。
- 每题 refs/target/dimension/depth 合法。
- 算法场出现算法专属维度。
- 研发场出现研发专属维度。
- 产品场出现产品专属维度。
- 无敏感泄漏、复合问题或虚构事实。
- 三场均生成有效 transcript/report/session Artifact。

## 不做事项

- 本规格不迁移 UI 到标准 Conversation。
- 不实现面试历史页面。
- 不实现实时 ASR/TTS。
- 不增加向量数据库。
- 不让模型读取原始简历文件。
- 不允许模型自定义 role track 或 probe dimension。
