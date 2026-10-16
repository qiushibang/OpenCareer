# crawl_all_sources 运行说明

## 目的

`crawl_all_sources` 按 source slug 的字典序遍历全部已注册招聘来源，并隔离单个来源
失败。由于 34 个来源完整运行约需 20 分钟，超过 MCP 单次调用 120 秒限制，工具每次
只运行一个来源，并通过 cursor 续跑。

## 参数

```text
dry_run: bool = true
cursor: string | null = null
```

- `dry_run=true`：只计算 transitions，不写岗位状态。
- `dry_run=false`：正式写入；继续经过 OpenWorker 的 MCP 审批。
- 首次调用不传 `cursor`。
- 后续调用把上次返回的 `next_cursor` 原样传回。
- 当 `has_more=false` 时本轮完成。

字节中国大陆社招/校招是可续跑来源，必须使用 `dry_run=false`。单次调用只处理一个
有界批次；返回 `status=running` 时 `next_cursor` 保持不变，调用方必须原样重试，
不能跳到下一来源。只有 `committed`、`degraded` 或 `failed` 后 cursor 才推进。

## 示例

第一次：

```json
{
  "dry_run": true
}
```

响应：

```json
{
  "results": [
    {
      "source_slug": "alibaba-token-foundry-social",
      "status": "dry_run",
      "transitions": {"unchanged": 61}
    }
  ],
  "total_sources": 34,
  "has_more": true,
  "next_cursor": "alibaba-token-foundry-social"
}
```

第二次：

```json
{
  "dry_run": true,
  "cursor": "alibaba-token-foundry-social"
}
```

## 失败行为

- 来源失败记录在 `results[0]`，并增加 `failed`。
- 批次响应保持 `ok=true`，使调用方仍可使用 `next_cursor` 继续后续来源。
- `warnings` 包含经过清理的失败摘要。
- 失败来源不返回部分岗位，也不触发 missing/offline。
- cursor 不属于当前 registry 时返回 `INVALID_INPUT`。
- 可续跑来源达到 10,000 上限、快照冲突或三遍仍漂移时返回 `degraded`，不更新正式
  Catalog，也不触发 missing/offline。

## 约束

- 不并发抓取。
- 不在 MCP 进程内启动后台长任务。
- 不绕过 OpenWorker 权限审批。
- registry 新增或删除来源后，应从空 cursor 开始新一轮。

## OpenWorker Automation

当前已创建：

```text
task: Career Job Radar Cursor Runner
id: task-a42c98acd2
cron: 0 * * * *
timezone: Asia/Shanghai
workspace: <repo>
agent: career
cursor file: .local-state/crawl-all-cursor.json
```

每次定时运行：

1. 读取 cursor 文件；
2. 调用一次 `mcp__career__crawl_all_sources(dry_run=false)`；
3. 将 `next_cursor` 写回 cursor 文件；
4. 输出当前来源 transitions 和剩余状态。

Automation 的 headless engine 现在复用 `SessionManager.prepare_mcp_tools()` 加载可信
workspace MCP。GUI 创建接口只有在 workspace 已存在且被 OpenWorker 标记为可信时，
才允许绑定 workspace 和 persona；默认 Automation 仍使用独立 scratch workspace。

Career MCP 没有可安全绑定的外部 target，因此不能获得 task standing approval。
每次正式抓取会在 Inbox 中等待批准。批准后当前 run 继续；其他 Automation 和
scheduler tick 不会被阻塞。

Scheduled run 在等待 Inbox 时会登记为 running。这样 REST/GUI resolve 只唤醒原
await，不会误触 durable resume 并重复执行同一个 MCP tool call。

生产复验时应同时检查 run transcript 和 `crawl_runs`：一个 MCP `tool_call_id`
只能对应一个 tool result，目标来源只能新增一条 crawl run。2026-08-06 的复验从
`bytedance-seed-campus` 推进至 `deepseek-careers`，返回 32 unchanged，DeepSeek
crawl run 总数从 2 增至 3。

2026-08-06 完成首个 34 来源 Automation 轮次。执行期间可临时提高 cron 频率，但
必须保留 skip-on-overlap 和逐次 Inbox 审批，并在轮次结束后恢复小时调度。最终
验收要求所有来源的 latest crawl run 均为 `succeeded`，cursor 为 null，且数据库
无重复 `(crawl_source_id, external_job_id)` 或外键错误。

美团多页 API 必须在单次 Adapter 运行内复用 HTTP 客户端连接。逐页新建 TLS 连接
会放大 CDN 间歇性握手超时；失败 run 不得产生 missing/offline，修复后再单独正式
重试该来源。
