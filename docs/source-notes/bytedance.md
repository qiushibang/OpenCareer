# 字节跳动官方招聘公开来源调查

- 调查日期：2026-08-05
- 来源 ID：`bytedance-seed-campus`
- 官方入口：<https://jobs.bytedance.com/campus/position>
- 启用范围：`2027届Seed大模型人才校招`
- 官方项目 ID：`7621018151002507573`
- 结论：Seed 与前沿技术两个互斥项目 Adapter 已实现并注册；不覆盖字节全部校招或社招。

## 数据契约

公开页面无需登录即可展示岗位。页面自身请求
`POST /api/v1/search/job/posts`，响应包含稳定数字 `id`、职位编码、标题、
完整 `description`、完整 `requirement`、城市、招聘类型和项目字段。详情 URL
使用数字 `id`：

```text
https://jobs.bytedance.com/campus/position/<id>/detail
```

列表请求含第一方页面动态生成的 `_signature`。直接删除签名会返回错误的猎头
平台 HTML，而不是岗位 JSON。因此项目不调用、保存、复用、生成或逆向签名。
Adapter 使用全新 Playwright 上下文打开公开页面，让官网自行完成请求，只读取
对应公开响应。

## 范围与规模

本次逐一验证：

| 范围 | 岗位数 | 页数（10 条/页） | 结论 |
|---|---:|---:|---|
| 社招 | 10,000（上限） | 1,000 | 超过 MCP 120 秒，不实现 |
| 全部校招 | 7,387 | 739 | 超过 MCP 120 秒，不实现 |
| 校招关键词 `AI` | 4,687 | 469 | 仍不完整，不实现 |
| 2027 前沿技术领域人才校招 | 136 | 14 | 已启用 |
| 2027 Seed 大模型人才校招 | 85 | 9 | 启用 |

将来源限定为一个官网明确项目，保证一次 crawl 能返回完整集合，避免不完整分页
误触发 `missing` / `offline`。

## 安全与失败策略

- 新建无持久状态的 headless Chromium context，不读取用户 Chrome profile。
- 不带用户凭据，不登录，不投递，不处理验证码。
- 只允许 `jobs.bytedance.com` 的固定校园项目页面和列表响应。
- 单页 20 秒超时，最多 20 页、200 条；图片、媒体和字体不加载。
- 项目 ID、项目名称、总数、分页、岗位 ID 或必填字段不一致时整轮失败。
- Playwright 在 FastMCP asyncio 线程外执行，避免同步 API 运行时冲突。
- 默认测试只使用本地缩减 fixture，不访问公网。

## 验收证据

- live Adapter：85 条、85 个唯一 ID，30.51 秒。
- 真实 MCP stdio dry run：`created=85`、`status=dry_run`，23.03 秒。
- 前沿技术 live：136 条、136 个唯一 ID，21.2 秒。
- 前沿技术真实 MCP dry run：`created=136`、22.31 秒。
- 前沿项目 ID：`7624064258157889845`；项目名：
  `2027届前沿技术领域人才校招`。
- 项目通用 transport 使用一个 browser/context 完成全部分页，避免逐页重启 Chromium。
- 聚焦来源测试：52 passed。
- 完整 Career/后端：96 passed，1 个上游弃用警告。
- GUI：109 passed。

## 运行要求

该来源使用 OpenWorker 已声明的 `browser` 可选依赖：

```bash
.venv/bin/pip install 'playwright>=1.44'
.venv/bin/playwright install chromium
```

缺少依赖或浏览器时来源会失败，不会返回部分岗位或触发下线。

## 2026-08-20 全量续跑实现

新增两个待生产完整轮次验收的来源：

- `bytedance-mainland-social`
- `bytedance-mainland-campus`

公开筛选元数据表明顶层职类分片比城市分片更稳定：岗位只有一个主职类，但可属于
多个城市。Runner 因此优先按官网公开顶层职类分片，并仅保留至少包含一个中国大陆
城市的岗位；没有职类元数据时才降级为大陆城市分片。

每次最多读取 20 页并把 shard offset、暂存岗位和 pass 写入
`catalog.crawl_cycles`、`catalog.crawl_cycle_shards` 和
`catalog.crawl_cycle_jobs`。首遍完成后必须再跑一遍；第二遍覆盖暂存全集才在同一
PostgreSQL 事务内提交 Catalog 和 `cycle=committed`。最多三遍仍漂移、同岗位 ID
返回冲突内容或分片达到 10,000 上限时标记 `degraded`，不执行 missing/offline。

每日容器在常规来源后执行独立的 resumable 预算，默认每个来源 12 个批次：

```bash
python -m extensions.career_mcp.crawl_cli \
  --resumable-only \
  --resumable-batches "${CRAWL_RESUMABLE_BATCHES:-12}"
```

离线、静态和隔离 PostgreSQL 16 真实官网 Gate 已通过；生产尚未部署这两个来源，
因此线上岗位雷达仍不能宣称已经切换到全量覆盖。

## 2026-08-20 本地 PostgreSQL 16 与官网 Gate

- Colima Docker runtime 中启动 PostgreSQL 16，使用非 superuser
  `opencareer_app` 验证 migration 1–7 和 FORCE RLS。
- 独立 `bytedance_test` 库真实运行：
  - `bytedance-mainland-social`：首批 20 页、200 条暂存、pass 1、Catalog 0。
  - `bytedance-mainland-campus`：首批 20 页、200 条暂存、pass 1、Catalog 0。
- 官网校招“游戏策划”职类当时为 26 条，用独立 Gate source 完成两轮完整 cycle：
  - 第一轮：pass 1 → pass 2 → committed，`created=26`。
  - 第二轮：pass 1 → pass 2 → committed，`unchanged=26`。
  - active 26、重复 `(crawl_source_id, external_job_id)` 为 0、事件只有 created，
    没有 missing/offline。
- 真实运行观察到校招研发职类 count 在数分钟内从 4,264 变为 4,265。Runner 已改为
  首遍吸收该基线漂移，第二遍再漂移则进入第三遍，第三遍仍漂移才 degraded。

## 2026-08-20 完整社招/校招隔离 Gate

- `bytedance-mainland-social` 完成 pass 3 并原子提交：
  `created=11,634`、active 11,634、invalid 0。
- `bytedance-mainland-campus` 完成 pass 3 并原子提交：
  `created=7,423`、active 7,423、invalid 0。
- 两个来源合计 19,057 条；来源内重复
  `(crawl_source_id, external_job_id)=0`，社招/校招跨来源重复 ID 为 0。
- `crawl_runs` 均为 succeeded，事件只有 created，没有 missing/offline。
- 长轮次暴露并修复三项收敛问题：
  - 已存在公司不再每批重复 upsert，避免社招/校招事务争抢 company 行锁；
  - pass 3 重新建立 count 基线，并允许遍内实时 count 漂移，最终以所有暂存岗位的
    `last_pass=3` 作为完整覆盖门禁；
  - 同 ID 内容在后续 pass 可更新，同一 pass 内不同内容仍视为冲突。
- 社招第三遍结束后有 6 条只在 pass 1 出现。最初逐条读取官方详情页确认 4 条明确
  下线、2 条仍在线；隔离 Gate 删除 4 条下线暂存记录，并将 2 条在线记录记为详情页
  直接确认后完成提交。
- 本轮只写本机 `bytedance_test` 隔离数据库，未部署或写入线上生产 Catalog；线上
  公司筛选继续显示旧来源约 220 条是预期状态。

## 2026-08-21 stale 详情尾部自动核验

- 第三遍完整列表仍有 1–20 条 stale 岗位时，Runner 使用一个全新的无状态
  Playwright context 逐条读取固定官方详情 URL。
- 仅将同时出现“职位描述”和“职位要求”的页面判为 `active`，仅将明确出现
  “该职位已下线”的页面判为 `offline`；未知正文、超时、异常跳转、非数字 ID 或
  数量超过 20 均失败关闭，不修改 staging。
- Repository 先核对结果 ID 与 stale 行完全一致，再在同一事务中更新在线行的
  `last_pass`、删除明确下线行；重新读取后全部行属于当前 pass 才允许提交。
- 真实 PostgreSQL 16 临时 cycle 验证 `active=2`、`offline=4`、剩余 2 行，并整体
  回滚。自动 verifier 对原 6 个官方 URL 返回：
  - `active`：`7506869832030390535`、`7506870288618850567`；
  - `offline`：`7352891772735506725`、`7523152599735798023`、
    `7644767618747189557`、`7646317548203968821`。
- 真实 URL Gate 为只读，未回写已经 committed 的 cycle；隔离 Catalog 仍为社招
  11,634、校招 7,423。线上 Alpha 未部署或修改。

## 2026-08-21 生产部署

- 恢复点：`20260821T032119Z`。服务器与离机副本的 14 个文件均通过
  `sha256sum -c`，PostgreSQL custom dump 可由 `pg_restore --list` 读取；
  `.env` 仅保存加密副本，解密密钥只在离机目录。
- 新后端镜像 `sha256:468d6b66…a3e1584` 已切换，旧镜像
  `sha256:4167e8b7…572079b`、旧容器和数据卷均保留。migration 7 已应用，
  PostgreSQL/Redis ready，REST 与 WebSocket smoke 通过，restart count 为 0。
- 将已完成三遍隔离 Gate 的快照按来源事务导入生产：
  `bytedance-mainland-social=11,634`、
  `bytedance-mainland-campus=7,423`，来源内与 active external ID 重复均为 0，
  无效记录为 0。
- 旧 Seed/前沿来源的 220 条中，214 条被新校招来源精确覆盖并标记
  `superseded`；未覆盖的 6 条继续保留，两个旧抓取入口已停用。
- 生产现为 29,612 个 active 岗位，其中字节 19,063 个；用户 Resume、Interview、
  Conversation、Message 计数与切换前一致。Blob 由 82 增至 84，对应两个完整原始
  来源快照。
- 生产官网复核 cycle 在后台串行续跑；校招已从 checkpoint 推进到 1,996 条，
  社招保留 200 条 checkpoint。访问限制时冷却 5 分钟后续跑，不会提交部分 Catalog。

## 2026-08-21 岗位雷达查询优化

- 字节全量上线后总 active 为 29,612，列表与筛选的旧 SQL 分别约 2.1 秒和
  2.4 秒；瓶颈是重复可见性函数、JD 大字段 projection 和多次 facet 全表扫描，
  不是 JSON 文件或 PostgreSQL 容量。
- migration 8 与轻量 Repository 已上线。最终服务器经 Caddy 的 10 次采样中，
  列表 P95 为 157.88ms，筛选 P95 为 138.77ms；active 数量与重复键保持不变。
- 后台官网复核在备份窗口暂停，切流完成后从原 checkpoint 恢复；正式 Catalog
  未使用未完成 cycle 的 staging 数据。
