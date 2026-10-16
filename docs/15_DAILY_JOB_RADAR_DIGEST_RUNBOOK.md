# 每日岗位雷达摘要运行说明

## 目的

每天汇总过去 24 小时的岗位事件和招聘来源健康状态，同时生成可审计的
Markdown 文件。摘要只读取 SQLite，不触发抓取或修改岗位状态。

## MCP 工具

```text
get_job_radar_digest(hours=24, sample_limit=20)
```

- `hours` 范围为 1–168。
- `sample_limit` 范围为 1–100。
- 聚合计数覆盖窗口内全部事件；`sample_limit` 只限制样例数量。
- `sources.items` 只返回 failed 或 pending 来源，健康来源通过聚合计数表示。
- 完整来源列表仍使用 `list_sources`。

## Automation

```text
task: Career Job Radar Daily Digest
id: task-7a4f067305
cron: 0 9 * * *
timezone: Asia/Shanghai
workspace: <repo>
agent: career
output: artifacts/job-radar-daily/YYYY-MM-DD.md
```

每次运行：

1. 调用 `mcp__career__get_job_radar_digest(hours=24, sample_limit=20)`；
2. 使用当前 Asia/Shanghai 日期生成文件名；
3. 写入窗口、来源健康、事件汇总、公司汇总、20 个最近事件样例和警告；
4. 每个样例保留岗位 ID 和官方来源 URL。

任务不得调用 Shell、`crawl_source` 或 `crawl_all_sources`。工作区必须可信，
父目录 `artifacts/job-radar-daily/` 已随仓库创建。

## 与抓取任务的关系

抓取任务独立运行：

```text
task: Career Job Radar Cursor Runner
id: task-a42c98acd2
cron: 0 * * * *
```

抓取任务负责推进一个来源并更新数据库；日报任务只读取最近 24 小时已持久化结果。
日报不会自动批准抓取，也不会绕过 Inbox。

## 真实验收

2026-08-06 smoke：

- 10,067 个历史岗位，其中 10,013 active、54 inactive；
- 过去 24 小时 10,560 个事件；
- 34 configured、34 healthy、0 failed、0 pending；
- 20 个最近事件样例均包含岗位 ID 和官方 URL；
- smoke 前后均为 106 crawl runs、10,562 job events、10,431 job versions，
  证明摘要工具没有写业务状态。

产物：

```text
artifacts/job-radar-daily/2026-08-06.md
```

## 已知运行风险

火山方舟可能在大响应后的下一轮模型请求触发“request burst”保护。摘要响应已通过
只返回异常来源明细降低体积；若保护仍发生，已写入的 Markdown 文件仍可审计，但
Automation 会话的最终总结可能不完整。

恢复步骤：

1. 确认 artifact 是否已写入且章节完整；
2. 确认 `crawl_runs/job_events/job_versions` 未变化；
3. 若 artifact 不存在，等待模型限流窗口后重新触发日报任务；
4. 不要因此重跑抓取来源。
