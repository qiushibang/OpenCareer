# 百度官方招聘来源调查

- 调查日期：2026-08-05
- 来源 ID：`baidu-careers`
- 范围：只访问百度官方 `talent.baidu.com` 的公开页面；未登录、未提交表单、未处理验证码，未进行高频请求或接口枚举。
- 结论：可进入 Stage 4 的 Adapter 设计，但应优先解析公开 SSR HTML 中的内嵌状态，不应先依赖未验证的 XHR 接口。

## 官方入口与公开访问

- 官方招聘首页为 <https://talent.baidu.com/>。本次请求返回 `302` 到公开社招入口 <https://talent.baidu.com/jobs/social>；该页面展示“社会招聘”、职位搜索和登录入口。
- 官方页面的内嵌导航还提供社会招聘 <https://talent.baidu.com/social-list>、校园招聘 <https://talent.baidu.com/campus> 和职位页 `/list`。这些路径来自该官方页面的 `window.__INITIAL_DATA__`，不是第三方目录。
- 首页响应的 `meta description` 明确称其为“百度官方招聘平台”，并列出社会、校园、实习生和海外招聘范围：[官方页面](https://talent.baidu.com/jobs/social)。

## 列表、详情和 JavaScript 形态

- `https://talent.baidu.com/jobs/social` 返回 `200 text/html`，并且 HTML 中设置 `window.__USE_SSR__=true`。首屏并非只能由浏览器执行 JavaScript 后获得。
- 页面将结构化 `window.__INITIAL_DATA__` 内嵌于 HTML，其中 `listData.listDetailData` 为职位列表，`detailData.postInfo` 为一条完整职位详情。已观察到的字段包括：
  - 列表：`name`、`postId`、`jobId`、`postType`、`publishDate`、`updateDate`、`workPlace`、`serviceCondition`、`workContent`、`projectType`。
  - 详情：上述 JD 字段之外还有 `orgName`、`education`、`workYears`、`recruitNum`、`recruitType`、`isValid`。
- 列表状态同时给出 `listData.pageNum`、`listData.pageSize` 和 `listData.total`。本次首屏观察值为 `pageNum: 1`、`pageSize: 10`、`total: 12`，说明站点模型使用页码分页；这只是当前响应快照，不能假定所有招聘类型的总数或页大小相同。
- HTML 仍加载 React/Ant Design 相关 JavaScript bundle，因此交互筛选、翻页和详情导航可能会使用 JavaScript。由于本次受控浏览会话未成功加载新标签，**未确认**公开 XHR/Fetch 的 URL、参数或响应契约；实现前只能在一次低频、正常浏览器会话中复核，不能猜测或逆向接口。

证据：官方社招页 [HTML/SSR 入口](https://talent.baidu.com/jobs/social)。

## 稳定身份与分页建议

- 每个观察到的职位同时有 UUID 形态的 `jobId` 和 `postId`，另有展示在标题中的 `J99969` 一类编号。
- 第一版应将 `jobId` 作为候选 `external_job_id`，并在 fixture 中验证同一岗位在列表和详情中的值一致。`postId` 应保存在 `raw_metadata`，待一次跨页/跨招聘类型样本确认其语义后再决定是否作为备用身份。
- 不应把职位标题或标题中的 `Jxxxxx` 文本作为唯一键：它们属于展示文本，不能从本次观察证明其跨页面稳定性。
- `pageNum/pageSize/total` 足以支持页码式发现循环；每次只获取一页，串行、低频运行，并在 `total` 或模板字段异常时将本次抓取标记为降级，而不是执行批量下线。

## 推荐 Adapter 类型

建议 `BaiduSsrHtmlAdapter`：

1. 低频 GET 官方招聘页，解析 `window.__INITIAL_DATA__` 中的 JSON 状态。
2. 从 `listDetailData` 生成 `JobPointer`；保存 `jobId`、`postId`、职位名、地点、招聘类型及来源 URL。
3. 若目标页的 `detailData.postInfo` 与列表中职位对应，则直接构造 `RawJobDocument` 和 `ParsedJob`；否则在确认官方详情 URL 后单独低频获取详情页。
4. 将实际 HTML 保存为 fixture；测试只解析 fixture，不访问公网。

这是“内嵌 JSON/SSR HTML”类型，符合项目来源优先级，当前不需要 Playwright，也不应实现未经证实的 API Adapter。

## robots、访问限制与风险

- 本次对官方 <https://talent.baidu.com/robots.txt> 的单次 GET 返回 `404` JSON (`{"error":"Not Found", ...}`)，因此未发现可据以解释允许范围的 robots 文件。`404` 不是授权，也不是绕过限制的理由。
- 本次对官方 <https://talent.baidu.com/sitemap.xml> 的单次 GET 返回 `200`，内容为 `{"status":"need-login","message":"need login!"}`。不应登录或尝试绕过该限制，也不将其作为发现职位的途径。
- 页面提供登录入口；本调查和未来自动源都不得使用登录态、Cookie、Token、验证码处理或签名逆向。
- 对 `429`、`403`、验证码页、登录重定向、非预期 HTML/JSON 或模板字段缺失，应返回 `AccessRestricted` 或 `degraded`，停止该轮自动抓取，不重试规避。
- 运行建议沿用项目策略：域名并发 `1`、明确 UA、6--12 小时一次或更慢、有限退避；页面内容可能调整，Adapter 必须保留原始 URL、首次发现时间、最近确认时间和 HTML fixture 元数据。

## 实现前的最小复核项

1. 仅在公开页面上以一次低频正常浏览确认社招、校招和翻页后的 SSR 结构是否一致。
2. 确认 `jobId` 在列表与对应详情中一致，并记录规范详情 URL；若不能确认，则只抓取 SSR 中自带的完整 JD。
3. 若浏览器正常翻页产生公开 XHR，再记录其真实请求；若无必要，不使用 XHR。
4. 保存最少的已获许可公开 HTML fixture，并以本地 fixture 测试解析、身份、版本变化和降级保护。

## 2026-08-05 Live Smoke 结果

- 已以一次低频、未登录 GET 调用 `https://talent.baidu.com/jobs/social`，响应未触发 401、403、429、登录重定向或 CAPTCHA 标记。
- 但最新响应中的 `window.__INITIAL_DATA__` 不能作为严格 JSON 解析，Career Adapter 返回 `BaiduSsrParseError: window.__INITIAL_DATA__ is invalid JSON`。
- 这属于页面状态契约异常。根据项目停止条件，`baidu-careers` 没有注册进默认生产 Adapter registry；不会通过猜测 JavaScript 表达式、重复探测、登录、Cookie、Token 或未证实 XHR 来规避。
- 已捕获的公开 fixture 仍用于离线 SSR 提取和 `JobSnapshot` 解析测试。只有在人工复核当前公开状态表达式、更新 fixture 和解析契约后，才可重新评估启用该来源。

## 参考

- [百度官方招聘社招入口](https://talent.baidu.com/jobs/social)
- [百度官方招聘首页](https://talent.baidu.com/)
- [百度官方 robots.txt（本次为 404）](https://talent.baidu.com/robots.txt)
- [百度官方 sitemap.xml（本次返回登录提示）](https://talent.baidu.com/sitemap.xml)
