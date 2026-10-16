# 岗位模拟面试双入口与启动修复设计

## 目标

让每一个岗位 JD 都有清晰、稳定的“模拟面试”入口，并修复进入
`InterviewView` 后点击“开始面试”没有任何反应的问题。

成功标准：

1. 每条岗位列表卡片和岗位详情头部都有独立“模拟面试”按钮。
2. 两个入口使用同一个设置流程，不在匹配结果内部保留重复入口。
3. 没有 fresh 简历匹配时，系统引导选择已确认简历并自动生成匹配。
4. 点击开始后必须立即显示进度或错误，不允许静默无反应。
5. Career Session 使用真实可信工作区连接 TurnEngine，并成功生成第一题。

## 已确认根因

真实 `coworker/personas/builtin/career.md` 属于 `code` family，因此 Career
Session 需要工作区。岗位启动逻辑创建新 Conversation 后把 `workspace` 清空；
App 的连接 effect 随后因 `gatesWorkspace("career") && !workspace` 直接返回。

结果是 `InterviewView` 把启动 turn 放入队列，但没有 Session/WebSocket 可以发送，
页面和网络均没有变化。

现有 App 测试把 Career Persona mock 成 `knowledge` family，绕过了真实工作区门禁，
因此没有捕获该故障。

## 交互设计

### 列表入口

每条岗位列表卡片右侧显示“模拟面试”按钮。按钮点击必须阻止卡片选择事件，不改变
当前详情选择，直接打开该岗位的统一面试设置弹层。

### 详情入口

岗位详情标题区显示高优先级“模拟面试”按钮，与收藏、查看官网并列。入口不依赖用户
先展开或执行“匹配简历”。

### 统一设置弹层

列表和详情入口共用同一个状态与弹层，包含：

- 面试简历。
- 面试时长：10/15/20 分钟，对应 5/8/10 题。
- 面试难度：简单/标准/深入。

如果该岗位已有 fresh 匹配，优先展示这些候选简历。如果没有 fresh 匹配，则展示已
确认简历；用户点击开始后，系统先为所选简历生成 fresh 匹配，再创建面试。

匹配失败、没有已确认简历或匹配结果不是 fresh 时，弹层内显示中文错误并保持用户
选择，不创建面试。

### 启动反馈

开始按钮提交后立即变为“正在准备面试…”并禁用。成功创建和绑定后进入
`InterviewView`；首题生成期间显示“面试官正在准备第一题…”。

连接、创建、绑定或 Agent turn 失败必须显示中文错误。不得无限保留一个没有可见
反馈的排队 turn。

## 组件边界

### `CareerJobsView`

拥有统一设置弹层和当前 launch 状态，向列表项与详情头部传递岗位 ID。它协调读取
简历、读取或创建匹配，并向 App 发出一个完整的 `InterviewLaunchPayload`。

### 岗位列表项

只负责展示入口和阻止点击冒泡，不读取匹配、不创建会话。

### `CareerJobMatchPanel`

继续负责匹配分析、申请准备包和定制简历。移除内部模拟面试设置与重复入口，避免
状态分裂。

### `App`

继续负责创建并绑定 Interview Conversation。启动 Career Session 时保留当前可信
工作区；如果没有可用工作区，在创建 Interview 前失败并返回明确错误。

### `InterviewView`

继续通过 `mock-interview` Skill 发起 TurnEngine turn。增加连接/启动中的明确反馈，
但不直接调用领域 Service 绕过 Agent Harness。

## 数据流

```text
列表或详情“模拟面试”
→ 打开统一设置弹层
→ 选择已确认简历、时长、难度
→ 获取该岗位匹配
→ 无 fresh 匹配时创建匹配
→ 生成完整 InterviewLaunchPayload
→ App 创建并绑定 Interview Conversation
→ 保留可信 workspace，连接 Career Session
→ 发送 mock-interview 启动 turn
→ InterviewView 展示第一题
```

## 错误处理

- 无已确认简历：提示先导入并确认简历。
- 自动匹配失败：显示 API 错误，不创建面试。
- 匹配结果 stale：拒绝启动并提示重新匹配。
- 无可信工作区：创建前失败，不留下孤立 Interview。
- WebSocket 未连接：显示等待状态；达到既有连接失败边界后展示错误。
- 重复点击：launch 进行中禁用所有入口和提交按钮。

## TDD 与验收

先增加失败测试，再修改生产代码：

1. App 使用真实 `code` family 且保留 workspace 后，发送启动 turn。
2. 没有 workspace 时显示错误且不调用创建 Interview API。
3. 每条岗位列表卡片都有“模拟面试”按钮，点击不切换岗位。
4. 详情标题区存在“模拟面试”按钮。
5. 两个入口打开同一个设置弹层。
6. 无 fresh 匹配时为所选确认简历创建匹配并启动。
7. 无简历、匹配失败、stale 和重复点击均有确定性断言。
8. 浏览器验收确认点击开始后出现请求、加载反馈和第一题。

## 不做事项

- 不改变 Interview Domain、schema v10 或 MCP 工具协议。
- 不绕过 TurnEngine、Skill、权限或 Conversation 绑定。
- 不增加新的全局导航页面。
- 不修改 OCR、打包或招聘 Adapter。
