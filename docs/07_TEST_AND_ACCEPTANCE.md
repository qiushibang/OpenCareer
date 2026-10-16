# 07 — 测试与验收计划

> 本文的 A-001–A-010 是早期基础 Gate，均已完成。新增功能继续遵循相同的隔离和
> 证据标准；当前重点 Gate 见本页第 3 节后半部分。

## 1. 测试层级

### OpenWorker 回归

- Persona registry/parser 测试。
- Skill loader 相关测试。
- MCP config/client 相关测试。
- 权限和文件根目录测试。
- GUI 最小 E2E 或 smoke test。

### Career MCP 单元测试

- Tool 参数和返回 schema。
- Domain service。
- Repository 查询。
- 错误转换。

### Crawler fixture 测试

- listing parse。
- detail parse。
- 空字段。
- 模板轻微变化。
- 非 200 响应模拟。

### Pipeline 集成测试

- created。
- unchanged。
- changed。
- missing 未下线。
- 达阈值 offline。
- reopened。
- source failed 时不增加 missing_count。

### 端到端

- OpenWorker Career Persona 调 MCP。
- 手动 JD 入库和检索。
- Agent 生成 Markdown 文件。
- 岗位雷达、Career Vault、匹配、申请材料和模拟面试 GUI 流程。
- 浏览器与 Tauri 两条语音输入路径。
- macOS/Windows 离线模型打包。

## 2. 测试隔离

- 默认测试不得访问互联网。
- 使用临时 SQLite。
- fixture 固定且记录来源日期。
- 在线 smoke test 使用标记，例如 `@pytest.mark.live`。
- CI 默认跳过 live。

## 3. 核心验收场景

### A-001 Persona

Given OpenWorker 启动，When 创建新会话，Then Career Persona 可见并可选择。

### A-002 未信任 MCP

Given 工作区未信任，When 打开会话，Then `.coworker/mcp.json` 不启动 Career MCP。

### A-003 信任后连接

Given 工作区已信任，When 新建 Career 会话，Then Career MCP 工具可用。

### A-004 Mock 工具

When 用户请求测试岗位，Then Agent 必须调用 MCP，并把返回内容写入文件。

### A-005 手动 JD

Given 一个完整 JD，When 导入并确认，Then Job、Version、Event 各产生正确记录。

### A-006 幂等

When 同一 Job 再次抓取且内容相同，Then 不新增 Job/Version/changed Event。

### A-007 修改

When requirements 改变，Then 新增 Version 和 changed Event，diff 包含 requirements。

### A-008 失败保护

When source 抓取失败或解析岗位数异常下降，Then 不批量标记 offline。

### A-009 查询

When 查询“北京 + internship + 最近 7 天”，Then 只返回符合条件的 active 岗位。

### A-010 来源追溯

每个岗位详情必须返回 source_url、first_seen_at、last_seen_at。

### A-011 Career Vault 与 OCR

简历原件保持私有；扫描 PDF 在断网环境使用本地模型；事实必须逐项确认；删除后无
临时图片或可识别原文残留。

### A-012 岗位匹配和材料

每项匹配和改写必须引用已确认事实。`none` 证据不能进入能力声明；stale 快照不能
导出；DOCX/PDF 发布必须原子且可校验。

### A-013 申请跟踪

收藏与申请阶段独立；状态更新使用 version/CAS；历史时间线不可重写。

### A-014 模拟面试

问题同时基于 JD 与简历证据，并且一个问题只对应一个深挖维度。非法问题不持久化。
面试位于标准 Conversation，可刷新恢复并生成报告、逐字稿和 session Artifact。

### A-015 全局语音输入

所有 Agent Composer 均有语音入口。浏览器点击后立即显示权限状态，桌面端继续使用
本地 Whisper。识别结果只进入当前 Conversation 草稿；切换会话后旧结果不得回填。
模拟面试不自动播放问题。

## 4. 质量门槛

合并 Career 变更前：

- 相关 Python 测试通过。
- OpenWorker 受影响测试通过。
- 无新增高严重度 lint/type 错误。
- 文档和配置示例同步更新。
- 新 Adapter 至少有 listing 和 detail fixture。
- 共享 GUI 行为需运行 GUI 全量测试和 `npm run build`。
- 数据库或打包变更需运行 Python `compileall`、迁移/外键检查和离线 Gate。
- 所有变更运行 `git diff --check`。

## 5. 手动演示脚本

1. 启动 Server 和 GUI，确认可信工作区 Career MCP 已连接。
2. 在岗位雷达筛选岗位，打开详情并核对官方来源。
3. 在求职档案切换一份已确认简历，检查原文件和事实页签。
4. 生成 fresh 岗位匹配，核对证据、缺口和 stale 状态。
5. 创建申请准备包或定制简历，逐条确认并导出。
6. 从岗位启动模拟面试，完成文字回答、下一题和刷新恢复。
7. 在普通 Conversation 和面试 Conversation 分别点击语音输入。
8. 允许麦克风，确认 transcript 进入草稿但没有自动发送。
9. 检查浏览器控制台和网络，不得出现新错误或问题 TTS 请求。

真实设备、在线来源或模型 Gate 必须记录环境、时间、对象 ID 和限制；不能用 fixture
或 mock 冒充真实验收。
