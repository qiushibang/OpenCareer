# 多公司全业务线整晚扩张实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在一个长时间连续开发窗口内，完成 11 家目标公司的官方招聘来源准入，修复多来源公司建模，并把所有通过准入的来源实现为可测试、可运行的生产 Adapter。

**架构：** 先将 Company 与 CrawlSource 解耦，使一家公司可以拥有多个互不重叠的招聘范围；随后使用统一准入流水线调查所有公司。每个通过准入的来源立即生成源专用规格与 TDD 子计划并内联实现，不积压“已确认但未编码”的来源。

**技术栈：** Python 3.12、SQLite schema v3、FastMCP、pytest、标准库 HTTP、必要时使用现有 Playwright browser extra。

---

## 计划优先级

本计划取代
`docs/superpowers/plans/2026-08-05-overnight-stage7-job-radar.md`
作为今晚主线。旧计划中的搜索、事件、自动摘要顺延，只保留抓取失败契约修复和
正式入库作为多来源扩张基础。

执行顺序遵循用户确认的“先广后深”：

1. 建立多来源公司模型。
2. 目标名单全部完成官方来源调查。
3. 每个通过准入的来源立即实现。
4. 扩展字节跳动公开招聘项目和职类分片。
5. 正式入库、重复抓取和全量回归。

## 时间预算

| 阶段 | 预算 | 结果 |
|---|---:|---|
| G0 基线 | 20 分钟 | 测试、数据库、服务状态冻结 |
| G1 schema v3 | 90 分钟 | Company 与 CrawlSource 解耦 |
| G2 第一轮准入 | 3 小时 | 腾讯、美团、快手、滴滴调查并通过即实现 |
| G3 第二轮准入 | 2 小时 | Kimi、阿里、小红书、智谱调查并通过即实现 |
| G4 字节扩深 | 2 小时 | 新增公开项目/职类分片 |
| G5 正式入库 | 60 分钟 | 已通过来源写入和幂等复验 |
| G6 回归与文档 | 60 分钟 | 完整测试、来源矩阵、进度罗盘 |
| 弹性时间 | 1–3 小时 | 用于可用来源 Adapter 实现或线上契约变化 |

预计连续执行 10–12 小时。来源被禁用后释放的时间立即转给下一个可用来源。

## Gate 0：基线与安全快照

**文件：**
- 修改：`docs/11_DEVELOPMENT_LOG.md`
- 修改：`docs/12_TONIGHT_PROGRESS.md`

- [ ] 记录 Git 状态、基线 commit、Python/Node、Server/GUI PID。
- [ ] 记录 SQLite 中 Company、CrawlSource、Job、Version、Event、CrawlRun 数量。
- [ ] 复制本地数据库到 `.local-state/backups/career-before-schema-v3.sqlite3`。
  备份属于本地状态，不提交 Git。
- [ ] 运行：

```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q
cd surfaces/gui && npm test -- --run
git diff --check
```

- [ ] 任何既有测试失败时停止新增来源，先恢复基线。
- [ ] 不执行 `git reset`、`git clean`、`git checkout --` 或覆盖用户改动。

## Gate 1：Company 与 CrawlSource 解耦

### Task 1.1：定义来源元数据

**文件：**
- 修改：`extensions/career_mcp/domain/crawler.py`
- 修改：`extensions/career_mcp/crawler/adapters.py`
- 修改：`extensions/career_mcp/tests/test_crawler_normalize.py`
- 修改：`extensions/career_mcp/tests/test_crawler_service.py`

- [ ] 先写失败测试：

```python
descriptor = SourceDescriptor(
    source_slug="bytedance-campus-seed-2027",
    source_name="字节跳动 2027 Seed 大模型人才校招",
    company_slug="bytedance",
    company_name="字节跳动",
    scope_key="project:7621018151002507573",
    adapter_type="playwright-json",
    base_url="https://jobs.bytedance.com/campus/position",
)
assert descriptor.company_slug == "bytedance"
```

- [ ] 确认测试因 `SourceDescriptor` 不存在失败。
- [ ] 新增不可变 `SourceDescriptor`。
- [ ] 将 `JobAdapter` 改为暴露 `descriptor` 与 `fetch_jobs()`。
- [ ] `FakeAdapter` 接受可选 descriptor；未传时从旧 source slug 生成测试用兼容值。
- [ ] `AdapterRegistry` 继续使用 `descriptor.source_slug` 作为唯一键。
- [ ] 更新小米、DeepSeek、字节现有 Adapter 的明确 descriptor。
- [ ] 运行全部 Adapter 和 crawler 测试。

### Task 1.2：SQLite schema v3

**文件：**
- 修改：`extensions/career_mcp/database/migrations.py`
- 修改：`extensions/career_mcp/database/repository.py`
- 修改：`extensions/career_mcp/tests/test_repository.py`
- 修改：`extensions/career_mcp/tests/test_crawler_repository.py`

- [ ] 写 v2 -> v3 失败测试，准备包含 2 个 Job、Version、Event、Run 的 v2 数据库。
- [ ] 测试要求迁移后：
  - `PRAGMA user_version = 3`；
  - `crawl_sources` 包含 `company_id`、`scope_key`、`adapter_type`、`base_url`；
  - Job、Version、Event、Run ID 和数量不变；
  - `xiaomi-careers` 关联 canonical company slug `xiaomi`。
- [ ] 实现 migration 3，只使用 ALTER、INSERT、UPDATE 和索引；不 drop 业务表。
- [ ] 增加 `crawl_sources(company_id, scope_key)` 唯一索引。
- [ ] 将 `ensure_crawl_source` 改为接收 `SourceDescriptor`，返回 canonical company ID。
- [ ] 保留历史 source slug，不重命名现有 MCP source。
- [ ] 在备份副本上执行一次迁移，再对真实本地数据库执行。
- [ ] 对比迁移前后所有业务表行数。

### Task 1.3：防止来源重叠

**文件：**
- 修改：`extensions/career_mcp/crawler/adapters.py`
- 修改：`extensions/career_mcp/services/crawler.py`
- 修改：`extensions/career_mcp/tests/test_crawler_service.py`

- [ ] 写失败测试：同一 Company 的两个 Adapter 返回相同 external ID 时，候选来源验收失败。
- [ ] 新增只读 `validate_source_overlap(candidate)`，比较数据库和当前 registry 中的
  `(company_slug, external_job_id)`。
- [ ] 只在来源注册/live 验收时调用；普通 crawl 不做跨源合并。
- [ ] 重叠时返回明确错误并保持候选 Adapter 未注册。

## Gate 2：统一来源准入流水线

### Task 2.1：来源调查模板

**文件：**
- 新增：`docs/source-notes/TEMPLATE.md`
- 修改：`docs/04_JOB_CRAWLER_SPEC.md`

- [ ] 模板固定包含：
  - 官方公司页与招聘入口；
  - robots/条款观察；
  - HTML、JSON-LD、SSR、XHR；
  - 列表、详情、分页；
  - 稳定岗位 ID；
  - 当前总数与最大页数；
  - 业务线/项目/职位类别范围；
  - Cookie、Token、签名、登录或验证码依赖；
  - fixture 可得性；
  - 启用或禁用结论。
- [ ] 明确每家公司首次调查最多 20–30 分钟。
- [ ] 确认不能完整分页的来源不得注册。

### Task 2.2：源专用 TDD 生成规则

每个通过准入的来源必须先创建：

```text
docs/superpowers/specs/2026-08-05-<source>-adapter-design.md
docs/superpowers/plans/2026-08-05-<source>-adapter.md
extensions/career_mcp/tests/fixtures/<source>/
extensions/career_mcp/tests/test_<source>.py
extensions/career_mcp/crawler/<source>.py
docs/source-notes/<source>.md
```

源专用设计必须从真实 source note 填入确切 URL、字段、ID 和分页，不能复制猜测
契约。实现顺序固定为：

1. fixture；
2. parser 红灯；
3. parser 最小实现；
4. pagination 红灯；
5. Adapter；
6. pipeline；
7. live smoke；
8. MCP dry run；
9. registry。

## Gate 3：第一轮公司准入与实现

### Task 3.1：腾讯

**文件：**
- 新增：`docs/source-notes/tencent.md`
- 通过后新增：`crawler/tencent.py`、`tests/test_tencent.py`、
  `tests/fixtures/tencent-careers/`

- [ ] 从腾讯官网确认招聘入口，不从第三方文章确定 API。
- [ ] 验证社招、校招、实习是否共享稳定 ID 和字段契约。
- [ ] 检查官网公开分页能否覆盖全部职位类别和业务范围。
- [ ] 若 API 无登录、无签名且提供完整 JD，立即生成源专用设计/计划并实现。
- [ ] 若多个入口互斥，使用同一 `company_slug=tencent` 的多个 source。
- [ ] live 和 MCP 均通过后注册，否则 source note 记录禁用。

### Task 3.2：美团

**文件：**
- 新增：`docs/source-notes/meituan.md`
- 通过后新增：`crawler/meituan.py`、`tests/test_meituan.py`、
  `tests/fixtures/meituan-careers/`

- [ ] 确认美团官方招聘域名及社招/校招入口。
- [ ] 验证职位 ID、详情、分页、城市、职类和业务部门字段。
- [ ] 评估全量页数与 MCP 120 秒预算。
- [ ] 通过即按源专用 TDD 流程实现；受限即禁用并切换。

### Task 3.3：快手

**文件：**
- 新增：`docs/source-notes/kuaishou.md`
- 通过后新增：`crawler/kuaishou.py`、`tests/test_kuaishou.py`、
  `tests/fixtures/kuaishou-careers/`

- [ ] 确认快手官网到招聘站的直接归属。
- [ ] 验证列表是否公开返回完整职责与要求。
- [ ] 检查分页总数、稳定 ID、社招/校招/实习边界。
- [ ] 通过即实现，不复用浏览器会话 Cookie。

### Task 3.4：滴滴出行

**文件：**
- 新增：`docs/source-notes/didi.md`
- 通过后新增：`crawler/didi.py`、`tests/test_didi.py`、
  `tests/fixtures/didi-careers/`

- [ ] 从滴滴官网确认中国招聘入口。
- [ ] 排除海外岗位和需要登录的投递流程。
- [ ] 验证业务线、职位类别、地点、完整 JD 和稳定 ID。
- [ ] 通过即实现；公开站只提供壳页面且请求受限时禁用。

## Gate 4：第二轮公司准入与实现

### Task 4.1：Kimi / 月之暗面

**文件：**
- 新增：`docs/source-notes/moonshot-kimi.md`
- 通过后新增：`crawler/moonshot.py`、`tests/test_moonshot.py`、
  `tests/fixtures/moonshot-careers/`

- [ ] 从月之暗面/Kimi 官网确认招聘入口和公司归属。
- [ ] 检查是否使用 Moka、飞书招聘或独立静态数据。
- [ ] 若与 DeepSeek 类似在官方 bundle 中公开完整数据，使用静态确定性解析。
- [ ] 若依赖短期签名或会话 Cookie，禁用自动来源，不逆向。

### Task 4.2：阿里巴巴

**文件：**
- 新增：`docs/source-notes/alibaba.md`
- 通过后新增：`crawler/alibaba.py`、`tests/test_alibaba.py`、
  `tests/fixtures/alibaba-careers/`

- [ ] 确认阿里官方招聘入口和中国岗位范围。
- [ ] 调查社招、校招与实习的公开筛选范围。
- [ ] 验证岗位 ID 在列表、详情和分页间稳定。
- [ ] 若全量过大，只有官网互斥事业群/职类 ID 可用于分片。

### Task 4.3：小红书

**文件：**
- 新增：`docs/source-notes/xiaohongshu.md`
- 通过后新增：`crawler/xiaohongshu.py`、`tests/test_xiaohongshu.py`、
  `tests/fixtures/xiaohongshu-careers/`

- [ ] 从小红书官网确认招聘域名。
- [ ] 检查列表/详情是否无需登录且可完整分页。
- [ ] 验证业务方向、职类、地点、招聘类型和稳定 ID。
- [ ] 若第三方 ATS 请求依赖会话，记录禁用。

### Task 4.4：智谱华章复核

**文件：**
- 修改：`docs/source-notes/zhipu-ai.md`
- 只有契约变化后才新增：`crawler/zhipu.py`、`tests/test_zhipu.py`

- [ ] 低频复核官网和 Moka 入口是否出现新的公开静态数据或无会话 API。
- [ ] 不复用之前观察到的 `csrfCk`、`moka-apply`、`connect.sid`。
- [ ] 契约未变化则保持禁用，并记录复核日期与响应。
- [ ] 只有无需会话的新契约出现时才进入 TDD。

## Gate 5：已有公司全业务线扩深

### Task 5.1：DeepSeek 与小米完整性

**文件：**
- 修改：`docs/source-notes/deepseek.md`
- 修改：`docs/source-notes/xiaomi.md`

- [ ] 复核 DeepSeek bundle `total` 与 jobs 数组，确认当前 32 条仍为完整集合。
- [ ] 复核小米 API 总数、页数、所有职类/业务字段，确认 2,522 条仍为完整集合。
- [ ] 完成 schema v3 canonical Company 迁移。
- [ ] 正式抓取并再抓一次，要求第二次全部 `unchanged`。

### Task 5.2：抽象字节校园项目 Adapter

**文件：**
- 修改：`extensions/career_mcp/crawler/bytedance.py`
- 修改：`extensions/career_mcp/tests/test_bytedance_browser.py`
- 新增：`extensions/career_mcp/tests/fixtures/bytedance-frontier-campus/`
- 修改：`docs/source-notes/bytedance.md`

- [ ] 写失败测试，将固定 Seed Adapter 改成接收：

```python
ByteDanceCampusProject(
    source_slug="bytedance-campus-frontier-2027",
    source_name="字节跳动 2027 前沿技术领域人才校招",
    project_id="7624064258157889845",
    project_name="2027届前沿技术领域人才校招",
    max_jobs=200,
)
```

- [ ] 保留现有 Seed source slug 兼容。
- [ ] 使用同一浏览器进程和 context 抓取一个项目的全部页，避免每页重启 Chromium。
- [ ] fixture-first 实现前沿技术项目；当前调查计数 136 条、14 页只作为预期，
  live 必须重新确认。
- [ ] live 与 MCP dry run 均低于 120 秒后注册。

### Task 5.3：调查字节其他校招项目

**文件：**
- 修改：`docs/source-notes/bytedance.md`
- 每个通过项目新增独立 fixture 目录和 registry descriptor。

- [ ] 从官方筛选响应枚举校招与实习项目 ID、名称和数量。
- [ ] 对每个项目确认与已启用项目互斥。
- [ ] 每个项目单独估算页数与 120 秒预算。
- [ ] 通过项目复用 `ByteDanceCampusProjectAdapter`，不复制 parser。
- [ ] 父级“全部校招”与子项目不能同时注册。

### Task 5.4：调查字节社招一级职类

**文件：**
- 修改：`docs/source-notes/bytedance.md`
- 通过后修改：`crawler/bytedance.py` 和对应 fixture/test。

- [ ] 从官网公开 filters 响应枚举一级职类 ID。
- [ ] 获取每个职类独立总数，验证职类间是否互斥。
- [ ] 单职类低于安全页数且完整抓取低于 120 秒时才注册。
- [ ] 社招总范围 10,000 条保持禁用，不能用第一页或关键词结果替代。

## Gate 6：失败契约与批量执行

**文件：**
- 修改：`extensions/career_mcp/domain/crawler.py`
- 修改：`extensions/career_mcp/services/crawler.py`
- 修改：`extensions/career_mcp/server.py`
- 修改：`extensions/career_mcp/tests/test_crawler_service.py`
- 修改：`extensions/career_mcp/tests/test_stage3_tools.py`

- [ ] 按旧 Stage 7 计划修复 failed crawl 返回 `ok=true` 的问题。
- [ ] `CrawlResult` 增加 sanitized `error_summary`。
- [ ] dry run 和正式 run 失败都返回 MCP `CRAWL_FAILED`。
- [ ] 新增 `crawl_all_sources(dry_run=true)`，按 source slug 顺序执行并隔离失败。
- [ ] 聚合 live 超过 110 秒时不在 GUI 单次调用，改为逐源审批运行。

## Gate 7：正式入库与完整回归

**文件：**
- 修改：`README.md`
- 修改：`docs/11_DEVELOPMENT_LOG.md`
- 修改：`docs/12_TONIGHT_PROGRESS.md`
- 新增：`docs/13_SOURCE_COVERAGE_MATRIX.md`

- [ ] 对所有新注册来源先执行 MCP dry run。
- [ ] 经现有审批执行正式入库。
- [ ] 每个来源立即执行第二次抓取，要求无重复 created。
- [ ] 生成覆盖矩阵：

```text
公司 | 官方入口 | 来源范围 | 调查状态 | Adapter | 当前岗位数 | live 耗时 | 限制
```

- [ ] 运行：

```bash
.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q
cd surfaces/gui && npm test -- --run && npm run build
git diff --check
```

- [ ] SQLite 验证：
  - 每个生产来源有成功 CrawlRun；
  - `(crawl_source_id, external_job_id)` 无重复；
  - 每个 Job 有 canonical Company、source URL、first/last seen 和 hash；
  - 失败来源没有增加 missing/offline。
- [ ] 重启 Server 后再启动 GUI。
- [ ] GUI `list_sources` 与覆盖矩阵一致。

## 动态执行规则

### 通过准入

立即暂停后续调查，完成该来源的 fixture、TDD、live、MCP 和 registry，再继续下一家。

### 禁用

source note 写清停止证据；不超过 30 分钟继续尝试，不逆向限制，立即切换下一家。

### 接近 120 秒

先检查官网是否公开支持更大分页。只能使用官网实际接受的分页参数；不能提高并发。
仍超时则寻找官网互斥分片，否则禁用。

### 线上数据变化

以 live 契约为准更新 fixture 元数据；不能为了让旧测试通过而硬编码旧总数。

## 今晚验收

硬性：

- 11 家公司全部完成调查覆盖。
- schema v3 与 canonical Company 生效。
- 现有三家公司迁移无数据损失。
- 所有通过准入的来源都完成生产 Adapter。
- 字节至少完成前沿技术校招项目的完整 live 准入。
- 完整后端、GUI、build 与 diff check 通过。

目标：

- 新增 3–5 家生产公司。
- 字节新增 1–3 个来源。
- 岗位总量显著超过现有 2,639 条。

不以降低安全标准换取：

- 公司数量；
- 业务线数量；
- 岗位总量；
- “已支持”表述。

## 计划自检

- 规格中的 11 家公司均有明确任务。
- 未猜测任何尚未 live 验证的 API、字段或 ID。
- Company/CrawlSource 分离先于多业务线扩张。
- 每个未知来源通过 source-specific spec/plan 消除实现占位符。
- 所有代码任务遵循先红后绿，所有在线测试显式且低频。
- 不修改 OpenWorker 核心权限、Agent Loop、Provider Router 或 MCP Client。
