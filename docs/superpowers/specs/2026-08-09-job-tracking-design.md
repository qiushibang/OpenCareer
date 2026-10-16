# 岗位收藏与申请跟踪设计

## 1. 目标

为本地单用户 OpenCareer 增加可追溯的岗位收藏与申请进度管理：

- 用户可以收藏或取消收藏任意已入库岗位。
- 用户可以记录申请阶段和私有备注。
- 每次申请阶段变化形成不可变时间线。
- 岗位雷达可以按收藏和申请阶段筛选。
- 岗位下线后，用户记录仍然保留。
- GUI 与 Career MCP 共用同一 Domain Service 和并发控制。

本阶段不自动投递，不登录招聘网站，也不根据对话、邮件或岗位状态推断申请进度。

## 2. 第一性原理与边界

### 2.1 岗位事实与用户状态分离

`jobs.status` 表示官方岗位是否仍在招聘，由 crawler pipeline 维护。收藏和申请阶段是用户私有状态，不得写入 `jobs`、`job_versions` 或 `job_events`。

新增两个独立维度：

- `is_favorite`：用户是否收藏岗位。
- `application_status`：用户记录的申请阶段。

一个岗位可以只收藏而不申请，也可以在未收藏时进入申请流程。

### 2.2 当前状态与历史分离

只保存当前阶段会丢失申请时间线，因此：

- `job_tracking` 保存当前状态，用于列表和详情快速读取。
- `job_application_events` 追加保存阶段变化，用于追溯。

收藏切换不写历史事件。申请阶段未变化时不重复写事件。

### 2.3 用户控制，不做流程猜测

不同公司会跳过或重复笔试、面试等环节。系统校验状态值，但不强制线性转换。用户可以从任意合法阶段切换到另一合法阶段，事件历史负责保留真实操作。

岗位从 `active` 变为 `inactive` 时，不自动修改收藏、申请阶段或备注。

## 3. 方案比较

### 方案 A：当前状态与追加事件分离

新增当前状态表和阶段事件表。查询简单，历史可追溯，并能用乐观版本阻止 GUI 与 MCP 相互覆盖。

这是采用方案。

### 方案 B：只保存当前状态

实现更少，但每次修改都会覆盖旧阶段，无法回答“何时投递、何时进入面试”。不满足“跟踪”的核心语义。

### 方案 C：复用 OpenWorker Todo 或 Automation

通用任务可以承载提醒，但不能自然表达岗位外键、收藏筛选和申请阶段历史。强行复用会把 Career 领域规则泄漏到通用核心，因此不采用。

## 4. 状态模型

内部值与中文显示如下：

| 内部值 | 中文显示 |
|---|---|
| `not_started` | 未开始 |
| `preparing` | 准备材料 |
| `applied` | 已投递 |
| `assessment` | 笔试/测评 |
| `interviewing` | 面试中 |
| `offer` | 已获 Offer |
| `accepted` | 已接受 Offer |
| `rejected` | 未通过 |
| `withdrawn` | 已撤回 |

规则：

- 新岗位的虚拟默认值为 `is_favorite=false`、`application_status=not_started`、`version=0`。
- 首次实际修改时才创建 `job_tracking` 行。
- 第一次进入 `applied`、`assessment`、`interviewing`、`offer`、`accepted`、
  `rejected` 或 `withdrawn` 时设置 `applied_at`；后续状态变化不覆盖该时间。
- 回到 `not_started` 不删除历史，也不清空 `applied_at`。
- 备注 trim 后最多 2,000 个字符；空字符串保存为 `NULL`。
- patch 归一化后与虚拟默认值完全相同时直接返回默认值，不创建空记录。
- 更新时间由服务端 UTC clock 生成，不接受客户端时间作为权威值。

## 5. 数据模型

数据库从 schema v6 升级到 v7。

```sql
CREATE TABLE job_tracking (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
    is_favorite INTEGER NOT NULL DEFAULT 0
        CHECK(is_favorite IN (0, 1)),
    favorited_at TEXT,
    application_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK(application_status IN (
            'not_started',
            'preparing',
            'applied',
            'assessment',
            'interviewing',
            'offer',
            'accepted',
            'rejected',
            'withdrawn'
        )),
    applied_at TEXT,
    note TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX job_tracking_favorite
    ON job_tracking(is_favorite, updated_at DESC);
CREATE INDEX job_tracking_application_status
    ON job_tracking(application_status, updated_at DESC);

CREATE TABLE job_application_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job_tracking(job_id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX job_application_events_job
    ON job_application_events(job_id, occurred_at DESC, id DESC);
```

本地 MVP 只有一个用户，因此不增加 `user_id`。未来云端多用户化必须先增加 owner 维度，不能共享当前表。

## 6. Domain 与持久化

新增 `domain/job_tracking.py`：

- 定义合法状态常量和顺序。
- `normalize_tracking_patch()` 校验至少提供一个可修改字段。
- 严格校验布尔值、状态、`expected_version` 和备注长度。
- 不读取数据库，不调用模型。

新增 `database/job_tracking_repository.py`：

- 读取单个岗位的当前 tracking 和事件。
- 使用 `LEFT JOIN` 将 tracking 摘要合并到岗位列表。
- 按 `favorite_only` 和 `application_status` 在 SQL 层筛选，不能只过滤当前 GUI 页。
- 首次更新使用 INSERT；已有记录使用
  `UPDATE ... WHERE job_id = ? AND version = ?`。
- 状态变化与事件 INSERT 位于同一事务。

新增 `services/job_tracking.py`：

- 所有写入使用短 `BEGIN IMMEDIATE` 事务。
- Repository 初始化和 schema migration 必须在业务事务开始前完成，避免迁移事务嵌套。
- 先确认岗位存在；不存在返回 `JOB_NOT_FOUND`。
- `expected_version=0` 只允许创建首行。
- CAS 未命中返回 `VERSION_CONFLICT`，不得静默覆盖。
- 目标状态与当前状态相同时不追加事件。
- 收藏切换维护 `favorited_at`：首次收藏设置当前时间，取消收藏清空。
- 写入失败回滚，不返回部分成功。

## 7. HTTP 契约

### 7.1 读取

```text
GET /v1/career/jobs/{job_id}/tracking
```

成功：

```json
{
  "ok": true,
  "tracking": {
    "job_id": "job-id",
    "is_favorite": false,
    "favorited_at": null,
    "application_status": "not_started",
    "applied_at": null,
    "note": null,
    "version": 0,
    "updated_at": null,
    "events": []
  }
}
```

### 7.2 更新

```text
PATCH /v1/career/jobs/{job_id}/tracking
```

请求：

```json
{
  "expected_version": 0,
  "is_favorite": true,
  "application_status": "preparing",
  "note": "本周完成申请材料"
}
```

`expected_version` 必填。`is_favorite`、`application_status` 和 `note` 至少出现一个。
成功返回更新后的完整 tracking。

### 7.3 岗位列表和详情

`GET /v1/career/jobs` 增加：

- `favorite_only=true`；缺省或 `false` 均表示不按收藏过滤
- `application_status=<合法内部值>`

列表摘要增加不含事件的 `tracking`。岗位详情增加完整 `tracking` 和阶段事件，避免 GUI 为首屏逐条发送请求。

### 7.4 稳定错误

| code | HTTP | 含义 |
|---|---:|---|
| `INVALID_INPUT` | 400 | 字段类型、版本或备注不合法 |
| `INVALID_STATUS` | 400 | 未知申请阶段 |
| `JOB_NOT_FOUND` | 404 | 岗位不存在 |
| `VERSION_CONFLICT` | 409 | tracking 已被其他入口更新 |
| `PERSISTENCE_ERROR` | 409 | SQLite 写入失败 |

响应不得包含 SQL、数据库路径或内部异常堆栈。

## 8. MCP 契约

Career MCP 新增：

- `get_job_tracking(job_id)`
- `list_tracked_jobs(favorite_only, application_status, limit, offset)`
- `update_job_tracking(job_id, expected_version, is_favorite, application_status, note)`

MCP 直接调用共享 Service，不回调 HTTP。工作区 MCP 的现有审批门继续生效，Agent 不得自动推断或批量推进申请阶段。

工具返回稳定 `ok/error/meta` 包装。`VERSION_CONFLICT` 时提示重新读取当前 tracking 后由用户决定，不自动重试覆盖。

## 9. GUI

继续使用岗位雷达“列表与详情同屏”，不新增侧栏入口或独立路由。

### 9.1 筛选

在现有筛选区增加：

- “仅看收藏”开关。
- “申请进度”下拉框。

筛选由服务端执行，变化后重置到第一页。

### 9.2 列表

每个岗位卡片增加：

- 收藏按钮。
- 非 `not_started` 时显示中文申请阶段标签。

点击收藏按钮不得触发岗位卡片选择。收藏使用乐观更新、禁用重复点击、失败回滚并显示中文错误。在“仅看收藏”模式下，取消收藏成功后再从列表移除，避免请求失败时岗位闪退。

### 9.3 详情

详情标题区增加收藏按钮。详情正文增加“我的申请进度”区域：

- 阶段下拉框。
- 最多 2,000 字的备注。
- 保存按钮和冲突提示。
- `applied_at`、`updated_at`。
- 按时间倒序展示阶段变化。

保存期间禁用重复提交。`VERSION_CONFLICT` 时重新读取详情并提示“记录已在其他入口更新，请确认最新内容后重试”，不自动覆盖用户内容。

所有交互文案使用中文，`Offer` 作为产品专有词保留。

## 10. 安全、隐私与性能

- tracking 是用户私有本地数据，不进入 crawler snapshot、岗位版本或公开来源摘要。
- 备注作为纯文本显示，不作为 HTML 注入，不传给模型。
- API 不接受 SQL、文件路径、客户端权威时间或任意排序列。
- tracking 事件默认只随单个岗位详情返回，列表不携带历史。
- 列表使用 `LEFT JOIN`，避免 20 条岗位产生 N+1 查询。
- 不新增依赖，不启用 Redis、任务队列或外部数据库。

## 11. 测试与验收

### 11.1 Domain 与 Repository

- 合法状态、未知状态、布尔严格类型、空 patch、备注长度。
- v6 到 v7 迁移保留现有 10,067 个岗位和 v6 匹配快照。
- 默认虚拟 tracking 不写数据库。
- 首次创建、CAS 更新、版本冲突和事务回滚。
- 状态未变化不重复事件，状态变化只追加一个事件。
- 收藏与申请阶段互不覆盖。
- inactive 岗位 tracking 保留。
- 收藏和申请阶段筛选在 SQL 分页前执行。

### 11.2 Service、HTTP 与 MCP

- HTTP 读取、更新、列表筛选、详情时间线。
- 错误码和 400/404/409 映射稳定。
- MCP 参数透传、审批属性和安全错误。
- GUI 与 MCP 使用相同旧版本并发更新时，只允许一个成功。
- 全新数据库首次调用不出现嵌套迁移事务。

### 11.3 GUI

- 收藏与申请阶段使用中文显示。
- 列表和详情状态同步。
- 收藏按钮不切换当前岗位。
- 仅看收藏和申请阶段发送服务端筛选参数。
- 乐观收藏成功、失败回滚和重复点击保护。
- tracking 保存、备注长度、版本冲突刷新。
- 时间线倒序且不显示内部状态值。
- 中文 UI 审计继续通过。

### 11.4 真实验收

- 在真实数据库收藏一个现有 DeepSeek 岗位。
- 将其从未开始更新为准备材料，再更新为已投递。
- 列表筛选只返回该收藏岗位，详情显示两个阶段事件。
- 将岗位数据库状态临时切换为 inactive 的隔离测试证明 tracking 不变。
- 取消收藏不删除申请历史。
- 后端、GUI、production build、schema v7、外键和 `git diff --check` 全部通过。
- 独立对抗审查覆盖并发覆盖、非法状态、备注注入和岗位下线四类风险。

## 12. 非目标

- 自动投递、自动登录、验证码处理。
- 从邮件、聊天或招聘网站自动推断阶段。
- 日历提醒、下一步截止日期和通知。
- Kanban 拖拽、批量状态修改和统计看板。
- 多用户共享、云同步和权限模型。
- 删除申请历史。
- 修改 OpenWorker Todo、Automation、Agent Loop 或权限核心。
