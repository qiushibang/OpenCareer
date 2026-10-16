# 滴滴出行官方招聘公开来源调查

- 调查日期：2026-08-06
- 官方入口：<https://talent.didiglobal.com/m?jobType=1>
- source slug：`didi-social-cn`
- canonical company slug：`didi`
- 当前社招：358 条、23 页
- 结论：公开 HTTP API 满足准入，Adapter 已注册。

## 列表

```text
GET https://talent.didiglobal.com/recruit-portal-service/api/job/front/list
  ?jobType=1&page=<N>&recruitType=1&size=10
Referer: https://talent.didiglobal.com/m?jobType=1
```

固定官方 Referer 后无需 Cookie、Token 或签名。响应实际每页 16 条，提供：
`jdId`、`jdNo`、标题、部门、地点、更新时间和 channel ID。

## 详情

```text
GET /recruit-portal-service/api/job/front/view/<jdId>
Referer: https://talent.didiglobal.com/social/p/<jdId>
```

详情提供完整 `jobDesc`、`qualification`、地点、部门、职类和招聘人数。
官方详情 URL 即 `/social/p/<jdId>`。

## 范围

滴滴官网将社会招聘、校园招聘、实习生招聘和海外招聘分为独立入口。本来源只抓取
`jobType=1/recruitType=1` 中国社会招聘，不访问海外站。

## 性能

- 20 个详情串行请求：5.696 秒。
- 358 个详情预计约 102 秒。
- 列表 23 页；完整 live 必须低于 MCP 120 秒。

## 安全

- 只允许 `talent.didiglobal.com/recruit-portal-service/api/`。
- 固定官方 Referer，不保存会话。
- 15 秒超时，列表/详情 2 MB。
- meta code、总数、分页、详情 ID、完整 JD 异常时整轮失败。

## 验收

- live Adapter：358 条、358 个唯一 ID、95.06 秒。
- 真实 MCP dry run：`created=358`、103.94 秒。
- 距 120 秒上限约 16 秒；总数明显增长时需重新评估职类分片。
