# 美团国内社招 Adapter 设计

## 目标

抓取美团官方中国社招全部公开业务线，使用官方海外城市枚举排除纯海外岗位。

## 架构

`crawler/meituan.py` 包含：

- `MeituanListingPage`
- `parse_meituan_listing`
- `parse_overseas_city_names`
- `MeituanSocialAdapter`
- 官方 POST transport

Adapter 先读取海外城市枚举，再串行读取 100 条/页的全部岗位。列表已包含完整 JD，
无需详情请求。现有 CrawlerService 负责版本和状态。

## 映射

- external ID：`jobUnionId`
- title：`name`
- location：`cityList[*].name`
- recruitment type：`experienced`
- source URL：官方 detail route
- description：部门、职类、职责、要求、优先条件、亮点、更新时间

## 过滤

只排除“所有地点都在官方海外城市枚举中”的岗位。没有地点、地点结构异常或海外
枚举获取失败时整轮失败，不能猜测。

## 失败保护

- status 必须为 1；
- pageNo/pageSize/totalPage/totalCount 跨页一致；
- jobUnionId 唯一且非空；
- jobDuty/jobRequirement 非空；
- 最终列表数等于 totalCount；
- 过滤后可为较小集合，但原始完整性必须先验证。

## 验收

- fixture parser 与过滤测试；
- 23 页 live smoke；
- 唯一 ID；
- MCP dry run；
- schema v3 canonical Company；
- 完整回归。
