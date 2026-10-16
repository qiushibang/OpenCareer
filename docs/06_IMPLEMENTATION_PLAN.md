# 06 — 分阶段实施计划、产出与停止条件

> 文档状态：当前路线图 + 历史启动计划。Stage 0–10 不是待执行列表，也不表示
> 每个可选项都已完成。准确完成证据见 `11_DEVELOPMENT_LOG.md` 和
> `12_TONIGHT_PROGRESS.md`。

## 总原则

一个人开发时，每个阶段都必须产生可演示结果。上一阶段没有通过验收，不进入后续复杂功能。

## 当前阶段

### Gate A：真人 Conversation 语音

- 浏览器允许麦克风后完成中文朗读。
- 验证“请求权限 → 录音 → 识别”的可见状态。
- 豆包 ASR 结果只进入草稿，不自动发送。
- 切换 Conversation 后麦克风和旧转写结果均被释放。

### Gate B：完整模拟面试体验

- 在标准 Career Conversation 中完成至少五轮。
- 验证 JD 与简历项目的岗位差异化深挖。
- 完成报告、逐字稿、同会话复盘追问和刷新恢复。
- 统计首题被单维度门禁拒绝后的重试次数，并优化真实模型稳定性。

### Gate C：跨平台离线打包

- macOS OCR 离线包已有本地 Gate 证据。
- 补齐 Windows x64 的模型打包、禁网 OCR 和安装包验证。
- 不在运行时下载 OCR 或 Whisper 模型。

### Gate D：招聘源运行稳定性

- 按覆盖矩阵观察来源成功率、岗位数量漂移和下线判断。
- 新增来源前先写 source note 和本地 fixture。
- 受限来源降级为手动 JD，不绕过登录、验证码或签名。

## 历史启动计划

### Stage 0：基线与环境

#### 目标

确认固定 OpenWorker 基线可以在开发机运行。

#### 任务

- Fork/clone 并锁定 commit。
- 执行上游环境安装。
- 启动 Server 和 GUI。
- 运行最小后端、前端测试。
- 阅读 Persona、Skill、MCP 代码。
- 建立开发日志。

#### 产出

- 可运行原版 OpenWorker。
- `docs/11_DEVELOPMENT_LOG.md`。
- 当前环境版本和命令记录。

#### 验收

- 后端健康。
- GUI 连接成功。
- 至少一组测试通过。

#### 停止条件

原版无法运行时只修环境或最小兼容问题，不开始 Career 功能。

### Stage 1A：Career Persona

#### 任务

- 创建 `coworker/personas/builtin/career.md`。
- 添加 Manifest/Registry 测试。
- 必要时添加 briefcase 图标映射。
- 确认新会话可选择 Career Agent。

#### 产出

- Career Persona。
- 自动化测试。
- 截图或开发日志说明。

#### 验收

Career 会话可开始普通对话与文件任务，不影响 Cowork/Code Persona。

### Stage 1B：Skill + MCP mock 贯通

#### 任务

- 创建 `career-jd-analysis` 和 `career-job-search` Skill 骨架。
- 创建 `extensions/career_mcp` Python 包。
- 实现 `health_check`、`get_mock_jobs`。
- 配置 `.coworker/mcp.json`。
- 信任工作区并连接 MCP。
- 让 Agent 输出 mock 岗位简报。

#### 产出

- 可运行 Career MCP。
- MCP 契约测试。
- `artifacts/mock-job-brief.md` 示例。

#### 验收

工具调用记录清晰，输出来自 MCP；关闭 MCP 时错误可理解。

### Stage 2：数据层和手动 JD

#### 任务

- 数据目录与配置。
- SQLite schema 和迁移。
- Repository。
- Manual Source。
- `import_manual_jd`、`get_job`、`search_jobs`。
- 文本清洗和确定性字段 parser。
- 允许 Agent 生成岗位分析文件。

#### 产出

- 本地数据库。
- MCP 工具。
- 手动 JD 集成测试。

#### 验收

同一 JD 重复导入不产生错误重复；原始文本和来源保留；查询可找到。

### Stage 3：爬虫框架

#### 任务

- Source Registry。
- Adapter Protocol。
- CrawlRun。
- normalize、identity、hash、version、event pipeline。
- fixture 测试框架。
- `crawl_source` 工具和 CLI。

#### 产出

- 无具体公司的通用框架。
- FakeAdapter 集成测试。

#### 验收

FakeAdapter 可模拟 created、unchanged、changed、missing、reopened。

### Stage 4：百度 Adapter

#### 任务

- 调查官方站点并记录 source note。
- 实现列表/详情获取。
- 保存 fixture。
- 标准化和错误保护。
- 在线 smoke test（可选，不进默认测试）。

#### 产出

- `baidu` Source 配置。
- Adapter 和 fixture。
- 抓取结果可被 Career Agent 查询。

#### 验收

完整 JD 可用；重复抓取幂等；解析失败不会批量下线。

### Stage 5：小米 Adapter

重点验证大列表、分页和分类。验收同 Stage 4。

### Stage 6：第三个来源

优先 MiniMax/飞书；如数据接口不稳定，可选择智谱或 DeepSeek，确保至少一个动态页面来源。

MVP 的爬虫完成门槛：3 家稳定来源，而不是强制 6 家全部完成。

### Stage 7：查询和事件体验

- `search_jobs` 条件完善。
- `list_recent_job_events`。
- Career Skill 输出统一简报。
- OpenWorker Automation 可选配置每日摘要。

#### 验收

用户可在对话中完成：

- 最近新增查询。
- 按公司和城市筛选。
- 查看岗位详情。
- 查看岗位变化。

### Stage 8：剩余 Phase 1 公司

依次评估 MiniMax、智谱、DeepSeek、字节。某站点受限时记录，不阻塞 MVP。

### Stage 9：最小申请材料包（P1）

只有岗位数据闭环稳定后开始：

- 简历导入和用户确认。
- Career Vault 最小模型。
- JD 与经历匹配。
- Markdown 申请材料包。

当时不在此阶段加入语音面试；该能力已在后续阶段实现。

### Stage 10：低成本云部署（可选）

- 单台云主机或容器。
- PostgreSQL 仅在需要时迁移。
- 定时抓取云端运行。
- OpenWorker 本地通过 HTTP MCP 连接。

域名备案可并行，但不阻塞本地演示。

## 历史建议节奏

### 第 1 周

Stage 0、1A、1B、Stage 2 基础。

### 第 2 周

Stage 2 完成、Stage 3、百度。

### 第 3 周

小米、第三来源、搜索与事件。

### 第 4 周

稳定性、文档、演示视频；有余力再做第 4–6 个来源。

## 每阶段提交规范

每个阶段建议独立提交，例如：

- `chore: pin openworker baseline and add project docs`
- `feat(career): add career persona`
- `feat(career-mcp): add mock job tools`
- `feat(career): import manual job descriptions`
- `feat(crawler): add adapter pipeline`
- `feat(crawler): add baidu source adapter`

不要把上游同步、格式化和新功能混在一个提交。
