# 04 — 国内 AI/互联网岗位采集规范

> 本规范继续作为抓取器的质量和合规约束。当前来源、scope、数量与禁用原因以
> `13_SOURCE_COVERAGE_MATRIX.md` 和 `source-notes/` 为准；不要从历史计划推断
> 线上可用性。

## 1. 目标

建立可维护、可测试、官方来源优先的 Job Source Adapter 系统。重点不是“爬得最多”，而是稳定获得完整 JD，并准确判断新增、变化和下线。

## 2. 数据源优先级

1. 官方公开 API。
2. 官方前端公开 XHR/JSON。
3. Sitemap、RSS、JSON-LD、内嵌 JSON。
4. 静态 HTML。
5. Playwright 渲染或监听网络。
6. 用户手动输入。

如果访问需要登录、验证码、私有 Token、签名绕过或高风险逆向，则不实现自动抓取，保留手动 JD。

## 3. Adapter 契约

建议接口：

```python
class JobSourceAdapter(Protocol):
    source_id: str

    async def health_check(self) -> SourceHealth: ...
    async def discover(self) -> list[JobPointer]: ...
    async def fetch_detail(self, pointer: JobPointer) -> RawJobDocument: ...
    def parse(self, document: RawJobDocument) -> ParsedJob: ...
```

可根据某些 API 一次返回完整职位，将 discover 和 detail 合并，但上层 Orchestrator 接口保持统一。

## 4. 分层对象

### JobPointer

- `external_job_id`
- `detail_url`
- `title_hint`
- `location_hint`
- `raw_metadata`

### RawJobDocument

- 请求 URL。
- HTTP 状态。
- 获取时间。
- 内容类型。
- 原始 body 或快照路径。
- 请求/响应必要元数据。

### ParsedJob

接近来源字段，不做跨来源枚举统一。

### NormalizedJob

业务统一字段，可持久化。

## 5. 网站调查标准步骤

每接一个公司必须先写 `source-notes/<source_id>.md`，记录：

1. 官方招聘入口。
2. 是否存在公开 API/XHR。
3. 分页方式。
4. 详情获取方式。
5. 稳定岗位 ID。
6. 是否需要 JavaScript。
7. 频率限制和 robots/使用条款观察。
8. 选择的 Adapter 类型。
9. 失败降级方式。

调查顺序：

- 查看 HTML 源码。
- 查看 JSON-LD/内嵌状态。
- 查看 Network Fetch/XHR。
- 用 curl/httpx 复现公开请求。
- 最后才使用 Playwright。

## 6. 首批实现顺序

### 1. 百度

目标：验证公开列表、详情、分页和 AI 关键词。必须保存真实 fixture，在线调查与测试解析分开。

### 2. 小米

目标：验证大量职位、分页、城市与分类。

### 3. MiniMax / 飞书招聘

目标：优先抽象通用 `FeishuJobsAdapter`，公司差异通过配置表达。只有确认多个飞书招聘站点接口结构可复用后才做通用化，避免过早抽象。

### 4. 智谱 AI

目标：校招/社招、职位分类与详情。

### 5. DeepSeek

目标：独立招聘域名和动态请求。

### 6. 字节跳动

目标：复杂分页和高价值岗位；因动态程度高，放在第一批后段。

## 7. 请求策略

- 设置明确 User-Agent，标识普通浏览器或项目名称，不伪装登录用户。
- 每源低频运行，MVP 一般 6–12 小时一次即可。
- 限制并发，域名级并发建议 1–2。
- 429、5xx 使用有限指数退避。
- 403/验证码不自动规避，记录 `AccessRestricted`。
- 设置超时和响应体大小上限。
- 不下载无关大文件。

## 8. Fixture 规范

目录：

```text
extensions/career_mcp/tests/fixtures/<source_id>/
├── listing_page_1.json|html
├── listing_page_2.json|html
├── job_detail_001.json|html
└── metadata.json
```

`metadata.json` 记录：

- 获取日期。
- 来源 URL。
- 内容类型。
- 是否做了脱敏。
- 预期岗位数和关键字段。

测试只读 fixture，不访问公网。在线 smoke test 标记为可选。

## 9. 标准化

### 文本

- 统一换行。
- 去除不可见控制字符。
- 保留段落语义。
- 不把职责和要求合并为单一字符串。
- 原始文本永久保留。

### 地点

MVP 保存来源文本和规范化列表，例如：

```json
{"raw": "北京/上海", "normalized": ["北京", "上海"]}
```

### 招聘类型

- `campus`
- `internship`
- `experienced`
- `talent_program`
- `unknown`

### 用工类型

- `full_time`
- `part_time`
- `intern`
- `contract`
- `unknown`

## 10. 身份与去重

优先级：

1. `source_id + external_job_id`
2. `source_id + canonical_detail_url`
3. 生成 fingerprint：公司、标题、地点、招聘类型、部门

不要只用标题，因为不同城市或部门可能重名。

## 11. 内容哈希

哈希应基于稳定业务字段，而不是整个原始 HTML：

- title
- department
- location
- responsibilities
- requirements
- deadline
- apply_url

字段排序和空白先规范化，再 JSON 序列化并 SHA-256。

## 12. 状态机

```text
首次发现 → active + created event
内容变化 → active + new version + changed event
一次未出现 → active，增加 missing_count
连续 N 次成功抓取未出现 → offline + offline event
重新出现 → active + reopened event
```

N 默认 3，并且只有当该 source 本次抓取整体成功时才能增加 missing_count。

## 13. 解析失败保护

若岗位数突然下降超过阈值、关键字段空值率异常或页面模板变化：

- 将 CrawlRun 标记为 degraded/failed。
- 不执行大批量下线。
- 保存异常快照。
- 返回需要人工检查的警告。

## 14. AI 关键词过滤

抓取阶段保存所有目标来源岗位或按配置保存相关类别；展示时支持关键词：

- AI / 人工智能
- 大模型 / LLM
- Agent / 智能体
- 多模态
- 机器学习 / 深度学习
- AIGC / 生成式
- RAG / MCP
- AI 产品

不要因为关键词未命中就丢弃原始岗位，避免中文命名差异导致漏数。可在展示或查询层过滤。
