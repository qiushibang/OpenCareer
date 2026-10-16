# 字节跳动中国大陆全量岗位续跑设计

## 目标

将字节跳动来源从两个固定校招项目扩展为官网公开展示的中国大陆社招和校招岗位，
并允许每日抓取任务跨多次有界调用续跑。只有完整轮次通过数量、唯一性和完整性校验
后，才允许更新正式岗位并执行 missing/offline 状态机。

本设计不抓取需要登录、验证码、用户凭据或私有接口的内容，不生成、保存、复用或
逆向官网请求中的 `_signature`。

## 当前问题

现有 `ByteDanceCampusProjectAdapter` 将一个不超过 200 条的项目作为一个原子集合：
一次 Playwright 会话读取全部分页，任意总数漂移或重复 ID 都使整轮失败。这适合
Seed 和前沿技术两个项目，但不能覆盖约 7,000 条校招和达到官方接口 10,000 条上限
的社招。

直接提高 `max_pages` 会产生三个问题：

- 单次 MCP 调用超过 120 秒，超时后没有续跑位置。
- 实时排序漂移会造成跨页重复和漏项。
- 部分结果若进入现有 `CrawlerService.crawl()`，会把尚未翻到的岗位记为 missing。

## 方案比较

### 方案 A：单次拉完全部分页

改动最少，但无法满足超时、故障恢复和排序漂移要求，不采用。

### 方案 B：每页直接写正式岗位

可续跑，但轮次中断后正式 Catalog 处于部分更新状态，也无法安全执行下线判断，
不采用。

### 方案 C：持久化暂存轮次，完整后原子提交

每次只读取有界分页，将原始岗位快照写入 PostgreSQL 暂存表；轮次完成并校验后，
在一个事务中对正式 Catalog 执行 created/unchanged/changed/reopened/missing。
该方案可恢复、可审计，并保持现有状态机语义，采用此方案。

## 来源范围

新增两个正式来源：

| source slug | 官网范围 | recruitment type |
|---|---|---|
| `bytedance-mainland-social` | 中国大陆公开社招 | `experienced` |
| `bytedance-mainland-campus` | 中国大陆公开校招与实习 | `campus` / `internship` |

原 `bytedance-seed-campus` 和 `bytedance-campus-frontier-2027` 在新来源首次完整提交前
继续保留。切换时先校验 external job ID 覆盖关系，再停用旧来源，避免重复展示。

“中国大陆”以官网响应中的城市元数据为准。只保留明确属于中国大陆的城市；香港、
澳门、台湾和海外岗位排除。城市缺失或无法判定的岗位记为轮次错误，不静默纳入或
丢弃。

## 分片与公开请求

Adapter 仍使用全新的无持久状态 Chromium context 打开字节官方公开列表页，并只
读取页面自己发出的 `POST /api/v1/search/job/posts` 成功响应。

社招或校招根范围若达到官网单查询上限，Runner 使用官网页面公开提供的地点筛选
拆分为城市分片；仍达到上限的分片再使用官网公开职类筛选细分。分片值必须来自同一
公开页面的筛选元数据，不能猜测内部 ID。

每个分片保存：

- 招聘范围、地点和职类组成的稳定 `shard_key`。
- 当前 `offset`、官方 `count` 和最近页指纹。
- 本轮已观察 external job ID。
- 请求页面 URL 和最终公开响应元数据。

不同分片允许岗位重叠，轮次暂存以 `(cycle_id, external_job_id)` 去重。相同岗位在
不同分片返回不同稳定业务字段时，轮次失败，不能任选一个版本。

## 持久化模型

PostgreSQL 新增：

```text
catalog.crawl_cycles
  id, source_id, status, pass_number, expected_total,
  started_at, updated_at, completed_at, error_summary

catalog.crawl_cycle_shards
  cycle_id, shard_key, filters_json, expected_count,
  next_offset, status, last_page_fingerprint, updated_at

catalog.crawl_cycle_jobs
  cycle_id, external_job_id, snapshot_json, content_hash,
  first_pass, last_pass, observed_at
```

`crawl_runs` 继续记录每次正式提交结果；有界抓取批次由 `crawl_cycles` 审计，不伪装
成已完成的正式 crawl run。SQLite 桌面模式提供结构等价的迁移，保持本地开发和
离线 fixture 测试可用；生产权威数据仍在 PostgreSQL。

同一 source 同时最多一个 `running` cycle。PostgreSQL 使用 advisory lock 和唯一
约束防止每日容器重叠执行。失败或进程退出后，下次调用从数据库中的 shard 与 offset
恢复，不依赖容器本地文件或 Redis。

## 有界批次与漂移收敛

一次调用最多处理 20 页或 200 条岗位，先达到者停止，并返回：

```json
{
  "source_slug": "bytedance-mainland-social",
  "cycle_id": "...",
  "status": "running",
  "processed_pages": 20,
  "observed_unique": 187,
  "has_more": true
}
```

完成所有分片后执行第二遍校验。第二遍重新读取分片边界页并继续合并新出现的 ID，
用于抵御抓取期间的实时排序漂移。满足以下条件时收敛：

- 每个分片的官方 count 在允许的两遍窗口内稳定。
- 所有分页响应均成功且字段契约有效。
- 暂存 external job ID 唯一，重复快照内容一致。
- 每个分片实际覆盖数达到其官方 count；重叠只在全局去重时扣除。
- 没有分片仍停在官网单查询上限。

最多执行三遍。三遍后仍漂移、任何分片达到不可再拆的上限，或官网 count 与覆盖数
无法解释时，将 cycle 标为 `degraded`，保留暂存证据，不提交正式 Catalog。

## 原子提交

完整轮次通过后，`CrawlerService` 在一个数据库事务内：

1. 锁定 source。
2. 从暂存快照生成 `NormalizedJob`。
3. 执行 created、unchanged、changed 和 reopened。
4. 仅对该完整 source 中未观察到的 active 岗位执行一次 `mark_absent`。
5. 写入成功 `crawl_run`、原始轮次摘要和 transition 计数。
6. 将 cycle 标记为 `committed`。

事务失败则全部回滚，cycle 标记为 `failed`。`running`、`degraded`、`failed` cycle
均不得增加 `missing_count`。

## Runner 与工具边界

每日 crawler 容器调用专用的有界 Runner，并循环到时间预算结束。每次进程启动都从
PostgreSQL 找到未完成 cycle；社招和校招独立推进，单个范围失败不阻塞另一个范围。

MCP `crawl_source` 只执行一个有界批次并返回进度，不在 MCP 进程内启动后台任务。
`crawl_all_sources` 遇到未完成的可续跑来源时不得推进到下一 source；只有该来源
`committed` 或明确失败后才更新全局 cursor。

## 错误与安全

- 403、验证码、登录页或响应 host 变化：`AccessRestricted`，不重试绕过。
- HTTP 方法、状态、portal type、offset 或筛选条件不匹配：忽略该响应并等待正确响应。
- 页面超时：当前 shard 保持原 offset，下次安全重试。
- 响应缺 JD、ID、标题或城市：cycle `degraded`。
- count 突降、分片集合变化或大量字段为空：cycle `degraded`。
- 不把 Cookie、签名、响应头中的敏感值写入数据库或日志。
- 日志只输出 cycle、shard、offset、数量、耗时和清理后的错误摘要。

## 测试与验收

默认测试全部使用本地 fixture，不访问公网，至少覆盖：

- 社招和校招来源的 portal、城市过滤和招聘类型映射。
- 单次 20 页后保存 offset，并由下一次调用恢复。
- 进程中断后重复批次幂等，不重复写暂存岗位。
- 跨页和跨分片重复 ID 去重。
- 相同 ID 不同内容使轮次失败。
- 排序漂移在第二遍收敛。
- 三遍仍漂移时 degraded 且 `missing_count` 不变。
- 完整轮次只提交一次，重跑为 unchanged。
- 两个 Runner 重叠时只有一个获得 source lock。
- 旧项目来源到新全量来源的覆盖迁移不产生重复 active 岗位。

真实官网 Gate 分社招和校招执行，记录官方分片 count、暂存唯一数、最终提交数、重复
数和排除的非中国大陆数量。生产验收要求：

```text
cycle status = committed
duplicate (crawl_source_id, external_job_id) = 0
running/degraded/failed cycle caused missing/offline = 0
second completed cycle transitions = unchanged only（官网真实变化除外）
```

覆盖矩阵只能在真实完整轮次通过后改为“全量”；若任何分片仍受 10,000 上限限制，
文档必须明确标为部分覆盖。
