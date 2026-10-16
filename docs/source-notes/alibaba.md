# 阿里巴巴官方招聘来源调查

- 调查日期：2026-08-06
- 集团入口：<https://talent.alibaba.com/?lang=zh>
- canonical company slug：`alibaba`
- 当前生产来源：`alibaba-token-foundry-social`
- 结论：集团官网公开 19 个业务招聘入口；Token Foundry 已通过准入并注册，
  其余入口必须逐个通过性能和重叠门后再注册。

## 官方业务入口

集团官网公开列出控股、淘天、淘宝闪购、飞猪、阿里国际、阿里云、
Token Foundry、千问办公、千问事业部、平头哥、高德、菜鸟、虎鲸文娱、盒马、
阿里健康、灵犀互娱、菜鸟驿站、亚博科技和橙狮体育共 19 个招聘站点。

其中 17 个站点的社会招聘页观察到同构 `/position/search` 契约。飞猪使用不同
SPA，尚未确认；橙狮当前返回 0 个岗位。

## 共享契约

同构站点由 first-party 页面先建立匿名 CSRF 上下文，随后：

```text
POST https://<business-host>/position/search
```

响应提供：

- 稳定数字 `id`；
- 标题、职类、部门、地点和发布时间；
- 完整 `description` 与 `requirement`；
- `totalCount`、`pageSize` 和 `currentPage`。

无状态裸 HTTP 返回 403，因此生产 Adapter 只使用 fresh Playwright context
建立页面自身的匿名上下文，不复制、导出、保存或复用 CSRF/Cookie。

## 当前规模

首轮页面统计：

| 业务 | 岗位数 |
|---|---:|
| 控股集团 | 580 |
| 淘天 | 607 |
| 淘宝闪购 | 235 |
| 阿里国际 | 163 |
| 阿里云 | 655 |
| Token Foundry | 61 |
| 千问办公 | 97 |
| 千问事业部 | 294 |
| 平头哥 | 192 |
| 高德 | 231 |
| 菜鸟 | 81 |
| 虎鲸文娱 | 144 |
| 盒马 | 357 |
| 阿里健康 | 59 |
| 灵犀互娱 | 123 |
| 菜鸟驿站 | 54 |
| 亚博科技 | 11 |
| 橙狮体育 | 0 |

一次尝试批量验证全部业务时，阿里云请求长时间无响应，已按停止条件终止。因此
不能把同构契约等同于全部来源已达到生产稳定性。

## Token Foundry 生产来源

- 官方入口：<https://careers-tongyi.alibaba.com/off-campus/position-list?lang=zh>
- source slug：`alibaba-token-foundry-social`
- scope：Token Foundry 社会招聘
- 当前 61 条，`pageSize=500` 单页完整返回。
- live Adapter：61 条、61 个唯一 ID、61 条完整 JD，5.25 秒。
- 真实 MCP dry run：`created=61`、6.24 秒。
- 离线聚焦测试：6 passed。

## 安全与停止条件

- 每轮 fresh browser/context，不保存 storage state。
- 不登录、不提交申请、不处理验证码。
- host、CSRF 页面请求、HTTP 状态、总数、分页、ID 或完整 JD 异常时整轮失败。
- 每个业务入口独立 source；正式注册前必须验证与其他阿里 source 的 ID 不重叠。
