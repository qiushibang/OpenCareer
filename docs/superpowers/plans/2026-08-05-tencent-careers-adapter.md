# 腾讯社招事业群 Adapter 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 使用腾讯官方公开 API 实现按事业群分片、完整 JD、可在 MCP 时限内运行的生产 Adapter。

**架构：** 纯 parser 处理 fixture，注入式 fetcher 驱动分页和详情；生产 transport 仅访问腾讯官方 JSON API。现有 pipeline 负责数据库状态。

**技术栈：** Python 3.12 标准库、pytest、SQLite schema v3、FastMCP。

---

## 文件

- 新增：`extensions/career_mcp/crawler/tencent.py`
- 新增：`extensions/career_mcp/tests/test_tencent_api.py`
- 新增：`extensions/career_mcp/tests/fixtures/tencent-careers/`
- 修改：`extensions/career_mcp/crawler/adapters.py`
- 修改：`extensions/career_mcp/tests/test_stage3_tools.py`
- 修改：`docs/source-notes/tencent.md`
- 修改：`docs/11_DEVELOPMENT_LOG.md`
- 修改：`docs/12_TONIGHT_PROGRESS.md`

## Task 1：Fixture 与 parser

- [ ] 保存一页缩减 listing、两个完整 detail、字典和 metadata。
- [ ] 写导入不存在模块的红灯测试。
- [ ] 实现 `TencentApiError`、`TencentScope`、`TencentListingPage`。
- [ ] 实现列表 parser：Code、Count、Posts、PostId、标题和 scope BG。
- [ ] 实现详情 parser：完整职责、要求、地点、事业群、职类、产品和详情 URL。
- [ ] 添加错误 envelope、空要求、ID 不一致、BG 逃逸和重复 ID 测试。

## Task 2：分页与详情

- [ ] 写注入 fetcher 测试，要求列表页按 1..N 串行、详情按稳定 ID 串行。
- [ ] 实现 `TencentCareersAdapter`，统一 observed timestamp。
- [ ] 验证 pageSize=100、总数固定、最终详情数等于 Count。
- [ ] 添加跨页重复、总数变化、空中间页和详情失败测试。

## Task 3：生产 transport

- [ ] 写 URL builder 测试，精确验证 BG、父/子职类和分页参数。
- [ ] 实现 allowlist、timeout、size、content type、redirect 和 JSON 检查。
- [ ] 不附带 Cookie、Token 或签名。
- [ ] 默认测试 monkeypatch `urlopen`，禁止访问公网。

## Task 4：Pipeline 与 registry

- [ ] 使用 fixture scope 驱动 `created=2`、第二次 `unchanged=2`。
- [ ] 验证 canonical Company 为 `tencent`。
- [ ] 对每个候选事业群执行 live Adapter smoke 和 overlap 验收。
- [ ] 只注册低于 120 秒且完整的事业群。
- [ ] CSIG/IEG 超时则生成互斥职类 scope，不注册父 scope。

## Task 5：MCP 与文档

- [ ] 对注册来源执行真实 stdio MCP dry run。
- [ ] 更新 `list_sources` 预期。
- [ ] 运行完整 Career/backend 和 GUI 回归。
- [ ] 记录每个事业群岗位数、耗时、启用/禁用结论。
- [ ] `git diff --check` 后提交。

## 自检

- 列表缺失 Requirement，因此所有岗位必须读取详情。
- 全量父源与事业群/职类子源不可并存。
- 11 条无公开 BG 岗位不宣称覆盖。
- 未使用第三方聚合、登录、验证码、Cookie 或签名。
