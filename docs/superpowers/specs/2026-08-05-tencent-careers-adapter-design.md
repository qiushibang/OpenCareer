# 腾讯社招事业群 Adapter 设计

## 目标

使用腾讯官方公开 JSON API 抓取中国社招岗位。以官网事业群作为互斥来源范围，
所有来源归属于 canonical Company `tencent`。

## 组件

`crawler/tencent.py` 提供：

- `TencentScope`：source slug/name、BG code/name、可选父/子职类 code。
- `TencentListingPage`：总数和岗位列表。
- `parse_tencent_listing`：列表 envelope 与分页解析。
- `parse_tencent_detail`：完整 JD 映射。
- `TencentCareersAdapter`：串行列表分页和详情请求。
- `fetch_tencent_json`：受限官方 GET transport。

## 数据流

1. 请求事业群第一页，`pageSize=100`。
2. 验证 `Code=200`、总数、页数和列表 IDs。
3. 串行读取剩余列表页。
4. 对每个唯一 `PostId` 串行读取详情。
5. 验证详情 `PostId` 与列表一致且事业群未逃逸。
6. 生成 `JobSnapshot`。
7. 现有 CrawlerService 负责持久化和状态转换。

## 字段映射

- external ID：`PostId`
- title：`RecruitPostName`
- location：`LocationName`
- recruitment type：`experienced`
- source URL：HTTPS canonical detail URL
- description：
  - 事业群
  - 产品
  - 职类
  - 工作年限
  - 岗位职责
  - 岗位要求
  - 部门介绍（非空时）
  - 更新时间

`RecruitPostId` 作为展示字段，不替代详情路由使用的 `PostId`。

## 分片

第一层使用 BG code。CSIG/IEG 如超时，使用同一 Adapter 的
`parent_category_id` / `category_id` 参数形成互斥子来源。

同一 Company 下所有候选来源必须调用 `validate_source_overlap`。父范围和子范围
不能同时注册。

## 安全与失败

- 只允许 `https://careers.tencent.com/tencentcareer/api/`。
- 15 秒单请求超时。
- 列表响应上限 5 MB；详情上限 2 MB。
- JSON content type、HTTP 200、API Code 200。
- 401/403/429/5xx、重定向 host、登录或验证码立即失败。
- 不发送 Cookie、Token、Referer 或浏览器状态。
- 总数、分页、岗位 ID、详情 ID、事业群变化时整轮失败。
- 不返回部分数据，避免误触发 missing/offline。

## 测试

- 缩减真实 listing/detail fixture。
- envelope、total、分页、重复 ID。
- 详情必填字段和 ID 一致性。
- scope query 参数。
- 跨页重复。
- Adapter 到 pipeline。
- SourceDescriptor canonical Company。
- live 事业群 smoke。
- MCP dry run。

## 注册

较小事业群逐个 live 验收后注册。CSIG/IEG 必须单独通过 120 秒预算；失败时改用
职类子分片，不降低完整 JD 标准。
