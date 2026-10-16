# 03 — 技术架构

## 1. 总体架构

```text
OpenWorker Desktop / Browser GUI
        │
        ▼
OpenWorker Local Agent Server
  ├── Career Persona
  ├── Career Skills
  ├── TurnEngine / Permissions / Memory / Automation
  └── MCP Client
        │ stdio（MVP）
        ▼
Career MCP Server
  ├── MCP Tools
  ├── Domain Services
  ├── Job / Resume / Match / Tracking / Interview Services
  ├── Versioned SQLite Repositories (schema v11)
  ├── Crawl Orchestrator
  ├── Source Adapters
  ├── Offline OCR
  └── Artifact Compilers
        │
        ├── SQLite
        ├── Private resume staging / generated artifacts
        ├── Raw snapshots / local fixtures
        └── Official recruitment pages
```

## 2. 组件职责

### OpenWorker

- 用户对话和多轮任务。
- 模型选择和调用。
- 工具调用编排。
- 权限审批。
- 文件交付。
- Skill 和 Persona。
- MCP 连接。

### Career MCP

- 对 Agent 提供领域工具。
- 校验参数和输出。
- 调用 Career Domain Services。
- 将内部异常转换为清晰工具错误。

### Domain Services

- 手动 JD 导入。
- 岗位搜索和详情。
- 抓取运行。
- 标准化和持久化。
- 去重、版本、事件。
- 简历导入、事实确认和私有文件生命周期。
- 岗位匹配、收藏、申请进度和 CAS 并发控制。
- 申请包、定制简历和导出校验。
- 模拟面试 Blueprint、Turn、评价和 Artifact。

### Adapters

- 只负责特定数据源的发现、请求和解析。
- 输出统一 RawJob/NormalizedJob。
- 不负责 Agent、GUI、业务文案。

## 3. 当前技术选择

- Python + FastAPI：OpenWorker 本地 Server 和 Career HTTP 边界。
- MCP Python SDK：可信工作区 stdio 工具。
- `sqlite3`：版本化本地数据库，当前 schema v11。
- `httpx`：公开官方 API 和页面请求。
- Playwright：仅用于必须由公开页面正常生成会话或签名的来源。
- RapidOCR + ONNX Runtime：完全离线的扫描 PDF OCR。
- React 18 + TypeScript + Vitest：GUI 和组件测试。
- Tauri + Rust STT sidecar：桌面壳和本地 Whisper。

当前不引入 Redis、Celery、Kafka、Elasticsearch、PostgreSQL 或向量数据库。

## 4. 目录与依赖方向

```text
MCP Tool → Application Service → Repository / Crawler → Infrastructure
```

禁止反向依赖：

- Crawler 不依赖 OpenWorker。
- Repository 不依赖 MCP。
- Domain Model 不依赖 SQLAlchemy ORM 细节（如成本可控，至少保持 schema 与 persistence 分离）。
- OpenWorker 核心不导入 `career_mcp` 内部模块；通过 MCP 通信。

## 5. 运行模式

### 本地开发

- OpenWorker Server：进程 A。
- Vite/Tauri GUI：进程 B。
- Career MCP：由 OpenWorker 按配置启动，或测试时独立运行。
- SQLite：本地数据目录。

### 本地定时抓取

使用 OpenWorker Automation 调用 Career Skill/MCP。`crawl_all_sources` 通过游标让每次
调用只处理一个来源，保留逐来源审批、超时和失败隔离。Career MCP 不维护第二套调度
系统。

### 云端后续

将 Career Domain 和 Crawler 部署到单台服务器，MCP 改为 HTTP；OpenWorker 可继续本地运行并连接远程 Career MCP。此项不属于 P0。

## 6. 数据流

### 手动 JD

```text
用户文本
→ Career Agent
→ import_manual_jd
→ 文本清洗
→ 字段抽取
→ Schema 校验
→ 岗位/版本/事件写入
→ 返回 job_id
→ Agent 生成分析文件
```

### 官方抓取

```text
Source 配置
→ Adapter.fetch_listing
→ Adapter.fetch_detail
→ Adapter.parse
→ normalize
→ validate
→ identity resolution
→ upsert job
→ compare hash/fields
→ version + event
→ crawl run summary
```

### 简历与申请材料

```text
PDF / DOCX / 文本
→ 私有 staging
→ 原生解析或离线 OCR
→ 用户逐项确认
→ Career Vault
→ 岗位证据匹配快照
→ 申请包 / 定制简历提案
→ 用户确认
→ 原子导出 DOCX + PDF
```

### 模拟面试

```text
Job + confirmed resume + fresh match
→ InterviewSession / Blueprint v2
→ 绑定标准 Career Conversation
→ TurnEngine 调用 mock-interview Skill
→ 单维度问题门禁
→ 文字或语音草稿回答
→ 评价与下一题
→ transcript / report / session artifacts
```

## 7. 错误模型

统一错误类型建议：

- `SourceUnavailable`
- `AccessRestricted`
- `ParseError`
- `ValidationError`
- `PersistenceError`
- `JobNotFound`
- `UnsupportedInput`

MCP 输出应包含：

- `ok`
- `error_code`
- `message`
- `retryable`
- `details`（不得泄露密钥）

## 8. 可观测性

MVP 使用结构化日志：

- source_id
- crawl_run_id
- adapter
- URL
- phase
- duration_ms
- parsed_count
- new_count
- changed_count
- offline_count
- error_code

不得默认记录用户完整简历或模型密钥。

## 9. 配置

主要运行配置：

- `CAREER_DATA_DIR`
- `COWORKER_STATE_DIR`
- `.coworker/mcp.json`
- `config/mvp_sources.yaml`

默认 SQLite 数据建议落在用户数据目录，不提交 Git。测试使用临时数据库。

## 10. 演进原则

只有满足以下条件才考虑拆服务：

- 多用户云端成为真实需求。
- 定时抓取需要独立常驻。
- SQLite 出现明确并发瓶颈。
- MCP 与抓取发布周期明显不同。

在此之前保持模块化单体。
