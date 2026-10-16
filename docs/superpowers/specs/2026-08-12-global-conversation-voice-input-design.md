# 全局 Conversation 语音输入设计

## 目标

所有 Agent Conversation 都支持语音输入，并在用户点击麦克风后立即给出明确的中文
状态反馈。模拟面试不再自动播放问题语音，也不再提供“重播问题”；面试官问题只以
文字显示，用户可以打字或使用与普通对话相同的语音输入。

## 选定方案

采用通用 Composer 语音控制器：

- 浏览器使用现有内存录音链路和豆包 ASR。
- Tauri 桌面端继续使用现有本地 Whisper 转写。
- 两种运行时在 Composer 中使用一致的状态和错误文案。
- ASR 结果只写入可编辑草稿，不自动发送。

不修改 Conversation、TurnEngine、权限机制或模型调用流程。

## 用户交互

所有 Conversation 的 Composer 都显示麦克风入口，包括 Career、Cowork、Code 和
其他 Persona。

浏览器状态流：

1. `idle`：显示“开始语音输入”按钮。
2. `starting`：点击后立即显示“正在请求麦克风权限…”，按钮不可重复触发。
3. `recording`：显示波形、计时、“停止录音”和“取消录音”。
4. `transcribing`：显示“正在识别…”，发送按钮保持不可用。
5. `idle`：识别文本进入 Composer 草稿，用户可编辑后发送。

桌面端保留本地 Whisper 的启动、录音和转写流程，但使用相同的用户可见状态：

- 正在请求麦克风权限…
- 正在录音
- 正在识别…

语音输入不会自动选择 Skill、不会自动发送消息，也不会改变当前模型和权限模式。

## 模拟面试变化

移除以下行为：

- 当前面试问题的自动 TTS 请求。
- 问题音频自动播放。
- “重播问题”按钮。
- 问题切换时的 TTS Blob URL 管理。

保留以下行为：

- 标准 Conversation 中的文字面试问题。
- 标准 Composer 的文字回答。
- 全局 Composer 语音输入。
- 面试状态条、提前结束、报告和同会话复盘。

模拟面试不再拥有专用语音控制器。语音是 Conversation 输入能力，不是 Interview
业务状态的一部分。

## 组件边界

### `useConversationVoice`

新增通用 Hook，负责浏览器语音输入：

- 检测安全上下文和录音能力。
- 立即进入 `starting` 状态。
- 启动现有 Browser AudioWorklet 内存采集。
- 停止或取消录音。
- 调用现有豆包 ASR HTTP 接口。
- 返回 transcript、状态、音量和中文错误。
- 切换 Conversation 或卸载时取消采集并清理内存。

Hook 不读取 InterviewSession，不播放音频，不发送消息。

### `Composer`

Composer 继续维护草稿，负责：

- 为所有 Conversation 渲染麦克风入口。
- 展示 starting、recording、transcribing 状态。
- 将 transcript 合并到当前草稿。
- 录音或识别期间禁用发送。

桌面端继续复用现有 Tauri dictation API；浏览器端使用 `useConversationVoice` 提供的
控制器。Composer 不直接实现底层音频编码。

### `App`

App 创建浏览器语音控制器并传给 Composer，不再基于
`waitingForInterviewAnswer` 决定语音入口是否出现。

App 不再创建 `useInterviewVoice`，面试状态条不再接收重播回调。

## 错误与资源清理

- 权限弹窗尚未响应：保持 `starting`，显示“正在请求麦克风权限…”。
- 用户拒绝权限：显示“未获得麦克风权限，请在浏览器地址栏允许后重试。”
- 无可用麦克风：显示“未检测到可用麦克风，请连接设备后重试。”
- 非安全上下文或浏览器不支持：按钮禁用并显示明确原因。
- 空音频或 ASR 失败：保留原草稿，显示“语音识别失败，请直接输入文字。”
- 取消录音：不调用 ASR，不修改草稿。
- 切换 Conversation、组件卸载或达到五分钟上限：停止或取消采集，释放
  AudioContext、MediaStream 和内存样本。

错误只影响语音输入，文字 Composer 始终可继续使用。

## 测试与验收

### Hook

- 点击后在 `getUserMedia` resolve 前立即进入 `starting`。
- 成功启动后进入 `recording` 并更新音量。
- 停止后进入 `transcribing`，完成后回到 `idle`。
- transcript 回填但不触发发送。
- 取消、切换 Conversation 和卸载均清理采集。
- 权限拒绝、无设备、空 transcript 和 ASR 失败显示中文错误。

### Composer 与 App

- Career、Cowork、Code Conversation 都显示语音入口。
- starting、recording、transcribing 有明确可见反馈。
- 录音和识别期间不能发送。
- transcript 可继续编辑。
- 模拟面试仍通过同一语音入口回答。
- 页面不再出现“重播问题”。
- 新问题出现时不调用 TTS 接口。

### 运行态

1. 在普通 Conversation 点击麦克风，立即看到权限请求状态。
2. 允许权限后看到波形和计时。
3. 停止后看到识别状态，文字进入草稿且未发送。
4. 在模拟面试中重复相同流程。
5. 切换会话时麦克风关闭。
6. 控制台无新增错误，网络中没有问题 TTS 请求。

## 非目标

- 不实现实时双向语音通话。
- 不实现语音活动检测或自动提交。
- 不保存原始录音文件。
- 不新增语音消息类型。
- 不更换豆包 ASR 或桌面 Whisper 模型。
