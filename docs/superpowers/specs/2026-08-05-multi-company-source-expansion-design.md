# 多公司全业务线来源扩张设计

## 目标

今晚从三来源 MVP 扩展为多公司岗位雷达。名单至少覆盖：

1. Kimi / 月之暗面
2. DeepSeek
3. 小米
4. 快手
5. 字节跳动
6. 美团
7. 滴滴出行
8. 腾讯
9. 阿里巴巴
10. 小红书
11. 智谱华章

“覆盖”分为两个独立验收层级：

- **调查覆盖**：确认官方入口、公开数据契约、分页、稳定 ID、完整 JD、
  访问限制和停止原因，并保存 source note。
- **生产覆盖**：完成 fixture、Adapter、离线测试、live smoke、MCP dry run
  和默认 registry 注册。

名单内公司今晚必须全部完成调查覆盖。生产覆盖只适用于满足公开、无需登录、
无需复用签名、可完整分页和 120 秒预算的来源。

## 产品范围定义

“所有业务线”不等于根据岗位标题猜测公司的内部组织。今晚采用可审计定义：

- 官网公开提供的招聘项目；
- 官网公开提供的一级职位类别；
- 官网公开提供的业务/部门筛选；
- 官网公开且互不重叠的校招、社招、实习范围。

只有官网能够稳定枚举、每轮能够完整抓取、且不同分片不会重复覆盖同一岗位时，
该范围才可注册为生产来源。

## 核心架构修正

当前 `source_slug` 同时承担公司身份和抓取来源身份。它适合“一家公司一个来源”，
但不能正确表达字节跳动的 Seed 校招、前沿技术校招、社招职类等多个来源。

Adapter contract 扩展为：

```python
class JobAdapter(Protocol):
    source_slug: str
    source_name: str
    company_slug: str
    company_name: str
    scope_key: str

    def fetch_jobs(self) -> list[JobSnapshot]: ...
```

- `company_slug`：稳定公司身份，例如 `bytedance`。
- `source_slug`：稳定抓取范围，例如 `bytedance-campus-seed-2027`。
- `scope_key`：官网范围标识，例如公开项目 ID 或一级分类 ID。
- `source_name`：面向用户的范围名称。

`crawl_sources` 在 schema v3 增加 `company_id`、`scope_key`、
`adapter_type` 和 `base_url`。Crawler Repository 使用 Adapter 元数据创建或查找
Company 与 CrawlSource，不再根据 source slug 伪造 Company。

## 迁移与兼容

schema v3 对现有来源做确定性回填：

| 现有 source slug | company slug | company name |
|---|---|---|
| `xiaomi-careers` | `xiaomi` | 小米 |
| `deepseek-careers` | `deepseek` | DeepSeek |
| `bytedance-seed-campus` | `bytedance` | 字节跳动 |

已持久化的小米岗位更新到 canonical Xiaomi Company，但保留原 job ID、source ID、
版本、事件和 crawl run。迁移不得删除或重建 2,522 条岗位。

现有 MCP source slug 保持可用，避免 GUI、历史对话和自动化引用失效。

## 分片与去重规则

每个生产来源必须是一个完整集合。分片只允许使用官网提供的稳定筛选 ID。

允许：

- 字节校招按互斥招聘项目 ID 分片；
- 字节社招按官网一级职位类别分片；
- 某公司明确分离的校招与社招入口；
- 官方 API 明确提供的互斥业务组。

禁止：

- 按关键词 `AI`、城市或标题临时分片后宣称全量；
- 同时启用会重复包含同一岗位的父范围与子范围；
- 只抓第一页；
- 将搜索引擎索引结果当成事实来源。

注册前必须比较 `(company_slug, external_job_id)`。若两个候选来源重叠，后注册
来源保持禁用，今晚不实现跨来源岗位合并。

## 来源准入流水线

每家公司按同一流程执行，单次初查预算 20–30 分钟：

1. 从公司官网确认招聘入口归属。
2. 检查 robots、HTML、JSON-LD 和内嵌状态。
3. 检查公开 Fetch/XHR、分页和详情请求。
4. 用不带 Cookie/Token 的受控请求验证公开契约。
5. 最后才使用无持久状态 Playwright。
6. 确认稳定 ID、完整 JD、全量计数和分页上限。
7. 写 source note。
8. 通过则保存缩减真实 fixture 并进入 TDD；不通过则记录禁用原因并切换下一家。

不得逆向或复用短期签名，不得使用用户浏览器 Cookie，不得登录、处理验证码或
绕过访问控制。

## 今晚来源队列

采用“先广后深”：

### 第一轮：全名单准入

按预计公开契约可用性排序：

1. 腾讯
2. 美团
3. 快手
4. 滴滴出行
5. Kimi / 月之暗面
6. 阿里巴巴
7. 小红书
8. 智谱华章复核

DeepSeek、小米和字节已有调查证据，不重复基础调查。

### 第二轮：通过即实现

每发现一个合格来源，立即完成：

```text
source note
-> reduced real fixture
-> failing parser test
-> minimal Adapter
-> pipeline test
-> live smoke
-> MCP dry run
-> registry
```

不能积累多个“只调查、以后再写”的合格来源。

### 第三轮：已有公司扩深

- DeepSeek：当前公开 bundle 32 条已经是当前完整数据集，重点做正式入库和
  幂等复验。
- 小米：当前公开 API 2,522 条已经覆盖官网公开职类和业务线，重点做公司身份迁移
  与重复抓取。
- 字节跳动：
  - 保留现有 Seed 大模型校招 85 条；
  - 优先增加前沿技术领域人才校招 136 条；
  - 调查其他公开校招项目 ID；
  - 调查社招一级职位类别分片；
  - 每个分片单独验证 120 秒预算；
  - 不注册 7,387 条校招总范围或 10,000 条社招总范围，除非页面公开支持足够大
    的稳定分页并通过完整 live smoke。

## 实现优先级

每家公司是否能在今晚进入生产 registry 由准入结果决定，不按品牌强行保证。

优先级评分：

1. 官方公开 JSON/API，无登录、无签名。
2. 列表直接包含完整 JD。
3. 稳定岗位 ID。
4. 可在 120 秒内完整抓取。
5. 覆盖范围大且可解释。
6. fixture 可稳定复现。

遇到受限来源立即停止，不能因为追求公司数量降低安全或完整性门槛。

## 测试策略

每个新 Adapter 必须包含：

- fixture provenance；
- envelope 和必填字段测试；
- 稳定 ID 与重复 ID 测试；
- 分页一致性和总数测试；
- host、redirect、content-type、body-size、timeout 测试；
- Adapter 到现有 pipeline 的 created/unchanged 测试；
- registry 和 MCP source-list 测试；
- 默认离线完整回归；
- 一次显式 live smoke；
- 一次真实 MCP dry run。

多来源架构额外测试：

- 一个 Company 可拥有多个 CrawlSource；
- 公司筛选可跨来源返回岗位；
- schema v2 -> v3 保留岗位、版本、事件和 runs；
- 重叠 source scope 在注册验收中失败；
- 单个来源失败不修改其他来源状态。

## 今晚成功标准

必须完成：

1. schema v3 与 Adapter metadata；
2. 11 家公司全部有最新 source note；
3. DeepSeek、小米、字节现有来源完成公司身份迁移和回归；
4. 所有通过准入的来源都实现，不留下已确认但未编码的来源；
5. 字节至少完成一个新增公开项目分片的准入，能否注册由 live 预算决定；
6. 完整测试与 `git diff --check` 通过。

目标而非硬保证：

- 新增 3–5 家生产公司；
- 字节新增 1–3 个互不重叠来源；
- 总岗位量显著高于现有 2,639 条。

无法承诺：

- 受登录、验证码、会话 Cookie 或签名保护的网站自动抓取；
- 一晚内覆盖各公司未公开的内部业务线；
- 一晚内证明 7 天稳定性。

## 停止条件

单个来源出现以下任一情况即禁用并切换：

- 登录、验证码、401、403、429 或访问控制；
- 必须复用 Cookie、Token 或短期签名；
- 列表总数无法确认；
- 分页不完整或超过 MCP 120 秒；
- 无稳定岗位 ID；
- 列表和详情都不能提供完整 JD；
- fixture 与 live 契约不一致；
- 解析失败可能触发批量 missing/offline。

## 非目标

- 新岗位列表前端。
- 自动投递。
- 简历与申请材料 P1。
- 第三方聚合岗位入库。
- 修改 OpenWorker 核心权限、TurnEngine、Provider Router 或 MCP Client。
- 为追求速度并发轰击招聘站点。
