# 小米官方招聘来源调查

- 调查日期：2026-08-05
- 来源 ID：`xiaomi-careers`
- 范围：仅访问小米官方招聘页面 `hr.xiaomi.com` 与其页面公开链接；未登录、未提交申请、未处理验证码、未保存或复用 Cookie/Token，未进行接口枚举或高频请求。
- **当前结论：fixture-first Adapter 已实现并注册。** 2026-08-05 的受控核验确认公开列表接口返回稳定 JSON，单页已包含完整 JD 字段和官方详情 URL。默认测试只读取本地 fixture；线上全量抓取仍须通过 OpenWorker 的 `crawl_source` 审批。

## 官方入口与公开发现

- 小米官方招聘首页为 [https://hr.xiaomi.com/](https://hr.xiaomi.com/)；该站点将“浏览全部职位”链接到 [探索机会页](https://hr.xiaomi.com/website/opportunities.html)。
- 探索机会页公开显示“城市”和“招聘项目”筛选、职位列表、总数及“上一页/下一页”控件。本次页面显示 `共 2522 个职位` 和 `1/253`；这是调查时刻的页面状态，不得作为固定总数或总页数。
- 页面中公开列出职位链接，例如 [AI芯片架构工程师](https://xiaomi.jobs.f.mioffice.cn/internship/position/7621123727820851507/detail)。该链接来自小米官方招聘页的正常 DOM，不是第三方目录。

## HTML、JavaScript 与公开 Fetch

- 浏览器正常加载探索机会页后，职位卡片和分页控件可见；它不是只靠静态 HTML 完成岗位发现的页面。
- 本次单页、未登录浏览器网络记录到一条同源公开 Fetch：

  ```text
  GET https://hr.xiaomi.com/website/api/agent/searchJobPage
      ?keyword=
      &cityZhNames=
      &pageSize=10
      &pageNum=1
  ```

  该请求与页面首屏十个职位和第 1 页相对应，说明目前存在以 `pageNum` / `pageSize` 表达的页码式列表请求。

- 受控列表请求返回 `HTTP 200`、`application/json`，顶层为 `code`、`message`、`data` 和 `traceId`；`code=0`、`message=成功`。`data` 包含 `list`、`pageSize`、`pageNum`、`pageTotal` 和 `total`。
- `data.list` 的每个岗位已包含 `title`、`cityZhNames`、`levelOneDeptName`、`description`、`requirement`、`publishTime`、`type`、`url`、`jobId` 和 `jobPostId`。因此列表响应本身即可提供完整职责和要求，不需要猜测详情 API。
- 未观察到可作为岗位数据来源的 SSR 内嵌状态；本轮证据支持“前端公开 Fetch 列表页”，不支持“SSR HTML Adapter”结论。

证据：[小米官方探索机会页](https://hr.xiaomi.com/website/opportunities.html)。

## 岗位身份、详情与完整 JD

- 已观察到的详情 URL 以数字段 `7621123727820851507` 表示一个岗位发布记录，并在 `/internship/position/<数字>/detail` 中出现。该数字对应 `jobPostId`，不是 Adapter 使用的 `external_job_id`。
- 列表同时提供 `jobId`、`jobPostId` 和详情 URL；详情 URL 的数字段等于 `jobPostId`，但不等于 `jobId`。例如，AI 芯片架构工程师的 `jobId` 为 `7621123727820392755`，`jobPostId` 为 `7621123727820851507`，且 URL 包含后者。Adapter 应以 `jobId` 作为候选 `external_job_id`，并保存 `jobPostId` 与完整 URL 为原始来源元数据。
- 已以正常浏览器打开该详情 URL，未登录时返回标题与列表职位一致的页面；页面仅在“投递”动作处显示登录入口。完整 JD 不依赖详情页，因为列表 JSON 已返回 `description` 与 `requirement`。

## 分页与推荐调查后的 Adapter 方向

首选 `XiaomiPublicApiAdapter`，而不是 HTML 或浏览器自动化：

1. 固定本次公开列表响应为本地 fixture，记录 URL、响应类型、日期和期望字段。
2. 从已确认的响应字段读取页码、总数和职位候选；串行分页，域名并发为 `1`。
3. 以 `jobId` 作为岗位身份；当前数据模型持久化详情 URL，其中已包含 `jobPostId`。独立 `raw_metadata` 字段不属于本次最小变更。
4. 以离线 fixture 测试验证字段缺失、重复 ID、错误响应和稳定内容哈希的降级行为。

本次未发现可证明存在详情 API 的证据，因此不应逆向、猜测或枚举任何 `mioffice.cn` 接口。

## robots、限制与合规边界

- 对 [https://hr.xiaomi.com/robots.txt](https://hr.xiaomi.com/robots.txt) 的单次请求返回通用排队页面，不是可解析的 robots 规则；这既不构成允许，也不构成可绕过的限制。
- 对 [https://xiaomi.jobs.f.mioffice.cn/robots.txt](https://xiaomi.jobs.f.mioffice.cn/robots.txt) 的单次请求返回 `Not Found`。`404` 不等于抓取许可。
- 未遇到登录页、验证码、401、403 或 429；详情页已验证无需登录即可浏览。尚未执行 253 页全量抓取，因此不能将单页 smoke 扩展为全量分页稳定性结论。
- 任一后续请求出现登录、验证码、Cookie/Token 要求、签名参数、403、429、明显排队/访问控制页、非预期内容类型或字段结构异常时，立即停止该轮请求，记录 `AccessRestricted` 或 `degraded`，不重试规避。
- 常规运行仍须遵循项目限制：明确 UA、域名并发 `1`、每 6--12 小时或更慢、无登录态、无高频枚举。

## Fixture 与最小 live smoke

- 已保存 `listing_page_1.json` 和 `metadata.json`。fixture 从真实第一页响应缩减为两条完整岗位，保留原始分页值并在元数据中标记 `reduced=true`；不含 Cookie、Token、签名或个人数据。
- 解析、错误契约、分页、默认 registry 和 SQLite pipeline 测试只读取本地 fixture，不访问公网。
- 实现后的单页 live smoke 返回 `page_num=1`、`page_total=253`、`total=2522` 和 10 条岗位；首条 `jobId=7621150010131237158` 与 fixture 一致。
- GUI 首次使用每页 10 条执行 dry run，需要约 253 个请求并连续两次超过 MCP 的 120 秒调用限制。该失败不是数据库或 MCP 挂载故障。
- 单次公开探针确认 `pageSize=100` 被官网支持：返回 100 条、`pageTotal=26`、`total=2522`，首条 ID 与 fixture 一致。Adapter 已改为每页 100 条，并拒绝响应未兑现该页大小。
- 修复后的完整只读抓取串行完成 26 页，返回 2522 个唯一岗位 ID，总耗时 46.8 秒，低于 MCP 调用限制。生产写入仍须由用户批准 `crawl_source`，遇访问限制或契约变化立即将 crawl run 标记失败。

## 可用性与降级条件

**已满足的准入事实：** 单次公开列表 GET 返回结构化岗位数据；列表含完整 JD；`jobId` 与 `jobPostId` 明确区分；官方详情 URL 无需登录即可打开并与列表标题一致。

**当前状态：** `xiaomi-careers` 已作为唯一默认生产 Adapter 注册。未经 `crawl_source` 审批不会访问网络或保存线上职位；用户仍可粘贴带官方 URL 的小米 JD，走现有手动 JD 导入链路。

**立即降级：** 若列表或详情需要登录、验证码、Cookie/Token、签名逆向，或连续出现 403/429/访问控制页，则将来源标为不可自动抓取，只保留官方入口和手动 JD。

## 参考

- [小米官方招聘首页](https://hr.xiaomi.com/)
- [小米官方探索机会页](https://hr.xiaomi.com/website/opportunities.html)
- [页面公开示例职位详情链接](https://xiaomi.jobs.f.mioffice.cn/internship/position/7621123727820851507/detail)
- [hr.xiaomi.com robots.txt（本次非 robots 规则响应）](https://hr.xiaomi.com/robots.txt)
- [xiaomi.jobs.f.mioffice.cn robots.txt（本次 404）](https://xiaomi.jobs.f.mioffice.cn/robots.txt)
