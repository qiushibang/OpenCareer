# 05 — 数据模型与 Career MCP 工具契约

> 当前实现使用 `sqlite3` 版本化迁移，schema 为 v13。本文保留最初岗位模型的详细
> 设计；新增表和工具的最终字段以
> `extensions/career_mcp/database/migrations.py`、Repository 类型和
> `extensions/career_mcp/server.py` 为准。

## 1. 设计目标

- 支持多公司、多数据源。
- 原始来源可追溯。
- 重复抓取幂等。
- 保存完整历史版本。
- MCP 输出稳定，不直接暴露 ORM 对象。

## 2. 核心实体

### Company

- `id`: UUID/字符串。
- `slug`: 唯一，如 `baidu`。
- `name`。
- `official_website`。
- `career_home_url`。
- `enabled`。
- 时间戳。

### JobSource

- `id`
- `company_id`
- `slug`
- `source_type`: `official_api/public_json/html/playwright/manual`
- `adapter`
- `base_url`
- `config_json`
- `crawl_interval_minutes`
- `enabled`
- `last_success_at`
- `last_failure_at`
- `consecutive_failures`

### Job

- `id`
- `company_id`
- `source_id`
- `external_job_id`
- `canonical_url`
- `apply_url`
- `title`
- `department`
- `location_raw`
- `locations_json`
- `recruitment_type`
- `employment_type`
- `category`
- `description_raw`
- `responsibilities_json`
- `requirements_json`
- `published_at`
- `deadline_at`
- `status`
- `content_hash`
- `first_seen_at`
- `last_seen_at`
- `last_changed_at`
- `missing_count`
- `created_at`
- `updated_at`

唯一约束优先：`source_id + external_job_id`。外部 ID 为空时通过 repository 层处理 canonical URL/fingerprint。

### JobVersion

- `id`
- `job_id`
- `version_number`
- `content_hash`
- `snapshot_json`
- `field_diff_json`
- `captured_at`
- `crawl_run_id`

### JobEvent

- `id`
- `job_id`
- `event_type`: `created/changed/offline/reopened`
- `summary`
- `changed_fields_json`
- `occurred_at`
- `crawl_run_id`

### CrawlRun

- `id`
- `source_id`
- `status`: `running/success/degraded/failed`
- `started_at`
- `finished_at`
- `discovered_count`
- `parsed_count`
- `new_count`
- `changed_count`
- `offline_count`
- `error_count`
- `error_summary`

### RawSnapshot

MVP 可只存文件路径：

- `id`
- `source_id`
- `crawl_run_id`
- `url`
- `content_type`
- `file_path`
- `sha256`
- `fetched_at`

### Career Vault 与求职准备

schema v4–v9 的历史 migration 增加过：

- 简历导入、确认事实和版本：多简历、脱敏事实、原文件生命周期和 OCR provenance。
- 岗位收藏、申请阶段和追加时间线：使用 version/CAS 防止并发覆盖。

`job_resume_matches`、Application Packet、定制简历草稿和 DOCX/PDF 导出已退出
运行时。历史表只为专项归档保留，归档验证后由显式 retirement 命令物理删除；
普通启动 migration 不执行这项破坏性清理。

### 模拟面试

schema v10–v13 增加并演进 `interview_sessions` 和 `interview_turns`，保存岗位、
简历、Conversation、immutable Blueprint、问题、回答、评价、下一动作和深挖
维度。新会话直接读取可见 JD 与已确认简历，不创建或读取匹配快照。

一个 Conversation 最多绑定一场 InterviewSession。问题必须通过 Blueprint v2
单维度门禁后才能持久化。

## 3. Schema

内部至少区分：

- Persistence model。
- Domain model。
- MCP request/response schema。

所有时间输出 ISO 8601，明确时区；未知为 null，不使用空字符串。

## 4. MCP 通用响应

推荐结构：

```json
{
  "ok": true,
  "data": {},
  "warnings": [],
  "meta": {
    "generated_at": "2026-08-04T09:00:00Z"
  }
}
```

错误：

```json
{
  "ok": false,
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "No job found for the supplied id",
    "retryable": false
  }
}
```

## 5. P0 MCP 工具

### `health_check`

输入：无。

输出：数据库状态、schema version、启用数据源数、MCP version。

### `get_mock_jobs`

仅 Stage 1 验证使用。返回固定岗位，完成真实数据库后可保留为测试模式或删除。

### `import_manual_jd`

输入：

- `raw_text`: 必填。
- `source_url`: 可选。
- `company_name`: 可选。
- `title`: 可选。
- `confirmed`: 默认 false。

行为：

- `confirmed=false` 时可只返回提取预览，不写正式 Job。
- `confirmed=true` 时入库，并创建 JobVersion 与 created event。
- 若抽取需要模型，模型层由 OpenWorker Skill/Agent 或可替换 parser 调用；MCP 不应静默编造字段。

输出：标准化预览、缺失字段、job_id（确认后）。

### `get_job`

输入：`job_id`。

输出：岗位详情、来源、当前版本、最近事件。

### `search_jobs`

输入：

- `query`
- `company_slugs`
- `locations`
- `recruitment_types`
- `statuses`
- `first_seen_after`
- `changed_after`
- `limit`（默认 20，最大 100）
- `cursor` 或 `offset`

输出：简洁岗位列表与分页信息。

### `list_recent_job_events`

输入：时间范围、事件类型、公司、limit。

输出：岗位变更事件和 changed fields。

### `list_sources`

输出每个源的启用状态、最近成功、最近错误、当前 Adapter。

### `crawl_source`

输入：`source_id`、`dry_run`。

这是执行型工具，应保留 OpenWorker 审批。输出 CrawlRun 摘要。`dry_run=true` 不修改正式岗位状态。

## 6. 已实现的扩展 MCP 工具

### 岗位跟踪与摘要

`get_job_tracking`、`list_tracked_jobs`、`update_job_tracking`、
`get_job_radar_digest`、`crawl_all_sources`。

### 简历和 Career Vault

`get_resume_import_text`、`preview_resume_import`、`confirm_resume_sections`、
`get_candidate_profile`、`list_confirmed_resumes`、`discard_resume_import`、
`delete_candidate_profile`、`get_confirmed_resume`。

### AI 简历诊断

分析由 Career Agent 和 `career-resume-coach` Skill 完成。Agent 只接收
`job_id + resume_id`，再通过 `get_job` 与 `get_confirmed_resume` 读取事实；
不使用关键词评分、脚本匹配、证据快照或文件生成。

### 模拟面试

`create_interview_session`、`get_interview_session`、`start_mock_interview`、
`submit_interview_answer`、`get_next_interview_question`、`finish_interview`、
`generate_interview_report`。

外部发送、状态写入、抓取和文件发布继续遵守 OpenWorker 权限审批。Agent 不能使用
工具参数绕过用户确认、事实门禁或 CAS。

## 7. 数据库迁移

SQLite 使用显式、单向 migration runner 和 `PRAGMA user_version`。当前
`SCHEMA_VERSION = 13`；不得靠启动时 `create_all` 或重建数据库覆盖用户数据。
旧生成数据的物理删除只能使用 `deploy.retire_legacy_career`，并且必须先通过
`deploy.archive_legacy_career` 生成和验证专项归档。

## 8. 示例查询

- 最近 7 天新增岗位。
- `title/description` 含“Agent”且城市北京。
- 某公司最近 30 天 changed 事件。
- active 但超过 48 小时未确认的岗位。

这些查询应有 repository 层单元测试。
