# 申请包确定性编译器设计

## 目标

将当前依赖 Career Skill 文案约束和人工复核的申请包生成流程，收敛为一个
不可绕过的确定性编译流程。正式申请包只从当前岗位、已确认简历和指定匹配快照
构建；任何校验失败都阻止写入正式目录。

本阶段只生成 Markdown 申请包。DOCX、PDF 和其他定制材料属于后续“定制材料
导出”阶段。

## 第一性原理

1. 无约束自然语言无法通过正则规则获得完整的语义安全保证。
2. 如果正式产物只能引用有限且可追溯的数据，最可靠的方案是限制输入表达能力，
   而不是在自由文本生成后猜测它是否合规。
3. 岗位、简历和匹配快照是唯一事实来源；对话记忆、未确认 preview 和模型补写
   都不是证据。
4. 校验器必须位于正式文件写入之前，并与写入操作处于同一受保护调用中。
5. 失败必须是无副作用的：不得留下正式文件、临时文件或新的匹配快照。

## 方案

采用“结构化申请包编译器 + 最终防御扫描”。

不采用仅对 Agent Markdown 做正则检查，因为它无法可靠识别改写后的资格推断，
也不能阻止 Agent 绕过校验器直接调用通用文件工具。

不采用模型二次审查，因为结果不稳定、不可复现，并会增加隐私暴露面和调用成本。

## 用户流程

1. 用户在 fresh 岗位匹配结果中点击“生成申请准备包”。
2. GUI 新建 Career 会话并仅预填 `job_id`、`resume_ids` 和 `snapshot_ids`。
3. Career Skill 调用受保护的 `create_application_packet`。
4. Service 重新读取当前岗位、简历和匹配结果，并验证 snapshot 精确一致。
5. 编译器构造结构化申请包，运行领域不变量校验，再渲染固定 Markdown。
6. 最终防御扫描通过后，工具原子写入正式目录并返回相对路径。
7. 任一步失败都返回稳定错误，正式目录不产生文件。

## 边界

### Domain

新增 `extensions/career_mcp/domain/application_packets.py`，只包含纯函数和不可变
数据结构：

- 将 MatchService 结果转换为结构化申请包。
- 校验证据状态、证据数量、引用来源和章节归属。
- 使用固定模板渲染八个 Markdown 章节。
- 对最终文本执行敏感信息和禁止结论的防御扫描。

Domain 不访问数据库、文件系统、网络或模型。

### Service

新增 `ApplicationPacketService`：

- 接受 `job_id`、1–5 个不同的 `resume_ids` 和等长 `snapshot_ids`。
- 通过 `MatchService.analyze(..., expected_snapshot_ids=...)` 获取权威结果。
- 只接受全部为 `fresh` 的结果。
- 调用 Domain 编译和校验。
- 将文件限制在 `artifacts/application-packets/`。
- 使用同目录临时文件和原子替换完成写入。
- 文件名由公司、岗位和日期经过现有安全命名规则生成，调用方不能传入路径。

Service 不接受任意 Markdown、自由格式简历正文、磁盘路径或 upload token。

### MCP

新增受保护工具：

```text
create_application_packet(job_id, resume_ids, snapshot_ids)
```

该工具属于写操作，继续经过 OpenWorker 现有 MCP 审批机制。不得修改 Agent Loop、
权限核心或通用 `write_file`。

成功响应：

```json
{
  "ok": true,
  "result": {
    "artifact_path": "artifacts/application-packets/example.md",
    "snapshot_ids": ["snapshot-1"],
    "validation": {
      "passed": true,
      "violations": []
    }
  }
}
```

失败响应保持 `ok=false`，不返回私人路径。

## 结构化内容规则

正式申请包固定包含：

```text
# 申请准备包
## 岗位与官方来源
## 使用的简历
## 岗位要求证据矩阵
## 建议重点强调的已确认经历
## 暂无佐证与待确认问题
## 简历调整建议
## 面试准备问题
## 数据版本与生成时间
```

### 岗位与简历

- 岗位名称、公司、官方 URL 和 job ID 原样来自 MatchService。
- 简历只显示 display name、resume ID 和 snapshot ID。
- 不输出手机号、邮箱、微信、出生日期、private path 或 upload token。

### 证据矩阵

- `direct` 和 `related` 的 evidence 数量必须等于权威结果数组长度。
- 每条 evidence 只能原样引用 `section`、`path`、`excerpt` 和 `matched_terms`。
- `none` 必须保持 evidence 空数组，固定显示“暂无已确认佐证”。
- 不允许出现“符合、不符合、满足、不满足、录用概率、匹配率”等资格结论。
- 不根据日期推导工作年限、在职月数、是否应届或资格。

### 强调、调整与面试模板

- “建议重点强调”只列出 `direct/related` 的原始 evidence，不生成新事实。
- “暂无佐证”只列出 `none` 的岗位要求，并提示用户补充真实经历或向招聘方确认。
- “简历调整建议”只允许固定动作：前置、合并重复表述、补充用户确认。
- “面试准备问题”根据要求状态使用固定问句，不把 `none` 绑定到任何简历事实。

## 校验不变量

编译前必须满足：

1. resume ID 和 snapshot ID 数量相等、顺序一致且无重复。
2. 所有 snapshot 均与当前岗位 hash 和简历 revision 一致。
3. 所有结果状态均为 `fresh`。
4. 每条 requirement ID 在单份简历结果中只出现一次。
5. `none` 的 evidence 必须为空。
6. 所有 evidence 必须来自同一 MatchService 响应。
7. evidence 数量、状态和 matched terms 不得被重算或改写。

渲染后必须满足：

1. 八个固定章节各出现一次且顺序固定。
2. 不含已知敏感字段值和私人路径。
3. 不含资格结论、百分比或日期推导短语。
4. 所有 job、resume 和 snapshot ID 与输入一致。
5. 每条 evidence excerpt 的出现次数与结构化包一致。

## 错误契约

- `INVALID_INPUT`：ID 为空、重复、数量不等或超过 5 份简历。
- `JOB_NOT_FOUND`：岗位不存在。
- `RESUME_NOT_FOUND`：简历不存在、未确认或已删除。
- `SNAPSHOT_MISMATCH`：输入 snapshot 与当前权威结果不一致。
- `STALE_MATCH`：任一匹配结果不是 fresh。
- `PACKET_VALIDATION_FAILED`：结构化或最终文本不满足不变量。
- `PERSISTENCE_ERROR`：安全路径内的原子写入失败。

错误响应只包含稳定代码和可读消息。内部异常、绝对路径和简历正文不得返回。

## 原子性与幂等

- 校验在打开目标文件前完成。
- 写入使用同目录临时文件，成功后原子替换。
- 写入失败必须清理临时文件。
- 同一 job、相同有序 snapshot 列表和同一日期生成同一文件名。
- 重复调用生成相同内容并安全覆盖，不产生带随机后缀的重复正式文件。
- snapshot mismatch 时 MatchService 的事务必须 rollback，不新增匹配快照。

## GUI 与 Skill

GUI 保持当前“新建 Career 会话并预填 opaque IDs、不自动发送”的行为。

`career-application-packet` Skill 改为只允许调用
`create_application_packet(job_id, resume_ids, snapshot_ids)` 生成正式文件。不得再
通过通用 `write_file` 创建 `artifacts/application-packets/` 下的正式申请包。

本阶段不新增复杂 GUI。Agent 返回成功路径；失败时显示工具返回的中文可操作错误。

## 测试与验收

### Domain

- 单简历和多简历合法结果生成八个固定章节。
- `direct/related` evidence 原样渲染且数量一致。
- `none` 不能携带 evidence，也不能出现在强调事实中。
- 敏感字段、私人路径、资格结论、百分比和日期推导被拒绝。
- requirement、resume 或 snapshot 引用错配被拒绝。

### Service

- fresh snapshot 成功原子写入安全目录。
- stale、snapshot mismatch 和 validation failure 均不创建文件。
- 相同输入重复调用幂等。
- 文件名不能目录穿越。
- 写入失败清理临时文件并返回稳定错误。

### MCP 与 Skill

- 工具参数完整传给 Service。
- 工具被注册为受保护写操作。
- 错误转换不泄漏绝对路径或私人数据。
- Skill 明确禁止使用通用 `write_file` 生成正式申请包。

### 端到端

- 用真实 DeepSeek 岗位、真实简历和已有 fresh snapshot 生成申请包。
- 与现有人工审查通过的 artifact 比较关键事实和 evidence 数量。
- 验证正式目录不存在未通过校验的文件。
- 后端完整回归、GUI 回归、production build 和 `git diff --check` 通过。
- 交付时执行独立对抗审查，重点尝试 snapshot 混用、none 证据注入、敏感字段
  注入、路径穿越和审批绕过。

## 阶段门

1. Gate A：Domain RED/GREEN，纯函数不变量全部通过。
2. Gate B：Service 原子写入、幂等和无副作用失败通过。
3. Gate C：受保护 MCP 工具与 Skill 贯通。
4. Gate D：真实 artifact、完整回归和对抗审查通过。

Gate D 通过前，不开始“岗位收藏与申请跟踪”。

## 明确不做

- 自由文本 Markdown 的通用语义审核。
- 模型作为校验器或评分器。
- 自动修改原始简历。
- DOCX/PDF 导出。
- 岗位收藏、申请状态或自动投递。
- 修改 OpenWorker Agent Loop、权限核心或通用文件工具。
