# DeepSeek 官方招聘公开来源调查

- 调查日期：2026-08-05
- 来源 ID：`deepseek-careers`
- 调查边界：仅访问 DeepSeek 官网、官网明确链接的招聘域名，以及列表直接公开的 Moka 详情页；未登录，未提交申请，未保存或复用 Cookie/Token，未处理验证码，未逆向签名，未枚举接口，未进行翻页或高频请求。
- Smoke 计数：调查阶段列表 1 次、公开详情 1 次；实现验收阶段入口和 bundle 各 1 次。
- **结论：`DeepSeekStaticBundleAdapter` 已实现并注册。** DeepSeek 招聘首页公开引用的 JavaScript bundle 内含一个明确的 `JSON.parse(...)` 数据集，提供全部岗位、UUID、地点和完整 JD。无需调用 Moka API、维持会话或运行浏览器。

## 1. 官方入口与归属

- DeepSeek 官方首页 <https://www.deepseek.com/> 的“加入 DeepSeek / 查看职位”直接链接到 <https://talent.deepseek.com/>。
- 招聘列表中的详情链接位于 Moka 租户
  `app.mokahr.com/social-recruitment/high-flyer/140576`。该租户由
  `talent.deepseek.com` 的岗位列表逐项直接链接，详情页公司字段显示
  `DeepSeek`，因此可确认它是 DeepSeek 官方招聘流程使用的公开详情页面，
  不是第三方岗位聚合来源。

## 2. 列表数据路径、HTML、SSR 与 API

本轮先请求 <https://talent.deepseek.com/robots.txt> 检查 robots 规则。该路径没有返回 robots 指令，而是返回了与招聘站一致的“在招职位”网页内容。

该列表响应可直接解析出：

- “职位类别”“工作地点”筛选文案；
- 岗位名称；
- 职位类别；
- 一个或多个工作城市；
- 指向 Moka 官方详情的链接。

后续受控普通 GET 确认招聘首页返回 `HTTP 200 text/html`、530 字节 HTML 外壳，并公开引用：

```text
https://talent.deepseek.com/static/main.264ac482b7.js
```

该官方静态 bundle 返回 `HTTP 200 text/javascript`、约 360 KB。bundle 中存在
明确的 `JSON.parse('...')` 数据集，包含：

- `crawledAt`
- `sourceUrl=https://app.mokahr.com/social-recruitment/high-flyer/140576#/`
- `total=32`
- `functionCategories`
- `jobs`

`jobs` 数组包含 32 个唯一 UUID，并包含标题、职能、地点和完整
`descriptionHtml`。页面正常加载没有发出列表 XHR/API；数据来自官方构建产物，
不是需要猜测的接口。

## 3. 分页

- bundle 数据集明确给出 `total=32`，且 `jobs` 数组包含 32 条；页面没有页码、
  下一页、游标或列表网络请求。
- 当前契约是一个完整静态数据集，不需要分页。Adapter 必须验证
  `total == len(jobs)`；不一致时整轮失败，不能将缺失岗位判定为下线。

## 4. 稳定岗位 ID

列表详情 URL 形如：

```text
https://app.mokahr.com/social-recruitment/high-flyer/140576#/job/2eb2e75d-29f3-47b5-bb10-39f12547d398
```

- 末段是 UUID 形态，且同一个 UUID 出现在列表链接和实际打开的详情 URL 中。
- 本次验证样本：
  `2eb2e75d-29f3-47b5-bb10-39f12547d398`，对应“服务端开发工程师（线上核心服务/Agent 后端/数据仓库）”。
- 该 UUID 是当前最合理的 `external_job_id` 候选，详情完整 URL应同时保存为
  `source_url`。
- 同一 UUID 同时存在于官方 bundle 和页面详情 URL。Adapter 使用 UUID 作为
  `external_job_id`，不能以职位标题替代 ID。

## 5. 一个列表公开详情与完整 JD

唯一详情 smoke：
<https://app.mokahr.com/social-recruitment/high-flyer/140576#/job/2eb2e75d-29f3-47b5-bb10-39f12547d398>

无需登录即可读取完整职位内容，包括：

- 职位名称；
- 公司 `DeepSeek`；
- 职能类型“全栈开发/算法”；
- 工作地点“浙江·杭州市 北京市”；
- 招聘方向和岗位类别“实习/全职”；
- 团队使命；
- 线上核心服务、Agent 后端研发、数据仓库三个方向的岗位职责；
- 各方向岗位要求及加分项；
- 申请入口。

官方 bundle 的 `descriptionHtml` 已包含完整 JD。Adapter 应使用标准库 HTML
解析器转换为保留段落的纯文本，不调用模型，不自行改写内容。

## 6. 内容类型与字段

| 层级 | 本次可见内容 | 可用性 |
| --- | --- | --- |
| DeepSeek 官网 | 招聘文案和 `talent.deepseek.com` 链接 | 官方归属证据 |
| 官方静态 bundle | `total`、`jobs`、UUID、标题、类别、地点、完整 `descriptionHtml` | Adapter 主数据源 |
| Moka 详情网页 | 标题、公司、类别、地点、招聘类型、职责、要求、加分项、申请入口 | 包含完整 JD |
| API/XHR | 页面正常加载没有列表 API/XHR | Adapter 不需要也不猜测接口 |

入口和 bundle 的状态、`Content-Type` 与响应体大小已记录在 fixture 元数据中。

## 7. robots 与限制

- `talent.deepseek.com/robots.txt` 本次返回招聘列表网页，而非可解析的
  `User-agent` / `Allow` / `Disallow` 规则。这既不构成抓取许可，也没有给出
  可执行的 robots 禁止项。
- 为遵守请求预算，本轮未额外请求 `app.mokahr.com/robots.txt`。
- 两次 smoke 均未遇到登录页、验证码、401、403、429、短期签名参数或显式
  Cookie/Token 依赖。
- 未确认服务条款中的自动访问许可或频率上限。任何后续在线运行仍应使用明确
  User-Agent、域名并发 `1`、6--12 小时或更慢的频率。
- 一旦出现登录、验证码、会话 Cookie 依赖、Token、签名、403、429、访问控制
  页面或非预期内容类型，立即停止并禁用自动来源，不重试规避。

## 8. Fixture 可得性

- **入口 fixture：已保存。** 530 字节 HTML 用于验证 bundle URL 发现。
- **bundle fixture：已保存。** 从 32 条官方数据缩减为两条完整真实岗位，
  `metadata.json` 记录 bundle URL、内容类型、原体积和预期 UUID。
- **详情 fixture：非必需。** bundle 已包含完整 JD；可保留一条详情 smoke
  作为列表 UUID 与详情 URL 一致性的证据。
- 默认测试只读本地 fixture，不访问公网。

## 9. 可用/禁用结论

### 当前结论

**`deepseek-careers` 已注册为生产来源，执行仍受 `crawl_source` 审批保护。**

准入依据：

1. DeepSeek 官网直接确认招聘域名；
2. 首页公开引用同源静态 bundle；
3. bundle 内有结构化 `JSON.parse(...)` 数据集；
4. `total` 与 32 条岗位一致；
5. bundle 与详情共享 UUID，且 bundle 已含完整 JD。

### 实现验收

1. quote-aware 扫描器只解码 `JSON.parse` 字符串，不执行 JavaScript；
2. 官方 Moka `sourceUrl`、`total`、唯一 UUID、字段和 HTML 转文本测试通过；
3. live Adapter smoke 返回 32 条、32 个唯一 UUID，耗时 0.23 秒；
4. 真实 MCP stdio dry run 返回 `created=32`，耗时 2.26 秒；
5. bundle URL、数据标记或关键字段变化时整轮失败。

若后续契约变化触发会话依赖、签名或访问控制，则结论立即改为**禁用自动
Adapter，仅保留官方入口和手动 JD 导入**。

## 官方引用

- DeepSeek 官网：<https://www.deepseek.com/>
- DeepSeek 官方招聘入口：<https://talent.deepseek.com/>
- DeepSeek 官方静态 bundle：<https://talent.deepseek.com/static/main.264ac482b7.js>
- 本次 robots 检查（实际返回列表 fallback）：<https://talent.deepseek.com/robots.txt>
- 本次列表公开详情样本：<https://app.mokahr.com/social-recruitment/high-flyer/140576#/job/2eb2e75d-29f3-47b5-bb10-39f12547d398>
