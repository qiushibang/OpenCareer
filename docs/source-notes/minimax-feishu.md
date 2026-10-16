# MiniMax 与飞书招聘官方公开来源调查

- 调查日期：2026-08-05
- 范围：只访问 MiniMax 官方 `minimax.io`、飞书官方 `hire.feishu.cn`，以及被 MiniMax 官方页面直接链接的飞书招聘租户 `vrfi1sk8a0.jobs.feishu.cn`。所有请求均为低频、未登录的普通 GET；未提交表单、未使用 Cookie/Token、未处理验证码、未猜测或调用 XHR/API。
- 结论：**暂不可作为后端生产 Adapter。** 受控浏览器会话确认公开列表可显示岗位并发现对应 XHR，但该请求包含短期 `_signature` 参数；项目不会复用、生成、逆向或绕过该签名。飞书招聘产品站本身不是职位目录，不能作为独立岗位源。

## 候选来源排序

| 排名 | 候选来源 | 结论 | 原因 |
| --- | --- | --- | --- |
| 1 | MiniMax 官方 Career 页链接的飞书招聘租户 | 仅供人工浏览，暂不实现 | 已验证无需登录的列表 UI、稳定详情 URL ID 和完整详情；列表 XHR 依赖短期签名，不能作为后端稳定契约。 |
| 2 | 飞书招聘产品站 `hire.feishu.cn` | 不可用 | 是面向招聘方的产品介绍及试用入口，不提供任意公司的公开职位列表或 JD。 |

排名不等于可自动抓取资格。项目要求真实来源先具备可冻结的列表与详情 fixture，且所有请求契约必须来自正常公开访问，不能由猜测得出。

## 1. MiniMax 官方入口和授权关系

- MiniMax 官方 [Career 页面](https://www.minimax.io/careers) 明确将 “Social Recruitment” 链接到 <https://vrfi1sk8a0.jobs.feishu.cn/index/>，并将 Top Talent、校招和实习岗位链接到同一租户的 <https://vrfi1sk8a0.jobs.feishu.cn/379481/> 路径。这个官方反向链接是将该飞书租户认定为 MiniMax 招聘入口的依据，而不是以第三方聚合站作为来源。
- 因此，候选来源的边界应定义为 `minimax-careers`：`minimax.io/careers` 用于发现和授权，`vrfi1sk8a0.jobs.feishu.cn` 用于展示岗位。它不是“全量飞书招聘职位”的来源。

## 2. MiniMax 飞书招聘租户

### 入口、列表与分页

- 社招公开入口：<https://vrfi1sk8a0.jobs.feishu.cn/index/>。
- 本次未登录访问该页可显示“开启新的工作 (200)”、招聘项目、职位类别、城市和职位标签；页面提供 `1` 至 `20` 的分页控件。页面所示总数和页数支持“当前每页约 10 条”的判断，但这不是已确认的请求参数契约。
- MiniMax 官方 Career 页中的校招链接显式包含 `current=1&limit=10`，例如 <https://vrfi1sk8a0.jobs.feishu.cn/379481/?keywords=&category=&location=&project=7495675705720965415&type=&job_hot_flag=&current=1&limit=10&functionCategory=&tag=>。这证明该站点公开 URL 使用过页码和页大小参数，但**不能据此假定**社招 `/index/` 使用同一参数或可直接构造下一页 URL。
- 列表卡片链接的职位路径形如 <https://vrfi1sk8a0.jobs.feishu.cn/index/position/7665691872693618953/detail>。数字 `7665691872693618953` 是当前最好的 `external_job_id` 候选；实现前必须至少验证它在列表、详情和翻页后仍一致，不能以职位标题作为身份。

### HTML、SSR 和 API 观察

| 层级 | 本次观察 | 结论 |
| --- | --- | --- |
| MiniMax Career | 官方 HTML 页面提供招聘说明和飞书招聘租户链接。 | 可作为官方入口与来源归属证据，不包含可用的职位明细。 |
| 社招列表 `/index/` | 一次未登录 GET 返回 `200 text/html; charset=utf-8`，约 127 KB；原始 body 不含已观察的职位 ID、职位名称或“开启新的工作”文本，但加载多份飞书招聘 JavaScript bundle。正常页面渲染后可见 200 条和分页。 | **CSR 列表**，不能直接将原始 HTML 作为列表解析 fixture。 |
| 职位详情 | 一次未登录 GET 返回 `200 text/html; charset=utf-8`，约 127 KB；原始 body 已含职位标题、“职位描述”和“职位要求”。[样本详情](https://vrfi1sk8a0.jobs.feishu.cn/index/position/7665691872693618953/detail) 可直接读到职责和要求全文。 | 可冻结为详情 HTML fixture；这足以证明完整 JD 对公开访问者可得。 |
| XHR/API | 受控浏览器会话观察到 `POST /api/v1/search/job/posts` 和筛选接口；列表请求包含 `_signature` 参数。 | 已确认请求存在，但该签名的生命周期和生成机制未获公开 API 契约支持。不得直接调用、复用、逆向或生成签名。 |

### 访问限制和停止条件

- 本次上述公开 GET 未遇到登录重定向、401、403、429 或 CAPTCHA 挑战；详情页仅显示“投递”入口，未进行点击或投递。
- 列表 HTML 引用了 `verify.snssdk.com/static/pc_slide.js`。本次没有向该地址发请求，也没有出现验证挑战；该脚本的存在不能被解释为可绕过或可自动处理验证。
- 租户的 [robots.txt](https://vrfi1sk8a0.jobs.feishu.cn/robots.txt) 本次返回 `404 Not Found`。这既不是抓取授权，也不改变项目的低频与公开访问边界。
- 未发现面向该租户的公开 API 文档、明确频率限制或稳定性承诺。运行时必须保持域名并发 `1`、低频（6--12 小时或更慢），并在 401、403、429、登录页、验证码、列表结构变化、缺少候选 ID 或详情关键字段时立即将本轮标记为 `AccessRestricted` 或 `degraded`，不重试规避。

### Fixture 可得性和准入条件

- **详情 fixture：可得。** 公开详情 HTML 含完整 JD，可在后续实现时低频保存一条或少量样本，并记录 URL、获取日期、内容类型和预期 ID/字段。测试只能读取该本地快照。
- **列表 fixture：当前不可得。** 原始列表响应是应用外壳，不能支撑离线 `discover()` 解析。不能把搜索工具的渲染结果当作可复现的 HTTP fixture。
- 受控浏览器会话已确认列表卡片链接的岗位 ID `7670433637955602751` 可直接打开同 ID 的详情 URL，且无需登录即可展示“增长数据分析师”的详情标题。
- 列表 XHR 使用短期 `_signature`。这已满足项目的停止条件：即使浏览器正常渲染，后端也不能把该参数当作稳定、无状态的公开 API 契约。
- 因此不保存列表 API fixture、不编写 `MiniMaxAdapter`；保留官网和租户页面作为人工浏览入口，用户可粘贴完整 JD 走手动导入。

## 3. 飞书招聘产品站

- 飞书官方 [飞书招聘产品页](https://hire.feishu.cn/index) 将自身描述为服务招聘方的招聘产品，提供“申请试用”和“购买咨询”，没有公开职位目录、职位详情或跨公司岗位搜索。
- 飞书官方 [HR 入门手册](https://www.feishu.cn/hc/zh-CN/articles/381040174542-%E9%A3%9E%E4%B9%A6%E6%8B%9B%E8%81%98-hr-%E5%85%A5%E9%97%A8%E6%89%8B%E5%86%8C) 说明该产品供购买后配置席位和权限的企业 HR 使用。这说明它是 ATS 产品，而非可抓取的公共职位总库。
- `jobs.feishu.cn` 是按招聘方租户划分的公开门户承载域名。只确认了 MiniMax 这个被其官网链接的租户；尚未比较第二个获官方授权的租户，因此不能抽象或命名为通用 `FeishuJobsAdapter`。

结论：飞书招聘产品站 **不可用作独立职位来源**。只有某公司以其官网明确链接到的、可无登录读取的具体租户，才能被单独评估；每个租户都需要独立确认列表、分页、详情、ID 和 fixture。

## 降级决策

1. 当前不注册 MiniMax 或飞书招聘生产 Adapter，不新增网络代码。
2. MiniMax 当前不再进行接口探测。只有该租户发布无签名的公开 API，或官方明确提供机器可读招聘数据时，才重新评估。
3. 保留官方 Career 页和详情 URL 作为用户跳转来源；用户粘贴完整 JD 仍走既有手动导入链路。

## 官方引用

- [MiniMax Career](https://www.minimax.io/careers)
- [MiniMax 飞书招聘社招列表](https://vrfi1sk8a0.jobs.feishu.cn/index/)
- [MiniMax 飞书招聘详情样本](https://vrfi1sk8a0.jobs.feishu.cn/index/position/7665691872693618953/detail)
- [MiniMax 飞书招聘校招入口（官方 Career 页所链接）](https://vrfi1sk8a0.jobs.feishu.cn/379481/?keywords=&category=&location=&project=7495675705720965415&type=&job_hot_flag=&current=1&limit=10&functionCategory=&tag=)
- [飞书招聘产品页](https://hire.feishu.cn/index)
- [飞书招聘 HR 入门手册](https://www.feishu.cn/hc/zh-CN/articles/381040174542-%E9%A3%9E%E4%B9%A6%E6%8B%9B%E8%81%98-hr-%E5%85%A5%E9%97%A8%E6%89%8B%E5%86%8C)
