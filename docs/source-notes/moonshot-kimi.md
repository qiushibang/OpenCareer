# Kimi / 月之暗面官方招聘公开来源调查

- 调查日期：2026-08-06
- 官方公司入口：<https://www.moonshot.cn/about/>
- 官方招聘入口：<https://careers.kimi.com/>
- Moka 社招入口：<https://app.mokahr.com/apply/moonshot/148506#/jobs>
- source slug：`moonshot-social`
- canonical company slug：`moonshot`
- 当前社招：91 条、4 页
- 结论：fresh browser context 可完整读取公开页面，准入 DOM Adapter。

## 归属

月之暗面官网导航中的“加入我们”直接指向 `careers.kimi.com`。该页面的
`Join us` 链接固定指向 Moka 租户 `moonshot/148506`，因此来源归属由公司官网
直接确认，不依赖第三方招聘聚合站。

## 数据路径

公开 Moka 页面会调用：

```text
POST https://app.mokahr.com/api/outer/ats-apply/website/jobs/v2
```

请求只包含公开的 `orgId=moonshot`、`siteId=148506`、分页和筛选字段，但响应
`data` 与 `necromancer` 是加密字符串。项目不逆向、复制或实现其解密协议。

浏览器正常渲染后的岗位卡片已经包含：

- UUID 详情链接；
- 标题和发布日期；
- 招聘类型、职类和可选地点；
- 完整岗位描述与要求。

因此 Adapter 仅从公开页面渲染后的 DOM 读取数据。

## 分页与完整性

- 页面固定显示 30 条/页。
- 分页控件公开 `data-page`，当前为 4 页。
- 实测页数为 `30 + 30 + 30 + 1`，合计 91 个唯一 UUID。
- 四页 fresh-context live smoke 为 6.63 秒。
- 同一 UUID 在本轮内重复出现且内容不一致时整轮失败。
- 页码不连续、非末页不足 30 条、末页为空或总数超过 600 条时整轮失败。

## 范围

该租户是月之暗面官方社会招聘入口，当前岗位均为全职，覆盖算法、技术、产品、
设计、市场、运营、职能和管理类。部分岗位未声明地点；两个岗位同时包含美国与
中国地点，没有仅限海外地点的岗位。本来源保留地点未知和中外混合岗位，不把标题
或职责中的“海外”推断为海外工作地点。

## 安全

- 每轮启动 fresh Playwright browser context。
- 不读取、导出、保存或复用 Cookie/storage state。
- 不调用响应解密逻辑，不登录、不提交申请、不处理验证码。
- 只允许 `app.mokahr.com/apply/moonshot/148506`。
- 页面、分页、UUID、完整 JD 或字段契约变化时整轮失败。

## Fixture

离线 fixture 保存两个公开岗位卡片的缩减结构：

- 一个包含职类和中国地点；
- 一个职类存在但地点未声明。

fixture 不包含 Cookie、Token、签名、申请人信息或加密响应。

## 验收

- live Adapter：91 条、91 个唯一 UUID、91 条完整 JD，8.69 秒。
- 53 条岗位声明地点，其余保持未知；没有仅限海外地点的岗位。
- 真实 MCP dry run：`created=91`、11.6 秒。
- 聚焦离线测试：9 passed。
