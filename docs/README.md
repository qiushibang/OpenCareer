# OpenCareer 文档导航

本页是项目文档的权威入口。开始开发前先阅读本页，再按任务类型读取对应文档。
不要根据旧实施计划中的未勾选项推断当前进度。

## 当前状态

OpenCareer 是基于 OpenWorker Fork 的本地优先求职 Agent。目前已贯通：

- Career Persona、Skills、可信工作区 MCP 和标准 Conversation。
- 手动 JD、官方招聘源采集、岗位标准化、版本和下线判断。
- 岗位雷达、筛选、详情、收藏和申请进度。
- 多简历 Career Vault、离线 OCR、事实确认和安全删除。
- AI 直接读取 JD 与脱敏简历的诊断、追问、改写建议和面试准备。
- JD/已确认简历直读的多轮模拟面试、复盘和历史记录。
- 所有 Conversation 的语音输入：浏览器使用豆包 ASR，桌面端使用本地 Whisper。

Career 数据库当前 schema 为 v13。GUI 使用 Tauri/React，后端使用 Python，
Career 领域能力通过 `extensions/career_mcp` 与 OpenWorker 核心隔离。

最新工程 Gate：

- GUI 全量：47 files / 256 tests passed。
- 全局 Conversation 语音聚焦回归：44 tests passed。
- 生产构建、Python compileall 和 `git diff --check` 通过。
- 真人麦克风转写仍需设备授权后的现场验收。

准确的逐阶段证据见
[`11_DEVELOPMENT_LOG.md`](11_DEVELOPMENT_LOG.md) 和
[`12_TONIGHT_PROGRESS.md`](12_TONIGHT_PROGRESS.md)。

## 文档优先级

发生冲突时按以下顺序判断：

1. 根目录 `AGENTS.md`：不可违反的项目和安全约束。
2. 本页：当前状态、文档分类和下一阶段方向。
3. 当前功能的最新 `docs/superpowers/specs/` 规格。
4. 当前代码、迁移和自动化测试。
5. `00`–`10` 基础文档。
6. 历史实施计划和开发日志。

历史计划记录当时的实施过程，不是当前 backlog。代码行为与旧计划不一致时，先检查
是否已有更新日期更晚的规格和验收记录。

## 开发入口

| 任务 | 必读文档 |
|---|---|
| 项目范围与产品决策 | [`00_SCOPE_AND_DECISIONS.md`](00_SCOPE_AND_DECISIONS.md) |
| OpenWorker 扩展边界 | [`02_OPENWORKER_INTEGRATION.md`](02_OPENWORKER_INTEGRATION.md) |
| 当前技术架构 | [`03_TECHNICAL_ARCHITECTURE.md`](03_TECHNICAL_ARCHITECTURE.md) |
| 招聘源和抓取器 | [`04_JOB_CRAWLER_SPEC.md`](04_JOB_CRAWLER_SPEC.md)、[`13_SOURCE_COVERAGE_MATRIX.md`](13_SOURCE_COVERAGE_MATRIX.md) |
| 数据和 MCP 工具 | [`05_DATA_MODEL_AND_MCP_TOOLS.md`](05_DATA_MODEL_AND_MCP_TOOLS.md)、`extensions/career_mcp/database/migrations.py` |
| 当前路线图 | [`06_IMPLEMENTATION_PLAN.md`](06_IMPLEMENTATION_PLAN.md) |
| 测试与验收 | [`07_TEST_AND_ACCEPTANCE.md`](07_TEST_AND_ACCEPTANCE.md) |
| 部署评估 | [`08_DEPLOYMENT_DOMAIN_COST.md`](08_DEPLOYMENT_DOMAIN_COST.md) |
| 当前 backlog | [`09_CODEX_TASK_BACKLOG.md`](09_CODEX_TASK_BACKLOG.md) |
| 安全和合规 | [`10_RISK_AND_COMPLIANCE.md`](10_RISK_AND_COMPLIANCE.md) |

## 运维手册

- [`22_LOCAL_QUICKSTART.md`](22_LOCAL_QUICKSTART.md)：源码本地网页版安装、数据备份与限制。
- [`21_OPEN_SOURCE_RELEASE.md`](21_OPEN_SOURCE_RELEASE.md)：干净快照发布与本地版验收边界。

- [`14_CRAWL_ALL_SOURCES_RUNBOOK.md`](14_CRAWL_ALL_SOURCES_RUNBOOK.md)：
  全来源游标抓取和审批。
- [`15_DAILY_JOB_RADAR_DIGEST_RUNBOOK.md`](15_DAILY_JOB_RADAR_DIGEST_RUNBOOK.md)：
  每日岗位摘要。
- [`16_RESUME_IMPORT_RUNBOOK.md`](16_RESUME_IMPORT_RUNBOOK.md)：
  简历导入、私有存储和删除。
- [`17_MOCK_INTERVIEW_COMPLETION_AUDIT.md`](17_MOCK_INTERVIEW_COMPLETION_AUDIT.md)：
  模拟面试规格验收矩阵。
- [`18_BACKUP_AND_ROLLBACK_RUNBOOK.md`](18_BACKUP_AND_ROLLBACK_RUNBOOK.md)：
  SQLite/文件卷、PostgreSQL、镜像与加密配置的正式备份、隔离恢复和回滚步骤。
- [`19_DOMAIN_AUTHING_LAUNCH_RUNBOOK.md`](19_DOMAIN_AUTHING_LAUNCH_RUNBOOK.md)：
  `app.opencareer.online`、Authing、备案后 DNS、双账号隔离验收和回滚步骤。
- [`20_FEEDBACK_SUPPORT_RUNBOOK.md`](20_FEEDBACK_SUPPORT_RUNBOOK.md)：
  站内反馈、脱敏诊断、管理员问题中心与独立主机检查；前三项已于 2026-09-20
  发布生产，独立主机检查及外部提醒按用户决策暂不启用。

## 历史与证据

- `docs/source-notes/`：各官方招聘源的公开接口、限制和合规证据。即使来源停用也
  保留，避免重复调查或误用受限接口。
- `docs/ocr/`：OCR 离线和打包 Gate 证据。
- `docs/superpowers/specs/`：已批准的设计决策。后续规格可以取代旧交互，但旧文件
  保留为决策记录。
- `docs/superpowers/plans/`：TDD 实施过程。只用于追溯，不作为未完成任务列表。
- `11_DEVELOPMENT_LOG.md`：按时间追加的工程证据，不回写或删除历史结论。
- `12_TONIGHT_PROGRESS.md`：累计阶段罗盘，文件名为历史遗留，内容继续保留。

## 当前剩余工作

云端 PostgreSQL 多租户、Principal（请求身份）、Career 数据隔离和 SessionManager 用户实例已经进入当前基线。Authing 单域名登录已于 2026-08-31 发布到 `https://app.opencareer.online`，备案号、DNS、HTTPS、migration 10 和匿名访问边界均已通过服务器 Gate：

1. 用两个独立测试账号完成对话、虚构简历、收藏和申请进度的交叉隔离验收。
2. 明确历史 `local` 数据是丢弃还是迁移给指定账号；不得自动绑定给首个登录用户。
3. 网站开通后 30 日内完成公安联网备案，并在页面补充公安备案标识。

云端 BYOK（用户自带 API Key 与自选模型）代码已实现并本地验收，规格见
`docs/superpowers/specs/2026-09-01-cloud-byok-model-config-design.md`，
待部署到生产并完成真实浏览器 Gate（配置 key、切换默认模型、双账号隔离）。

原产品质量方向继续保留，其中面试体验拆成两个原子任务：

1. 面试体验：完成真人麦克风 Gate，以及完整五轮标准 Conversation 面试和同会话
   复盘的人工验收。
2. 首题稳定性：降低真实模型触发单维度门禁后的重试次数。
3. 跨平台打包：完成 Windows x64 OCR 离线 Gate；macOS 已有本地验收证据。
4. 来源稳定性：持续观察官方招聘源并更新覆盖矩阵，不以来源数量替代质量。

对应五个可执行任务为 `OC-101` 至 `OC-105`。

## 文档维护规则

- 新功能先写或更新最新规格，再写 TDD 计划。
- 完成后只把事实证据追加到开发日志和阶段罗盘。
- 不在 README 维护易过期的实时岗位数量；数量放在覆盖矩阵或验收日志。
- 不删除来源证据、迁移说明、隐私 Gate 和已批准规格。
- 可以删除无引用、可自动再生成、且不含验收证据的临时清单或导出文件。
