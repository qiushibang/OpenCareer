# 每日岗位抓取容器（M0.5）

这一层解决的问题是：**让岗位数据每天自己更新，不需要任何人打开桌面 App 手动触发。**

> 前提是 M0 已经跑起来（`deploy/README.md`）。抓取容器和后端容器互不依赖，可以先上线 M0，
> 过几天再加这个；出问题也只影响「岗位不更新」，不会让朋友们打不开网站。

---

## 一、为什么是独立容器，而不是塞进后端

| 做法 | 问题 |
| --- | --- |
| 抓取跑在用户请求后端里 | 浏览器依赖大；抓取卡住会拖慢正常使用；多实例还会重复访问招聘网站 |
| 用项目自带的 Scheduler（`coworker/automation/scheduler.py`） | 它跑在 FastAPI 进程内，生命周期和用户后端绑死；后端重启、崩溃、升级都会打断抓取 |
| **独立抓取容器（本目录）** | 浏览器只装一份；网络请求只打一遍；抓取挂了不影响任何人用产品 |

关键设计是**抓取和落库分成两个阶段**：

```
阶段一 fetch     每个数据源只请求一次网络  ──►  快照（JobSnapshot）
阶段二 persist   同一批快照写入 PostgreSQL 共享岗位目录 ──► 统一 upsert、统一判断 offline
```

所以**对招聘网站的请求量不随用户人数增长**。用户的收藏和申请状态仍按 `user_id` 隔离。

---

## 二、组成部分

| 文件 | 作用 |
| --- | --- |
| `extensions/career_mcp/crawl_cli.py` | 命令行抓取入口（在仓库里，不在本目录）。桌面上也能直接用 |
| `Dockerfile` | 抓取镜像 = 后端精简依赖 + playwright + chromium |
| `requirements-crawler.txt` | 只比后端多一个 `playwright` |
| `entrypoint.sh` | 调度循环：每天 `CRAWL_AT` 附近跑一轮 |
| `docker-compose.yml` 里的 `crawler` 服务 | 连接 PostgreSQL 共享岗位目录 + 资源上限 |

---

## 三、上线

```bash
cd deploy
docker compose build crawler          # 第一次会比较久：要下 chromium 和一堆系统库
docker compose up -d crawler
docker compose logs -f crawler        # 应该看到「调度已启动：每天 04:00」
```

**先手动跑一轮**，别等到第二天才发现配错了：

```bash
# 只跑一个便宜的源，确认链路通（不占用常驻容器）
docker compose run --rm crawler once --only tencent-wxg-experienced

# 确认 PostgreSQL 共享岗位目录写入成功
```

顺利的话日志形如：

```
[crawl ...] FETCH OK   tencent-wxg-experienced: 42 条，21.3s
[crawl ...] CACHE      tencent-wxg-experienced -> /cache/snapshots/... (42 条)
[crawl ...] WRITE OK   tencent-wxg-experienced -> postgres: {"created": 42}
```

第二天再看，`created` 会变成 `unchanged`（内容没变）和 `changed`（JD 改了）——这说明去重在工作，
不会每天重复堆一份。

---

## 四、常用操作

```bash
# 看有哪些数据源
docker compose run --rm crawler list

# 只验证数据源还通不通，不写库
docker compose run --rm crawler once --dry-run

# 某个站点改版天天报错，先摘掉它（改 .env 后 up -d 重建）
CRAWL_SKIP=xiaohongshu-social-cn,zhipu-campus

# 写库失败了想重试，但不想再打一次网站——用上一轮的快照缓存重放
docker compose run --rm crawler once --from-cache

# 换时间：改 .env 里的 CRAWL_AT=03:30，然后 docker compose up -d crawler
```

新增用户不需要修改 Crawler：共享岗位目录只抓取一次，用户自己的收藏和申请记录由后端按用户写入。

---

## 五、可调参数（都在 `.env` 里）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CRAWL_AT` | `04:00` | 每天几点开始（容器内时区 `TZ`，默认 `Asia/Shanghai`） |
| `CRAWL_JITTER_MINUTES` | `25` | 在 `CRAWL_AT` 后随机延迟 0~25 分钟，避免每天同一秒去敲人家网站 |
| `CRAWL_RUN_ON_START` | `0` | 设 `1` 则容器启动就先抓一轮（首次部署想立刻见数据时用） |
| `CRAWL_ONLY` / `CRAWL_SKIP` | 空 | 临时缩小/摘除数据源，逗号分隔 |
| `CRAWL_SOURCE_TIMEOUT` | `300` | 单个源的墙钟上限（秒）。防止浏览器挂住把整晚堵死 |
| `CRAWL_PAUSE_SECONDS` | `3` | 相邻源之间歇一下，降低被风控识别的概率 |

---

## 六、已知问题和边界

**必须知道的：**

1. **抓取失败是常态，不是故障。** 招聘网站改版、加验证码、限流都会让某个源失败。CLI 的设计是
   **单源失败不影响其它源**，退出码 1 表示「部分失败但已写入成功的部分」，容器不会因此退出。
   日志里持续报错的源，用 `CRAWL_SKIP` 摘掉，别让它每天刷屏。

2. **生产环境只有一个共享岗位目录。** Crawler 通过 `DATABASE_URL` 写 PostgreSQL 的公开岗位表；
   简历、收藏和申请进度由后端按 `user_id` 隔离。`--data-dir` 与 sqlite 仅保留给本地兼容测试。

3. **内存。** chromium 峰值几百 MB，当前 2G 服务器编排把 Crawler 放在可选 profile 中，
   默认不启动；如果同时有人在用，可能会紧张——
   把 `CRAWL_AT` 放到确定没人用的时间。

**尚未在真实服务器上验证的：**

- `docker compose build crawler`（本地沙箱没有 Docker）。**`playwright install --with-deps chromium`
  这一步是唯一可能卡住的地方**，网络慢时要几分钟到十几分钟，务必第一次手动跑一遍看着它完成。
- 6 个 Playwright 源在服务器上的真实成功率。它们在本地桌面能跑，但服务器 IP 更容易被风控盯上。
  建议第一周每天看一眼日志，把稳定失败的源摘掉。
- 全部 35 个源跑一整轮的总耗时。腾讯占 24 个 scope，且是「列表 + 逐个详情」模式，是最慢的一块。

**已经验证过的（本地真实运行，非推演）：**

- CLI 的三种模式：`--list`、实时抓取、`--from-cache` 重放。
- PostgreSQL 共享岗位目录、断点续跑和查询性能有独立测试；sqlite 多库写入只作为本地兼容能力保留。
- **去重幂等**：同一批快照重放第二次，结果是 `unchanged: 17`，`job_versions` 没有增长。
- **零网络缓存重放**：用缓存快照重新落库，不再次请求招聘网站。
- **单源失败容错**：同一轮里有源超时失败，成功的源照常写入，退出码 1。
- WAL 模式切换、`entrypoint.sh` 的 `sh -n` 语法检查、定时时刻计算、compose YAML 与卷引用校验。
