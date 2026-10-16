# 快手官方招聘公开来源调查

- 调查日期：2026-08-06
- 官方社招入口：<https://zhaopin.kuaishou.cn/recruit/#/official/social/>
- source slug：`kuaishou-social-cn`
- canonical company slug：`kuaishou`
- 当前国内社招：1,417 条，142 页
- 结论：使用无持久状态 Playwright 准入，Adapter 已注册；标准 HTTP transport 禁用。

## 数据契约

官方页面请求：

```text
GET /recruit/e/api/v1/open/positions/simple
  ?pageNum=<N>
  &pageSize=10
  &positionNatureCode=C001
  &recruitProject=socialr
  &workLocationCode=domestic
```

列表直接包含稳定数字 `id`、标题、完整 `description`、完整
`positionDemand`、职位类别代码、工作地点代码、工作经验代码和更新时间。

官方字典：

```text
GET /recruit/e/api/v1/dictionary/batch
  ?types=workLocation,positionCategory,positionExperience
```

字典明确标记地点 `parentCode=domestic/foreign`，Adapter 只接受 domestic 地点。

## HTTP 与浏览器边界

直接无状态 HTTP 请求返回 400 或 API `系统错误`，网关响应设置匿名 session Cookie。
项目不读取、保存或复用该 Cookie。

公开页面在全新 Playwright context 中可正常取得数据。Adapter：

- 不加载用户 Chrome profile；
- 不导出 storage state；
- 不读取 Cookie；
- 页面关闭后销毁 context；
- 只消费第一方页面公开取得的 JSON。

## 分页预算

- API 只接受 `pageSize=10`，20/50/100/500 均返回 400。
- 11 页完整 UI 分页实测 3.416 秒。
- 142 页预计约 44 秒，必须用全量 live smoke 重新确认。
- 每页总数、ID 唯一性和最终计数必须一致。

## 字段映射

- external ID：`id`
- title：`name`
- duties：`description`
- requirements：`positionDemand`
- location：`workLocationsCode` 通过官方字典映射
- category：`positionCategoryCode`
- experience：`workExperienceCode`
- recruitment type：experienced
- source URL：官方国内社招列表页；external ID 单独保存

官网详情使用页面内抽屉且 URL 不变化，不能伪造不存在的详情路径。

## Fixture

保存两条真实岗位、缩减字典和 metadata。默认测试不启动浏览器、不访问公网。

## 页漂移与完整性

官网实时排序会导致单轮 142 页出现重复 ID 和漏项。Adapter 最多执行四轮：

1. 每轮总数必须保持 1,417；
2. 相同 ID 内容必须一致；
3. ID 并集达到总数立即停止；
4. 110 秒或四轮后仍不完整则整轮失败。

官方社招聚合当前包含 1 条 `recruitProjectCode=epiboly` 外包子项目，其
`positionNatureCode=C001` 且由国内社会招聘页面返回。允许项目集合固定为
`socialr`、`epiboly`；其他值失败。

## 验收

- 全量 live：1,417 条、1,417 个唯一 ID，80.72 秒。
- 真实 MCP dry run：`created=1417`，62.18 秒。
- 默认离线测试不访问公网。
