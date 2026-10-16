# 09 — Codex 可执行任务 Backlog

每个任务都应作为一个小 PR/commit 范围执行。只执行“当前 backlog”；OW-000 至
OW-020 是已完成的项目启动档案。

## 当前 backlog

### OC-201 M0 云端服务器 Gate

**目标**：在阿里云真实执行后端镜像构建和 IP Compose，验证健康检查、受保护 REST、
Alpha 403、WebSocket 101、模型对话和脱敏简历。

**读取**：`deploy/README-aliyun.md`、`.trae/rules/project_rules.md`。

### OC-202 M1a-2 Career 数据隔离

**目标**：根据 `request.state.principal.user_id` 选择独立 Career SQLite 和私有简历
目录，保持桌面和 legacy 单用户路径不变。

**前置**：OC-201 通过；M1a-1 已完成代码 Gate。

**读取**：`superpowers/plans/2026-08-17-m1-multi-tenant.md`。

### OC-101 真人麦克风 Gate

**目标**：在浏览器真实授权麦克风，验证中文录音、豆包 ASR、可编辑草稿和不自动
发送；再抽查 Tauri 本地 Whisper。

**验收**：普通 Conversation 与模拟面试均通过；切换会话后无录音或旧 transcript
残留；控制台无新增错误。

**读取**：`superpowers/specs/2026-08-12-global-conversation-voice-input-design.md`、
`superpowers/plans/2026-08-12-global-conversation-voice-input.md`。

### OC-102 完整五轮 Conversation 面试

**目标**：从岗位入口完成五轮 JD/简历驱动面试、报告和同会话复盘。

**验收**：问题维度合法、非法问题不持久化、刷新可恢复、三份 Artifact 完整且通过
隐私检查。

**读取**：`superpowers/specs/2026-08-12-conversation-native-mock-interview-design.md`、
`superpowers/specs/2026-08-11-resume-grounded-interview-intelligence-design.md`、
`17_MOCK_INTERVIEW_COMPLETION_AUDIT.md`。

### OC-103 首题稳定性

**目标**：降低真实模型因复合问题或 probe dimension 冲突导致的重试次数。

**约束**：不能放宽单维度门禁；优先改 Prompt、Skill 和结构化错误反馈。

**读取**：`superpowers/specs/2026-08-12-single-dimension-question-validation-design.md`、
`superpowers/plans/2026-08-12-single-dimension-question-validation.md`。

### OC-104 Windows OCR 离线包

**目标**：补齐 Windows x64 的 OCR 模型打包、安装后禁网解析和残留审计。

**验收**：运行时不下载模型，fixture 与 macOS 使用相同质量门槛。

**读取**：`superpowers/specs/2026-08-10-scanned-pdf-ocr-design.md`、
`superpowers/plans/2026-08-10-scanned-pdf-ocr.md`、
`ocr/2026-08-10-gate0-evidence.md`。

### OC-105 来源稳定性观察

**目标**：更新来源覆盖矩阵，记录成功率、数量漂移、耗时和失效原因。

**约束**：只访问公开官方来源；新增 Adapter 前必须有 source note 和离线 fixture。

**读取**：`13_SOURCE_COVERAGE_MATRIX.md`、`14_CRAWL_ALL_SOURCES_RUNBOOK.md` 和
对应 `source-notes/<company>.md`。

## 已完成的启动档案

### OW-000 基线检查

**目标**：确认固定 OpenWorker commit 可运行。

**读取**：AGENTS、START_HERE、上游 README。

**修改**：只新增开发日志，除非环境兼容必须修复。

**验收**：Server、GUI、最小测试。

### OW-001 Career Persona

**修改建议**：

- `coworker/personas/builtin/career.md`
- Persona tests
- 必要图标配置

**禁止**：修改 TurnEngine。

### OW-002 Career Skills 骨架

新增：

- `.coworker/skills/career-jd-analysis/SKILL.md`
- `.coworker/skills/career-job-search/SKILL.md`
- `.coworker/skills/career-application-packet/SKILL.md`

先写清流程，不实现 P1 业务。

### OW-003 Career MCP 包

创建 `extensions/career_mcp`，实现 stdio Server、`health_check`、`get_mock_jobs` 和测试。

### OW-004 MCP 工作区配置

新增 `.coworker/mcp.json`。检查当前 `mcpServers` schema、跨平台命令和 Workspace Trust。

### OW-005 端到端 Mock Demo

让 Career Agent 调 `get_mock_jobs`，生成 `artifacts/mock-job-brief.md`。补充演示说明或 E2E。

### OW-006 Career 数据配置

实现数据目录、SQLite URL、日志和 `.gitignore`。

### OW-007 数据模型和迁移

Company、JobSource、Job、JobVersion、JobEvent、CrawlRun、RawSnapshot。

### OW-008 Repository

实现 Job upsert、search、detail、event query，提供单元测试。

### OW-009 Manual JD Tool

实现预览和确认写入两阶段；原始文本、缺失字段、幂等测试。

### OW-010 Crawler Contract

实现 Adapter protocol、FakeAdapter、Orchestrator、pipeline。

### OW-011 Change Detection

实现 stable hash、field diff、version/event、missing/offline/reopened。

### OW-012 Career MCP 查询工具

实现 `get_job`、`search_jobs`、`list_recent_job_events`、`list_sources`、`crawl_source`。

### OW-013 百度调查和 fixture

先产出 source note 和 fixture，再写 Adapter。

### OW-014 百度 Adapter

解析、标准化、集成测试、可选 live smoke。

### OW-015 小米 Adapter

重点分页、大列表、分类。

### OW-016 第三 Adapter

优先 Feishu/MiniMax；不可行则选智谱或 DeepSeek。

### OW-017 Job Search Skill 完善

让 Agent 正确选择工具、使用筛选条件、输出来源。

### OW-018 自动化摘要

复用 OpenWorker Automation，配置可选每日运行或摘要。不得重建调度 UI。

### OW-019 稳定性和演示

- 一键启动说明。
- 测试报告。
- 演示数据。
- 视频脚本。
- 架构图。

### OW-020 P1 决策门

只有以下指标满足才进入简历与申请材料：

- 3 家来源稳定。
- 7 天重复运行无严重重复或误下线。
- Manual JD 与搜索工具稳定。
- Career Agent 端到端可演示。
