# PostgreSQL、上下文与岗位数据平台设计

> 日期：2026-08-18
>
> 状态：已批准
>
> 决策：本轮完成云端 PostgreSQL 持久化、上下文入库、精确 Origin、多用户隔离和共享爬虫
> 数据链路；Redis 仅保存可重建运行态。

## 1. 成功标准

- 云端所有持久业务数据都写入 PostgreSQL，不再以 SQLite、JSONL 或 JSON 文件作为唯一副本。
- 简历原件、报告、DOCX/PDF 和抓取快照以 Blob 记录进入 PostgreSQL。
- 完整 Conversation、压缩摘要、Memory、Skill 加载和每轮 Context Manifest 可查询。
- 所有用户数据通过 `user_id` 和 RLS 隔离；共享岗位不按用户复制。
- Crawler 每个来源只访问一次并写共享 Job Catalog。
- HTTP 和 WebSocket Origin 继续按协议、主机和端口精确匹配，支持多入口但不支持通配。
- 桌面模式继续使用 SQLite 和本地文件，不要求用户安装 PostgreSQL。
- SQLite 到 PostgreSQL 迁移可校验、可重复执行并可回滚。

## 2. 存储职责

### 2.1 PostgreSQL

PostgreSQL 是云端唯一权威持久层，保存：

- 身份与部署入口。
- 共享岗位、来源、版本、事件和抓取运行。
- 用户简历、投递、匹配、面试和生成物。
- Conversation、消息、压缩摘要、Memory、Todo、Inbox、审批和 Automation。
- 简历原件、报告、导出文件和抓取原始快照。
- 审计事件和每轮 Context Manifest。

### 2.2 Redis

Redis 只保存删除后可自动恢复的数据：

- `SessionManager` 所有权租约。
- WebSocket presence 和跨实例事件通知。
- 热门岗位查询缓存。
- API 限流计数。
- Crawler 单实例锁。
- 短期幂等键和后台任务唤醒信号。

Redis 不保存简历、消息、岗位、评价、审批或唯一任务状态。Redis 不可用时，系统降低性能或
退回单实例协调，但不能丢失已提交业务数据。

### 2.3 临时文件

OCR、DOCX/PDF 渲染和抓取解析可以使用容器临时目录。事务完成后，产物进入 PostgreSQL Blob
并删除临时文件。容器重启后不依赖临时目录恢复业务。

## 3. PostgreSQL 数据域

使用一个数据库和多个 schema，避免微服务拆分：

### 3.1 `identity`

- `users`
- `auth_credentials`
- `deployment_origins`

静态 Alpha token 只保存不可逆哈希。`deployment_origins.origin` 保存完整 origin 字符串，
唯一约束区分不同协议和端口。

### 3.2 `catalog`

- `companies`
- `job_sources`
- `crawl_sources`
- `crawl_runs`
- `jobs`
- `job_versions`
- `job_events`
- `raw_snapshots`

`jobs` 保留 `(crawl_source_id, external_job_id)` 唯一约束。版本和事件只追加，不覆盖历史。

### 3.3 `career`

所有表包含 `user_id`：

- `resume_imports`
- `candidate_profiles`
- `candidate_facts`
- `profile_versions`
- `resume_previews`
- `job_tracking`
- `job_application_events`
- `job_resume_matches`
- `application_packets`
- `tailored_resume_drafts`
- `interview_sessions`
- `interview_turns`

私人表通过 `job_id` 引用共享 `catalog.jobs`，不复制岗位正文。

### 3.4 `agent`

- `conversations`
- `messages`
- `compactions`
- `context_manifests`
- `session_skills`
- `memories`
- `todos`
- `inbox_items`
- `inbox_resolutions`
- `automations`
- `automation_runs`
- `audit_events`

`messages` 使用 `(conversation_id, sequence)` 唯一约束并只追加。消息内容保存为 JSONB，支持
文本、工具调用和多模态引用。

### 3.5 `blob`

`objects` 字段至少包括：

- `id`
- `scope`: `shared` 或 `user`
- `user_id`: 私人 Blob 必填
- `kind`
- `media_type`
- `original_name`
- `size_bytes`
- `sha256`
- `content BYTEA`
- `created_at`
- `deleted_at`

当前简历上限为 10 MB，适合 Alpha 阶段直接使用 `bytea`。PostgreSQL TOAST 负责大值存储；
下载接口流式返回，不把完整文件读入模型上下文。

## 4. 多用户隔离

### 4.1 Principal

HTTP、WebSocket、后台任务和 MCP 子进程都先解析成 `Principal.user_id`。用户 ID 不再用于
构造云端持久路径，而是作为数据库租户键。

### 4.2 RLS

所有用户表启用并强制 Row Level Security。每个事务开始后执行：

```sql
SET LOCAL app.user_id = '<validated-user-id>';
```

策略只允许：

```sql
user_id = current_setting('app.user_id', true)
```

应用查询仍显式带 `user_id`；RLS 是第二道防线，不替代 Repository 条件。Crawler 使用独立
数据库角色，只能写 `catalog` 和 shared Blob。

### 4.3 连接池

使用 `psycopg` 3 和 `psycopg_pool`。每个请求取得连接后必须开启事务、设置 Principal，再
执行查询。连接归还池前事务结束，避免租户设置泄漏到下一请求。

## 5. 完整上下文管理

### 5.1 Canonical Conversation

完整消息按顺序进入 `agent.messages`。模型上下文压缩只改变发送给模型的视图，不删除、覆盖
或改写 canonical messages。

### 5.2 Compaction

每次压缩新增 `agent.compactions`：

- `conversation_id`
- `version`
- `boundary_sequence`
- `summary`
- `omitted_message_count`
- `source_hash`
- `created_at`

恢复会话时选择最新有效 Compaction，再加载 boundary 之后的消息。旧 Compaction 保留用于
审计，不参与当前上下文。

### 5.3 Durable Memory

`agent.memories` 保存全局、工作区和会话级 Memory，包含版本、状态和时间。Memory 与
Compaction 分离：Memory 是用户可管理的长期事实，Compaction 是 Conversation 的压缩视图。

### 5.4 Skill 状态

`agent.session_skills` 保存：

- `conversation_id`
- `skill_name`
- `skill_version`
- `content_sha256`
- `loaded_at`

后续轮次根据 Conversation 和 Skill hash 判断是否需要重新加载。Skill 文件更新后 hash
变化，下一轮重新加载；否则不重复调用 `load_skill`。

### 5.5 Context Manifest

每次模型调用前写入或在调用事务中生成 `agent.context_manifests`：

- Conversation 和 turn ID。
- 使用的 message sequence 范围。
- Compaction ID。
- Memory IDs。
- Skill 名称和 hash。
- InterviewSession、岗位和简历证据引用。
- provider/model、估算 token 和实际 token。
- context 内容哈希。

Manifest 不保存 API key、token 或未脱敏密钥。它使“模型为什么看到这些上下文”可追溯，
同时避免把完整 Prompt 再复制一份。

### 5.6 每轮组装顺序

1. Persona 和安全规则。
2. 已加载 Skill 指令。
3. 全局与工作区 Memory。
4. 最新 Compaction。
5. Compaction boundary 后的近期消息。
6. 当前 InterviewSession 或 Career 业务证据。
7. Todo、待处理审批和本轮动态环境。
8. 最新用户消息。

Context 预算不足时按既有 Compaction 策略处理，不丢弃当前用户消息、安全规则和当前业务
证据。

## 6. 精确匹配

### 6.1 Origin

新增 `OriginPolicy` 存储接口：

- 桌面 Adapter：现有本地 origin 集合。
- 云端 Adapter：启动时读取 `identity.deployment_origins`，并允许环境变量提供应急精确项。

每项必须由 URL parser 验证：

- 只允许 `http` 或 `https`。
- 必须有 host。
- 端口参与匹配。
- 不允许 path、query、fragment 和 `*`。
- 比较值是规范化后的完整 origin，不做后缀或正则宽匹配。

数据库不可用时 fail closed，只保留编译期本地 origin 和明确的应急环境项。HTTP CORS 与
WebSocket 使用同一个 `OriginPolicy`。

### 6.2 岗位与简历

“精准匹配”同时包括：

- PostgreSQL B-tree 精确筛选公司、城市、岗位类型、状态和更新时间。
- `tsvector` + GIN 做中文可用的岗位全文候选召回。
- 已确认简历事实与 JD requirement 的确定性证据引用。
- 匹配快照保存 job content hash、resume revision 和逐项 evidence ref。

模型只解释无法用规则可靠判断的语义关系，不负责去重、状态、身份或分数计算。当前不引入
向量数据库，避免不可解释的相似度替代事实匹配。

## 7. Repository Seam

调用方只依赖以下深模块：

- `ConversationRepository`
- `MemoryStore`
- `InboxRepository`
- `CareerRepository`
- `JobCatalogRepository`
- `BlobRepository`
- `ContextManifestRepository`

每个模块各有 SQLite/文件 Adapter 和 PostgreSQL Adapter。桌面构造本地 Adapter；云端由
`DATABASE_URL` 构造 PostgreSQL Adapter。领域代码和 Agent loop 不判断数据库类型。

Redis 位于独立 `RuntimeCoordinator` interface，不进入 Repository。

## 8. 迁移

### 8.1 工具

新增一次性、可重入迁移命令：

```bash
python -m deploy.migrate_to_postgres --source /data --database-url ...
```

迁移按业务主键 upsert，并记录批次、源哈希、行数和错误。重复执行不能生成重复消息、岗位
版本或 Blob。

### 8.2 顺序

1. PostgreSQL schema 和 RLS 测试。
2. 只读连接与健康检查。
3. 停止用户写入，备份 SQLite/JSONL/JSON/私有文件清单。
4. 迁移共享岗位和抓取历史。
5. 迁移用户 Career、Conversation、Context、Memory、审批和 Blob。
6. 对比每表计数、主键集合、外键、文件 SHA-256 和抽样业务查询。
7. PostgreSQL 影子读取。
8. 切换 `DATABASE_URL`，执行 REST/WS/简历/面试 smoke。
9. 保留原数据卷只读回滚。

不采用长期双写。双写会制造两套权威来源；迁移窗口使用短暂停写和影子读取。

### 8.3 回滚

切换失败时停止新后端，清除 `DATABASE_URL`，恢复旧镜像和原 SQLite 数据卷。PostgreSQL
数据保留用于诊断，但不反向覆盖旧库。

## 9. 爬虫

Crawler 从多目标 SQLite fan-out 改为单目标 PostgreSQL：

```text
fetch once
  -> validate
  -> Blob raw snapshot
  -> catalog transaction
  -> version/event/run
  -> Redis cache invalidation event
```

- 使用 PostgreSQL advisory lock 或 Redis lock 防止重复调度；PostgreSQL lock 是最终门禁。
- 单来源事务，失败不影响其他来源。
- degraded/failed 不增加 missing_count。
- 每日调度保留 04:00 和随机抖动。
- 当前 286 条数据先迁移，再运行全来源 dry-run 和分批正式抓取。
- active 数以官方当前结果为准，历史 9,960 只作为异常检测基线。

## 10. 部署

`docker-compose.ip.yml` 和域名版新增：

- `postgres:16`
- `redis:7`
- backend/crawler 的 `DATABASE_URL`
- `REDIS_URL`
- PostgreSQL 数据卷和健康检查

当前 2C2G 服务器上，Crawler 只在计划窗口启动，不能与内存压力测试并发。PostgreSQL 设置
保守连接数和内存；Redis 设置内存上限与 `allkeys-lru`，因为其内容可重建。

生产切换前先在独立 Compose project 或备用端口完成迁移演练。`.env` 继续不提交。

## 11. 依赖

新增云端依赖：

- `psycopg[binary,pool]>=3.2,<4`
- `redis>=5,<6`

桌面安装可以保留这两个轻量依赖，或后续拆成 `[cloud]` extra；云端 requirements 必须同时
更新国内与普通清单。新增依赖只用于 PostgreSQL Adapter 和 RuntimeCoordinator。

## 12. 验收

- 两个用户相同主键和同名简历不能跨 RLS 读取。
- 连接池复用不能泄漏上一请求的 `app.user_id`。
- Canonical messages、Compaction、Memory 和 Context Manifest 可完整恢复。
- Redis flush 后无需人工补数据即可恢复服务。
- Blob 迁移前后 SHA-256 一致。
- SQLite/JSONL 迁移重复执行无重复数据。
- Origin 对协议、host、端口逐字匹配；通配、路径和恶意后缀全部拒绝。
- HTTP CORS 和 WebSocket 使用相同 allowlist。
- Crawler 单源失败不触发岗位下线。
- 完整抓取复跑主要产生 unchanged。
- 桌面 SQLite 全量回归通过。
- Alpha 前端仍用 `vite build --mode alpha`，不包含 token。
