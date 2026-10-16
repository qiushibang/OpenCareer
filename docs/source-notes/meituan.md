# 美团官方招聘公开来源调查

- 调查日期：2026-08-06
- canonical company slug：`meituan`
- 官方入口：<https://hr.meituan.com/web/social>
- source slug：`meituan-social-cn`
- 结论：公开 API 满足国内社招全业务线准入，Adapter 已注册。

## 列表 API

```text
POST https://hr.meituan.com/api/official/job/getJobList
Content-Type: application/json
```

请求：

```json
{
  "page": {"pageNo": 1, "pageSize": 100},
  "jobShareType": "1",
  "keywords": "",
  "cityList": [],
  "department": [],
  "jfJgList": [],
  "jobType": [{"code": "3", "subCode": []}],
  "typeCode": [],
  "specialCode": []
}
```

页面请求包含 `u_query_id`、`r_query_id` 追踪字段；删除后公开请求仍返回成功，
因此 Adapter 不生成或复用这些字段。

当前响应：

- `status=1`
- `data.page.totalCount=2264`
- `data.page.totalPage=23`
- `pageSize=100`
- 列表直接包含完整 `jobDuty` 和 `jobRequirement`

主要字段：

- `jobUnionId`：稳定岗位 ID
- `name`
- `jobType`
- `jobFamily` / `jobFamilyGroup`
- `cityList`
- `department`
- `departmentIntro`
- `jobDuty`
- `jobRequirement`
- `precedence`
- `highLight`
- `refreshTime`

## 详情 URL

```text
https://hr.meituan.com/web/position/detail
  ?jobUnionId=<jobUnionId>
  &highlightType=social
```

详情页面无需登录，可直接读取完整 JD。列表 API 已含完整内容，Adapter 不需要逐岗
请求详情。

## 国内范围

社招列表包含部分海外岗位，项目明确排除海外岗位。官网提供海外城市树：

```text
POST https://hr.meituan.com/api/official/en/city/search
Content-Type: application/json
{}
```

Adapter 每轮读取该官方枚举并构建海外城市集合。岗位全部地点都属于海外集合时
排除；至少包含一个非海外地点时保留。

国内热门城市接口：

```text
POST https://hr.meituan.com/api/official/city/search
{"hotCity": true, "keyword": ""}
```

## 业务线覆盖

列表的 `department`、`jobFamily`、`jobFamilyGroup` 已覆盖美团公开社招业务和职类。
单一来源抓取全部社招后做海外过滤，不按关键词或部门分片。

## 安全

- 无登录、Cookie、Authorization、Token 或签名。
- API 返回 `application/json`。
- 只允许 `hr.meituan.com/api/official/`。
- 单请求 15 秒，列表上限 10 MB，城市枚举上限 5 MB。
- 状态、分页、总数、稳定 ID、完整职责/要求异常时整轮失败。

## Fixture

保存缩减真实 listing、海外城市枚举和 metadata。fixture 不包含用户信息或会话状态。

## 验收

- 原始社招：2,264 条。
- 官方海外城市树过滤后国内岗位：2,090 条。
- 2,090 个唯一 `jobUnionId`。
- live Adapter：12.45 秒。
- 真实 MCP dry run：`created=2090`，11.40 秒。
- 默认测试完全离线。
