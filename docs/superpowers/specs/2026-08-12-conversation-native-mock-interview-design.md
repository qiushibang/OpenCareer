# 标准对话内模拟面试设计

## 目标

模拟面试必须表现为一场真实的 Career Agent 对话，而不是独立于 Agent 的第二套页面。
从岗位启动后，会话立即出现在“最近会话”；用户可以在标准 Transcript 和 Composer
中完成文字或语音面试，刷新或重新打开会话后继续，结束后在同一会话进入复盘。

## 当前问题

现有实现已经创建 OpenWorker Conversation，并将 InterviewSession 的
`conversation_id` 与其绑定。但 GUI 随后执行 `setSurface("interview")`，离开标准
Conversation 页面并渲染完整的 `InterviewView`。

这造成：

- 最近会话和当前面试视觉割裂。
- Transcript、Composer、审批卡和面试问答存在两套展示路径。
- `activeInterviewId` 主要保存在当前 GUI 内存，重新打开最近会话时不能按
  `conversation_id` 恢复面试。
- 用户可见消息可能暴露内部 Skill Prompt，而不是只显示原始回答。
- 浏览器录音、问题 TTS 和报告入口被锁在专用页面内。

## 选定方案

采用“标准对话 + 紧凑面试状态条”。

标准 Conversation 是唯一主界面。InterviewSession 继续保存岗位、简历、Blueprint、
Turn、评价和报告状态；OpenWorker Conversation 继续保存用户与 Agent 消息、审批、
模型运行和最近会话。两者通过唯一 `conversation_id` 关联，不复制状态。

不修改 Agent Loop、Provider Router、权限系统或 Conversation 存储语义。

## 启动与导航

从岗位列表或详情点击“模拟面试”：

1. 校验可信工作区、已确认简历和 fresh 匹配快照。
2. 生成新的 Career Conversation ID。
3. 创建并绑定 InterviewSession。
4. 将 GUI 切换到该 Conversation，保持 `surface="session"`。
5. 连接成功后发送第一轮启动指令。
6. 首轮保存后将 Conversation 命名为
   `模拟面试 · {position}`，并刷新最近会话。

不再切换到 `surface="interview"`。选择最近会话始终回到标准 Conversation 页面。

## Conversation 到 Interview 的恢复

新增只读接口：

```text
GET /v1/career/interviews?conversation_id=<conversation_id>
```

返回：

- 已绑定面试：标准 `CareerInterviewResult`。
- 没有绑定：`ok=true, interview=null`。
- 非法 ID 或持久化错误：现有结构化错误。

Repository 增加按 `conversation_id` 查询。Service 在 `BEGIN IMMEDIATE` 事务内检查
同一 Conversation 不得创建或绑定第二场 Interview，保证恢复结果唯一。MVP 数据量
下无需新增 schema 或索引；若后续出现大量历史面试，再单独评估索引迁移。

GUI 在以下时机查询：

- 切换 Career Conversation。
- 浏览器刷新恢复 Session。
- 创建面试后。
- 面试 Turn 完成后。

普通 Career Conversation 返回 null，不显示面试状态条。

## 标准对话布局

### 会话标题

```text
模拟面试 · 大模型推理算法工程师
```

标题仍可由用户手工重命名。确定性命名发生在第一轮完成、Conversation 已持久化后，
避免被内部启动指令生成的自动标题覆盖。

### 顶部状态条

状态条位于标准会话标题下方、Transcript 上方，不占用 RightRail。

`ready`：

- 公司、岗位、所选简历、难度和计划题数。
- “开始面试”。

`in_progress`：

- 第 N / 预算题。
- 当前 probe target 的用户可读名称。
- 当前深挖维度的中文名称。
- 已用时间。
- 重播问题、提前结束。

`generating_report`：

- “正在生成面试复盘”。

`completed`：

- “复盘已生成”。
- 下载报告、逐字稿。
- 快捷追问：“第三题怎样回答更好”“生成补强计划”。

状态条只显示用户可理解的信息，不显示 target ID、fact path、depth 数字或内部状态码。

## 消息与内部指令

用户可见 Transcript：

- 启动气泡：`开始模拟面试`。
- 用户气泡：候选人的原始文字或确认后的 ASR transcript。
- Agent 气泡：面试问题和最终复盘摘要。
- 标准审批卡、错误提示和处理中状态。

模型输入仍包含：

- `interview_session_id`。
- `turn_id`。
- Skill 加载和工作流指令。

复用 Engine 已有 `_display` sidecar，将“模型实际输入”和“用户可见文本”分离。
WebSocket `user_message` 只在附带合法 Skill 时接受可选 `display`：

- 必须是字符串。
- 长度不得超过普通消息上限。
- 仅影响 Transcript，不改变模型输入。
- 未提供时保持现有 `/skill ...` 显示规则。

面试回答通过 `display=原始回答` 展示；启动通过 `display=开始模拟面试` 展示。
内部 Prompt 继续持久化，确保恢复后模型仍知道 InterviewSession 和 Turn。

## Composer 与语音

面试进行中继续使用标准 Composer：

- 占位文案：`输入回答，或使用语音回答…`。
- Enter/发送：提交当前回答。
- 面试结束后恢复普通 Career Composer 行为。

将 `InterviewView` 中以下能力提取为对话内可复用控制器：

- 当前问题 TTS 自动播放。
- 重播问题。
- Browser/Tauri 录音运行时选择。
- 录音波形。
- 停止、取消和卸载清理。
- ASR transcript 写入 Composer 草稿。

ASR 结果不自动提交。用户可编辑后发送。切换会话、切题或卸载时必须停止麦克风并清理
内存音频，不创建临时音频文件。

## 回合状态

Conversation 控制 Agent 执行，InterviewSession 控制业务状态。

启动：

```text
Conversation user turn
→ mock-interview Skill
→ start_mock_interview
→ Agent 返回保存后的第一题
→ Transcript 显示问题
→ 状态条刷新
```

回答：

```text
Composer 原始回答
→ display sidecar 显示原始回答
→ 内部 Prompt 携带 interview_session_id / turn_id
→ submit_answer + evaluation + next question
→ Agent 返回下一题
→ Transcript 和状态条刷新
```

完成：

```text
最后回答或提前结束
→ finish + generate_report
→ Agent 返回复盘摘要与文件路径
→ 状态条切换 completed
→ Conversation 保持可写
```

完成后用户的普通追问继续进入同一 Career Agent Conversation，不创建新面试或新会话。

## 错误与恢复

- `VERSION_CONFLICT`：重新读取 InterviewSession，保留未发送的 Composer 草稿。
- 面试查询暂时失败：Conversation 历史仍可查看，状态条显示“重试”，不清空消息。
- Conversation 没有绑定面试：按普通 Career 对话渲染。
- 绑定到其他 Conversation：拒绝，不自动改绑。
- 重复启动：复用已绑定 Interview，不创建第二场。
- 语音失败：保留文字输入，显示中文错误。
- 权限审批：继续在标准 Composer 上方显示，不绕过审批。
- 删除 Conversation：不级联删除 Interview Artifact，避免误删私有复盘；删除后的
  Interview 历史入口后续由面试历史功能承接。

## 组件边界

新增：

- `ConversationInterviewBar`
  - 只负责面试状态展示和状态操作。
- `useConversationInterview`
  - 按 Conversation 恢复、轮询和刷新 InterviewSession。
- `useInterviewVoice`
  - TTS、录音、ASR 和资源清理。

修改：

- `App.tsx`
  - Conversation-first 启动与恢复。
  - 移除独立 Interview surface 分支。
  - 拦截面试中的 Composer 发送。
- `Composer.tsx`
  - 提供面试语音控制插槽和动态 placeholder。
- `api.ts`
  - 按 Conversation 查询面试。
  - Skill user message 的安全 display sidecar。
- `careerInterview.ts`
  - 生成内部 Prompt 与可见文本。

保留：

- `InterviewView` 在迁移完成前仅作为待拆分来源。
- Domain、Service、Repository、MCP 和 Artifact 编译逻辑继续复用。

迁移验证通过后删除 `InterviewView` 及其专用 surface，不长期保留两套入口。

## 测试

后端：

- 按 Conversation 查询已绑定面试。
- 普通 Conversation 返回 null。
- 同一 Conversation 不能创建或绑定第二场面试。
- 并发创建不会产生重复绑定。
- 非法 Conversation ID 返回稳定错误。
- display sidecar 只在 Skill 消息中生效并受长度限制。

GUI：

- 岗位列表与详情入口都打开标准 Conversation。
- 新会话出现在最近会话并使用确定性标题。
- 选择最近会话恢复状态条。
- 浏览器刷新恢复当前题和进度。
- 内部 ID、Turn ID 和 Skill Prompt 不出现在 Transcript。
- 用户回答以原文气泡展示。
- 问题以 Agent 气泡展示。
- 审批卡在标准 Composer 上方。
- Browser/Tauri 语音、取消、切题、卸载清理。
- ASR 只填草稿，不自动提交。
- 提前结束、报告下载和同会话复盘追问。
- 普通 Career Conversation 不显示面试状态条。

真实验收：

1. 从真实岗位点击“模拟面试”。
2. 最近会话出现 `模拟面试 · {岗位}`。
3. 完成至少五轮文字面试。
4. 至少一轮使用浏览器麦克风并编辑 transcript 后发送。
5. 刷新页面并从最近会话恢复。
6. 完成后在同一会话追问一个复盘问题。
7. 验证三份 Artifact、隐私、审批和控制台无错误。

## 非目标

- 不重写 Agent Loop、Conversation 或权限系统。
- 不把 InterviewSession 合并进 Conversation 数据库。
- 不实现实时双向流式语音。
- 不新增面试历史独立页面。
- 不在本阶段删除 Interview Artifact。
