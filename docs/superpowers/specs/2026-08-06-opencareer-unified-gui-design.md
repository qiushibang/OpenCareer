# OpenCareer 统一求职产品 GUI 设计

## 1. 背景

当前 Career Persona 已接入岗位搜索、JD 分析和简历导入能力，但 GUI 仍沿用
OpenWorker 的通用 Coworker 产品表达：

- 主品牌显示为 `OpenWorker`。
- Career 空会话显示开发任务示例和 `Let's build something.`。
- 输入框提示为 `Ask the coworker...`。
- 用户需要先理解 Persona，才能找到求职功能。

这导致产品能力已经垂直化，而首屏心智仍是通用工作 Agent。

## 2. 产品决策

采用统一求职产品方案，用户可见品牌为 **OpenCareer**。

OpenWorker 继续作为底层 Agent Harness 和上游工程基线。此次改动只调整 GUI
的产品表达、Career 空会话和默认入口，不重写 Agent Loop、会话、权限、MCP、
Automation 或 Provider Router。

`OpenOffice` 不作为产品名，因为它与现有办公软件品牌高度混淆，也无法直接表达
求职场景。

## 3. 目标

1. 用户打开产品后，首先感知到的是求职 Agent，而不是通用 Coworker。
2. Career 空会话直接展示当前真实可用的三条核心路径。
3. 点击任一快捷任务后，立即进入现有对话和工具调用链路。
4. 保留 OpenWorker 通用能力和其他 Persona 的可访问性。
5. 不展示尚未实现的独立页面或虚假业务状态。

## 4. 非目标

- 不新增“我的简历”“收藏岗位”“申请材料”等独立页面。
- 不在首页硬编码岗位总数、今日新增数或简历完成度。
- 不修改 Career MCP 工具协议和数据库。
- 不删除 Coworker 或其他 Persona。
- 不进行全量视觉系统、设置页、Cloud 文案或桌面包名重构。
- 不修改上游许可证、代码包名和内部兼容标识。

## 5. 用户体验

### 5.1 品牌

侧栏左上角用户可见字标从 `OpenWorker BETA` 改为 `OpenCareer BETA`。

本阶段只修改主工作区的核心品牌入口。涉及 OpenWorker Cloud、OAuth client、
文件目录和内部协议的名称保持原样，避免把展示层改名扩散为不必要的系统迁移。

### 5.2 默认入口

没有可恢复会话或用户历史选择时，GUI 默认选择 `career` Persona。

如果用户已有最近会话或明确选择了其他 Persona，继续遵守现有恢复逻辑，不强制
跳回 Career。这样既建立求职产品默认心智，也不破坏用户的连续工作状态。

### 5.3 Career 空会话

Career 新会话在没有消息时显示：

- 眉题：`你的求职 Agent`
- 标题：`今天从哪里开始？`
- 说明：`我会基于已确认的真实经历，帮你发现岗位、判断匹配并准备申请材料。`

提供三个真实快捷入口：

1. **建立求职档案**
   - 辅助文案：`导入简历并逐项确认经历`
   - 点击后预填简历导入指令，并提示用户通过附件菜单上传 PDF/DOCX 或粘贴文本。
   - 不自动打开系统文件选择器，避免把首页组件与上传实现耦合。

2. **发现合适岗位**
   - 辅助文案：`从官网岗位中按目标公司、城市和方向搜索`
   - 点击后预填一条要求用户补充求职目标的岗位搜索请求。

3. **分析一份 JD**
   - 辅助文案：`粘贴职位描述，查看要求、匹配点和风险`
   - 点击后预填 JD 分析请求，等待用户粘贴内容。

快捷入口统一使用“预填但不自动发送”。用户可以检查和补充输入，避免无参数工具
调用，也延续现有审批和对话机制。

### 5.4 Composer

当 `personaId === "career"` 时，占位文案改为：

`告诉我你的求职目标，或直接导入简历…`

其他 Persona 保留原有占位文案，避免 Career 品牌化破坏通用模式。

### 5.5 其他 Persona

Coworker 使用现有 `SessionIntro`。Chat、Code 和其他 Persona 继续使用现有空会话
逻辑。Career 专属内容通过 persona id 分支渲染，不改变其数据模型。

## 6. 组件边界

新增一个小型、无数据请求的 `CareerWelcome` 展示组件：

- 输入：`onPrefill(text: string)`.
- 输出：标题、说明和三个快捷任务按钮。
- 依赖：现有图标和样式体系。
- 不直接调用 API，不读取数据库，不管理上传。

`App.tsx` 只负责在 `idle && agent === "career"` 时选择该组件，并把现有
`prefillComposer` 传入。

`Composer.tsx` 根据 `personaId` 选择占位文案。

`Sidebar.tsx` 修改用户可见主字标。

默认 Persona 的改动限定在 `App.tsx` 初始状态。会话恢复、Persona 注册和切换逻辑
继续复用现有实现。

## 7. 错误与降级

- 工作区未选择时，快捷入口仍可预填；实际发送继续由现有 Folder Gate 约束。
- Career Persona 不存在时，现有 Persona/会话恢复逻辑应继续工作，不因欢迎组件
  抛错。
- 上传失败、MCP 不可用和审批拒绝仍由现有 Composer、工具卡片和错误消息处理。
- 欢迎页不请求实时岗位统计，因此不会因 Career MCP 离线而显示错误或过期数字。

## 8. 测试与验收

### 8.1 组件测试

- `CareerWelcome` 渲染三条求职任务，不出现开发任务示例。
- 点击每条任务会调用 `onPrefill`，且不会自动发送。
- Career Composer 显示求职占位文案。
- 非 Career Composer 仍显示原占位文案。
- Sidebar 显示 `OpenCareer BETA`。

### 8.2 集成回归

- 新安装或无历史状态时默认 Persona 为 `career`。
- 有历史会话时仍恢复原 Persona。
- Career 空会话显示专属欢迎页。
- Coworker 空会话仍显示现有 `SessionIntro`。
- 其他 Persona 的空会话和发送流程不变。

### 8.3 验证命令

- 运行新增 GUI 定向测试。
- 运行现有 GUI 全量测试。
- 运行 GUI production build。
- 浏览器 smoke test：创建 Career 新会话，验证品牌、欢迎页、三条快捷入口和输入框。

## 9. 实施边界

预计只修改或新增以下 GUI 文件及其测试：

- `surfaces/gui/src/App.tsx`
- `surfaces/gui/src/components/CareerWelcome.tsx`
- `surfaces/gui/src/components/Composer.tsx`
- `surfaces/gui/src/components/Sidebar.tsx`
- 对应 `*.test.tsx`
- 必要的局部样式文件

每一行实现改动必须能追溯到品牌、默认入口、Career 欢迎页或 Career Composer 文案。
