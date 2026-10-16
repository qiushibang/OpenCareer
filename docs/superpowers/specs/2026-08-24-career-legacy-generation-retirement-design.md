# Career 旧匹配与文件生成链路下线设计

## 目标

彻底下线 Application Packet、脚本岗位匹配、Tailored Resume Draft 及其
DOCX/PDF 导出链路，同时保证新的 AI 简历诊断和模拟面试继续工作，并保留现有
面试历史。

本次采用“两阶段收缩”：

1. 先让所有运行时消费者脱离旧匹配快照，再移除旧 API、MCP、服务和镜像依赖。
2. 在专项归档通过后删除旧表和专属 Blob。

本地实现不触发线上部署。生产执行必须经过停写、完整恢复点、专项归档、隔离恢复
和明确部署批准。

## 已确认决策

### 历史数据策略

采用“先归档再删除”：

- 旧匹配、申请包、定制简历草稿和导出文件保存为离线可恢复归档。
- 归档不形成线上只读产品能力。
- 新版本不保留旧 API 兼容窗口；已删除路径返回框架标准 `404`。
- 归档验证通过后物理删除旧数据库表和专属 Blob。

### 模拟面试数据流

模拟面试不再读取或创建匹配快照。启动契约只包含：

```text
job_id=<job id>
resume_id=<resume id>
```

服务端在当前 Principal 范围内直接读取完整 JD 和已确认简历，构造面试事实
上下文。确定性代码仅负责：

- ID、输入和面试状态机校验。
- 租户隔离与资源可见性。
- JD 与简历事实的稳定引用。
- 问题、评价和 Artifact 的安全校验。

确定性代码不得计算匹配状态、关键词命中、能力覆盖、简历排序、推荐、评分或
录用概率。问题生成、事实分析和追问策略继续由 AI 完成。

### 历史面试

- 保留全部 `interview_sessions`、turn、Conversation 和面试 Artifact。
- 已有会话继续使用其创建时持久化的 immutable blueprint，不再要求原
  `job_resume_matches` 记录存在。
- 新会话使用直接 JD/简历事实上下文，不产生 `snapshot_id`。
- 历史 blueprint 中的旧字段只作为历史会话数据保留，不参与新分析。

## 删除范围

### 运行时能力

删除：

- `MatchService` 及 SQLite/PostgreSQL 匹配仓储。
- Application Packet 的领域、服务、仓储和文件写入。
- Tailored Resume Draft 的领域、服务和仓储。
- Tailored Resume DOCX/PDF 生成、LibreOffice 转换、下载和 Blob 写入。
- 对应 HTTP 路由、错误映射和服务工厂。
- 对应 MCP 工具、注册项和 Alpha tool allowlist。
- `career-application-packet`、`career-tailored-resume` 等旧 Skill。
- 前端旧 API 类型、请求函数、启动依赖和测试 fixture。
- SQLite→PostgreSQL 迁移工具中旧表和旧 Blob 的导入路径。

保留：

- AI 简历诊断对话及 `get_confirmed_resume`。
- Career Vault 的 PDF/DOCX 导入、OCR、原件预览和原件下载。
- 普通 Conversation PDF 附件和模型 PDF 支持。
- 模拟面试状态机、语音、报告、逐字稿和会话 Artifact。
- 已发布数据库 migration 文件，作为已部署数据库的迁移历史。

### 镜像依赖

后端镜像移除只服务于旧导出链路的：

- `libreoffice-writer`
- `fonts-noto-cjk`

若其他保留能力被测试证明依赖其中任一包，则保留实际仍需的最小依赖，并在实施
记录中说明证据。不得因为删除导出链路而删除 OCR extra、Playwright Chromium
或普通 PDF 处理依赖。

## 新模拟面试上下文

面试服务通过注入的岗位读取器和简历读取器取得：

- 岗位标题、公司、职责、要求和完整 JD 文本。
- 所选简历的已确认章节和脱敏事实。

上下文为事实索引，不是匹配结果。每个可引用事实具有稳定、可验证的 ref，供 AI
生成单维度问题并供现有门禁验证。上下文不得包含：

- `snapshot_id`
- `snapshot_status`
- `direct`、`related`、`none` 等匹配结论
- 匹配分数、推荐顺序或脚本生成的优劣判断

前端、HTTP 和 MCP 的新建面试契约同步删除 `snapshot_id`。已有会话响应若需要
兼容历史记录，可以返回历史 blueprint 中的不可变数据，但新会话不得生成该字段。

## 归档格式与安全

新增显式、只读的运维归档命令。归档覆盖 SQLite 和 PostgreSQL 中的：

- `job_resume_matches`
- `application_packets`
- `tailored_resume_drafts`
- `tailored_resume_exports`
- 上述记录直接引用的 Markdown、DOCX 和 PDF Blob 或本地文件

归档目录至少包含：

```text
manifest.json
database/
blobs/
SHA256SUMS
```

`manifest.json` 记录：

- 格式版本和生成时间。
- 数据库类型和非敏感来源标识。
- 各表行数。
- 各 Blob 的 ID、kind、media type、大小和 SHA-256。
- 缺失、重复或无法读取的对象。

归档约束：

- 默认不修改源数据库和 Blob。
- 目标目录必须不存在或为空，不允许覆盖已有恢复点。
- 不把数据库凭据、token、联系方式或文件正文写入日志。
- 任一记录、Blob、计数或哈希无法验证时，命令以非零状态失败。
- 删除迁移必须接收归档清单并再次验证，不能仅凭布尔开关跳过归档。

## 数据库收缩

破坏性删表不得进入应用启动时自动执行的标准 migration。运行时下线与物理数据
清理是两个独立动作：

1. 新代码能够在旧表仍存在时正常运行，但不再读取或写入旧表。
2. 专用 retirement 命令验证归档后，在事务中执行结构收缩。

现有已发布 migration 保持不变。收缩 SQL 和 SQLite 重建逻辑由 retirement
命令显式调用，不注册到普通 Server、GUI 或 Career MCP 启动路径。命令完成后写入
现有迁移账本或等价的非敏感完成标记，以支持幂等检查和运维审计。

### SQLite

SQLite retirement 步骤：

1. 验证专项归档清单。
2. 重建 `interview_sessions`，移除 `snapshot_id` 列及其到
   `job_resume_matches` 的外键。
3. 保留 session、turn、版本、Conversation 绑定和 Artifact 路径。
4. 按外键依赖顺序删除导出、草稿、申请包和匹配表。
5. 删除只属于旧链路且已归档的本地生成文件。
6. 执行 `PRAGMA foreign_key_check` 和 `PRAGMA integrity_check`。

任一步失败时回滚数据库事务；文件删除只在数据库提交和归档复验后执行。未运行
retirement 命令的旧数据库可以继续启动新代码，只是保留不再使用的历史表。

### PostgreSQL

提供不进入自动 migration 注册表的收缩 SQL，由 retirement 命令在单一受控事务
内执行：

1. 验证专项归档清单和部署恢复点。
2. 从 `career.interview_sessions.data` 中移除新代码不再需要的
   `snapshot_id`，同时保留完整历史 blueprint。
3. 删除旧表相关 trigger、policy、constraint 和 index。
4. 按顺序删除 `career.tailored_resume_exports`、
   `career.tailored_resume_drafts`、`career.application_packets`、
   `career.job_resume_matches`。
5. 仅清理旧表直接引用、kind 属于旧链路且没有其他引用的用户 Blob。
6. 保持所有现有 RLS、Origin、Token、Principal 和可见岗位约束不变。

Blob 清理必须通过结构化引用和 kind 双重确认，不允许按文件名、路径前缀或模糊
字符串批量删除。命令重复运行时只能报告“已完成”，不能扩大删除范围。

## API 与错误行为

- 已删除 HTTP 路由不注册，由 FastAPI 返回标准 `404`。
- 已删除 MCP 工具不出现在 discovery 中。
- Alpha allowlist 不再包含旧工具名。
- 岗位不存在或不可见时，面试创建返回安全的 `JOB_NOT_FOUND`。
- 简历不存在、未确认、已删除或跨租户时返回 `RESUME_NOT_FOUND`，不泄露所有权。
- 历史 blueprint 损坏时返回明确读取错误，不调用 MatchService 兜底。
- 归档不完整、哈希不一致或行数变化时拒绝删除迁移。

不增加 `410` 兼容处理器，也不保留只读旧 API，因为这会继续携带服务、仓储和
权限维护成本。

## 实施顺序

1. 改造模拟面试为 JD/简历直读，并完成聚焦回归。
2. 删除前端 `snapshot_id` 启动依赖和旧 API 客户端。
3. 删除旧 MCP、HTTP、Alpha allowlist、Skill 和运行时服务。
4. 增加专项归档命令及其完整性验证。
5. 增加显式 SQLite/PostgreSQL retirement 命令和 Blob 清理。
6. 删除旧领域、仓储、迁移导入代码与专属测试。
7. 移除镜像中的 LibreOffice/Noto CJK。
8. 更新权威文档、备份 runbook、开发日志和阶段状态。

每一步保持桌面版和云端 alpha 的非旧功能可启动。生产迁移和部署不属于本地代码
实施步骤。

## TDD 与验收

所有行为变更遵循 RED → GREEN：

1. 面试服务测试先证明只用 `job_id + resume_id` 创建会话，且不调用匹配服务。
2. HTTP、前端和 Skill 测试证明新建面试契约没有 `snapshot_id`。
3. MCP、HTTP 和 Alpha 测试证明旧工具和路由已消失。
4. 归档测试覆盖只读、拒绝覆盖、行数、Blob SHA-256、缺失 Blob 和清单篡改。
5. SQLite retirement 测试证明未提供有效归档时不修改数据库；成功后旧表
   消失、历史面试可读、外键和完整性通过。
6. PostgreSQL retirement 测试证明未提供有效归档时不修改数据库；成功后表、
   policy、trigger 和专属 Blob 正确清理，
   其他租户数据与保留 Blob 不受影响。
7. PDF/DOCX 简历导入、OCR、原件预览、普通附件和面试 Artifact 回归继续通过。
8. `rg` 残留审计不得发现运行时对旧模块、表、工具或镜像依赖的引用；历史规格、
   migration 和开发日志中的记录允许保留。

最低工程 Gate：

```bash
python -m pytest <focused backend tests> -q
cd surfaces/gui && npm test -- --run
cd surfaces/gui && npx tsc
bash deploy/build-frontend.sh
python -m coworker.server.run --help
python -m extensions.career_mcp.crawl_cli --list
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
git diff --check
```

PostgreSQL destructive retirement 仅在配置专用测试数据库时执行。若本机没有
`TEST_DATABASE_URL`，必须明确报告未运行，不能把 skip 记为通过。

## 生产切换 Gate

生产执行固定为：

1. 停止用户写入。
2. 按备份 runbook 创建并校验完整恢复点。
3. 生成旧能力专项归档并校验两份副本。
4. 在隔离数据库和文件卷完成恢复演练。
5. 部署新代码并显式执行 retirement 命令。
6. 验证 health、REST、WebSocket、岗位、简历、AI 诊断、模拟面试和 Blob。
7. Gate 全部通过后恢复流量。

任一步失败都停止切换，保留当前线上容器和数据库不变。回滚使用旧镜像与完整恢复
点，不尝试用已收缩数据库直接启动旧代码。
