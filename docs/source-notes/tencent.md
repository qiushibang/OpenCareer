# 腾讯官方招聘公开来源调查

- 调查日期：2026-08-05
- 公司：腾讯
- canonical company slug：`tencent`
- 官方社招入口：<https://careers.tencent.com/zh-cn/search.html>
- 官方校招入口：<https://join.qq.com/>
- 本轮实现候选：腾讯中国社招，按官方事业群分片
- 结论：公开 API 满足准入；23 个互斥事业群/职类来源已通过 live 验收并注册。

## 官方归属

腾讯招聘官网 `careers.tencent.com` 提供社会招聘，腾讯官方校招页面
`join.qq.com` 提供应届生、实习生和人才专项。本轮先实现中国社招；校招入口作为
后续独立来源调查，不能与社招混成一个不完整集合。

## 列表契约

官网公开调用：

```text
GET https://careers.tencent.com/tencentcareer/api/post/Query
  ?countryId=
  &cityId=
  &bgIds=<事业群 Code>
  &productId=
  &categoryId=
  &parentCategoryId=
  &attrId=
  &keyword=
  &pageIndex=<从 1 开始>
  &pageSize=100
  &language=zh-cn
  &area=cn
```

- 无登录、Cookie、Token 或签名。
- `pageSize=100` 已验证生效。
- 响应 `Code=200`，`Data.Count` 为总数，`Data.Posts` 为岗位列表。
- 全部未筛选中国社招当前为 2,308 条。
- 列表提供 `PostId`、标题、地点、事业群、产品、职类、职责、更新时间和工作年限。
- 列表不提供完整 `Requirement`，不能仅保存列表数据。

## 详情契约

```text
GET https://careers.tencent.com/tencentcareer/api/post/ByPostId
  ?postId=<PostId>
  &language=zh-cn
```

详情无需登录，返回完整：

- `RecruitPostName`
- `Responsibility`
- `Requirement`
- `LocationName`
- `BGName`
- `ProductName`
- `CategoryName`
- `RequireWorkYearsName`
- `LastUpdateTime`
- `DepartmentIntroduction`

详情页面：

```text
https://careers.tencent.com/jobdesc.html?postId=<PostId>
```

`PostId` 同时存在于列表、详情 API 和详情 URL，是 external job ID。

## 官方筛选与事业群计数

筛选字典：

```text
GET /tencentcareer/api/data/GetMultiDictionary
  ?language=zh-cn
  &type=Nationality,WorkPlace,OuterType,BG,PostAttr
```

当前事业群：

| BG Code | 事业群 | 岗位数 |
|---|---|---:|
| `953` | CDG 企业发展事业群 | 86 |
| `29294` | CSIG 云与智慧产业事业群 | 407 |
| `956` | IEG 互动娱乐事业群 | 1,217 |
| `29292` | PCG 平台与内容事业群 | 58 |
| `14129` | WXG 微信事业群 | 258 |
| `958` | TEG 技术工程事业群 | 225 |
| `78` | S1 职能系统－职能线 | 10 |
| `2233` | S2 职能系统－财经线 | 17 |
| `2234` | S3 职能系统－HR 与管理线 | 19 |

九个事业群合计 2,297 条；未筛选总数为 2,308 条，另有 11 条未归属公开 BG。
父级全量与 BG 分片不能同时注册。

## 大事业群职类分片

CSIG 和 IEG 如事业群级完整抓取超过 120 秒，可使用官网一级/二级职类继续分片。

CSIG 一级职类主要计数：技术 139、产品 162、设计 2、销售/服务/支持 69、
营销/公关 8、战略/投资 11、法律/公共策略 1、行政支持 11。

IEG 一级职类主要计数：技术 306、产品 456、内容 5、设计 307、
销售/服务/支持 24、营销/公关 85、战略/投资 23、行政支持 2。

IEG 二级大类可继续拆分：

- 技术：技术研发 219、质量 6、技术运营 4、安全 5、AI/算法/大数据 72。
- 产品：产品 27、游戏产品 387、项目 42。
- 设计：设计 55、游戏美术 252。

只有事业群/职类 ID 组合互斥并通过 overlap 验收后才可注册。

## 请求预算

- 20 个详情串行请求实测 5.623 秒，约 0.28 秒/岗位。
- 事业群不超过约 300 条时预计可在 120 秒内完成。
- CSIG 407 和 IEG 1,217 需要实际 live smoke；超时则使用官方职类分片。
- 不提高域名并发来规避 MCP 超时。

## robots 与限制

`/robots.txt` 本次返回 302 fallback HTML，而不是可解析 robots 指令。页面和 API
未要求登录，也未出现 401、403、429、验证码或签名。静态 CDN 脚本的直接 curl
返回 403，因此不继续请求或绕过；Adapter 不依赖该脚本。

## Fixture 计划

保存：

```text
extensions/career_mcp/tests/fixtures/tencent-careers/
├── listing_page_1.json
├── detail_1.json
├── detail_2.json
├── dictionaries.json
└── metadata.json
```

fixture 不保存 Cookie、Token、签名或个人信息。

## 启用策略

1. CDG、CSIG、PCG、WXG、TEG、S1、S2、S3 使用事业群来源。
2. IEG 使用 15 个互斥职类来源；IEG 父来源不注册。
3. 23 个来源当前合计 2,288 条、2,288 个唯一 ID，overlap 为 0。
4. 11 条无公开 BG 和 9 条 IEG 无公开职类岗位本轮不宣称覆盖。
5. 校招 `join.qq.com` 作为独立来源后续调查。

## Live 与 MCP 验收

- CDG：86 条，live 22.56 秒，MCP dry run 24.04 秒。
- PCG：58 条，15.53 秒。
- WXG：258 条，76.42 秒。
- TEG：225 条，58.83 秒。
- S1/S2/S3：10/17/19 条，均低于 6 秒。
- CSIG：407 条，使用 `pageSize=500` 后 106.92 秒。
- IEG 最大分片“游戏产品”：387 条，live 101.07 秒，MCP dry run 105.72 秒。
- IEG 其他 14 个分片均低于 66 秒。
- 全部生产 scope 的列表复验：2,288 条、2,288 个唯一 ID、跨 scope overlap 0。

默认测试继续只读本地 fixture，不访问腾讯官网。
