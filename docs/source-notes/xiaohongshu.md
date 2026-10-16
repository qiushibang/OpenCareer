# 小红书官方社会招聘来源调查

- 调查日期：2026-08-06
- 官方入口：<https://job.xiaohongshu.com/social/position>
- source slug：`xiaohongshu-social-cn`
- canonical company slug：`xiaohongshu`
- 当前岗位：875 条、88 页
- 结论：fresh browser 多轮有界分页满足准入。

## 公开契约

官网页面调用：

```text
POST /websiterecruit/position/pageQueryPosition
```

列表响应直接包含稳定数字 `positionId`、标题、地点、发布日期、职类、完整
`duty` 和 `qualification`。请求包含页面动态生成的 `x-s/x-t` 签名；项目不复制、
生成或逆向签名，只驱动 fresh browser 中的官网分页控件。

## 完整性

- 固定 10 条/页，当前 88 页、875 条。
- 单轮因实时排序曾得到 874 个或 873 个唯一 ID，不能直接去重后返回。
- 最多三轮有界并集；总数和页数必须稳定。
- 同 ID 内容变化立即失败。
- 唯一 ID 并集必须精确等于官方 total，否则整轮失败。
- 110 秒硬停止，岗位总数上限 1,000。

## 安全

- 每轮 fresh Playwright browser/context。
- 不读取、保存或复用 Cookie、storage state、`x-s` 或 `x-t`。
- 不登录、不提交申请、不处理验证码。
- host、响应、分页、字段、完整 JD 或总数变化时整轮失败。

## 验收

- 探索性两轮并集：875/875，28.25 秒。
- live Adapter：875 条、875 个唯一 ID、875 条完整 JD，24.55 秒。
- 真实 MCP dry run：`created=875`、40.4 秒。
- 聚焦离线测试：7 passed。
