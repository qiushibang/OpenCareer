# Aiden-only Composer Model Design

## Goal

OpenCareer 的对话模型选择器只显示并使用
`aiden:deepseek-v4-flash`，且新会话默认选择该模型。

## Scope

- Composer 模型选择器只显示 `DeepSeek V4 Flash · Aiden`。
- 新会话默认模型改为 `aiden:deepseek-v4-flash`。
- 载入使用其他模型的历史会话时，Composer 切换到 Aiden。
- Settings 继续显示其他 Provider 和模型，已有密钥与配置不删除。
- Aiden 不可用时明确显示模型未就绪，不回退到其他模型。

## Design

在 GUI 模型边界增加一个纯函数策略：输入 Server 返回的模型、当前模型和
Aiden 可用状态，输出 Composer 唯一允许的模型与当前选中值。Settings 仍直接使用
Server 的完整 `models`，因此不受影响。

当前本地状态通过已有 `set_default_model` 路径迁移为
`aiden:deepseek-v4-flash`。OpenWorker 通用 Server 的 fresh-state 默认值保持不变，
避免破坏 Provider 首次配置规则；OpenCareer Composer 自身始终选择并发送 Aiden。

## Verification

- 纯函数测试证明其他模型不会进入 Composer。
- 本地默认模型持久化为 Aiden，Composer 策略保证新会话使用 Aiden。
- GUI 全量测试与 production build 通过。
- 后端 Provider、Settings 和 Server 回归通过。

## Non-goals

- 不删除火山方舟、OpenAI 或其他 Provider 配置。
- 不移除 Settings 中的模型管理能力。
- 不修改模型路由、工具调用或会话存储协议。
