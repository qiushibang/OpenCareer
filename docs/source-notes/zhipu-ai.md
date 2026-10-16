# 智谱 AI 官方招聘公开来源调查

- 调查日期：2026-08-05
- 来源 ID：`zhipu-ai-careers`
- 范围：仅检查智谱官网及官网公开链接的 Moka 招聘租户；未登录、未提交申请、未使用或复用 Cookie/Token、未处理验证码、未逆向签名、未枚举接口。
- **最新结论：启用 `zhipu-campus`，继续禁用社招。** 2026-08-06 使用 fresh browser context 复核后，校招 19 条全部提供完整 JD；社招 145 条中 3 条官方详情明确为“职位描述：暂无”，不满足完整性门。

## 2026-08-06 fresh browser 复核

- 旧调查中的重复 302 只证明裸 HTTP 不可用，不代表正常公开浏览器页面不可读。
- fresh Playwright context 不读取、保存或复用 Cookie/storage state，也不登录或处理验证码。
- 社招共 5 页，页数为 `30 + 30 + 30 + 30 + 25`，145 个唯一 UUID，跨页完整遍历约 13 秒。
- 校招共 1 页，19 个唯一 UUID；与社招 UUID overlap 为 0。
- 校招 19 条均含完整隐藏 JD；live Adapter 3.24 秒，真实 MCP dry run `created=19`、5.39 秒。
- 社招有 3 条卡片无描述，详情页同样明确显示“职位描述：暂无”。不得跳过这 3 条后宣称全量，因此不注册 `zhipu-social`。
- `zhipu-campus` 使用共享 Moka DOM transport 和智谱专用 metadata parser；元数据按“团队、用工类型、可选职类、可选地点”解析，不按标题猜测。

## 1. 官方招聘入口及归属证据

- 智谱官网“加入我们”页为 <https://www.zhipuai.cn/zh/joinus>。页面直接展示“校园招聘”“社会招聘”、工作地点和职位类别，页脚主体为“北京智谱华章科技股份有限公司”。
- 该官网页面公开引用的自身 Next.js 路由脚本为
  <https://www.zhipuai.cn/_next/static/chunks/app/(frontend)/%5Blocale%5D/(routes)/joinus/page-a66a1539a83d007f.js>。
- 路由脚本将社会招聘按钮固定指向
  <https://app.mokahr.com/social-recruitment/zphz/148983?locale=zh-CN#/>，
  将校园招聘按钮固定指向
  <https://app.mokahr.com/campus-recruitment/zphz/148984#/home>。
  脚本还公开了带第一页和分类条件的 Moka URL，例如
  <https://app.mokahr.com/campus-recruitment/zphz/148984#/jobs?keyword=&page=1&anchorName=jobsList&zhineng%5B0%5D=235377>。
- 因而可确认 `zphz` 下的 Moka 社招租户 `148983` 和校招租户 `148984` 是智谱官网指定的官方招聘入口，而不是第三方聚合来源。

## 2. 列表数据路径、API、SSR 与 HTML

### 智谱官网入口页

对 <https://www.zhipuai.cn/zh/joinus> 的一次低频普通 GET 返回：

- `HTTP 200`
- `Content-Type: text/html; charset=utf-8`
- `X-Powered-By: Next.js, Payload`
- 约 443 KB HTML

HTML 服务端已包含招聘分类、地点和分类简介，并包含 Next.js Flight 数据。因此该页属于可直接读取的 SSR/HTML 招聘入口页，但它只提供六个职位类别简介，不是逐岗位列表，也不包含岗位 ID、岗位详情 URL或完整 JD。

### Moka 职位列表

对官网公开的校招第一页 URL
<https://app.mokahr.com/campus-recruitment/zphz/148984#/jobs?keyword=&page=1&anchorName=jobsList&zhineng%5B0%5D=235377>
进行了一次低频、无登录、无 Cookie 请求。结果没有返回职位列表 body，而是重复：

```text
HTTP 302
Location: /campus-recruitment/zphz/148984
```

响应同时下发 `csrfCk`、`moka-apply` 和 `connect.sid` 等 Cookie。客户端在三次跟随后仍停留于相同重定向，随后按停止条件终止；未保存、复用或分析这些 Cookie。

当前证据只能确认 Moka 前端入口，不能确认：

- 列表是 API、XHR、SSR 还是客户端渲染数据；
- 任何公开 API URL、请求方法、参数或响应 schema；
- 无状态后端请求能否稳定读取列表。

不得根据 Moka 产品惯例猜测接口，也不得继续枚举网络路径。

## 3. 分页

- 官网静态脚本公开写有 `page=1` 和 `anchorName=jobsList`，说明前端路由表达页码和列表锚点。
- 本次没有获得列表响应中的 `total`、`pageSize`、`pageCount`、下一页链接或游标。
- 因此只能记录“前端 URL 使用页码参数”；**分页契约未确认**，不能据此实现分页抓取。

## 4. 稳定岗位 ID

- 当前官网入口页没有逐岗位 ID。
- 公开搜索索引曾显示该官方 Moka 校招租户下的 UUID 形态详情 URL：
  <https://app.mokahr.com/m/campus-recruitment/zphz/148984#/job/7a0c6875-9804-44c5-9244-1b1f0ddfaed2>。
- 该 URL 中的 UUID 是岗位 ID 候选，但本次未能从实际列表响应验证它与列表记录一致，也未做跨页或重复访问稳定性验证。

结论：**无可用于 Adapter 的已验证稳定岗位 ID。** 不得仅凭搜索索引样本确定 `external_job_id`。

## 5. 详情与完整 JD

- 搜索索引对上述官方 Moka URL展示了职位名“26届校招-后训练算法工程师”、发布日期、职位性质、部门、职位描述和职位要求，说明公开网页至少曾向搜索引擎暴露完整 JD。
- 但本次列表 smoke 未返回任何列表岗位，无法满足“详情必须由本次列表公开”的约束，因此没有执行详情 live smoke。
- 当前只能记录“完整 JD 可能公开可见”；不能把搜索摘要当作稳定详情 HTTP 契约或 fixture。

## 6. 内容类型与字段样本

### 已确认的官网 HTML 字段

| 层级 | 字段样本 |
| --- | --- |
| 招聘类型 | 校园招聘、社会招聘 |
| 工作地点 | 北京、深圳、上海、杭州、成都、吉隆坡 |
| 社招类别 | 算法/研发、销售、产品经理/项目经理 |
| 校招类别 | 算法、研发、运营 |
| 类别简介 | “持续改进训练框架和策略，提升模型训练效率等” |

### 仅由官方详情搜索索引观察、未 live 验证的字段

`职位名称`、`职位性质`、`职能类型`、`所属部门`、`发布日期`、`职位描述`、`职位要求`。

Moka 列表的响应内容类型和字段 schema 均未确认。

## 7. robots 与访问限制

- 本轮没有继续请求 <https://www.zhipuai.cn/robots.txt> 或
  <https://app.mokahr.com/robots.txt>。列表请求已经触发重复重定向并下发会话 Cookie，按用户要求立即收敛，不扩大探测。
- 因此 robots 规则为**未知**；未知不代表允许。
- 未遇到登录页、验证码、401、403 或 429，但 Moka 列表的重复 302 和会话 Cookie 依赖已足以阻止无状态 Adapter 准入。
- 未来若重新评估，仍禁止登录、Cookie/Token 复用、验证码处理、签名逆向、接口枚举和高频请求。

## 8. Fixture 可得性

- **官网入口 fixture：技术上可得，但不足以实现岗位 Adapter。** HTML 只能固定招聘类型、地点、类别和官方 Moka 链接。
- **列表 fixture：不可得。** 本次只得到重复 302 响应头，没有职位列表 body。
- **详情 fixture：本次未获取。** 因列表未公开出可验证详情 ID，按约束不单独请求搜索索引中的详情。

没有列表 fixture 就无法离线验证发现、分页、ID、字段映射、去重和下线保护，因此不具备生产 Adapter 的最低测试条件。

## 9. 可用/禁用结论与停止条件

### 当前状态

2026-08-05 的裸 HTTP 结论为：禁用单一 `zhipu-ai-careers` 来源。该结论已由
2026-08-06 的 fresh browser 复核细化为：

- 启用 `zhipu-campus`；
- 禁用 `zhipu-social`，原因是官方 145 条岗位中 3 条没有完整 JD。

可保留：

- 智谱官网招聘入口；
- 官网确认的 Moka 社招和校招跳转；
- 用户粘贴完整 JD 后的手动导入；
- 官方原始 URL 的来源追溯。

### 重新评估的最低条件

只有在正常公开访问、不依赖登录态或会话 Cookie 的前提下，同时确认以下事实，才可重新评估：

1. 一次列表请求可返回可冻结的岗位数据；
2. 分页参数和终止条件明确；
3. 列表提供稳定岗位 ID 和官方详情 URL；
4. 一条列表详情可返回完整 JD；
5. 可保存列表与详情 fixture 并完全离线测试。

### 立即停止条件

出现以下任一情况立即停止，不重试规避：

- 重复重定向或必须维持会话 Cookie；
- 登录、验证码、401、403、429 或访问控制页；
- Token、短期签名或非公开请求参数；
- 需要猜测/枚举 API；
- 列表或详情缺少稳定 ID、完整 JD；
- 内容类型或关键字段与 fixture 不一致。

## Live smoke 计数

- 智谱官网招聘入口：1 次普通 GET，用于确认归属、SSR/HTML 和公开 Moka 链接。
- Moka 列表：1 次逻辑请求；因相同 302 自重定向，在客户端限制内终止。
- 岗位详情：0 次；列表未提供可验证详情，故未请求。

## 官方 URL 汇总

- 智谱官网招聘页：<https://www.zhipuai.cn/zh/joinus>
- 智谱官网招聘路由脚本：<https://www.zhipuai.cn/_next/static/chunks/app/(frontend)/%5Blocale%5D/(routes)/joinus/page-a66a1539a83d007f.js>
- 智谱 Moka 社招入口：<https://app.mokahr.com/social-recruitment/zphz/148983?locale=zh-CN#/>
- 智谱 Moka 校招入口：<https://app.mokahr.com/campus-recruitment/zphz/148984#/home>
- 官网公开的校招分类第一页：<https://app.mokahr.com/campus-recruitment/zphz/148984#/jobs?keyword=&page=1&anchorName=jobsList&zhineng%5B0%5D=235377>
- 搜索索引观察到但未 live 请求的官方详情样本：<https://app.mokahr.com/m/campus-recruitment/zphz/148984#/job/7a0c6875-9804-44c5-9244-1b1f0ddfaed2>
