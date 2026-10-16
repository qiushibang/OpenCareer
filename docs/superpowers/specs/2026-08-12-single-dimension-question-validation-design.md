# 单问题单深挖维度校验设计

## 目标

Blueprint v2 每题已经声明一个 `probe_dimension`，问题文本也必须只索取该维度的一类
信息。修复真实算法面试中“介绍项目背景以及个人负责工作”以单句形式绕过复合问题
门禁的问题。

## 判定原则

采用确定性的高置信拦截，不新增模型调用或依赖：

1. 将问题按“以及、并且、同时、另外、此外、还、并”等明确并列连接词切分。
2. 使用小型中文意图词表识别各片段要求的深挖维度。
3. 只有两个独立片段分别命中不同维度时才拒绝。
4. 当前 `probe_dimension` 必须与文本命中的维度一致；未命中意图词时保持兼容，
   不因不确定而拒绝。
5. Blueprint v1 保持原行为。

应拒绝：

- `context`：介绍项目背景以及你具体负责的工作。
- `architecture`：说明整体架构，并介绍如何优化 P95 延迟。
- `strategy`：说明产品策略，同时介绍成功指标。

应放行：

- `context`：介绍项目背景以及当时的业务约束。
- `personal_contribution`：说明你负责的模块和个人决策。
- `performance`：说明如何降低延迟并提升吞吐量。

同一维度中的多个限定项仍是一类回答，不视为复合问题。

## 实现边界

- 在 `extensions/career_mcp/domain/interviews.py` 增加纯函数文本校验。
- `validate_question()` 只对 Blueprint v2 调用该校验。
- 继续由现有 Service 返回 `QUESTION_VALIDATION_FAILED`，具体原因固定为
  `question text spans multiple probe dimensions` 或
  `question text conflicts with probe dimension`。
- `mock-interview` Skill 明确每题文本只能索取当前 `probe_dimension` 的信息。
- 不修改数据库、Repository、Provider、Agent Loop 或 GUI。

## 测试与验收

- 先用真实漏网原句观察 RED。
- 覆盖算法、研发、产品跨维度组合。
- 覆盖同维度并列、未命中词表、Blueprint v1 兼容。
- 运行 Interview Domain、Service、Tools、三岗位离线 Gate、Skill 合同和
  `git diff --check`。
- 真实模型 Gate 以至少一个岗位重新运行五轮为最终行为抽查；若模型持续生成非法
  问题，门禁必须拒绝且不能写入 Turn。

## 非目标

- 不做通用中文语义分类器。
- 不要求所有合法问题使用固定模板。
- 不用模型判断模型自己生成的问题。
- 不把一个维度内的多个指标误判为多个问题。
