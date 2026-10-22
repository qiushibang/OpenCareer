# 开发日志

## 2026-08-04：仓库初始化

- 初始目录仅包含 OpenWorker Career 规划资料，不是 Git 仓库，也不包含 OpenWorker 源码。
- 已将全部资料移动到根目录内临时备份 `.bootstrap-20260804-234456/`，并对除校验清单自身外的全部文件完成 SHA-256 校验。
- 原计划的同级目录备份受运行沙箱限制而被拒绝，未写入任何文件；因此采用上述根目录临时备份替代方案。
- 已初始化 Git，配置只读远端 `upstream` 为 `https://github.com/andrewyng/openworker.git`，并创建分支 `feature/career-agent-mvp`。
- 当前基线提交：`01b6f83b3927e02912dda84bb392942c13ca70d1`。
- 已恢复 Career 资料包；保留上游 README、LICENSE、依赖和启动脚本。`TRAE_START_HERE.md` 已作为 `CODEX_START_HERE.md` 恢复。

## 2026-08-04：Stage 0 环境检查

- Python：`3.9.6`，低于上游要求的 `3.10+`。
- Node：`v20.20.2`；npm：`10.8.2`。
- Git：`2.50.1`。
- Rust：未安装。浏览器 GUI smoke 不依赖 Rust；Tauri desktop smoke 将不作为本轮前置验收。
- 已发现 `uv`，下一步使用其安装 Python 3.12 后运行上游 `packaging/setup_dev_env.sh`。

## 2026-08-04：Stage 0 后端基线

- 已使用 `uv` 安装 Python `3.12.13`，并以该解释器创建项目 `.venv`。
- 首次运行上游 bootstrap 时，静默的 pip Git 依赖检出没有输出且持续较长时间；中断后以非静默方式复现。根因是固定 `aisuite` 提交的正常 Git checkout，而非依赖冲突。
- 已成功运行等价的上游依赖安装：`.venv/bin/pip install --verbose --timeout 30 --retries 1 -e '.[messaging,dev]'`。
- 已验证：`.venv/bin/python -c 'import aisuite, coworker; print("imports-ok")'`。
- 已通过：`.venv/bin/pytest tests/test_builtin_personas.py tests/test_persona_loading.py tests/test_skills.py tests/test_mcp.py -q`，结果为 `28 passed, 1 warning in 3.20s`。
- 警告来自上游 FastAPI/Starlette 对 `httpx` 的弃用提示；本轮未修改上游依赖或测试。

## 2026-08-05：Stage 0 GUI 与服务 smoke

- 已通过 GUI 单测：`npm ci && npm test`，结果为 `18` 个测试文件、`108 passed`。
- 首次 Server 启动被沙箱拒绝创建默认状态目录 `~/.config/coworker`；以 `COWORKER_STATE_DIR="$PWD/.local-state"` 重试后成功。
- 带 `X-OpenWorker-Token` 请求的 `http://127.0.0.1:8765/docs` 返回 `200`。

## 2026-08-05：Stage 1A 与 Stage 1B

- 新增 `coworker/personas/builtin/career.md`，没有修改 Persona registry、TurnEngine、权限系统或 Provider Router。
- Persona 相关回归：`42 passed`。
- GUI 原有图标集没有 `briefcase`，因此只新增该单一图标及 manifest 解析白名单。
- 新增工作区 Skills、可信工作区 MCP 配置，以及最小独立 `extensions/career_mcp` 包。
- Career MCP 单测与 workspace Skill 测试通过：`14 passed`。
- 验证未信任工作区不加载 Career MCP，可信后解析 `.venv/bin/python -m extensions.career_mcp.server`。
- 使用 MCP SDK stdio 客户端验证 `health_check`、`get_mock_jobs`；使用 OpenWorker `SessionManager.prepare_mcp_tools` 验证真实 bridge 发现并调用 `mcp__career__get_mock_jobs`。
- 已生成 `artifacts/mock-job-brief.md`，内容明确标识为 mock smoke 数据。
- 未进行真实模型驱动的 GUI Career 会话演示：当前环境未提供模型 API key，不能伪造该验收。Stage 2 未开始，遵守阶段门槛。

## 2026-08-05：火山方舟模型接入

- 已使用 OpenWorker 现有的 OpenAI-compatible Provider 配置火山方舟；没有修改 Provider Router 或新增依赖。
- 已保存到项目隔离的本地 SecretStore：`.local-state/secrets.json`，目录权限 `0700`、文件权限 `0600`；该目录已加入 `.gitignore`。
- 已配置并验证北京地域 OpenAI-compatible endpoint：`https://ark.cn-beijing.volces.com/api/v3`。
- 已将 `ep-20260805104206-rng4r` 加入模型选择列表并设置为默认模型。
- Provider `/models` 只读验证通过；最小文本 completion 验证通过。密钥未写入仓库、日志或命令输出。

## 2026-08-05：Career Agent GUI 会话创建

- 已使用项目隔离状态目录启动本地 Server：`http://127.0.0.1:8765`。
- 已启动 GUI 开发服务器：`http://127.0.0.1:1420`。GUI 启动时必须将 `COWORKER_STATE_DIR` 指向仓库根目录的 `.local-state`，以读取 Server token。
- 已通过 GUI 启用 Career Persona，并在“New session”菜单选择 Career Agent；会话页面显示模型 `ep-20260805104206-rng4r`。
- 已在 Career GUI 会话请求 mock 岗位分析、确认写入审批，并生成 `artifacts/gui-mock-job-brief.md`。Stage 1B 端到端验收通过。

## 2026-08-05：Stage 2 手动 JD 与本地岗位库

- 新增 Career SQLite 配置、版本化 migration、纯函数 JD parser、Repository 和 JobService；未修改 OpenWorker 核心、未新增依赖、未访问公网。
- `import_manual_jd` 先返回不落库预览，只有 `confirmed=true` 才写入 Job、JobVersion 与 created JobEvent。
- 相同公司与相同规范化 JD 重复确认时返回原 `job_id` 和 `duplicate=true`，不新增版本或事件。
- 新增 `get_job`、`search_jobs` MCP 工具；返回来源 URL、原始文本、版本、事件与 UTC 时间戳。
- 已通过 Career MCP 测试：`11 passed`；OpenWorker MCP/Skill/Persona 回归：`21 passed, 1 warning`。
- 已通过 MCP SDK stdio smoke：发现 `import_manual_jd`、`get_job`、`search_jobs`，并完成预览、确认写入和详情读取。

## 2026-08-05：Career MCP GUI 挂载修复

- GUI 手动验收发现：工作区 MCP 的 stdio 子进程未显式指定 `cwd`，相对命令 `.venv/bin/python -m extensions.career_mcp.server` 会依赖 Local Server 的启动目录；连接失败时被 OpenWorker 跳过，导致 Career Agent 缺少 MCP 工具。
- `SessionManager.prepare_mcp_tools` 现在为未声明 `cwd` 的 stdio MCP 绑定已信任的工作区目录；显式 `cwd` 配置保持不变。
- 新增回归测试，确保可信工作区 MCP 在工作区目录中启动。测试先失败（`cwd=None`），修复后通过。
- 重启本地 Server 并重连 Career 会话后，日志出现 Career MCP 的 `ListToolsRequest`，证明 `health_check`、`get_mock_jobs`、`import_manual_jd`、`get_job`、`search_jobs` 已由 OpenWorker 发现。

## 2026-08-05：Stage 2 环境继承修复与复验

- GUI 预览和 `health_check` 已通过，但确认写入初次返回泛化的 `PERSISTENCE_ERROR`。进程环境检查确认：MCP SDK 的默认 stdio 环境会裁剪父进程自定义变量，Career MCP 未收到 `CAREER_DATA_DIR`，因此使用了默认数据库目录。
- `coworker.mcp.client.stdio_environment` 现在显式继承 Local Server 环境，并让 MCP 配置中的 `env` 值覆盖同名变量。新增回归覆盖父环境保留和配置覆盖；先失败（函数不存在），实现后通过。
- 相关回归命令：`.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q`，结果 `34 passed, 1 warning`。`git diff --check` 通过。
- 重启 Server 与 GUI 后，真实 Career GUI 会话调用 `import_manual_jd(confirmed=true)` 返回现有记录的 `job_id=9c17e2a0-cc19-448a-81a2-4179c2489b49` 与 `duplicate=true`，证明 MCP 子进程与验收服务使用同一隔离数据库。截图证据：`shot-20260805-061836-972242000.jpg`。
- 隔离数据库上的详情和文本搜索复验通过：`get_job` 返回 Version 1 和 created Event；`search_jobs(query="Agent")` 返回该岗位、`total=1`。
- 未将模型随后尝试的 Shell 读取当作验收，也未批准该请求。由于模型未稳定服从“仅调用 MCP”的指令，GUI 的“首次创建 `created=true`”尚缺可见人工证据；自动化 MCP/服务集成测试已覆盖首次创建。Stage 3 保持冻结。

## 2026-08-05：GUI 会话 MCP 挂载复验

- 重新启动 Local Server 与 GUI，均显式使用仓库的 `COWORKER_STATE_DIR`；Server 同时使用隔离 `CAREER_DATA_DIR`。
- 在 GUI 新建 Career Agent 会话后，界面显示 `Access Browser · openworker-career`，Server WebSocket 记录携带该工作区路径。
- Server 记录 Career MCP 的 `ListToolsRequest`；在 GUI 请求 `mcp__career__health_check` 并批准工具卡后，记录 `CallToolRequest`。这确认可信工作区 MCP 已挂载到 GUI 会话并可执行。
- 复验截图：`shot-20260805-062717-698814000.jpg`（工具审批卡）与 `shot-20260805-062745-292898000.jpg`（工具步骤完成）。
- 同时重跑：`.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q`，结果为 `34 passed, 1 warning`。

## 2026-08-05：Stage 2 首次 GUI 写入与 Stage 3 启动

- 在新建的可信 Career GUI 会话中，已按 MCP 审批流程执行 `import_manual_jd(confirmed=false)` 和同一原文的 `confirmed=true`。预览工具结果显示 `confirmation_required=true`；确认调用后，隔离数据库存在唯一岗位 `49e8ad37-810d-4429-9f7b-fb6432dd0cd1`，公司为 `OpenWorker Career Stage2 验收公司`、标题为 `Stage2 GUI 验收实习生`，并且恰有 Version 1 和一个 `created` Event。
- GUI 证据：`shot-20260805-070121-195902000.jpg`（预览审批）、`shot-20260805-070215-701763000.jpg`（确认审批）、`shot-20260805-070225-717051000.jpg`（确认工具步骤完成）。Server 记录两次 Career MCP `CallToolRequest`。
- Stage 2 的 GUI 首次写入验收已补齐；`get_job`、筛选搜索与重复确认此前已通过真实 MCP/隔离库复验。Markdown brief 的 GUI 写入审批仍未重跑，因此 Stage 2 状态在罗盘中保留为部分通过。
- 开始 Stage 3 的离线基础：新增 crawler snapshot/normalization/adapter 边界，以及 SQLite schema migration 2。没有接入网络或真实公司 Adapter。
- TDD 证据：`test_crawler_normalize.py` 先因缺少 crawler 模块失败，实现后 `2 passed`；schema v2 测试先断言失败（实际版本 1），实现 migration 后与 Stage 2 Repository 回归共 `4 passed`。

## 2026-08-05：Stage 3 离线状态机

- 新增独立的 `JobSnapshot`、`NormalizedJob`、`CrawlResult`、`JobAdapter` 和 fixture-only `FakeAdapter`。Adapter 不操作 SQLite、MCP、Agent 或 GUI；normalize 为纯函数。
- SQLite schema 升至 v2：增加 `crawl_sources`、`crawl_runs`、`jobs.crawl_source_id` 和 `jobs.missing_count`。Stage 2 表和手动 JD 导入回归仍通过。
- `CrawlerService` 在一个成功 run 的事务内执行 created、unchanged、changed、missing、offline、reopened；Adapter 异常写入 failed run，且不处理任何既有岗位的缺失或下线。
- 发现并修复一个身份边界问题：两个 external job 的内容相同不能被当作同一岗位。crawler job page 现在拥有独立 `job_sources` 记录，`crawl_sources` 仍表示整站来源，内容 hash 继续只表示内容。
- 添加无库 `dry_run`，仅从 adapter 快照计算初始 created 转移，且不创建 SQLite。已存在数据库的差异预览和执行型 MCP crawl 工具留待下一小步。
- 新增只读 MCP 工具 `list_sources` 和 `list_recent_job_events`，沿用现有 envelope 和 `limit` 验证；没有注册真实 Adapter 或访问网络。
- TDD 证据：状态机测试先因缺少 `CrawlerService` 失败，实现后 `4 passed`；只读 MCP 测试先因工具缺失失败，实现后与状态机测试 `6 passed`。
- 完整受影响回归：`.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q`，结果 `43 passed, 1 warning`；`git diff --check` 通过。

## 2026-08-05：Stage 3 无写差异预览与受保护执行工具

- `CrawlerService.crawl(..., dry_run=True)` 现在在已有 schema v2 数据库中只读比较候选快照和持久化岗位，预测 created、unchanged、changed、missing、offline 或 reopened。测试确认 changed 预览不会增加 Version 或 Event。
- 新增 `AdapterRegistry`；`crawl_registered_source` 只能执行显式注入的 Adapter。默认 Career MCP 不注册 `FakeAdapter` 或任何真实 Adapter，未知 source 返回 `SOURCE_NOT_FOUND`。
- 注册 `crawl_source(source_slug, dry_run=false)` MCP 工具。工作区 MCP 配置的默认 `requires_approval=true` 使其继续受 OpenWorker Interactive 审批卡保护；没有修改 TurnEngine、权限系统或 MCP Client。
- 新增 TDD：已有库差异预览和显式 registry 测试先失败，实施后 crawler service 与 Stage 3 MCP 工具测试共 `9 passed`。真实在线抓取未启动。

## 2026-08-05：Stage 2 与 Stage 3 最终验收

- Stage 2：在新的可信 Career GUI 会话中，Agent 先通过 `mcp__career__get_job` 读取 `49e8ad37-810d-4429-9f7b-fb6432dd0cd1`，再通过 OpenWorker `write_file` 审批写入 `artifacts/stage2-gui-job-brief.md`。文件已检查，包含岗位、公司、地点、招聘类型、职责、要求、来源 URL、版本和事件，且标记数据来源为 Career MCP。
- GUI 证据：`shot-20260805-073136-732045000.jpg`（MCP 读取审批）、`shot-20260805-073213-901012000.jpg`（文件写入审批）、`shot-20260805-073228-190189000.jpg`（两步完成）。
- Stage 3：使用真实 stdio MCP SDK 发现工具 `crawl_source`、`list_sources` 和 `list_recent_job_events`，与已有 Career MCP 工具共同暴露。`crawl_source` 默认仍只接受显式注册的 Adapter，未知来源安全返回 `SOURCE_NOT_FOUND`。
- 最终回归：`.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q`，结果 `46 passed, 1 warning`；`git diff --check` 通过。
- Stage 2 与 Stage 3 均通过。Stage 4 才可开始一个公开官方来源的合规调研；不在本轮实现任何真实 Adapter 或联网抓取。

## 2026-08-05：Stage 4 百度 SSR Adapter 尝试

- 已完成百度官方招聘调查、公开 SSR fixture 捕获、quote-aware `window.__INITIAL_DATA__` 提取、`listData.listDetailData` 到 `JobSnapshot` 的确定性映射、重复 `jobId` 保护，以及注入式 Adapter 到 Stage 3 pipeline 的离线测试。
- 公开 fixture 响应为 HTML，包含十条职位和稳定 UUID `jobId`；fixture 元数据只记录来源 URL、日期、响应类型、体积和两个预期 ID。
- 一次可选 live smoke 没有触发访问控制，但当前页面的内嵌状态不是严格 JSON，抛出 `BaiduSsrParseError`。按页面状态异常停止条件，已将百度从默认生产 Adapter registry 移除；未重复请求、未尝试登录、Cookie、验证码、签名或未证实 XHR。
- 离线测试：百度 Adapter、registry disabled 和 Stage 3 MCP 测试 `17 passed`。Stage 4 状态为“实现完成但来源禁用，待人工复核公开 SSR 状态表达式”。

## 2026-08-05：小米与 MiniMax 公开数据请求核验

- 已在本地 Server 与 GUI 健康运行的前提下，进行每个来源一次的低频、未登录公开核验；未提交表单、未投递、未登录、未复用 Cookie/Token，也未对接口做枚举或重试。
- 小米官方探索机会页 `https://hr.xiaomi.com/website/opportunities.html` 的正常浏览器加载实际发出 `GET /website/api/agent/searchJobPage?keyword=&cityZhNames=&pageSize=10&pageNum=1`。
- 该精确 URL 的一次公开 GET 返回 `HTTP 200 application/json`，`code=0`。`data` 包含分页字段；每个岗位包含 `title`、`cityZhNames`、`levelOneDeptName`、`description`、`requirement`、`publishTime`、`type`、`url`、`jobId`、`jobPostId`。列表本身提供完整职责和要求。
- 小米详情页面从官方列表 URL 正常打开，标题与列表职位一致；登录仅出现在投递入口。列表中 `jobId` 与 `jobPostId` 不同，详情 URL 数字段对应 `jobPostId`，因此后续 Adapter 应用 `jobId` 作为岗位身份，并同时保存 `jobPostId` 与详情 URL。
- MiniMax 官方 Career 页授权的飞书招聘租户可在未登录浏览器中显示列表和详情，且列表 ID 与详情 URL ID 一致；但浏览器实际列表请求包含短期 `_signature`。项目不直接调用、复用、逆向或生成该签名，故不实现或注册 MiniMax 生产 Adapter。
- 结论：小米成为第一个真实 Adapter 候选，下一步是 fixture-first 的 `XiaomiPublicApiAdapter`；MiniMax 保留人工浏览和手动 JD 导入路径。

## 2026-08-05：Stage 4 小米公开 API Adapter

- 新增小米专用设计与实施计划、公开第一页最小 fixture 和来源元数据。fixture 保留两条完整真实岗位，明确标记为从十条响应缩减，不含 Cookie、Token、签名或个人数据。
- TDD 先因缺少 `crawler.xiaomi` 失败，再实现纯 JSON 解析；覆盖 API envelope、分页、`jobId` 身份、`jobPostId` 详情 URL、完整职责/要求、重复 ID、必填字段和 HTTPS 来源校验。
- 新增 `XiaomiPublicApiAdapter`：串行分页、单次 crawl 统一观测时间、300 页上限、15 秒超时、2 MB 响应上限、`hr.xiaomi.com` 重定向 host 校验、JSON content type 校验和访问限制停止策略。未新增依赖。
- 默认 registry 现在仅启用 `xiaomi-careers`；百度继续因 SSR 契约异常禁用，MiniMax 继续因短期签名禁用。执行仍通过现有审批保护的 `crawl_source`。
- fixture pipeline 测试确认两条岗位产生 `created=2`，SQLite 保存稳定 `external_job_id` 与官方详情 URL。
- 实现后的单页 live smoke 通过：`page_num=1`、`page_total=253`、`total=2522`、`jobs=10`，首条 `jobId=7621150010131237158`。本轮未执行 253 页全量线上抓取。
- 完整受影响回归：`.venv/bin/pytest tests/test_mcp.py extensions/career_mcp/tests tests/test_skills.py tests/test_builtin_personas.py -q`，结果 `69 passed, 1 warning`；警告仍为上游 Starlette/httpx 弃用提示。

## 2026-08-05：GUI 空白页与开发 token 启动竞态修复

- 空白页可稳定复现为 `TypeError: Cannot read properties of undefined (reading 'includes')`。Server 日志同时显示 `/v1/settings`、`/v1/sessions` 等请求为 `401`，WebSocket 为 `403`。
- 根因是 Server 与 Vite 并行启动：Vite 在新的 `sidecar-8765.token` 写入前读取了旧 token。无有效 token 的 `/v1/health` 仍返回 redacted `{"status":"ok"}`，而 GUI 将缺失的 `model` 写入 React 状态，最终在 model display 的 `.includes` 调用处崩溃。
- `getHealth()` 现在拒绝非 2xx 或缺少非空 `model` 的响应，使 redacted health 进入现有启动重试路径，不再污染 UI 状态。新增 `api.auth.test.ts` 回归测试先复现 promise 错误解析，修复后通过。
- 按 Server 先、GUI 后的顺序重启后，REST 请求和 WebSocket 均恢复为 200/accepted，Career MCP 出现 `ListToolsRequest`。
- GUI 全量单测 `109 passed`；`npm run build` 通过；新浏览器标签完整渲染且控制台无 error；`git diff --check` 通过。

## 2026-08-05：小米 dry run 超时修复

- GUI 中两次 `crawl_source(source_slug="xiaomi-careers", dry_run=true)` 均返回 `TimeoutError`。根因是 Adapter 使用 `pageSize=10`，2522 个岗位需要 253 次串行请求，超过 MCP 工具桥的 120 秒调用限制；Career MCP 健康和工具挂载均正常。
- 单次公开探针确认官网支持 `pageSize=100`：第一页返回 100 条、26 页、总数 2522，首条 `jobId` 与既有 fixture 一致。
- 新增回归要求生产 URL 使用 `pageSize=100`，并在响应 `pageSize` 不一致时整体失败，避免静默回退到 253 页。测试先以 URL 仍为 10、未拒绝 mismatch 两项失败，修复后通过。
- 修复后的完整只读 Adapter 抓取返回 2522 条、2522 个唯一 ID，总耗时 46.8 秒，低于 MCP 120 秒限制；未写数据库。
- 重启服务后，真实 MCP stdio `crawl_source(source_slug="xiaomi-careers", dry_run=true)` 在 47.3 秒内返回 `ok=true`、`status=dry_run`、`transitions={"created": 2522}`，证明 GUI 所用工具路径不再超时。
- 完整回归：Career/后端 `70 passed, 1 warning`，GUI `109 passed`，`git diff --check` 通过。

## 2026-08-05：DeepSeek 静态 bundle Adapter

- DeepSeek 官方招聘入口 `https://talent.deepseek.com/` 返回 530 字节 HTML 外壳，并公开引用同源 `/static/main.<hash>.js`。静态 bundle 内含 DeepSeek 官方 Moka 租户对应的 `JSON.parse(...)` 数据集，当前提供 32 条岗位、唯一 UUID、地点和完整 `descriptionHtml`。
- 新增缩减真实 fixture、来源元数据和 `DeepSeekStaticBundleAdapter`。Adapter 只执行入口和 bundle 两次串行公开 GET，不执行 JavaScript，不调用未验证 API，不附带 Cookie、Token、签名或浏览器状态。
- TDD 覆盖同源 bundle 发现、quote-aware JavaScript 字符串解码、租户和总数校验、UUID 去重、HTML 转文本、请求限制、registry，以及 `created -> unchanged -> changed` pipeline。默认 registry 现为 `deepseek-careers`、`xiaomi-careers`。
- live Adapter smoke 返回 32 条、32 个唯一 UUID，耗时 0.23 秒；真实 MCP stdio `crawl_source(source_slug="deepseek-careers", dry_run=true)` 返回 `created=32`，耗时 2.26 秒，未写数据库。
- 聚焦来源测试 `43 passed`；完整 Career/后端回归 `86 passed, 1 warning`；GUI `109 passed`。警告仍为上游 Starlette/httpx 弃用提示。
- 按 Server 先、GUI 后的顺序重启后，Career GUI 的 `list_sources` 显示 `deepseek-careers` 与 `xiaomi-careers` 共两个来源；GUI 审批后的 DeepSeek dry run 显示 32 条新岗位且未写库。截图：`shot-20260805-145450-105150000.jpg`、`shot-20260805-145524-091890000.jpg`。
- 百度因 SSR 契约异常、MiniMax 因短期签名、智谱 AI 因 Moka 会话状态继续禁用。下一来源按既定顺序调查字节跳动官方招聘。

## 2026-08-05：字节跳动 Seed 校招浏览器 Adapter

- 字节官网社招公开结果上限 10,000 条、全部校招 7,387 条、`AI` 关键词仍有 4,687 条，均无法在 MCP 120 秒内完整遍历。将来源严格限定为官网独立的 `2027届Seed大模型人才校招`：项目 ID `7621018151002507573`，当前 85 条、9 页。
- 列表和详情无需登录，响应提供完整职责、要求、城市、招聘类型、稳定数字 ID 与详情 URL；但列表请求含第一方页面动态 `_signature`。Adapter 不保存、复用、生成或逆向签名，而是用全新 Playwright context 打开公开筛选页并读取页面自身取得的 JSON。
- 新增真实缩减 fixture、纯 parser、20 页/200 条安全界限、跨页一致性和完整计数校验。Playwright 传输为懒加载 browser extra，缺失依赖、登录/验证码、异常 host、超时或契约变化均整轮失败。
- 首次 MCP stdio dry run 因 Playwright Sync API 与 FastMCP asyncio 同线程冲突返回内部 `status=failed`。新增回归后，将浏览器抓取移到专用工作线程；复验返回 `status=dry_run`、`created=85`，耗时 23.03 秒。
- live Adapter 返回 85 条、85 个唯一 ID，耗时 30.51 秒。聚焦来源测试 `52 passed`；完整 Career/后端 `96 passed, 1 warning`；GUI `109 passed`；`git diff --check` 通过。
- 按 Server 先、GUI 后重启，GUI `list_sources` 显示三个来源并新增 `bytedance-seed-campus`；经审批的 GUI dry run 显示 85 条校园招聘新岗位且未写库。截图：`shot-20260805-151555-098522000.jpg`、`shot-20260805-151657-146861000.jpg`。

## 2026-08-07：本机 Aiden Responses Provider

- 只读确认 `~/.codex/aiden-app-home` 的模型目录包含 `deepseek-v4-flash`，配置使用 `https://aiden-aiproxy.bytedance.net/v2` Responses API。当前 TRAE 进程没有可复用的 `X-Aiden-*` 会话头，但本机 Aiden CLI 能动态取得 ByteCloud JWT。
- 不带会话头、仅使用运行时 JWT 的裸 Responses smoke 返回 HTTP 200 和 `AIDEN_SMOKE_OK`。没有把 JWT、会话头或 Codex/Aiden auth 配置复制到项目。
- 新增独立 `aiden:` Provider。OpenAI SDK 使用动态 `api_key` callable，每次请求执行 `aiden auth get-bytecloud-jwt-token`；可选 `X-Aiden-X-Client`、`X-Aiden-Session-Id`、`X-Aiden-Terminal-Id` 只从当前环境读取。
- 项目隔离 SecretStore 仅保存非敏感 CLI 路径；模型列表新增 `aiden:deepseek-v4-flash`，标记 1,000,000 token 上下文。默认模型继续保持火山方舟 endpoint。
- 真实 Provider 文本调用返回 `OPENWORKER_AIDEN_OK`，强制工具调用正确产生 `echo({"text":"AIDEN_TOOL_OK"})`，流式 Router 返回 `STREAM_AIDEN_OK`；真实 Server `/v1/chat/completions` 返回 `SERVER_AIDEN_OK`。
- Aiden Provider 与相关 Provider/Settings/Server 回归 `120 passed, 1 warning`，GUI `121 passed`；警告仍来自上游 Starlette/httpx 弃用提示。

## 2026-08-05：多公司扩张 G0/G1

- Git identity 已配置为 `qiushibang <126876622+qiushibang@users.noreply.github.com>`；多公司扩张规格与 10–12 小时计划已提交为 `66c239e`。
- G0 基线：Career/后端 `96 passed, 1 warning`，GUI `109 passed`，`git diff --check` 通过。迁移前数据库为 Companies 4、CrawlSources 1、Jobs 2525、Versions 2525、Events 2525、Runs 1。
- 已生成 `.local-state/backups/career-before-schema-v3.sqlite3`；与迁移前原库 SHA-256 均为 `fa21e0cc427a9e34cb8182940c24bfa2d968b0d604f39e72b43f86a2db253cb4`。
- 新增 `SourceDescriptor`，将 canonical Company 与抓取来源分开。小米、DeepSeek、字节 Seed 和禁用中的百度均保留原 source slug，同时声明 company、scope、Adapter 类型和官方 base URL。
- SQLite 升至 schema v3：`crawl_sources` 新增 `company_id`、`scope_key`、`adapter_type`、`base_url`。先在备份副本迁移，再迁移真实库；六张业务表行数完全不变，`PRAGMA foreign_key_check` 无错误。
- 小米原 Company 行保持 ID 不变并从 `xiaomi-careers` canonical 化为 `xiaomi / 小米`；CrawlSource 更新为“小米官方招聘”和 `all-public-jobs`。
- Repository 支持一个 Company 关联多个互斥 CrawlSource；新增显式来源重叠验收，候选来源与同公司其他来源共享 external ID 时拒绝注册。
- G1 Career 全量回归 `80 passed`；SourceDescriptor 变更提交为 `0884c3c`。

## 2026-08-06：腾讯社招多事业群 Adapter

- 腾讯官方社招公开 API 无登录、Cookie、Token 或签名。列表 API 支持 `pageSize=500`，详情 API 按稳定 `PostId` 返回完整职责、要求、事业群、产品、职类、地点和更新时间。
- 未筛选中国社招为 2,308 条。使用 8 个直接事业群来源和 15 个 IEG 互斥职类来源，覆盖 2,288 条；另有 11 条无公开事业群、9 条 IEG 无公开职类，未宣称覆盖。
- 初始 `pageSize=100` 的 CSIG live smoke 因实时排序产生跨页重复 ID，整轮安全失败。官网验证 `pageSize=500` 后，CSIG 单页返回 407 个唯一 ID，消除页漂移。
- 新增通用 `TencentCareersAdapter`、`TencentScope`、列表/详情 parser、官方 transport、缩减真实 fixture 和 SourceDescriptor。23 个生产 scope 列表复验为 2,288 条、2,288 个唯一 ID、跨 scope overlap 0。
- live：CDG 86 条/22.56 秒；WXG 258 条/76.42 秒；TEG 225 条/58.83 秒；CSIG 407 条/106.92 秒；IEG 最大“游戏产品”387 条/101.07 秒，其余 scope 均低于 66 秒。
- 真实 MCP dry run：CDG `created=86`/24.04 秒；IEG 游戏产品 `created=387`/105.72 秒。两个代表最小和最大规模的工具路径均低于 120 秒。
- 腾讯校招 `join.qq.com` 保留为后续独立来源调查；社招父源和 IEG 父源不注册，避免与子来源重叠。

## 2026-08-06：美团国内社招 Adapter

- 美团官方社招 `hr.meituan.com/web/social` 使用公开 POST JSON API。删除页面附带的 `u_query_id`、`r_query_id` 后请求仍成功，证明它们不是访问凭据；Adapter 不生成或复用这些字段。
- `pageSize=100` 生效，当前原始社招 2,264 条、23 页；列表直接包含稳定 `jobUnionId`、完整 `jobDuty`、`jobRequirement`、部门、职类、地点和更新时间，无需逐岗详情请求。
- 项目排除海外岗位。Adapter 每轮读取美团官方海外国家/城市树，只排除全部地点均属于海外枚举的岗位；混合国内/海外地点保留。
- 新增 Meituan parser、串行分页、海外过滤、POST allowlist transport、缩减真实 fixture、pipeline 和 registry 测试。
- live Adapter 返回 2,090 个国内唯一岗位，耗时 12.45 秒；真实 MCP dry run 返回 `created=2090`，耗时 11.40 秒。

## 2026-08-06：快手国内社招浏览器 Adapter

- 快手官方国内社招页面公开 1,417 条岗位，列表直接包含稳定数字 ID、完整职责和要求；官方 dictionary 映射地点、职类和工作经验。
- 标准 HTTP 请求依赖网关匿名 session 并返回 API `系统错误`，因此禁用 HTTP transport。生产 Adapter 只使用 fresh Playwright context，不读取、保存或复用 Cookie/storage state。
- API 固定 `pageSize=10`，142 页 UI 分页 11 页样本耗时 3.416 秒。实时排序导致单轮/双轮分页出现重复并漏 1 个 ID，不能跳过重复。
- 实现最多四轮的有界并集：总数必须稳定、重复 ID 内容必须一致、唯一 ID 达到官方 total 立即停止，110 秒或四轮后仍不完整则失败。
- 官网社招聚合含 1 条 `epiboly` 外包子项目且 `positionNatureCode=C001`；允许集合固定为 `socialr/epiboly`。
- 全量 live 返回 1,417 条唯一岗位，80.72 秒；真实 MCP dry run 返回 `created=1417`，62.18 秒。

## 2026-08-06：滴滴中国社招 Adapter

- 滴滴官方人才站将中国社招、校招、实习和海外招聘分开。中国社招列表 API 当前 358 条、23 页，固定实际 page size 16。
- 标准 HTTP 使用官方页面 Referer 后可公开访问列表和详情，无 Cookie、Token 或签名。列表提供 `jdId/jdNo`，详情提供完整 `jobDesc/qualification`。
- 新增串行列表/详情 Adapter、稳定 ID 和分页校验、缩减真实 fixture、pipeline 和 registry 测试。
- 20 个详情样本 5.696 秒；全量 live 358 条唯一岗位 95.06 秒；真实 MCP dry run `created=358`，103.94 秒。
- 当前距 120 秒上限约 16 秒；岗位数明显增长时必须重新评估职类分片，不能提高并发规避。

## 2026-08-06：Kimi / 月之暗面社招 Adapter

- 月之暗面官网“加入我们”经 `careers.kimi.com` 直接指向 Moka 租户 `moonshot/148506`，来源归属由公司官网确认。
- Moka 公开 API 响应为加密字符串，项目不逆向解密。生产 Adapter 使用 fresh Playwright context 读取正常渲染后的公开岗位卡片，不读取、保存或复用 Cookie/storage state。
- 页面当前 4 页、每页 30 条，合计 91 个唯一 UUID；卡片直接包含标题、发布日期、职类、可选地点和完整 JD。
- 新增纯卡片 parser、严格分页/UUID 校验、asyncio 专用线程、缩减 fixture、pipeline 和 registry 测试。
- live Adapter 返回 91 条完整岗位，8.69 秒；真实 MCP dry run 返回 `created=91`，11.6 秒。

## 2026-08-06：阿里巴巴业务入口与 Token Foundry Adapter

- 阿里集团官网公开 19 个业务招聘入口；17 个社会招聘站观察到同构 `/position/search` 完整-JD 契约，飞猪契约未确认，橙狮当前 0 岗位。
- 无状态裸 HTTP 返回 403。Adapter 仅用 fresh Playwright context 建立页面自身的匿名 CSRF 上下文，不导出、保存或复用 Cookie/Token。
- 批量全站验收在阿里云长时间无响应后主动终止，未将“同构”误判为“全部生产可用”。
- 首个生产 scope 限定 Token Foundry：当前 61 条唯一岗位，`pageSize=500` 单页完整返回。
- live Adapter 61 条完整 JD、5.25 秒；真实 MCP dry run `created=61`、6.24 秒；聚焦测试 6 passed。

## 2026-08-06：小红书社会招聘 Adapter

- 小红书官方社招当前 875 条、88 页，列表响应直接提供稳定 ID、地点、职类、完整职责和要求。
- 请求带页面动态 `x-s/x-t` 签名；Adapter 不读取、生成或逆向签名，只在 fresh Playwright context 中驱动官网自身分页。
- 实时排序导致单轮出现 873/875 或 874/875 个唯一 ID；实现最多三轮有界并集，总数稳定、同 ID 内容一致且唯一数精确等于 total 才返回。
- live Adapter 返回 875 条完整岗位，24.55 秒；真实 MCP dry run `created=875`，40.4 秒；聚焦测试 7 passed。

## 2026-08-06：智谱 fresh browser 复核与校招 Adapter

- 旧禁用结论来自 Moka 裸 HTTP 重复 302；fresh browser 复核确认社招 145 条、校招 19 条，两个 scope UUID overlap 为 0。
- 将 Kimi 的 Moka DOM transport 最小参数化，并改为原子提取整页，避免逐卡读取时 React 重渲染造成节点漂移；Kimi 回归保持通过。
- 智谱 metadata 使用独立 parser，按团队、用工类型、可选职类和可选地点解析。
- 社招 145 条中 3 条官方详情明确“职位描述：暂无”，因此继续禁用，不静默跳过。
- 仅注册 `zhipu-campus`：live 19 条唯一完整岗位、3.24 秒；真实 MCP dry run `created=19`、5.39 秒。

## 2026-08-06：抓取失败 MCP 契约

- `CrawlResult` 新增可选 `error_summary`；正式抓取和 dry run 的 Adapter 异常均保留安全错误摘要。
- `crawl_source` 遇到 `status=failed` 现在返回 `ok=false`、`code=CRAWL_FAILED`、`retryable=true`，不再把失败包装成成功响应。
- 聚焦领域与 MCP 工具回归 15 passed；成功路径的返回结构保持不变。

## 2026-08-06：字节前沿技术校招扩深

- 将固定 Seed 实现扩展为 `ByteDanceCampusProjectAdapter` 和不可变项目 descriptor，同时保留原 `ByteDanceSeedCampusAdapter`、parser 与 URL builder 兼容。
- 通用项目 transport 在一个 fresh browser/context 内完成全部分页，不读取或复用 `_signature`，由官网页面自行生成请求。
- 注册 `bytedance-campus-frontier-2027`，项目 ID `7624064258157889845`，与 Seed 使用同一 canonical Company 但独立 scope。
- live 返回 136 条、136 个唯一 ID、全部校招，21.2 秒；真实 MCP dry run `created=136`、22.31 秒。

## 2026-08-06：正式入库首批与实时分页漂移修复

- 正式入库 DeepSeek 32、字节 Seed 85、字节前沿技术 136、Kimi 91、Token Foundry 61、小红书 875、智谱校招 19、美团国内社招 2,090 条。
- 美团首次正式抓取因实时排序产生跨页重复 ID，明确返回失败且 0 条写入。新增最多三轮有界并集后成功写入 2,090 条，第二轮全部 `unchanged`。
- 小红书首次二次复验在三轮后仍未覆盖全部 875 个唯一 ID，明确失败且未触发下线。将已有安全并集上限扩为四轮后，复验全部 `unchanged=875`。
- 所有首批来源均完成幂等复验；失败运行保留在 `crawl_runs` 作为审计证据。

## 2026-08-06：正式入库完成与数据库审计

- 快手正式入库 1,417 条、滴滴 358 条，第二轮全部 unchanged。
- 小米实时变化首轮为 2,444 unchanged、24 changed、43 created、54 missing；第二轮 2,511 unchanged、54 offline，验证两次缺失才下线。
- 腾讯 23 个互斥 scope 第一轮写入 2,282 条，第二轮每个 scope 均全量 unchanged；当前计数较早期调查少 6 条，为官网实时下架。
- 最终数据库：schema v3、34 个 CrawlSource、10,014 条历史 Job、9,960 active、54 inactive、71 个 CrawlRun；`PRAGMA foreign_key_check` 0 errors。
- 11 家目标公司 crawler active 合计 9,957；另有 3 条手动验收岗位。覆盖矩阵写入 `docs/13_SOURCE_COVERAGE_MATRIX.md`。
- 入库前备份 SHA-256 为 `341a902bd9bdc825f7750c498e6340b5f8c1272b5f66f86c732e10aa4db7d8e7`；当前数据库 SHA-256 为 `d926e835f43d7f8bd12c7f50388c2c877ef97502d1a641a29a17791cc51a4cee`。

## 2026-08-06：最终 Server/GUI 与 MCP 验收

- Server 使用仓库根目录 `.local-state` 和 `career/` 数据目录启动，健康检查返回方舟模型 `ep-20260805104206-rng4r`。
- GUI 必须使用仓库根目录下的绝对 `COWORKER_STATE_DIR=<repo>/.local-state` 启动；在 `surfaces/gui` 中使用 `$PWD/.local-state` 会错误指向子目录并导致 401/403。
- 瞬时 401 响应曾使 `getInbox()` 返回 `undefined`，随后 `sessionInbox[0]` 触发空白页。新增失败回归后，将缺失 `items` 规范化为 `[]`。
- fresh Playwright 浏览器验收：`#root` 约 41 KB，历史 Career 会话正常显示，控制台 0 errors。
- 真实 MCP `list_sources` 返回 34/34 configured；`search_jobs(query="大模型")` 命中 1,967 条并返回真实腾讯、字节等岗位。

## 2026-08-06：crawl_all_sources 游标批量调度

- 新增 `CrawlBatchResult` 和 `CrawlerService.crawl_all_sources()`：按 source slug 排序、聚合 transitions、隔离单来源失败。
- 34 个来源完整运行约需 20 分钟，不能放入单次 120 秒 MCP 调用。MCP 工具每次固定执行一个来源，返回 `next_cursor/has_more`，由调用方续跑。
- `dry_run` 默认 true；正式写入继续经过现有 MCP 审批。不使用并发或后台任务。
- 单来源失败以批次结果和 warning 返回，不阻断 cursor 继续后续来源；非法 cursor 返回 `INVALID_INPUT`。
- 聚焦回归 18 passed；真实 stdio MCP 发现 9 个工具，首次 dry run 在 6.43 秒内返回 Token Foundry `unchanged=61` 和 continuation cursor。
- 使用说明：`docs/14_CRAWL_ALL_SOURCES_RUNBOOK.md`。

## 2026-08-06：OpenWorker Automation 接入

- 手工推进下一个 cursor：`bytedance-campus-frontier-2027` dry run 返回 `unchanged=136`，28.44 秒；下一 cursor 为该 source slug。
- 发现 headless scheduled engine 未调用 `prepare_mcp_tools()`，且 GUI Automation 固定使用 scratch + cowork，导致 Career MCP 无法挂载。
- TDD 新增可信 workspace/agent 绑定和 scheduled MCP 挂载回归；默认 scratch Automation 行为不变。
- `create_automation` 仅接受存在且已信任的显式 workspace；scheduled run 复用现有 MCP manager，不复制 MCP 客户端或权限逻辑。
- 创建并启用 `task-a42c98acd2`，每小时整点、`Asia/Shanghai`、Career persona；cursor 存于 `.local-state/crawl-all-cursor.json`。
- Career MCP 不符合 target-bound standing approval 条件，因此每次正式抓取仍进入 Inbox 等待批准，不绕过安全门。
- 10:50 端到端 scheduled run 正确进入 Inbox；批准后正式抓取 `bytedance-seed-campus` 85 条 unchanged，并将 cursor 写回。
- 首次验收发现同一 `tool_call_id` 执行两次：scheduled run 未登记 `_running_sessions`，Inbox resolve 误触 durable resume。新增精确红灯后，在 scheduled engine loop 前后复用 `mark_running/mark_idle`，防止原 await 与 resume 并行。
- Automation/MCP/Career 聚焦回归 203 passed，GUI 110 passed；生产 build 通过。
- 重启 Server 加载修复后，11:00 整点 scheduled run 再次通过 Inbox 单次批准：`deepseek-careers` 返回 32 unchanged，数据库 crawl run 从 2 精确增加到 3，cursor 更新为 `deepseek-careers`。
- 新 run transcript 中 `call_d40aki0zu49hwgo8n25sl1ey` 只有一个 tool result；Automation run_count 为 2、下一次运行仍为每小时整点，确认 durable resume 重复执行已消除。
- 最终复验命令覆盖 Automation、MCP、Career、Persona 和 Skill：后端 200 passed、GUI 110 passed；GUI production build 与 `git diff --check` 通过。

## 2026-08-06：34 来源完整 Automation 轮次

- 将 Automation 临时调整为每分钟触发，保留 skip-on-overlap 和逐次 Inbox 审批；从 `deepseek-careers` 后连续完成剩余 30 个来源，结束后恢复 `0 * * * *`。
- 一次 Agent 尝试使用 Shell 读取 cursor，按任务安全约束拒绝；Automation 指令收紧为只使用 `read_file/write_file`，后续运行未再触发 Shell。
- 美团连续两次在 TLS 握手阶段失败，失败 run 均为 0 observed、0 transitions，没有触发岗位下线；其余来源继续完成。
- 最小复现显示美团两个 CDN IP 均存在间歇性 TLS 建连延迟。原实现每页使用 `urlopen` 新建连接，23 页抓取会放大失败并超过 MCP 预算。
- TDD 增加瞬时网络错误重试和单客户端复用测试；默认美团 Adapter 改为在一次抓取内复用 `httpx.Client`，fixture 注入和现有解析契约保持不变。
- 完整线上 Adapter 由失败恢复为 2.34 秒返回 2,097 个唯一国内岗位；Automation 正式重试成功：13 created、305 changed、1,779 unchanged、6 missing。
- 最终 34/34 来源最新 run 均为 succeeded；数据库 10,067 jobs、10,013 active、54 inactive，重复键和外键错误均为 0。本轮事件为 53 created、340 changed、23 missing。

## 2026-08-06：每日岗位雷达摘要

- 新增只读 `get_job_radar_digest(hours=24, sample_limit=20)`：SQLite 完整聚合岗位、事件、公司和来源健康，样例上限不截断总数。
- 来源健康统计覆盖全部 configured Adapter；响应明细只包含 failed/pending 来源，避免 34 个健康来源明细放大模型上下文。
- `career-job-search` Skill 从 mock 流程更新为真实 `get_job_radar_digest/list_sources/search_jobs/get_job/list_recent_job_events` 路由，要求分页、岗位 ID 和官方 URL。
- 创建 `task-7a4f067305`，每天 09:00 Asia/Shanghai 生成 `artifacts/job-radar-daily/YYYY-MM-DD.md`；禁止 Shell 和 crawler 工具。
- 真实 smoke 产物为 `artifacts/job-radar-daily/2026-08-06.md`：10,560 个窗口事件、34/34 healthy、20 个官方 URL 样例。
- smoke 前后均为 106 crawl runs、10,562 job events、10,431 job versions，证明摘要链路只读。
- 方舟在部分 run 的最终总结阶段触发 request-burst 保护；已通过缩小来源健康明细降低响应体积。完整 Markdown 已落盘，会话总结仍保留为运行风险。
- 真实 stdio MCP 发现 10 个工具，摘要响应约 11.9 KB；最终后端相关 210 passed、GUI 110 passed，GUI production build 和 `git diff --check` 通过。

## 2026-08-06：Stage 9 简历导入与 Career Vault

- 用户明确选择在原 7 天稳定观察门槛前开始 P1；本阶段只实现导入、预览、分项确认、查询和删除，不开始岗位匹配或申请材料生成。
- 默认模型切换为 `ep-20260806151220-8km7l`，沿用原火山方舟 API Key 与 Base URL；重启后健康检查和 Settings 均返回新模型 ready。
- schema v4 新增 `resume_imports`、`resume_previews`、`candidate_profile`、`candidate_facts`、`profile_versions`，迁移不改变现有岗位和抓取数据。
- 新增本地文本/PDF/DOCX 提取；DOCX 使用 `python-docx`，PDF 复用 `pypdf`，扫描 PDF/OCR 明确后置。
- 新增 6 个简历 MCP 工具与 `career-resume-import` Skill；申请材料 Skill 只允许读取 confirmed Career Vault facts。
- GUI Career 会话新增 PDF/DOCX 和粘贴文本导入；prepared prompt 只包含 opaque token 和元数据，不包含文件字节或完整简历。
- synthetic smoke 通过本地 HTTP 与真实 stdio MCP 完成两次分项确认、默认遮罩查询和全量删除；16 个 MCP 工具，删除后私人文件 0。
- 最终回归：Career 185 passed、OpenWorker/Automation/MCP/Skill 93 passed、GUI 113 passed；GUI production build 与 `git diff --check` 通过。
- 最终数据库为 schema v4，Career Vault 五张表均 0 行、外键错误 0；34 个来源最新 run 仍全部 succeeded。两个 Automation 已恢复原调度。

## 2026-08-06：OpenCareer 统一求职产品前端

- 用户选择统一求职产品方案，用户可见主品牌确定为 `OpenCareer`；OpenWorker 继续作为底层 Agent Harness 和内部兼容标识。
- 新增 Career 专属空会话首页，提供“建立求职档案”“发现合适岗位”“分析一份 JD”三个真实入口；点击只预填请求，不自动发送。
- 无历史状态时默认进入 Career Persona；已有会话仍由原恢复逻辑决定 Persona，不强制覆盖。
- Career Composer 使用求职语境占位文案；Coworker、Code、Chat 和其他 Persona 保持原有行为。
- 侧栏、浏览器标题和同屏 Progress 引导统一为 OpenCareer；OpenWorker Cloud、OAuth 和工作区内部名称未做系统迁移。
- 浏览器 smoke 验证三个入口、预填不发送、标题和品牌均正确，控制台 0 errors；截图保存至 `artifacts/opencareer-unified-gui.png`。
- 最终 GUI 回归 121 passed；TypeScript 与 Vite production build 通过。构建仍有原有的动态/静态混合导入和大 chunk 警告，本次未扩大处理范围。

## 2026-08-07：简历 PDF 导入路径修复与 Career 功能入口

- 真实会话 `cac06ef6-55f` 使用了普通聊天 PDF 附件。该路径只把 PDF 内容交给当前对话，不会调用 `/v1/career/resumes/stage`，因此没有 Career Vault `upload_token`。
- Agent 随后错误猜测 `upload_token="attached-pdf"` 并要求用户提供内部 token。审批历史保留了该错误调用，但 Career Vault 的 `resume_imports`、`resume_previews`、`candidate_profile`、`candidate_facts`、`profile_versions` 均为 0 行，没有写入未确认简历事实。
- Career 空会话首页从 3 个入口扩展为 5 个：建立求职档案、发现合适岗位、分析一份 JD、查看岗位雷达、查看求职档案。
- “建立求职档案”现在直接打开专用 PDF/DOCX importer，不再让模型指导用户查找 token。附件菜单明确区分“PDF（仅用于对话）”和“导入简历到求职档案（PDF/DOCX）”。
- `career-resume-import` Skill 明确规定 upload token 只允许由 GUI 内部传递；Agent 不得要求用户复制、查看或提供 token，也不得把普通聊天 PDF 作为 Career Vault 导入处理。
- 新增 CareerWelcome、Composer 和 Skill 回归。最终后端/Career 回归 208 passed，GUI 124 passed；生产 build 与 `git diff --check` 通过。
- 当前岗位雷达和求职档案通过首页动作进入对话并调用 Career MCP 展示。独立岗位列表、公司筛选和岗位详情 Dashboard 尚未实现，仍是下一项最小产品增量。

## 2026-08-07：Composer 锁定 Aiden 默认模型

- 用户确认只隐藏 Composer 模型选择器中的其他模型；Settings 继续保留完整 Provider 和模型配置，未删除任何 API Key。
- 新增 `composerModelPolicy`，Composer 只显示并发送
  `aiden:deepseek-v4-flash`。载入旧会话时主动切换到 Aiden，避免仅隐藏菜单但仍使用历史模型。
- Aiden 未登录或不可用时显示模型未连接，不回退到火山方舟、OpenAI 或其他模型。
- 当前 `.local-state/prefs.json` 已通过现有设置 API 将默认模型迁移为
  `aiden:deepseek-v4-flash`；`/v1/health` 返回同一模型。
- OpenWorker 通用 `SessionManager` 默认值保持不变，避免破坏 Provider 首次配置与 Aiden liveness 规则。
- 回归结果：GUI 126 passed；Provider、Settings、Aiden 与 Server 92 passed；production build 与 `git diff --check` 通过。

## 2026-08-08：求职档案一级页面与全局中文界面

- 新增左侧固定“我的求职档案”入口和独立档案页面，包含“已确认档案”“原始简历”“版本记录”三个页签；更新简历继续复用现有专用 importer。
- Career Vault 增加档案、版本和关联原文件查询；HTTP API 默认脱敏，敏感信息仅在用户显式点击后读取，删除继续要求精确确认文本。
- PDF 通过鉴权 fetch 转为本地 blob 预览；DOCX 使用 `python-docx` 在本地生成转义后的标题、段落和表格 HTML；API 不暴露私人路径或内部 token。
- GUI 核心导航、Composer、审批、设置、Persona、连接器、自动任务、收件箱和状态文案统一为中文；OpenCareer、Aiden、DeepSeek、Skill、MCP、模型 ID 和用户内容保持原样。
- 新建对话菜单固定“职业 Agent”为第一项，核心 Persona 名称和 tagline 使用确定性中文映射；Career 首页保留五个中文功能入口。
- 运行态首次验收发现 `openworker-server` 无法导入 `extensions`。根因是根 `pyproject.toml` 的 setuptools 包发现仅包含 `coworker*`；加入 `extensions*` 后，仓库外控制台脚本导入回归和三个真实档案 API 均通过。
- 真实中文 PDF 文件名首次预览触发 `Content-Disposition` Latin-1 编码错误。新增中文文件名红灯后，响应改用 ASCII fallback 和 RFC 5987 `filename*=UTF-8''...`，真实 `/original/content` 返回 200 并生成 blob 预览。
- 浏览器验收：职业 Agent 第一、中文 tagline、已有档案默认脱敏、三个页签、中文 PDF 预览和版本接口均正常；干净标签页控制台 0 error。
- 最终回归：Career/OpenWorker 相关后端 210 passed，GUI 137 passed；production build 和 `git diff --check` 通过。保留既有 TestClient 弃用警告、Vite 混合导入和大 chunk 警告。
- 当前 Server 与 GUI 分别运行在 `http://127.0.0.1:8765` 和 `http://127.0.0.1:1420`。下一最小任务是独立岗位列表、筛选和岗位详情页面。

## 2026-08-08：独立岗位雷达页面与档案字段中文化

- 左侧新增一级“岗位雷达”入口，采用用户选择的列表与详情同屏布局；列表每页 20 条，默认只显示在招岗位，选择岗位时仅更新右侧详情。
- 新增只读岗位页面 API：`GET /v1/career/jobs`、`GET /v1/career/jobs/filters`、`GET /v1/career/jobs/{job_id}`。筛选覆盖关键词、公司、城市、招聘类型和状态，错误响应使用稳定中文消息。
- 列表 API 只返回摘要，不再携带完整 JD、职责和要求；详情 API 保留完整正文、首次发现、最近确认、最近变化、版本和事件，避免 20 条列表响应重复传输大段正文。
- 官网入口只接受 `http://` 和 `https://`；`manual://` 不展示外链。页面 API 不接受 SQL、任意排序列或本地路径，不调用模型和 MCP 工具循环。
- 档案递归字段渲染接入集中中文映射，`birth_date`、`degree`、`start_date`、`end_date`、`gpa`、`ranking` 等不再直接暴露内部字段名；未知字段仅转换为可读文本，不修改 Career Vault schema。
- 浏览器真实验收：默认显示 10,013 个在招岗位；DeepSeek 公司筛选得到 32 条，关键词 `Code Agent` 组合筛选得到 2 条；点击第二条后右侧标题和完整 JD 同步更新。档案页面显示“学历、结束时间、GPA、排名、开始时间”等中文标签。
- 手工浏览器验收期间重启 Vite 产生的连接中断日志属于测试操作；稳定后新开干净标签页复验为控制台 0 error。Server/GUI 需使用同一绝对 `COWORKER_STATE_DIR`，使运行时 sidecar token 保持一致。
- 最终回归：后端 214 passed（仅既有 TestClient 弃用警告），GUI 145 passed，production build 通过。保留既有 Vite 混合导入和大 chunk 警告。
- 已知数据质量风险：筛选元数据当前包含 707 个地点标签，存在“北京/北京市”等同义值；本轮不做有损裁剪。下一最小任务是建立地点规范化规则和迁移预览，再决定是否合并历史标签。

## 2026-08-08：多城市筛选、招聘标签、多简历库与搜索入口

- 新增确定性地点拆分纯函数，支持 `、`、中英文逗号、分号和斜杠；简单城市名移除末尾“市”，复杂行政文本不做猜测映射。新抓取岗位在 normalize 阶段拆分，已有岗位在筛选查询时兼容拆分，无破坏性迁移。
- 地点筛选计数按岗位去重。真实筛选项从 707 个原始值收敛为 336 个独立地点，组合项为 0；选择“广州”得到 492 个岗位，仍包含工作地点为“广州市、深圳市”的岗位。
- 招聘类型统一显示为“社会招聘、校园招聘、实习、类型未标注”，兼容 `experienced` 和 `social` 两个内部值；岗位列表和详情增加彩色类型标签，不再向用户展示 `experienced`。
- Career Vault 继续保留一个真实事实库，每个已确认 `resume_import` 作为独立简历文档。新增简历列表、按 ID 读取内容、版本和原文件的只读 API；页面改为左侧简历库、右侧“简历内容/原始简历/版本记录”，并提供“新增简历”入口。
- 多简历 API 不返回 `upload_token` 或 `private_path`，默认继续遮罩敏感字段。当前真实库有 1 份确认简历；双简历独立读取由 Repository、Service、HTTP 和 GUI 自动测试覆盖，没有写入演示用虚假简历。
- 删除侧栏独立“搜索”导航行，在 `OpenCareer BETA` 右侧新增搜索图标；点击继续打开原 `SearchModal`，折叠侧栏时的顶部搜索保持不变。
- 浏览器验收：独立城市选项、广州多城市命中、中文招聘标签、简历库、原档案中文字段和品牌栏搜索弹窗均正常；干净标签页控制台 0 error。
- 最终回归：后端 221 passed（仅既有 TestClient 弃用警告），GUI 148 passed；production build 与 `git diff --check` 通过。保留既有 Vite 混合导入和大 chunk 警告。
- 当前未实现简历重命名、目标岗位标签、单份删除和简历对比。下一最小任务是为每份简历增加用户可编辑名称与目标岗位元数据，再设计单份删除的引用完整性规则。

## 2026-08-08：简历名称、目标岗位标签与单份安全删除

- Career 数据库升级到 schema v5；`resume_imports` 新增 `display_name`、`target_roles_json` 和 `deleted_at`，已有简历名称回填原文件名，原始文件名保持不变。
- 每份简历支持独立名称和最多 10 个目标岗位标签。Service 统一执行 trim、去空、顺序去重和长度校验；GUI 使用中文编辑弹窗，列表和详情均展示蓝色岗位标签。
- 新增 `PATCH /v1/career/resumes/{resume_id}` 和 `DELETE /v1/career/resumes/{resume_id}`。API 不接受磁盘路径，也不返回 `upload_token` 或 `private_path`；非法元数据返回 400，未找到返回 404，确认名不匹配返回 409。
- 单份删除要求输入当前简历名称精确确认。删除后清空提取全文、删除该简历 preview、移除私有原文件并从简历库隐藏；`candidate_facts`、`profile_versions` 和其他简历保持不变。
- GUI 增加“编辑信息”和“删除此简历”。删除提示明确共享事实会保留；成功后按原索引选择相邻简历。实际文件删除仅在隔离测试数据库执行，真实简历浏览器验收只打开弹窗，未提交删除。
- 内容去重兼容软删除：重新上传相同文件会复用稳定 import ID，但刷新 token、文件名、全文和 staged 状态，清除删除标记及旧标签，不会被软删除审计行阻塞。
- 浏览器真实验收确认旧库自动迁移到 schema v5、名称正确回填、编辑弹窗预填名称、目标岗位输入可用、删除按钮在未输入精确名称时禁用。同步重启 Server 与 GUI 后 token 一致；控制台仅保留重启期间的 Vite 连接中断记录。
- 最终回归：后端 227 passed（仅既有 TestClient 弃用警告），GUI 150 passed；production build 和 `git diff --check` 通过。保留既有 Vite 混合导入和大 chunk 警告。
- 下一最小任务：设计简历与目标岗位的关联及多简历对比视图，继续复用共享真实事实库，不复制候选人事实。

## 2026-08-09：岗位与简历证据匹配闭环

- Career 数据库升级到 schema v6，新增 `job_resume_matches`。快照按岗位
  `content_hash` 与简历 `updated_at` 幂等保存，保留历史版本并返回
  `fresh/stale_job/stale_resume/unavailable_resume`。
- 新增确定性匹配 Domain：保守分类 hard/preferred/unspecified，只从已确认
  简历章节生成可追溯 excerpt；输出 direct/related/none，不输出百分比或录用概率。
- 正式岗位最初只有 3/10,067 条结构化 `requirements`。TDD 增加官方 JD 标题
  白名单解析，覆盖 DeepSeek、美团、腾讯、小米、字节及后续真实变体；当前
  10,056/10,067 条可分析，覆盖率 99.89%。剩余 11 条为空占位、仅 `-` 或
  无可靠要求边界，继续返回 `INSUFFICIENT_JOB_DATA`，不做语义猜测。
- 新增 `POST/GET /v1/career/jobs/{job_id}/matches`、
  `match_job_to_profile(job_id, resume_ids, snapshot_ids)`、岗位详情简历选择、
  证据矩阵、多简历比较、stale 提示和 Career 会话预填。GUI 不自动发送，
  文件写入继续经过 OpenWorker 审批。
- 真实 DeepSeek 岗位“AGI 核心业务管培生”和确认简历生成 fresh 快照
  `ad17d0bb-dc26-4e44-b24f-fc5bccb4c88e`：4 条要求，1 条 related、3 条
  none，HTTP 和 DOM 均未出现手机号、邮箱、私人路径或上传 token。
- 浏览器发现 StrictMode 会在第二次 mount effect 中清空申请包预填。新增红灯后，
  Composer 只在 `resetKey` 真实变化时清理草稿；真实浏览器确认 opaque IDs
  正确预填且用户消息数为 0。
- 对抗审查由两个独立审查线程交叉验证，确认并修复：非 basic 嵌套联系方式泄漏、
  同时间快照排序不稳定、GUI snapshot IDs 未被 MCP 校验、Agent 对 none 项
  推导资格与工作月数。额外真实验收发现并阻止
  `get_candidate_profile(include_sensitive=true)`；Skill 现固定使用 false。
- 申请准备包经 Career Agent、MCP、Shell 和文件写入审批重新生成：
  `artifacts/application-packets/deepseek-agi管培生-申请准备包-20260809.md`。
  文件包含 8 个固定章节、官方 URL、job/resume/snapshot ID、精确 7 条 evidence；
  不含资格判断、日期推导或敏感联系方式。
- 最终回归：后端 263 passed，GUI 155 passed，production build 通过，
  schema v6、`PRAGMA foreign_key_check` 0、`git diff --check` 通过。保留既有
  Starlette/httpx 弃用警告、Vite 混合导入和大 chunk 警告。
- 下一最小任务：增加申请包确定性内容校验器，进一步降低模型不遵守 Skill 文案的
  残余风险；随后开始岗位收藏与申请状态跟踪设计。

## 2026-08-09：申请包确定性编译与校验

- 新增结构化申请包编译器，正式产物固定为八个章节，只接受 fresh 匹配快照、
  1–5 份不同简历和等量唯一 snapshot ID。校验失败时阻止写入，不再依赖模型
  自由生成 Markdown 后补救。
- 新增 `create_application_packet` 和 `validate_application_packet`。正式产物
  必须通过权威数据重新编译、文件名校验和 SHA-256 字节比对；通用文件工具或
  Shell 修改后会返回 `ARTIFACT_CONTENT_MISMATCH`。
- 写入使用同目录临时文件、`fsync` 和 `os.replace`；正式目录、目标文件
  symlink、绝对路径及 `../` 路径均被拒绝。不同 snapshot 集合使用哈希后缀隔离，
  同一日期和 snapshot 集合保持路径及字节幂等。
- 匹配证据入口与最终 Markdown 共用敏感值规则，覆盖手机号、邮箱、私人路径、
  微信号、分隔身份证号和出生日期变体；同时拒绝匹配率、资格结论和工作月数推导。
- `MatchService` 在业务读取前使用 `BEGIN IMMEDIATE` 保证岗位、简历与 snapshot
  一致。真实复验发现全新数据库首次调用会与 Repository 迁移事务嵌套；新增红灯后，
  调整为先完成 Repository 迁移再加业务锁，并保留并发更新阻断测试。
- 两轮独立对抗审查确认隐私变体和 artifact 完整性无剩余 major：
  symlink、路径逃逸、正文篡改、snapshot/文件名错配均被拒绝。
- 真实 DeepSeek 产物：
  `artifacts/application-packets/deepseek-agi-核心业务管培生-申请准备包-20260809-4a5d28c3cd.md`；
  `validate_application_packet` 返回 `valid=true`，SHA-256 为
  `392d965cb0bfb207e057b3869f78bc3b01d2459a030dfd77e8eabcdd948ff70f`。
- 最终后端回归 `318 passed`，仅保留既有 Starlette/httpx 弃用警告；
  schema v6、`PRAGMA foreign_key_check` 0、正式目录仅一个文件且
  `git diff --check` 通过。
- 下一最小任务：按既定顺序设计并实现岗位收藏与申请状态跟踪。

## 2026-08-10：岗位收藏与申请跟踪

- Career 数据库升级到 schema v7，新增 `job_tracking` 当前状态和
  `job_application_events` 追加时间线。收藏与申请阶段相互独立，岗位下线不删除
  用户记录，crawler 管理的 `jobs`、`job_versions` 和 `job_events` 不承载私有状态。
- 新增严格 Domain 校验、Repository 和事务 Service。首次实际修改才创建记录；
  GUI 与 MCP 都提交 `expected_version`，已有记录使用
  `UPDATE ... WHERE job_id = ? AND version = ?`，并发旧版本返回
  `VERSION_CONFLICT`。状态、事件和返回结果重读均在同一
  `BEGIN IMMEDIATE` 事务提交前完成。
- 岗位列表通过 `LEFT JOIN job_tracking` 在 SQL 分页前执行收藏和阶段筛选；
  `COALESCE(..., 'not_started')` 保证没有实体 tracking 行的岗位也属于默认“未开始”。
  详情返回完整 tracking 和倒序事件，列表只返回摘要。
- 新增 HTTP `GET/PATCH /v1/career/jobs/{job_id}/tracking` 和 Career MCP
  `get_job_tracking/list_tracked_jobs/update_job_tracking`。数组、标量和 JSON
  `null` 均交给共享 Domain validator，稳定返回 `400 INVALID_INPUT`，不泄露
  SQLite、路径或异常堆栈。
- 岗位雷达新增“仅看收藏”、申请阶段筛选、列表和详情收藏、申请备注、中文时间线。
  收藏乐观更新失败会回滚；CAS 冲突会读取服务端最新版本；收藏筛选中取消收藏后
  重新查询服务器，并同步选中项、空态和末页 offset。时间线固定按
  `Asia/Shanghai` 显示到分钟。
- 两路独立对抗审查发现并通过 TDD 修复 5 个 Major：v7 DDL 隐式提交导致迁移残留、
  HTTP 非对象请求绕过错误契约、虚拟 `not_started` 筛选遗漏、收藏冲突不刷新、
  收藏筛选取消后的列表/详情/分页不一致。另修复时间线只显示日期的 Minor。
- 修复后窄复核均为 `major_remaining:false`：后端复核通过 migration 4 项、
  PATCH API 12 项及独立 DDL 故障/重连/重试探针；GUI/查询复核通过定向后端
  17 项、GUI 12 项和 production build。
- 真实 DeepSeek 岗位
  `ad9b82d1-e411-4677-bbe8-8ca535357a71` 完成收藏、准备材料、已投递、筛选和恢复；
  `jobs.status/content_hash/updated_at` 前后不变，外键错误 0。
- Playwright 在隔离岗位 `Career GUI 验收实习生` 完成未开始→准备材料→已投递、
  备注保存、收藏筛选和恢复；时间线显示“已投递/准备材料”及分钟。恢复后当前状态为
  未收藏、未开始、空备注；不可变事件按设计保留。全流程 HTTP 4xx/5xx、console
  error 和 page error 均为 0。
- 最终回归：后端 `345 passed`（仅既有 Starlette/httpx 弃用警告），GUI
  `162 passed`，production build、Python 编译、schema v7、
  `PRAGMA foreign_key_check` 和 `git diff --check` 通过。Vite 继续保留既有
  混合静态/动态导入和大 chunk 警告。
- 运行约束：独立启动 Server 与 Vite 时，两者必须使用同一绝对
  `COWORKER_STATE_DIR`，否则 Vite 无法读取当前 sidecar token，浏览器会收到
  401/403。同步启动后干净浏览器认证和 WebSocket 均正常。
- 下一最小任务：按既定顺序设计并实现定制材料导出，不提前进入 OCR 或招聘来源扩充。

## 2026-08-10：定制简历 DOCX/PDF 导出

- Career 数据库升级到 schema v8，新增 versioned `tailored_resume_drafts` 和
  `tailored_resume_exports`。每份草稿固定绑定一个 job、一份未删除确认简历和一个
  fresh match snapshot；Agent、GUI 和 export 全部使用 CAS version。
- `prepare` 先持久化整份脱敏 baseline。学校、公司、职位、项目名和日期等结构字段
  原样锁定；Agent 只能为 direct/related evidence 对应的 editable fact 提交子集
  proposal。数字、日期、URL、敏感值、资格结论、跨简历 path 和 `none` 绑定由
  Domain 确定性拒绝。
- 新增 Career MCP `prepare_tailored_resume` 和
  `submit_tailored_resume_proposals`，stdio 实际发现 24 个工具。MCP 不暴露
  confirm、export、download 或敏感联系方式；新
  `career-tailored-resume` Skill 要求提交后停止并让用户回岗位雷达逐条确认。
- HTTP 新增 draft list/get/PATCH/confirm/export 和 authenticated DOCX/PDF
  download。数组、标量和 JSON `null` 统一进入 Service 校验；错误响应不返回简历
  正文、联系方式、绝对路径、SQL 或堆栈。
- 固定 `ats_single_column_zh_v1` 单栏模板先生成 DOCX，再由同一个 DOCX 通过
  LibreOffice 生成 PDF。生产校验要求 PDF 可读且为 1–2 页；DOCX/PDF hashes、
  页数、目录边界和发布文件集合均被验证。
- 双文件在随机私有临时目录完成后才 rename 发布。短 `BEGIN IMMEDIATE` 事务重新
  验证 version、confirmed 状态和 freshness，再写 metadata、CAS 标记 exported、
  fsync 父目录并 commit；数据库或 commit 失败会删除发布目录，删除失败隔离为
  `.orphan-*`。正式目录已加入 Git ignore。
- 岗位雷达在恰好一份 fresh match 时显示“生成定制简历建议”，只向新 Career
  composer 预填 job/resume/snapshot opaque IDs，不自动发送。草稿面板并排展示
  原事实和建议措辞，支持确认、省略、证据内编辑、冲突刷新、stale 阻断、正式导出
  和 authenticated DOCX/PDF 下载；exported 草稿不再显示修改控件。
- 真实浏览器使用合成岗位完成 pending → confirmed → exported：PATCH 和 export
  均为 200；生产 LibreOffice 生成 DOCX 36,975 bytes、PDF 42,632 bytes、1 页；
  两种格式均包含候选人姓名和目标岗位，保存 hashes 与文件一致。全流程 HTTP
  4xx/5xx、console error、page error 和 request failure 均为 0。
- 验收合成岗位、简历、snapshot、draft、export、private source 和发布目录已按精确
  ID 清理；清理后 marker 记录 0、外键错误 0。当前真实 Career 数据库 schema 为
  v8。
- 对抗审查通过 TDD 修复：已确认结构化技能词未进入 proposal 白名单、stale draft
  无法作为只读草稿重开、已导出草稿仍显示编辑控件、下载失败无稳定中文反馈、导出
  目录错误使用结构化 company 对象、LibreOffice profile 泄漏、缺失或篡改文件仍被
  幂等/下载返回。
- 最终回归：后端 `413 passed`，GUI `170 passed`，production build、Python
  compile、schema v8、`PRAGMA foreign_key_check`、MCP stdio discovery、
  `git diff --check` 和 Git ignore 检查通过。仅保留既有 Starlette/httpx 弃用、
  Vite 混合导入和大 chunk 警告。
- 下一最小任务：按既定顺序开始 OCR 规格与实施计划；不得在设计前直接把 OCR 接入
  已确认事实库。

## 2026-08-10：扫描 PDF 本地 OCR Gate 0（通过）

- 已完成并提交 OCR 设计与实施计划，固定“原生文字优先、只对稀疏页回退、本地离线、
  仍需五章节用户确认”的边界；OCR Gate E 前不进入招聘来源扩充。
- 依赖门禁淘汰 ONNX Runtime 1.28.0：Windows cp312 wheel 存在，但 macOS 12
  arm64/x86_64 不可用。三平台共同候选收敛为 RapidOCR 3.9.2、ONNX Runtime
  1.19.2、OpenCV 4.10.0.84、NumPy 1.26.4；RapidOCR 和 ONNX Runtime 的直接
  依赖也完成三目标 `--only-binary` wheel 校验。
- RapidOCR wheel 内置 detection、orientation、recognition 三模型，bytes 和
  SHA-256 已写入 `config/ocr-model-manifest.json`。RapidOCR/PaddleOCR 为
  Apache-2.0，ONNX Runtime 为 MIT；运行时显式传入本地模型路径并在 socket 级
  断网验证，没有触发 ModelScope 或其他下载。
- 新增两份仅含虚构内容的 image-only PDF fixture；`pypdf` 提取均为空。中文和
  中英混合断网识别通过，不打印识别全文、绝对模型路径或私有字段。
- 固定 ONNX 单线程、RapidOCR 内部长边 1600、200 DPI 顺序处理后，本机实测：
  1 页 1.36 秒/620 MB 峰值，3 页 3.46 秒/873 MB，10 页 12.32 秒/852 MB；
  内存未随允许的 10 页上限线性增长。
- macOS arm64 PyInstaller onedir 断网识别通过，三模型 hash 一致。窄收集产物
  229 MB；冷文件缓存首次约 23.5 秒，warm 约 2 秒。production sidecar 必须使用
  `collect-data rapidocr`，不得 `collect-all` 打入 ONNX transformer 工具和
  RapidOCR 可选后端。
- `ocr-gate0.yml` 在私有远端 run `31374122574` 完整通过 macOS arm64、macOS
  Intel 和 Windows x64 installed/frozen 双重断网识别；三个 artifact digests
  已记录。Gate 0 正式通过，业务 OCR 可以进入 Domain TDD RED。
- 完整证据：`docs/ocr/2026-08-10-gate0-evidence.md`。
- 下一最小任务：进入 OCR Domain 的 TDD RED，先实现不可变值、polygon 稳定排序、
  confidence 聚合、native/OCR 选择和质量 warning 纯函数。

## 2026-08-10：扫描 PDF 本地 OCR Gate A（adapter 完成）

- OCR Domain 以 RED 开始并完成 14 项纯函数测试：固定 polygon 排序、0.50 行阈值、
  字符加权 confidence、native/OCR 严格择优、quality warning 和逐页 provenance；
  Domain 不导入 RapidOCR、ONNX、PDFium、SQLite、HTTP 或 Agent。
- 页级 orchestration 以 RED 开始并完成 11 项测试：native-only 不初始化 runtime，
  稀疏页最多 10 页、单 workflow 并发、逐页释放、200 DPI 与尺寸/像素上限，以及
  runtime/page failure 的稳定降级。真实 PDFium smoke 为 1655×2339、
  3,871,045 pixels。
- 新增唯一 production `RapidOcrEngine`。adapter 从版本控制 manifest 读取固定
  engine/model identity，校验 RapidOCR 与 ONNX Runtime 版本、三模型 bytes 和
  SHA-256，并拒绝包目录外路径；模块导入阶段不加载 RapidOCR/ONNX，首次识别才构造
  runtime，所有模型路径均由本地 package resource 决定。
- adapter RED 因 `extensions.career_mcp.ocr` 不存在而失败；最小实现后 9 项测试
  通过，覆盖 identity、真实输出转换、缺失/篡改模型、非法 manifest/role、import、
  constructor 和 inference failure。所有失败只返回 `OCR_UNAVAILABLE` 与无绝对
  路径安全消息。
- 真实中文扫描 fixture 在 socket 级断网下通过 production adapter：识别 4 行，
  三个 model ID/hash 与 Gate 0 manifest 一致；验收输出未打印 OCR 全文或模型路径。
- 当前定向回归 `42 passed`，包含 adapter、OCR Domain、orchestration 和既有 resume
  parsing；`compileall` 与 `git diff --check` 通过。当前 `.venv` 未安装 `ruff`
  executable，因此该静态检查命令未运行，未将其误记为代码告警。
- 下一最小任务：按 Task 5 先写页级 PDF extraction RED，将现有
  `domain/resume.py` 接入 `ResumeOcrService`；native PDF、DOCX、TXT 必须保持
  不初始化 OCR。

## 2026-08-10：扫描 PDF 本地 OCR Gate D（四 fixture）

- 新增确定性 `low-quality-skewed.pdf`：单页 69,401 bytes、无原生文字层，
  SHA-256 为
  `bf3a7dea4e62411f9d83f93a30687072b565d0c917b9fc84e1be4dea8ed721ca`；
  连续生成两次 hash 一致。
- production `ResumeService`、`PdfiumPageRenderer`、`RapidOcrEngine` 在
  socket `connect/connect_ex/create_connection` 全部禁用时完成真实 staging；
  低质量结果为 `method=ocr`、`review_required=true`、
  `warnings=["OCR_SPARSE_TEXT"]`、OCR 页 `[1]`。
- 中文 fixture 为 `ocr`、48 字符、无 warning；中英 fixture 为 `ocr`、78 字符、
  无 warning；hybrid fixture 为 `hybrid`、222 字符、无 warning，且只对第 2 页
  OCR，metadata 固定 `native_pages=[1]`、`ocr_attempted_pages=[2]`。
- staging 后隔离目录只包含 `career.sqlite3` 和 content-addressed 原始 PDF；
  未产生 PNG、JPG、JPEG、BMP、NPY、ONNX 副本、页面图或 debug 文件。
  `artifacts` 与 `.local-state` 前后快照 hash 均为
  `423b5e5cf3210b92920cbc9cd89d4205e5d7a997bacbec4b553510a6a5ad8372`。
- 继续执行现有五章节 preview/explicit confirm 后，精确名称删除成功；原始 PDF
  被移除、`resume_imports.extracted_text` 清空、`deleted_at` 设置，5 个
  `candidate_facts.source_import_id` 引用按既有软删除不变量保留。
- 四份 fixture 均执行相同的真实引擎、断网、确认、删除与残留 acceptance；
  `4 passed in 8.06s`。OCR/解析/Service 定向回归 `78 passed in 9.88s`，
  Python compile 和
  `git diff --check` 通过。
- 下一最小任务：进入 production PyInstaller sidecar 收集与 macOS/Windows
  离线 smoke。

## 2026-08-10：扫描 PDF 本地 OCR production macOS packaging

- `openworker-server.spec` 对 OCR 采用窄收集：RapidOCR 只收 package data，
  ONNX Runtime、OpenCV、NumPy 只收运行时动态库；同时打入 OCR manifest 和
  RapidOCR/ONNX Runtime package metadata。未使用 `collect_all("rapidocr")`
  扩大到可选 backend 或 transformer 工具。
- 新增 frozen sidecar 专用 `--verify-ocr-installation` 入口。自检在进程内禁用
  socket 连接，校验 production adapter、三模型 bytes/hash、中文 fixture OCR 和
  必需词，只输出 method、页码、engine identity 和布尔匹配结果，不输出 OCR 全文、
  私有路径或模型路径。
- 首次 frozen 自检安全失败，定位为 `importlib.metadata.version()` 在包内找不到
  RapidOCR/ONNX Runtime `.dist-info`。只补齐这两份 metadata 后自检通过，未放宽
  固定版本或模型哈希门禁。
- `build_dmg.sh` 在签名前自动检查 staged sidecar 中 manifest 恰好一份、三模型
  各一份且 bytes/hash 精确一致，并直接运行禁网 frozen OCR。该 Gate 在完整构建中
  连续通过。
- 本机补齐 Rust 1.97.1 与 CMake 4.4.2。第一轮 Tauri build 因既有
  `whisper-rs-sys` 缺 CMake 失败；安装构建工具后重跑成功，不涉及 OCR 或业务代码
  修改。
- `OCW_SKIP_NOTARIZE=1 packaging/build_dmg.sh` 完整通过 PyInstaller、staged OCR、
  GUI production build、Tauri `.app` 和 `hdiutil` DMG。只读挂载 DMG 后，从镜像
  内 `OpenWorker.app/Contents/Resources/sidecar/openworker-server` 再次执行禁网
  OCR 成功；GUI 和 sidecar 均为 arm64。
- 产物 `OpenWorker_0.1.7_aarch64.dmg` 为 236,235,577 bytes，SHA-256
  `c5f83e738af36904a13aef6365e2f39678698f9398e170dae2de82c24c49f8ae`；
  定向 installation/offline acceptance 回归 `6 passed in 10.14s`。
- 当前 DMG 为 ad-hoc 签名、未 notarize 的本机验收包；没有 Apple Developer ID 和
  updater signing key，不能作为公开发布包。下一最小任务是镜像相同 Gate 到
  `build_windows.ps1`，完成 Windows x64 NSIS/MSI production packaging。

## 2026-08-10：申请支持材料 Gate A

- 按已批准的“申请支持材料与模拟面试”设计，先扩展现有确定性申请包，不新增
  数据库、MCP 工具、GUI 入口或第二套文件生命周期。
- 申请包从八章扩展为十一章，新增“自我介绍”“内推与 HR 沟通文本”和
  “申请 Checklist”。自我介绍与沟通文本只组合 `direct/related` 的已确认证据；
  `none` 要求不会变成候选人声明。
- Checklist 只把简历已确认、snapshot fresh、官方来源已记录和确定性编译通过
  标记为完成；官网复核、联系方式检查、事实核对、官网投递和岗位雷达状态更新
  保持未勾选。
- RED 为 `4 failed, 34 passed`，失败均由三个章节尚未实现触发。最小 GREEN 后
  Domain 与 Service 为 `52 passed`；Skill RED 因旧八章契约失败，更新后申请包、
  Service、MCP wrapper 与 Skill 定向回归 `72 passed in 3.86s`。
- `compileall` 和相关文件 `git diff --check` 通过。下一最小任务是 Mock
  Interview Domain RED：固定题量、Blueprint、单问题引用、隐藏评价、状态机和
  三份报告 Artifact 的纯函数契约。

## 2026-08-11：Mock Interview 文本闭环与真实 TurnEngine Gate

- Mock Interview 已贯通 schema v10、Domain、Repository/CAS、事务 Service、七个
  Career MCP 工具、`mock-interview` Skill、authenticated HTTP、岗位入口、
  `InterviewView`、Tauri capture-only WAV、Volcengine VoiceProvider、SecretStore
  设置和 ASR/TTS 降级 UX。Agent 推理继续使用 OpenWorker TurnEngine、Provider
  Router、Persona、Skill 和 MCP，没有在 Career Service 中建立第二套模型循环。
- 真实 Aiden 首轮暴露了“一个问号、两个语义请求”缺陷：
  `你好，请先简单介绍一下你自己，以及你为什么对 AI Agent 工程师这个岗位感兴趣？`
  旧 validator 只在超过两个问号时拒绝。按 TDD 新增真实问题 RED，确认
  `1 failed, 16 passed`；最小修复将显式问号上限收紧为一个，并拒绝“分句连接词 +
  新疑问/命令起始词”。Domain GREEN 为 `17 passed`，Service/MCP/HTTP 聚焦回归
  `41 passed`。
- 修复后的真实 Aiden/TurnEngine 首轮首先再次生成复合题，Career MCP 返回
  `QUESTION_VALIDATION_FAILED`；模型在同一工具循环中修正为
  `请先简单介绍一下你自己和你的技术背景。`，且数据库只保存这一条合法问题。
  这证明约束由 Domain 强制，而非只依赖 prompt。
- 使用隔离真实绑定完成五轮：
  - Session：`01b29b0c-3b43-4dc7-8713-5cb7bc861165`
  - Job：`eed4833d-92dd-4c32-9a87-bee5c356515c`
  - Resume：`1c822020-9b68-4500-942b-16d25141ecdd`
  - Snapshot：`233cf42e-e4c0-4f64-ba1a-b1a521a89c9d`
  - 模型：`aiden:deepseek-v4-flash`
  - 动作：`FOLLOW_UP → DEEP_DIVE → SWITCH_TOPIC → FOLLOW_UP → WRAP_UP`
  - 终态：`completed / idle / version 14`，5 个 turn 均有回答和隐藏评价。
- 五个问题全部重新通过当前 `validate_question()`；首题只使用 `INTRO`，其余 refs
  只使用 Blueprint 的 `requirement-2` 或 `requirement-3`。第 2 题直接追问上一轮
  的“质量验收”，满足自适应追问要求。面试回答未写回 Career Vault：
  `candidate_facts=3`、`candidate_profile=1`、`profile_versions=1`、
  `resume_imports=1`，且新增回答文本不在 fact/version JSON 中。
- 三份私有 Artifact 均为 `0600`，且目录内无 symlink：
  - `interview-report.md`：5,169 bytes，
    SHA-256 `8dbce36d8d84247bcc6347928c9f537afbdee2db45b35277f9488fc32fa4c704`
  - `transcript.md`：1,867 bytes，
    SHA-256 `7b3d3cd378bb29b4def4777cb7e56f6937e01f072618fe6998763e0e644d5911`
  - `session.json`：1,345 bytes，
    SHA-256 `d770b717dc64ec91def89497842aa93ec4d247975b9a9d8ef6b8a95102fb9f47`
- 对抗 Gate 覆盖 stale/mismatch、已删除简历、旧 CAS、重复回答、重复题号、未知
  refs、双问题 proposal、评分越界、敏感评价、供应商失败、畸形/超限音频、取消录音、
  TTS 失败降级、Artifact symlink 和报告发布失败。额外隔离删除简历 smoke 返回
  `RESUME_NOT_FOUND` 且 `interview_sessions=0`。schema 为 10，
  `PRAGMA foreign_key_check=[]`。
- 最终回归：
  - Mock Interview 后端聚焦：`73 passed, 1 warning`
  - 申请包与匹配回归：`75 passed`
  - GUI：39 files、`195 passed`
  - Rust STT：`6 passed`
  - `cargo check --manifest-path surfaces/gui/src-tauri/Cargo.toml` 通过
  - GUI production build、Python `compileall` 和 `git diff --check` 通过
  - 音频残留、secret assignment 文件和 group/world-readable Interview
    Artifact 均为 0
- 保留的非阻塞告警是既有 Starlette/httpx 弃用提示，以及 Vite 混合静态/动态导入
  和大 chunk 提示。当前 `.venv` 没有 `ruff` executable，未把该命令记为通过。
- **未通过的唯一发布 Gate：真实 Volcengine ASR/TTS。**
  `/v1/settings/voice-provider` 返回 `configured=false`，当前机器没有 Speech API
  Key（或 App ID + Access Token）、ASR Resource ID、TTS Resource ID 和 Speaker。
  fake transport、协议 framing、内存/错误/降级测试已通过，但不能替代真实云端
  smoke。获取独立 Speech 凭证后，下一最小任务是配置 SecretStore，录制指定中文
  句子、播放指定问题并记录延迟与 request ID；通过前不得把 Mock Interview 整体
  标记为完成。

## 2026-08-11：Mock Interview 权威 Conversation Binding Gate

- 真实 Career Agent Creation Workflow 暴露了信任边界缺陷：模型把
  `current-career-conversation` 作为 `conversation_id` 传给 MCP，而真实
  OpenWorker Session ID 是 `career-conversation-entry`。因此模型可控文本不能
  作为会话身份。
- 修复后 `create_interview_session` 不再暴露 `conversation_id`，只创建空绑定
  Session。GUI 从成功的 Career create tool result 读取 UUID，以当前真实
  `sessionId` 通过 authenticated HTTP 和 CAS 绑定；冲突最多重新 GET 并重试一次，
  绑定成功后才打开 InterviewView。Service 只允许空值绑定一次，不同非空值返回
  `INTERVIEW_STATE_CONFLICT`。
- 目标 RED 精确命中 HTTP 404、缺失 GUI API/helper 和 App 未绑定。最小 GREEN：
  后端 `3 passed`，GUI `11 passed`。Mock Interview 后端聚焦回归更新为
  `78 passed, 1 warning`；GUI 全量为 40 files、`202 passed`；production build、
  Python `compileall` 和相关 `git diff --check` 通过。
- 第一次修复后真实 Aiden 回合证明绑定值正确，但暴露 Skill 歧义：GUI 绑定使
  create 返回的 version 过期，模型仍在同一回合抢跑首题；且连续使用错误的
  `question.text`。新增 Skill RED 后明确创建成功必须停止本轮，并固定首题对象为
  `question/topic/refs`，Skill 回归 `7 passed`。
- 最终隔离真实 TurnEngine 验收：
  - OpenWorker Session：
    `career-conversation-entry-authoritative`
  - InterviewSession：
    `baaad67b-8ac6-4edb-b245-933686620460`
  - create 参数仅包含 job/resume/snapshot、15 分钟和 standard，确认不含
    `conversation_id`
  - 创建回合在 create 后停止，没有 `start_mock_interview` 或源码探索
  - SQLite 持久化 `conversation_id` 精确等于真实 OpenWorker Session ID
  - 后续独立 Start Workflow 读取绑定后的 `expected_version=2`，首次即以
    `{"question", "topic", "refs"}` 成功保存首题，无 VERSION_CONFLICT
- 隔离 Server 已停止，`8877` 已释放；本轮和此前 conversation-entry 临时目录均已
  删除。真实 Volcengine ASR/TTS Gate 仍因缺少独立 Speech 凭证保持未完成。

## 2026-08-11：原始 Mock Interview 规格逐条完成审计

- 重新读取用户提供的 1347 行技术规格，不以实施计划勾选替代完成证明。逐项审计
  MVP Done Definition 的 23 条要求，并写入
  `docs/17_MOCK_INTERVIEW_COMPLETION_AUDIT.md`。
- 审计发现三个可本地补齐的遗漏：
  1. Transcript 分析没有显式输出重复表达、偏题程度和 STAR/结构完整度。
  2. 逐题复盘没有原始规格要求的“参考优化”。
  3. Skill 没有声明行为面试、产品场景、技术理解和可选公司动机题型。
- 按 TDD 先观察报告和 Skill 两组 RED。最小 GREEN 不新增模型调用：
  - 重复表达统计归一化后至少 4 字的重复句段。
  - 偏题程度由 `10 - relevance` 派生。
  - STAR/结构完整度复用 hidden `structure`。
  - 参考优化只建议按现有 `coaching_structure` 重组原回答，并明确只使用原回答和
    已确认事实。
  - 题型仅在当前 JD、简历、Blueprint 和 Previous Turns 支持时使用。
- 回归结果：
  - Mock Interview 后端聚焦：`78 passed, 1 warning`
  - GUI：40 files、`202 passed`
  - Rust STT：`6 passed`
  - GUI production build、Python compileall 和相关 `git diff --check` 通过
- 该次审计时完成度为：20 项已证明、2 项部分证明、1 项未完成。部分证明项是中文
  云端 ASR 和 TTS；未完成项是至少五轮真实语音面试。当时 SecretStore
  `configured_auth=false`，ASR/TTS Resource ID 和 Speaker 均为空，不能用 fake
  transport 结果替代真实 Voice Gate；下一节记录该 Gate 的后续关闭证据。

## 2026-08-11：豆包语音 2.0 真实 Voice Gate

- 用户提供了同一豆包语音应用的旧版控制台认证，并已开通：
  - 豆包流式语音识别模型 2.0 小时版。
  - 豆包语音合成模型 2.0 字符版。
- 根据官方接入文档将生产配置修正为 ASR
  `volc.seedasr.sauc.duration`、TTS `seed-tts-2.0`，并选择官方 2.0
  “儒雅逸辰”标准面试官音色。只保存 App ID 与 Access Token；截图中的 Secret Key
  不用于当前协议。SecretStore 保持 `0600`，凭证未进入 Git、日志或 Artifact。
- 真实单项 smoke：
  - TTS 返回 29,037 bytes MP3，约 2,741 ms。
  - TTS→内存 PCM16 WAV→真实 ASR 返回 30 字 transcript，约 8,753 ms；
    `OpenWorker` 和“求职 Agent”均保留。
  - ASR request/log ID：
    `51c4148b-1835-4633-91c2-7de137ba9d97` /
    `202608110556202124F38096769BC1BBA9`
  - TTS request/log ID：
    `beed0d10-a1bc-49c8-a85d-3c6378b1a106` /
    `20260811055618137ECC92F2FBD7712998`
- 隔离真实 Aiden/TurnEngine 五轮云端语音闭环通过：
  - Conversation：`career-real-voice-five-turns`
  - Interview：`24c52cb6-4577-461d-8062-08b0fcde33a8`
  - 动作：`FOLLOW_UP → FOLLOW_UP → SWITCH_TOPIC → FOLLOW_UP → WRAP_UP`
  - 终态：`completed / idle / version 15`
  - 五题 TTS 延迟 1,261–1,874 ms；五次 ASR 延迟 12,093–16,624 ms。
  - 五轮 transcript 为 43–69 字，每题只有一个合法 Blueprint ref。
- 三份 Artifact 均为 `0600`：
  - report SHA-256：
    `13c5de0fa649221e96b01992971318ba0612d44f685257b100e140e873c915de`
  - transcript SHA-256：
    `43f2b86e4d4ac5a4efd5a704224a99648c82f636ec158d9a1d162616a11156f0`
  - session SHA-256：
    `51d61728449f19c73287761aea29bea6ccbb0991a53e84dbca4b7eb9d3a4788e`
- 隐私审计：凭证泄漏文件、音频残留、Career Vault 回写、Artifact symlink 和外键
  违规全部为 0。隔离 Server 和数据库/state 已删除，`8878` 已释放。
- 原始规格 23 项 MVP Done Definition 现全部有当前状态证据。五轮云端音频由自动
  验收生成；物理麦克风采集由 Rust capture 与 GUI 测试覆盖，本轮没有真人现场朗读。

## 2026-08-11：岗位模拟面试双入口与启动无反应修复

- 岗位列表中的每条 JD 和岗位详情标题区现在都有独立“模拟面试”入口。两个入口共用
  同一设置弹层；如果所选简历没有 fresh 匹配，GUI 先调用现有匹配 API 生成快照，再
  创建 Interview。`CareerJobMatchPanel` 内的旧入口已移除，避免三套状态并存。
- 浏览器复现确认“开始面试无反应”有三个连续原因：
  1. 真实 Career Persona 属于 `code` family，但岗位启动时把 `workspace` 清空，
     Session 连接 effect 因工作区门禁直接返回。
  2. MCP 首次调用的标准权限审批只出现在隐藏的对话/收件箱，专用面试页不可见。
  3. `InterviewView` 把 `ready` 错判为完成态，第一次 refresh 后清空 pending，
     导致首题生成后不再轮询。
- 修复保持 OpenWorker 安全边界：
  - 创建 Interview 前要求当前可信 workspace，并在新 Career Conversation 中保留。
  - 权限审批继续使用标准 `ApprovalCard` 和 `Session.approve()`，只把卡片原地展示在
    InterviewView 上，不自动批准。
  - 只有 `completed/cancelled/failed` 停止首题轮询；`ready` 继续显示
    “面试官正在准备第一题…”。
- TDD 证据：
  - 双入口、自动 fresh 匹配、去重、workspace、审批和轮询均先观察目标 RED。
  - 相关 GUI：4 files、`30 passed`。
  - GUI 全量：40 files、`206 passed`。
  - `npm run build` 通过；保留既有 Vite 混合导入和大 chunk 警告。
- 真实浏览器最终验收：
  - 列表与详情入口均存在，设置弹层显示已确认简历、时长和难度。
  - Interview `dc6fbc46-3180-4510-91a9-e2d2589a6669` 在专用页显示连续准备状态。
  - 两次 MCP 审批均在专用页原地完成。
  - 批准后自动展示第 1 题“请简单介绍一下你自己。”，TTS 请求成功，控制台 0 error。

## 2026-08-11：浏览器模拟面试录音

- 浏览器版 `InterviewView` 现已复用既有豆包 ASR HTTP 接口，不再只在 Tauri
  桌面环境显示录音入口。运行时适配器保留原 Rust/Tauri capture，同时为浏览器选择
  `getUserMedia + AudioWorklet`。
- 浏览器采集只在内存中处理音频：
  - AudioWorklet 发送 mono Float32 分片与 RMS level。
  - 主线程线性重采样为 16 kHz，编码 signed PCM16 和标准 RIFF/WAVE。
  - 5 分钟约 9.6 MB，低于后端 20 MB / 300 秒门禁。
  - 停止、取消、切题、卸载和权限等待期间离开页面都会停止 track、断开 node、
    关闭 AudioContext、清空分片和 timer。
  - 不创建音频文件、音频 Blob URL 或浏览器持久化记录；ASR 文本只写入可编辑草稿，
    不自动提交。
- `VoiceRecordingMeter` 改为接收外部标准化 level，Browser/Tauri 共用。普通
  Composer 将既有 `dictation_level` 轮询上移到调用方，桌面语音波形行为保持不变。
- TDD 证据：
  - 48 kHz / 44.1 kHz 重采样、PCM16 clamp、WAV header/data length。
  - getUserMedia 请求时机、level、stop/cancel、空音频、重复 start、权限错误、
    300 秒触发和权限返回晚于取消的竞态。
  - Browser/Tauri 运行时选择、桌面 level polling。
  - 浏览器入口、ASR 可编辑草稿、取消不调用 ASR、不支持提示、中文权限错误、
    自动停止和卸载清理。
  - 真实浏览器发现非有限 level 会产生 `height: NaN`，补充 RED 后在波形边界归零。
- 验证结果：
  - 定向录音与 UI：5 files、`38 passed`。
  - GUI 全量：42 files、`230 passed`。
  - `npm run build` 和 `git diff --check` 通过；仅保留既有 Vite 混合导入和大
    chunk 警告。
- 真实浏览器检查：
  - `http://localhost:1420` 为安全上下文。
  - `getUserMedia`、`AudioContext`、`audioWorklet`、`AudioWorkletNode` 均可用。
  - 新建 Interview `6a79aeaf-defb-44c3-aa41-bd1625a7f3ea`，经两次标准 MCP
    审批后显示第一题和浏览器“开始录音”按钮。
  - IDE 托管浏览器点击后停在 macOS/Chrome 系统麦克风授权，自动化无法代替用户
    允许权限或提供真人语音。因此“真人朗读 → WAV → 豆包 ASR → 可编辑草稿”仍是
    明确的设备级手工 Gate，未用 fake 音频冒充通过。

## 2026-08-11：JD/简历驱动的面试智能

- 新 InterviewSession 升级为 Blueprint v2。确定性 Domain 根据当前 JD 分类
  `algorithm/engineering/product/general`，从已确认简历生成最多 16 张脱敏
  `evidence_cards`，并构建带 refs、岗位维度和最大深度的 `probe_plan`。
- 首题不再固定为自我介绍。有可见证据时必须同时引用岗位 requirement 和简历
  fact path；无证据时只允许岗位知识/场景题，禁止暗示候选人做过相关项目。
- schema 升级至 v11，InterviewTurn 新增 nullable 的 `question_topic`、
  `probe_target`、`probe_dimension` 和 `depth_level`。v10 历史 Turn 升级后四列
  均为 null；v1 Blueprint 继续走 legacy validator。
- Service 创建 Session 时通过 `ResumeRepository.get_resume_match_input()` 读取
  已确认 sections，不保存完整简历。首题和后续题均由 Service 校验 target、
  dimension、depth、refs 和动作转换后原子持久化。
- Career Persona 只增加长期面试边界；`mock-interview` Skill 读取 Blueprint v2，
  按算法、研发、产品维度连续深挖；GUI 启动 Prompt 改为 JD + 已确认简历驱动。
- 对抗审查覆盖敏感字段、混合岗位、无证据退化、不可见 direct evidence、伪造 ref、
  复合问题、深度 1→3 跳跃、同 target 的 `SWITCH_TOPIC` 和 v1 历史兼容。额外发现
  hard gap 可能排在普通 evidence target 前，已修正 Skill 为首题选择
  “最高优先且有 resume evidence 的 target”。
- 三岗位离线 Gate 使用算法、研发、产品固定 fixture，均通过首题双引用、岗位专属
  dimension、同 target 深度 1→2 和 Blueprint 隐私检查：`3 passed`。
- 最终验证：
  - Career 后端：`502 passed`。
  - 通用后端（排除未安装的 Bedrock optional extra）：`1159 passed, 1 skipped`。
  - GUI：42 files、`230 passed`；`npm run build` 通过。
  - schema v11、`PRAGMA foreign_key_check` 为 0；Python `compileall` 和
    `git diff --check` 通过。
- 完整通用测试另有 7 项 Bedrock 失败，原因是当前 `.venv` 未安装
  `boto3/botocore`，与本次面试改动无关。合并两个测试根目录会因同名
  `test_server.py` 产生 pytest import collision，因此按目录分别执行。
- 本轮尚未运行真实 Aiden 算法/研发/产品三场 TurnEngine Gate，不能用离线 fixture
  冒充真实模型通过。下一最小任务是执行三场至少五轮真实模型面试并记录 Session、
  depth chain、role-specific dimensions、Artifact hash 和隐私结果。

## 2026-08-12：JD/简历驱动面试真实三岗位 Gate

- 使用真实模型 `aiden:deepseek-v4-flash`，分别完成算法、研发、产品岗位各五轮
  模拟面试。三场均由 AI 生成首题、隐藏评价、后续动作和复盘报告，不使用固定问题
  或伪造模型响应。
- 算法岗位 Session `ca64e2c0-7e31-44da-bff1-7fc8f3b204d0`：
  - `project[0]` 从 context 1 连续深挖到 personal_contribution 2、
    evaluation 3，再切换到 requirement-1 的 context 1、optimization 2。
  - report/session/transcript SHA-256 分别为
    `e39df927f7acb7200a5042a9fb1542e87cbd656e51b9ab9a001815371fdb69b3`、
    `6e824d5dc355fd02af580b795cdb93c316f58f1dd1b9e003e144a83298efd287`、
    `4b31a3d3e2075f81432453a301038fa0758cf6ea8224df1f93bc711c228c9e36`。
- 研发岗位 Session `2868eac7-a4dd-4cc4-9849-1cc344821655`：
  - `project[0]` 深挖到 depth 2，随后覆盖 concurrency、consistency 和
    architecture。
  - report/session/transcript SHA-256 分别为
    `69b9cf272ede7e4f186f981326a18b53c0a7dc7f26884f923a42d64d823acac5`、
    `cb53e9b1e13a36e54ab1255504f4463c430ac86af99afc2435a1b1d507dbb425`、
    `f481b5fc5a85be37a365772d8ecde879fc8973abdf385ccc2d0fb4815af831c6`。
- 产品岗位 Session `fc6dc0a6-df39-4f32-aa85-a9b0d0cd3755`：
  - `project[0]` 从 context 1 深挖到 personal_contribution 2、
    evaluation 3，再切换到 role-scenario 的 user_problem 1、tradeoff 2。
  - report/session/transcript SHA-256 分别为
    `257cdbf5aef41e393835da8a8c90bb0a7dedcddd475f6a4de06aca4dc44c8f66`、
    `245eed8d5ed37f79fe2705023184b92f912302b47bc138247e13c37f8956cc8f`、
    `b6acaa3f19d6777fbc3ac0d835033a7e4b277798e8a8ce03e6af3f21a61b8d4a`。
- 三场均生成 `interview-report.md`、`session.json` 和 `transcript.md`，
  `privacy_passed=true`；临时业务数据库和正式 Artifact 在每场结束后删除，只保留
  不含简历敏感值的验收摘要及哈希。
- 真实产品场第一次运行暴露 Prompt 缺口：Skill 没有明确 `issues`、
  `coaching_structure`、`fact_refs` 必须是字符串数组，AI 连续提交非法评价后停在
  evaluating。先增加 Skill 静态合同 RED，再补完整 evaluation JSON 形状；重跑后
  五次回答均成功评价并完成报告。
- 真实 Gate 同时证明确定性门禁可拒绝首题缺少岗位名称、越界引用和复合问题，且
  Service 会把具体违规原因返回 AI 纠正。剩余质量风险是模型首题经常需要多次重写；
  算法首题“包括项目背景以及个人工作”虽只有一个句号层级，语义上仍接近两个回答
  要求，后续应增加文本与单一 probe dimension 的一致性 Gate。
- 收尾回归：面试 Domain/Repository/Service/Tools、三岗位离线 Gate、Skill 和
  Persona 合同共 `77 passed`；GUI 面试启动 Prompt `9 passed`；Python
  `compileall` 与全工作区 `git diff --check` 通过。

## 2026-08-12：单问题单深挖维度质量门禁

- Blueprint v2 问题新增高置信、确定性的跨维度文本校验。只分析“以及、并且、
  同时、并介绍”等明确并列片段；不同片段命中不同维度时拒绝，同一维度内的多个
  限定项继续允许。Blueprint v1 行为不变。
- TDD 直接复现真实漏网句“项目背景以及个人负责工作”：修改前定向测试
  `2 failed, 5 passed`，实现后 `7 passed`。对抗样例覆盖：
  - context + personal_contribution。
  - architecture + performance。
  - strategy + metrics。
  - context 内“背景 + 业务约束”和 performance 内“延迟 + 吞吐”放行。
- `mock-interview` Skill 明确问题文本只能索取当前一个 `probe_dimension`，并要求
  WRAP_UP 前至少覆盖一个岗位专属维度，避免真实模型只使用 context 等通用维度。
- 真实算法五轮 Gate 最终通过：
  - Session：`ee8bd4b7-b0fa-4293-b30a-01d655c05cba`。
  - 首题只询问推理服务优化项目启动的业务问题，对应 `context`。
  - depth chain：project context 1 → personal_contribution 2；
    requirement-2 context 1 → evaluation 2；role-scenario inference 1。
  - 新门禁在真实生成中实际拒绝过
    `question text conflicts with probe dimension`。
  - report/session/transcript SHA-256 分别为
    `dab83a0387e0230b2c92ea79c00acda14f6de97c1884bb13ed29edfb1d10dd33`、
    `f82c29a3f81d2e685794112972622eb11a2f69148917335329d37daadfdfa9bc`、
    `583c5867a0259b0ddea941fb9030ebc006dbbcbd0e262278de5bb3172ac2cd71`；
    `privacy_passed=true`。
- 真实 Gate 同时暴露隐私测试误报：将整个 Session JSON 扫描时，随机 UUID 的数字
  片段可能被压缩成手机号形状。新增确定性 RED 后，验收脚本只扫描岗位、Blueprint
  和 Turn 用户内容；机器 ID 不再参与文本隐私判断，回答中的真实手机号仍会失败。
- 剩余非阻塞稳定性风险：模型偶尔先生成复合问题、读取规则源码，或向工具额外传入
  `_raw`；当前均被工具 schema/Domain 门禁拒绝，非法内容不会持久化。后续最小任务
  是限制真实验收 Agent 的通用源码工具，并在工具适配层拒绝未知参数前返回更明确
  的结构化提示。
- 最终聚焦回归 `85 passed`；Python `compileall`、全工作区
  `git diff --check` 和调试残留扫描通过。

## 2026-08-12：标准对话内模拟面试（方案 A）

- 模拟面试不再切换到独立 GUI surface。岗位入口创建 Career Conversation 和
  InterviewSession 后保持标准 Transcript、Composer、审批卡与最近会话路径。
- Repository/Service 新增按 `conversation_id` 恢复，并在
  `BEGIN IMMEDIATE` 事务内禁止一个 Conversation 创建或绑定第二场面试。
  `GET /v1/career/interviews?conversation_id=...` 对普通会话稳定返回
  `{"ok": true, "interview": null}`。
- WebSocket Skill 消息支持受限的 `display` sidecar：内部 Prompt 继续携带
  Interview/Turn ID，用户气泡只显示“开始模拟面试”或原始回答；无 Skill、空值及
  超长 display 均拒绝。
- GUI 新增 `useConversationInterview`、`ConversationInterviewBar` 和
  `useInterviewVoice`。最近会话/刷新可恢复岗位、题目进度和当前中文深挖维度；
  ASR 只写入可编辑 Composer 草稿，不自动提交；切题和卸载会取消录音并释放 TTS
  URL。
- 第一轮完成后会话确定性命名为 `模拟面试 · {岗位}`；完成报告后同一 Conversation
  仍可继续追问复盘。
- TDD RED 证据：
  - Repository：缺少反向查询，`1 failed`。
  - Service：缺少查询与唯一绑定，`3 failed, 1 passed`。
  - HTTP：collection GET 返回 `405`。
  - display sidecar：仍显示完整内部 Prompt。
  - App：5 个新流程断言落入旧 `InterviewView`。
  - 语音 Hook/Composer 插槽：模块不存在或控件不渲染。
- 最终验证：
  - 面试后端集中回归：`92 passed`。
  - GUI 完整回归：45 files、`244 passed`。
  - Conversation-native 重点 GUI：`17 passed`。
  - `npm run build`、Python `compileall`、`git diff --check` 通过；仅保留既有
    Vite 混合导入和大 chunk 警告。
- 旧 `InterviewView.tsx` 及测试已无生产引用。因文件包含此前未提交工作，本轮未
  直接删除，避免在共享工作树误删用户改动；运行时只有标准 Conversation 路径。
- 真实浏览器运行态 Gate：
  - Conversation `91f26765-2d1`，Interview
    `c6f1f47e-c237-4325-a994-d77e9a1242ae`，岗位为
    `美团 · Agent Harness 工程师`。
  - 岗位入口后未离开标准 Conversation；状态条、Transcript、Composer、标准
    审批卡、浏览器录音按钮同时可见。
  - 启动气泡只显示“开始模拟面试”；第一轮测试回答只显示原文，页面正文不含该
    Interview ID。内部工具仍收到完整 Session/Turn 参数。
  - 首题在 8 次非法尝试后第 9 次通过单维度门禁；非法问题均未持久化。真实风险为
    首题生成稳定性偏低，不是 Conversation 迁移回归。
  - 第一轮已评价并生成 FOLLOW_UP 第二题，Session 当前为
    `in_progress / waiting_for_answer / version=4`。
  - 刷新及新标签冷启动均恢复标题 `模拟面试 · Agent Harness 工程师`、状态条、
    第一题、回答和第二题；新标签控制台 0 error，仅 React DevTools info。
  - TTS `/voice/synthesize` 返回 200，浏览器“开始录音”按钮可见；未请求系统麦克风
    权限或使用假音频，因此真人 ASR 仍保持为设备级待验收项。

## 2026-08-13：全局 Conversation 语音输入与暂停问题播报

- 所有标准 Conversation 现在共用 `useConversationVoice` 和
  `ConversationVoiceControl`。Career、Cowork、Code 等 Agent 均通过同一个
  Composer 入口获得语音输入，不再受模拟面试状态限制。
- 浏览器继续复用内存 AudioWorklet 录音和豆包 ASR；Tauri 继续使用本地 Whisper。
  两条路径的识别结果只写入可编辑草稿，不自动发送。
- 浏览器状态机固定为
  `idle → starting → recording → transcribing → idle`。点击麦克风后在等待系统
  权限前同步进入 `starting`，用户可立即看到“正在请求麦克风权限…”；录音和识别
  阶段分别显示“正在录音”和“正在识别…”。
- Conversation 切换或组件卸载会递增捕获 epoch 并取消录音，避免旧会话的异步权限
  或识别结果写入新会话。
- 标准 Conversation 生产路径已移除 `useInterviewVoice`、问题自动 TTS 和
  `ConversationInterviewBar` 的“重播问题”按钮。旧 `InterviewView` 仍无生产引用，
  因共享工作树已有改动继续保留，不作为当前运行路径。
- TDD RED 证据：
  - `useConversationVoice` 和 `ConversationVoiceControl` 初始均因模块不存在失败。
  - Composer 新契约有 `4 failed, 4 passed`：三类 Agent 不渲染通用入口，Tauri
    仍显示英文 `Starting microphone…`。
  - App 普通 Career Conversation 找不到“开始语音输入”。
  - 播放移除测试确认旧状态条仍显示“重播问题”，等待回答时合成 API 被调用 1 次。
  - 对抗性并发测试确认识别期间切换 Conversation 会把旧 transcript 回填 1 次；
    加入 epoch 校验后旧结果被丢弃。
- GREEN 与回归证据：
  - 状态 Hook `5 passed`；控件 `3 passed`；Composer `8 passed`。
  - 语音/面试聚焦回归 `44 passed`。
  - GUI 全量 `47 files / 256 passed`。
  - `npm run build`、Python `compileall`、`git diff --check` 均通过；仅保留既有
    Vite 混合导入和大 chunk 警告。
- 真实浏览器 Gate：
  - 现有模拟面试 Conversation 与普通新 Career Conversation 均显示
    “开始语音输入”。
  - 点击后立即显示“正在请求麦克风权限…”；切换 Conversation 后恢复 idle 控件。
  - 模拟面试状态条没有“重播问题”；捕获的 100 条网络请求中没有
    `/voice/synthesize`；控制台 0 error，仅 React DevTools info。
  - IDE 托管浏览器不能代替用户允许系统麦克风权限。因此“真人朗读 → 豆包 ASR →
    可编辑草稿且不自动发送”仍是唯一未完成的设备 Gate。

## 2026-08-14：项目文档治理与清理

- 新增 `docs/README.md` 作为文档权威入口，明确当前实现、文档优先级、运维手册、
  历史证据、剩余工作和维护规则。
- 更新 `AGENTS.md`、`CODEX_START_HERE.md` 和根 README，移除“从 Stage 0
  重新开始”、早期 MCP mock 里程碑和“第一版不做语音面试”等过时指引。
- 更新范围、产品需求、OpenWorker 集成、架构、数据/MCP、实施路线、测试验收、
  部署、backlog 和合规文档，使其反映 schema v11、Career Vault、材料、模拟面试
  和全局语音输入。
- `06_IMPLEMENTATION_PLAN.md` 将 Stage 0–10 明确标记为历史启动计划，不暗示云部署
  等可选项已经完成；`09_CODEX_TASK_BACKLOG.md` 只把 OC-101–OC-105 作为当前任务，
  并为每项链接权威规格或运行手册。
- 根 README 删除易过期的逐公司岗位数量和耗时，改为引用来源覆盖矩阵；源码启动
  说明明确要求从 OpenCareer Fork checkout 运行，不再引导 clone 上游空白仓库。
- 删除无引用、可自动再生成的根目录 `FILE_MANIFEST.txt`。保留 source notes、OCR
  Gate、已批准规格、TDD 计划和开发日志，因为它们仍是合规、决策或验收证据。
- 读者测试发现并修复：四方向/五任务口径、历史 Stage 完成状态、backlog 规格链接、
  README 实时数字、上游 clone 指引和简化目录误读。
- 验证：`docs/README.md` 相对链接检查通过；过时阶段语句扫描无命中；
  `FILE_MANIFEST.txt` 无残留引用；`git diff --check` 通过。

## 2026-08-17：M1a-1 请求身份上下文

- 读取并校正外部《OpenCareer M1 多租户改造方案（文件级实施计划）》，保存仓库内
  TDD 计划：
  `docs/superpowers/plans/2026-08-17-m1-multi-tenant.md`。
- 新增 `coworker/server/identity.py`：
  - 桌面无鉴权配置时解析为 `Principal(user_id="local", via="local")`。
  - 保留当前 `COWORKER_API_TOKEN` legacy 行为，兼容 sidecar 自动生成 token。
  - `OPENCAR_USER_TOKENS` 非空时具有更高优先级，legacy token 必须失效。
  - token 使用 `secrets.compare_digest`；错误配置和跨用户重复 token 均 fail-closed。
- HTTP 鉴权成功后写入 `request.state.principal`；tokenless health/callback 路由保持
  原行为。带有效用户 token 的 health 仍可读取完整健康信息。
- 两个 WebSocket 入口在原有精确 Origin 门禁后解析身份，写入
  `ws.state.principal`；错误 token 仍以 1008 拒绝，握手只返回 `openworker`
  子协议，不回显用户 token。
- TDD RED 证据：
  - 身份模块不存在，测试 collection 失败。
  - HTTP 用户 token 返回 401。
  - WS 用户 token 返回 1008。
  - 非空但错误的 token 表错误回退接受 legacy。
  - 同一 token 绑定两个用户时错误归入第一个用户。
- 最终验证：
  - 身份、Alpha、Cloud、Server 聚焦回归：`76 passed`。
  - `python -m coworker.server.run --help` 通过。
  - Crawler CLI 离线列出 34 个来源。
  - Alpha 前端类型检查与 `vite build --mode alpha` 通过，产物约 3 MB。
  - Python `compileall`、`git diff --check` 和安全不变量扫描通过。
- 当前边界：
  - M1a-1 只把身份放入请求上下文，没有改变 Career 数据目录、SessionManager、
    MCP 子进程或部署编排，因此尚未提供多租户数据隔离。
  - 本机没有 Docker，M0 的服务器镜像/Compose/WebSocket 真实 Gate 仍需在服务器执行。
  - 对 `http://203.0.113.10:18080/_openworker/v1/health` 的只读探测 8 秒超时；
    SSH 主机可达但当前环境无可用认证，返回 `Permission denied`。未同步代码、未重启
    容器、未修改服务器。
  - 下一步先完成 M0 服务器 Gate，再实施 M1a-2 按用户隔离 Career 数据和私有简历。

## 2026-08-14：隔离式浏览器 Alpha 与 Cloudflare Quick Tunnel

- 新增 `OPENCAR_ALPHA_TEST=1` 服务端策略：公开入口仅展示 Career Persona；拒绝
  工作区、设置、Provider、连接器、MCP、自动化、Memory、Browser、OpenAI 兼容
  endpoint，以及本机目录/Artifact reveal 等管理操作。WebSocket 只接受独立 Alpha
  workspace 的 Career 会话，并在创建后移除所有工具与任何 session allowlist。
- 新增 `scripts/run_alpha_quick_tunnel.sh`：使用独立 state、Career data 与 workspace，
  写入无个人信息的三条示例 JD，自动信任仅该 workspace，并使用 Alpha Vite 同源代理。
  浏览器不会获得 sidecar token，REST/WS 都由本机 Vite 代理添加认证；正常开发服务
  保持 `8765/1420`，Alpha 默认使用 `8766/1421`。
- 新增 `scripts/seed_alpha_demo.py` 和 `tests/test_alpha_mode.py`。验证：
  `tests/test_alpha_mode.py tests/test_server.py -q` 为 `54 passed`；Alpha Vite
  production build 通过；shell syntax、Python compile 与 `git diff --check` 通过。
- 安装 Cloudflare `cloudflared 2026.8.1` 后，实际启动流程已到达 Quick Tunnel 命令，
  但当前受控 Agent 运行环境向长连接进程发送 `SIGKILL`，未生成公网 URL。未将此
  视作 Tunnel 验收通过；应在开发者自己的终端运行脚本以完成 URL 生成与手机蜂窝网络
  验收。

### 合规约束更新

- 用户确认公司合规不允许使用 Cloudflare。未生成、未分享任何公网 URL；Quick Tunnel
  启动脚本已改为 `scripts/run_alpha_local.sh`，只启动隔离的 localhost Alpha，不再调用
  `cloudflared`。后续多用户测试必须先确定公司批准的内网或发布渠道。

## 2026-08-18：M0 真实服务器 Gate 与 Alpha DeepSeek 会话修复

- 阿里云 IP 形态完成首次真实部署：后端与 Caddy 容器健康，`/v1/health` 返回
  `model=deepseek:deepseek-v4-flash`，前端首页、REST、Alpha 403 门禁和 WebSocket
  子协议均通过；腾讯微信事业群公开 JSON 来源抓取 283 条真实岗位。
- 修复四层 Alpha 会话故障，未放宽 Origin、token、workspace 或本机控制能力限制：
  1. `/v1/providers`、`/v1/settings` 的 403 错误对象被前端当数组使用，触发
     `.find()` / `.map()` 未捕获异常并白屏；现归一化为安全返回形状。
  2. Alpha 无法读取本地模型设置时误判“未连接模型”，Composer 拦截消息；现由
     Alpha 策略采用后端健康信息。
  3. Career 会话未采用 `/health.default_workspace`，导致 `/ws/session` 因
     workspace 不匹配被 1008 拒绝；Alpha 现使用后端专用 `/data/workspace`。
  4. 前端硬编码 `aiden:deepseek-v4-flash` 覆盖后端模型，容器报
     `Aiden CLI was not found`；Alpha 现明确使用 health 返回的
     `deepseek:deepseek-v4-flash`，桌面 Aiden 策略保持不变。
- TDD 与回归：
  - 新增 Alpha 403 fetcher 回归测试及 Alpha 模型策略测试。
  - GUI `48 files / 259 passed`，`npx tsc`、`vite build --mode alpha`、
    `git diff --check` 通过。
- 真实浏览器最终验收：
  - 线上产物 `index-DiQbsrzf.js`；模型控件显示 `deepseek-v4-flash`。
  - 用户消息“请只回复：DeepSeek 最终验收通过”得到同文 AI 回复。
  - 后端 `/ws/session?...workspace=/data/workspace&agent=career` 为 accepted，
    最近 5 分钟 `Aiden CLI was not found` 计数为 0。
- 本机缺少 Docker CLI 和 Python FastAPI 依赖，因此本机 Compose config 与
  `python3 -m coworker.server.run --help` 未执行成功；服务器容器健康和真实浏览器
  Gate 已覆盖本次部署路径。

## 2026-08-18：云端简历预览、DSML Tool Call 与隐私 Gate

- DeepSeek V4 Flash 将工具调用输出为 DSML 文本而不是 OpenAI 结构化
  `tool_calls`。Provider 现只在本轮已提供的工具白名单内恢复 DSML，并仅对
  `load_skill` 做已观察到的 `skill -> name` 参数归一化；未知工具和无 schema
  调用继续拒绝。
- 真实诊断发现 Alpha WebSocket 原策略执行 `engine.registry.retain(set())`，
  导致模型实际收到 0 个工具。现改为显式 Career 产品工具 allowlist；Shell、通用
  文件、连接器、抓取、删除、`save_skill` 和未来新增 MCP 工具默认仍不可用。
- 真实浏览器完成简历导入只读链路：
  `load_skill -> get_resume_import_text -> preview_resume_import`，最终展示
  basic、education、experience、project、skill 五段掩码预览。持久化证据为
  `resume_previews=1`、`profile_versions=0`、`confirm_resume_sections=0`；
  未经用户批准没有确认任何分区。
- 对抗审查修复两项隐私泄漏：审批卡、工具摘要/raw 和 Inbox 不再显示上传 token、
  preview token 或 proposal 明文；专用导入的用户气泡使用安全中文 display，模型
  内部 handoff 仍保留完整 token。合成简历真实 UI Gate 中可见
  `Upload token:` 计数为 0。
- `career-resume-import` Skill 补齐 proposal 结构约束：`basic` 为对象，其余四段、
  `missing_fields` 和 `warnings` 为列表，避免模型依赖领域校验逐项试错。
- 真实浏览器附加验收：
  - DeepSeek 精确回复“OpenCareer 文字对话正常”。
  - 岗位雷达显示 286 个岗位，并可打开真实腾讯 AI 产品经理岗位。
  - 模拟面试设置因没有已确认简历正确禁用开始按钮并给出中文提示；未绕过事实门禁。
- 自动化证据：
  - GUI 全量 `48 files / 263 tests passed`，TypeScript 与 Alpha build 通过。
  - Alpha/Provider/Skill 聚焦 `47 passed`；Server + Skill API + Provider
    `105 passed`；Python compileall 与 `git diff --check` 通过。
- 剩余边界：必须等待用户逐区明确批准后，才能调用确认工具并继续真实模拟面试问答。

## 2026-08-18：云端真实五轮模拟面试与首题稳定性优化

- 用户明确批准 basic、education、experience、project、skill 五段后，真实调用
  `confirm_resume_sections`，生成完整档案 v1；岗位面试设置正确选中已确认简历并解锁
  “开始模拟面试”。
- 在公网 Alpha 对“微信读书产品部-AI产品经理”完成 10 分钟、标准难度、5 题真实
  文字闭环。Interview `f770e140-c129-4133-97a4-a92b812b8bf2` 在网络中断后通过
  刷新恢复 version 12，并继续完成 finish/report；三份官方 Artifact 均生成。
- 对抗回答覆盖模糊口径和缺少量化证据。报告将第四题评为 `7/7/4/2/2`、第五题评为
  `8/7/6/5/4`，准确指出指标口径矛盾、个人贡献边界模糊和证据不足。
- 真实链路暴露两项 Skill 决策缺陷：首题因复合问句和岗位名不精确产生多次重试；
  低证据回答后模型曾切换话题而非优先追问。未放宽 Question Validator。
- TDD 修复仅修改 `mock-interview/SKILL.md` 和 Skill 契约测试：
  - 问题不得有前置陈述，必须为单句且仅一个问号。
  - 首题必须原样包含 InterviewSession 的当前岗位标题。
  - `evidence <= 4` 或缺少指标口径/个人贡献时，当前 target 仍可深挖则禁止
    `SWITCH_TOPIC`，必须 `FOLLOW_UP` 或 `VERIFY_CLAIM`。
- 自动化回归：面试 Domain/Service/Tools/Acceptance/Skill `67 passed`；共享
  Server/Alpha/Provider `104 passed`；`git diff --check` 通过。
- 定点部署仅替换服务器持久卷中的 `mock-interview/SKILL.md`，最终 SHA-256 为
  `28c63d5dfbdc3f859fab660eb810a77a5ee9831a41d9f17a78d60cc0b1493465`；
  后端重启后 health 正常，未同步本地 M1 改动。
- 部署后真实复测：
  - 低证据回答得到 `evidence=2`，同一 `experience[0]` target 触发 FOLLOW_UP，
    下一题直接追问可量化结果。
  - 最终首题只执行 `load_skill -> get_interview_session ->
    start_mock_interview` 三步，一次保存，无校验重试。

## 2026-08-19：Exact Origin HTTP/WS 接线

- HTTP CORS 与 `/ws/session`、`/ws/events` 统一使用 `OriginPolicy`，不再通过正则
  允许任意 localhost 端口。桌面默认项改为明确列举的 Tauri Origin 和
  `localhost:1420` / `127.0.0.1:1420`。
- `OPENCAR_EXTRA_ORIGINS` 继续作为应急精确项，scheme、host、port 均参与匹配；
  wildcard、path、query、fragment、恶意域名后缀和未列出的本地端口均拒绝。
- 新增 PostgreSQL `identity.deployment_origins` 只读 Adapter。数据库不可用时，
  数据库 Origin 不进入策略，只保留桌面默认项与显式环境变量项。
- TDD RED 分别命中缺少策略构建器和 `localhost:1421` 被旧正则放行；GREEN 后
  Origin/PostgreSQL 聚焦 `19 passed`，Identity/Alpha `10 passed`，完整 Server
  `53 passed`，Python compileall 与 `git diff --check` 通过。
- 本轮只修改本地代码，尚未部署；线上 Alpha 仍运行原有精确环境变量配置。

## 2026-08-19：PostgreSQL Resume 与共享 Catalog 真实 Gate

- 云端 Resume/Profile 已按请求 Principal 使用 PostgreSQL：暂存、Blob 原件、预览、
  分区确认、Profile Facts/Versions、列表、元数据、单份删除和整档删除均受 RLS 与
  组合租户外键保护；桌面路径继续使用 SQLite/私有文件。
- Career MCP 子进程由每用户 `SessionManager` 注入固定
  `OPENCAR_PRINCIPAL_USER_ID`。Resume、Job、Tracking、Match、Interview 共用该
  Principal 的 PostgreSQL Adapter；云端缺 Principal 时 fail closed。
- SQLite→PostgreSQL 迁移补齐 Candidate Profile、Facts、Versions、Previews，并按
  公司 slug、来源业务键、岗位业务键和 Resume content hash 映射随机本地 ID；
  同源重跑与源文件变化重跑不复制 Match。
- 真实 PostgreSQL Resume/迁移/REST/本地兼容聚焦回归 `31 passed`；综合回归曾因
  Gate 库固定测试 ID 污染出现 2 项失败，隔离测试数据后定点 `2 passed`。
- 真实官方来源 dry-run：DeepSeek 33、小米 3,202、美团 2,182，共 5,417 条；滴滴在
  180 秒墙钟门槛超时并正确返回部分失败，未写失败来源。
- 独立 `opencareer-crawler:postgres-gate` 使用国内 requirements/wheel、阿里云
  pip/apt 与 npmmirror Playwright 构建成功，未替换线上镜像。
- 同机缓存回放首次 5,417 条耗时 31 秒；完整复跑耗时 8 秒，全部为 unchanged。
  Gate PostgreSQL 当前 5,420 active jobs，业务键重复 0；三源 latest run 均
  succeeded，7 个 Raw Snapshot Blob 的 Python SHA-256 校验错误数为 0。
- 线上 Alpha backend/caddy 未重启、未切换 `DATABASE_URL`，本轮 Gate 不影响当前
  公网 Alpha。

## 2026-08-19：Context 历史迁移与 Application Packet 入库

- `deploy/migrate_to_postgres.py` 新增 `--state-root` 模式。Conversation JSONL、
  Session metadata、Compaction、Workspace、Memory、Inbox、Automation/Run 分别写入
  `agent` 权威表；routing、mentions、subscriptions、wakes 原文件内容与 SHA-256
  写入 `agent.audit_events(event_type='legacy_context_snapshot')`。
- Context 迁移按相对路径和文件 SHA-256 生成稳定聚合 hash，并使用
  `opencareer_meta.data_migrations(source_kind='agent_context_state')` 保证同一快照
  幂等。生产 Repository 已真实恢复两条消息、Compaction、Memory、已解决 Inbox 和
  Automation。
- Application Packet 云端改为确定性编译后，在同一租户事务写
  `career.application_packets` 与用户 `blob.objects` Markdown；同输入通过确定性 ID
  与 advisory lock 只生成一条记录和一个 Blob。桌面未注入 Repository 时继续使用
  原有原子文件和 symlink 防护。
- `0004_application_packet_blob_integrity.sql` 将 Packet `blob_id` 提升为正式列，并
  用 `(user_id, blob_id)` 组合外键约束用户 Blob。历史无 Blob 的旧 Packet 保留
  `NULL`，不删除记录或伪造产物；所有新写入均提供非空 Blob。
- 真实 PostgreSQL 对抗验证覆盖：Alice/Bob 租户隔离、Packet/Blob SHA-256、同输入
  幂等、Blob 内容篡改拒绝和 MCP 固定 Principal。宽回归 `103 passed`，Schema +
  Packet 定点 `9 passed`，Context CLI/Repository `3 passed`。
- 工程 Gate：后端 `--help`、Crawler `--list`、TypeScript 和 alpha build 通过；
  `git diff --check` 与 Python compile 通过。本机仍无 Docker CLI，两个 Compose
  config 未执行。Alpha 未重启、未切换 PostgreSQL，本轮不影响线上。

## 2026-08-19：Tailored Resume 与 Export PostgreSQL/Blob 接线

- 新增 `0005_tailored_resume_exports.sql`：Draft 显式引用同租户 Match，Export
  使用 `(user_id, draft_id)` 组合外键，并以两个组合外键分别引用 DOCX/PDF 用户
  Blob；新表启用并强制 RLS。旧 Draft 仅在 Match 可验证时回填正式 snapshot 列。
- `PostgresTailoredResumeRepository` 保存完整 Draft 状态机、SQL CAS version、
  Export 元数据和 Blob 内容。Service 继续复用现有 evidence/freshness/confirmation
  规则；桌面未注入 Repository 时仍走 SQLite 与原子文件发布。
- 云端 Export 在事务外私有临时目录完成 DOCX/PDF 渲染和页数校验，再在一个短事务内
  写两份 Blob、Export 元数据并 CAS 标记 Draft exported。元数据失败会回滚两份
  Blob；同版本并发导出收敛为一条 Export 和两份 Blob。
- FastAPI 所有 Tailored list/get/update/confirm/export/download 路由改为使用
  `request.state.principal`。Career MCP 的 prepare/proposal 工厂复用同 Principal
  的 PostgreSQL Match 与 Draft Repository；confirm/export/download 仍不进入 MCP
  工具发现边界。
- SQLite→PostgreSQL 迁移新增 `--workspace-root`：读取真实 DOCX/PDF，拒绝 symlink、
  缺失和 SHA-256 不一致，再写 Blob 与 Export。Draft 同时归一化字段并使用 Match
  业务去重后的 ID 映射。
- PostgreSQL 时间戳在 Repository 边界统一序列化为 UTC `Z`，避免等价
  `TIMESTAMPTZ` 与 Resume JSON 字符串被误判 stale。
- 云端后端镜像新增 `libreoffice-writer` 与 `fonts-noto-cjk`，Crawler 镜像不增加
  该依赖。线上 Alpha 未重建、未重启，因此当前公网实例不受影响。
- 验收证据：Tailored/PostgreSQL 聚焦 `84 passed`；宽回归 `171 passed`；真实 REST
  完成 Alice 导出/下载且 Bob 同 export ID 被拒绝；Blob 篡改、双写回滚、并发幂等、
  历史导出迁移均通过。后端 `--help`、34 来源 Crawler 列表、TypeScript、alpha build、
  Python compile 与 `git diff --check` 通过。本机无 Docker CLI，Compose config 和
  新后端镜像真实构建未执行。

## 2026-08-19：四计划隔离服务器最终 Gate

- 影响范围：本轮只重建并重启隔离容器
  `opencareer-postgres-tailored-gate` 与静态 Gate Caddy。线上
  `opencareer-alpha-backend-a-1` 仍运行原镜像
  `sha256:063cfbe2…1668e`，health 为 `healthy`、restart count 为 `0`，未切换
  PostgreSQL、未重建、未重启。
- PostgreSQL Foundation / Context / Exact Origin：
  - 隔离后端 health 返回 `storage.mode=postgres`、`postgres=ready`、
    `redis=ready`；镜像 `sha256:9e2e9f8a…8d3cf` 以 UID `10001` 运行，
    `/usr/bin/libreoffice` 可用，restart count 为 `0`。
  - HTTP 精确 Origin Gate：允许入口 `200`，恶意域名后缀与外部 Origin 均 `403`，
    无 Origin 的同源请求 `200`；WebSocket 使用同一策略且未放宽 token。
  - Redis turn lease 新增 owner 查询与 CAS 替换。旧 owner 仍在 presence 时禁止抢占；
    presence 已消失时新连接可原子回收。真实预置
    `disconnected-gate-owner` 后，浏览器立即收到“孤儿租约恢复成功”，未等待
    300 秒 TTL。
  - Context 历史迁移、Application Packet、租户 RLS、Migration ledger 与 Blob
    完整性继续由 PostgreSQL 聚焦回归覆盖。
- PostgreSQL Job Catalog / Crawler：
  - 隔离数据库 `opencareer_gate_fresh` 的当前 SQL 结果为
    `jobs=10802`、`active=10802`、`job_versions=10769`、
    `crawl_sources=34`、`duplicate(source_id, external_job_id)=0`。
  - `python -m extensions.career_mcp.crawl_cli --list` 当前列出 34 个官方公开来源；
    云端只写共享 PostgreSQL Catalog，桌面默认 SQLite 路径保留。
- Interview Evaluation / Progress：
  - 从岗位入口创建真实 Interview
    `f76888e4-bad6-4648-ae94-c6af37008726`，绑定 Conversation
    `ff130d04-34a`，完成 5 轮对抗回答。SQL 终态为
    `status=completed`、`phase=idle`、`version=14`、`turns=5`。
  - 五题服务端分数依次为 `31 / 31 / 44 / 38 / 56`；每题均保存一个
    `question_score`、`primary_pain`、`reason`、`improvement`，且
    `target_competency` 与当前 `probe_dimension` 逐字一致。动作覆盖
    `FOLLOW_UP`、`SWITCH_TOPIC` 与 `WRAP_UP`，低分 target 达到
    `max_depth` 后可合法切题。
  - 报告、逐字稿、会话 Blob 分别为
    `8428e719-a4c3-4b36-a3e3-063049e8ddaf`、
    `12269560-ef6d-4d69-8409-956c04f149a7`、
    `4672d28a-98f9-4e8f-be59-b6cd8e45c816`。重新读取 BYTEA 后计算的 SHA-256
    分别与数据库值 `d4437c8b…3315`、`df801c40…d849`、
    `e6938ca0…cb31` 完全一致。
  - 桌面和 375x812 浏览器均真实检查。移动端采用单栏主对话、可关闭左侧覆盖层和
    全宽进度抽屉；五张题卡宽度 346 px，无重叠或横向滚动。Composer 的
    “执行前询问”、模型、语音与发送控件水平可读且互不覆盖；页面不存在“重播问题”
    或“提前结束”。
- Tailored Resume / Blob：
  - 真实 Export `c50317fe-2e9f-4f18-81fd-ecad726313a9` 绑定 Draft
    `ef09d2db-ef90-4581-a568-8de88b3aaba6`。浏览器真实请求 DOCX/PDF 下载接口。
  - DOCX Blob `dbd61b89-6c77-4f52-ad84-0d07708e89b3` 为 36,945 bytes，
    SHA-256 `f7935bd2…8ac0`；PDF Blob
    `8c03ea1b-ec9b-44f8-b9da-88f7119c1f1d` 为 50,387 bytes、1 页，
    SHA-256 `8fb65583…a4b8`。浏览器下载文件、PostgreSQL BYTEA 与元数据 SHA
    三方一致。
- 最终自动化 Gate：
  - GUI 全量：`49 files / 267 passed`。
  - 四计划 Python 聚焦：`179 passed, 9 skipped`；Compose/Origin/Alpha/Identity/
    Migration 补充组：`35 passed, 4 skipped`。Skip 均为未提供独立测试数据库的
    显式集成测试，真实 PostgreSQL 证据由隔离服务器 SQL 与浏览器 Gate 补足。
  - `npx tsc`、`vite build --mode alpha`、Python compileall、后端 `--help`、
    34 来源 CLI 与 `git diff --check` 通过；Alpha 产物为 3.0 MB。
- 计划逐项审计：
  - `2026-08-18-postgres-foundation.md` Task 1–7：依赖/Compose、版本迁移、RLS、
    Blob、Storage Factory/health、幂等迁移 CLI 和回归 Gate 均有实现与当前证据。
  - `2026-08-18-agent-context-and-origin.md` Task 1–8：Conversation、Compaction、
    Memory/Todo/Inbox/Automation、Session Skill hash、Context Manifest、
    RuntimeCoordinator、Exact Origin 和历史迁移均有生产 Adapter 与自动化覆盖。
  - `2026-08-18-postgres-job-catalog-crawler.md` Task 1–7：Repository、精确/全文搜索、
    可追溯 Match、单 PostgreSQL Crawler CLI、幂等迁移、34 来源 Gate 和隔离演练均
    完成。Task 8 的“公网生产切库”被本轮“不影响线上 Alpha”的明确约束替代；所有
    生产路径已在隔离服务器验证，但没有伪报公网切流。
  - `2026-08-18-interview-evaluation-progress.md` Task 1–8：评价 Skill、服务端
    0–100 计算、v2 持久化、报告、五题看板、未完成会话恢复、Skill hash 复用和
    真实五题 Gate 均完成。
  - `2026-08-19-tailored-resume-postgres-blob.md` Task 1–5：`0005`、Draft CAS、
    DOCX/PDF 双 Blob 原子发布、request-scoped REST/MCP 和历史 Export 迁移均完成。
- 剩余风险：`npm audit --omit=dev` 报告既有直接依赖 `xlsx` 1 个 high
  （SheetJS prototype pollution / ReDoS），当前 npm 包无 `fixAvailable`。本轮未升级
  或替换解析库，避免把无关大范围依赖迁移混入数据库和面试 Gate；后续应单独评估
  替换库及不可信工作簿输入边界。

## 2026-08-19：正式备份与隔离回滚演练

- 恢复点 ID：`20260819T072425Z`。服务器副本位于
  `/opt/opencareer-backups/20260819T072425Z`，离机副本位于
  `.local-state/backups/server/20260819T072425Z`；两端
  `sha256sum -c SHA256SUMS` 均通过。
- 备份集共 158 MiB（离机目录占用 169 MiB），包含：
  - Alpha 数据卷的 45 个文件和 3 个 SQLite Online Backup；
  - `opencareer_gate` 与 `opencareer_gate_fresh` 的 PostgreSQL custom dump；
  - 当前 Compose、Caddyfile、静态前端、Caddy data/config、Crawler cache；
  - 精确的旧 Alpha Docker image archive；
  - AES-256-CBC/PBKDF2 加密的 `.env`。
- `.env` 解密密钥只保留在离机副本，权限 `0600`；服务器临时密钥已删除。解密后
  SHA-256 与服务器当前 `.env` 完全一致，未在日志或对话中输出内容。
- SQLite/文件卷恢复到临时 Docker volume 后：
  - 45 个文件大小与 SHA-256 全匹配；
  - 3/3 SQLite `PRAGMA integrity_check=ok`；
  - 恢复文件 owner UID 为 `10001`；
  - 旧镜像无公网启动后 health 为 `ok`，读取到 286 个岗位、2 份简历和 5 张
    Coworker 状态表。
- PostgreSQL 两个 dump 分别恢复到临时数据库：
  - 两边均为 40/40 张业务表逐表行数完全一致；
  - Gate count manifest SHA-256 为 `2969c392…b7aad`；
  - Catalog count manifest SHA-256 为 `d18d30c0…92660d`；
  - Gate 7 个 Blob、Catalog 218 个 Blob 的源库/恢复库全量内容指纹一致；
  - Catalog 仍为 `10802 active / 34 sources / 0 duplicate business keys`。
- Catalog 超级用户视角存在 9 条既有对抗性篡改 Blob；应用可见的 79 条 Blob
  `sha_mismatch=0`。恢复库逐字节保留这 9 条源数据，没有把测试数据误修或误判为
  备份损坏。
- 恢复后的新后端认证 health 为
  `status=ok / postgres=ready / redis=ready`。随后执行隔离回滚动作：停止新后端，
  旧 Alpha 镜像与恢复卷继续健康；镜像归档重新加载后的 ID 仍为
  `sha256:063cfbe2…1668e`。
- 演练期间线上 `opencareer-alpha-backend-a-1` 始终运行原镜像，最终 health 为
  `healthy`、restart count 为 `0`，没有停止、替换或重启。演练临时容器、卷和两个
  临时数据库均已删除。
- 新增 [`18_BACKUP_AND_ROLLBACK_RUNBOOK.md`](18_BACKUP_AND_ROLLBACK_RUNBOOK.md)，
  固化 FORCE RLS dump、加密密钥分离、隔离恢复、切换 Gate 和不反向覆盖 SQLite 的
  回滚规则。

## 2026-08-19：最终停写备份与 PostgreSQL 生产切流

- 最终恢复点 ID 为 `20260819T103248Z`。服务器副本位于
  `/opt/opencareer-backups/20260819T103248Z`，离机副本位于
  `.local-state/backups/server/20260819T103248Z`；离机 28 个文件、约 209 MiB，
  `sha256sum -c SHA256SUMS` 全部通过。加密密钥仅在离机副本
  `meta/deploy.env.key` 保留，权限 `0600`，服务器副本已删除。
- 最终停写时间为 `2026-08-19T10:32:49Z`。新后端
  `opencareer-alpha-backend-pg-1` 使用镜像 `sha256:9e2e9f8a…8d3cf`，
  Caddy 反代到 `172.18.0.1:18765`。旧后端
  `opencareer-alpha-backend-a-1` 和原卷 `opencareer-alpha_data-a` 均保留，
  旧容器处于 stopped，可即时回滚；三者 restart count 都为 0。
- PostgreSQL 最终 SQL Gate：
  - Catalog `jobs=10802 / active=10802 / sources=34 / duplicate=0`；
  - 共享 Catalog 的 company/source/run/job/version/event/snapshot 及 79 个共享
    Blob 在迁移前后逐表计数完全一致；
  - Career 为 2 份 Resume、5 条 Candidate Fact、1 个 Profile Version、
    3 个 Interview Session、8 个 Turn、1 条 Match；
  - Context 为 10 个 Conversation、158 条 Message、1 条 Compaction；
  - 2 个用户 Blob 重算 SHA-256 mismatch 为 0；
  - adversarial user 可见 Resume、Conversation、用户 Blob 均为 0。
- 迁移过程中发现并修复三类真实旧数据兼容问题：
  - 同一岗位/简历有两个 `in_progress` 面试。全部历史保留，较旧会话确定性迁移为
    `cancelled/idle` 并写迁移原因，最新活动会话保持可恢复。
  - Compaction 的 `created_at` 可能是 Unix 浮点秒。迁移边界统一转为 UTC
    `datetime`，ISO 字符串保持原语义。
  - 已有共享 Catalog 时旧 SQLite 岗位不得再次入库。282 条旧岗位只映射到权威
    Catalog，4 条无租户引用的旧/演示岗位跳过；company/source/job/version/event
    均保持只读，若未命中岗位被用户数据引用则硬失败。
- 自动回滚实际覆盖了前端归档元数据、Docker mount 参数、活动面试唯一约束、
  Context 时间戳、Catalog 膨胀、RLS 清理口径和 WebSocket smoke 参数等失败点。
  每次失败均恢复旧前端、旧 Caddy 和旧后端，原 SQLite 卷未被覆盖。
- 最终 CLI smoke 通过 health、岗位、简历、面试、原件下载和带精确 Origin/workspace
  的 WebSocket。真实公网浏览器进一步确认岗位雷达显示 10,802、档案可读、面试进度
  可恢复，加载 `index-4spGwk6I.js`，控制台无错误且页面无横向溢出。
- 新后端最终 health 为
  `storage.mode=postgres / postgres=ready / redis=ready`。CLI WebSocket smoke
  在握手后立即关闭产生一条 `WebSocketDisconnect 1006` 日志；真实浏览器连接和
  后续 REST 均正常，该日志不是服务端崩溃或重启。

## 2026-08-19：模拟面试评价重试风暴熔断

- 真实 PostgreSQL Conversation `2si6lj8oaq4` 复现了 Answer Workflow 的旧故障：
  `get_next_interview_question` 连续猜测 `question_type` 和评价维度，并调用无关
  Career 工具探索参数。FastMCP 原 schema 把 `evaluation` 暴露为
  `additionalProperties=true` 的裸对象，没有 `version`、题型、维度或动作枚举。
- MCP 边界改为严格 Pydantic schema：
  - `version` 固定为 `2`；
  - `question_type` 仅允许 7 个正式题型；
  - `active_dimensions[].name` 仅允许 26 个正式评价维度；
  - `next_action` 仅允许 5 个状态机动作；
  - 评价和下一题对象均拒绝额外字段。
- `mock-interview` Answer Workflow 复用 `submit_interview_answer` 返回的完整 Session，
  不再无条件二次读取；评价失败最多修复一次，并禁止调用 `health_check`、岗位查询和
 来源工具探索 schema。评价 Skill 明确题型枚举和项目/简历题的分类规则。
- TurnEngine 增加结构化 validation retry rail：同一工具在一轮内第二次返回
  `QUESTION_VALIDATION_FAILED` 或 `EVALUATION_VALIDATION_FAILED` 后，以
  `tool_validation_retry_exhausted` 结束本轮，禁止第三次模型重试。普通字符串、数组
  和成功工具结果不受影响。
- TDD 证据：
  - 新 schema 与 Engine rail 测试先分别因缺少 enum、模型继续第三次调用而失败；
  - Engine/stop `27 passed`；
  - 面试/Skill/API `89 passed`；
  - Server 工具/WebSocket 聚焦 `14 passed`；
  - `git diff --check` 通过。
- 旁路真实模型 Gate 使用 `deepseek:deepseek-v4-flash`、生产 PostgreSQL/Redis 和独立
  `/data`：
  - 修复前复现 4 次 `get_next_interview_question`，第 4 次才成功，耗时 70.60 秒；
  - 修复后严格限制为 2 次，第一次 FastMCP schema 拒绝缺少维度 `name`，第二次成功，
    无 `health_check/get_job/search_jobs` 等无关工具，耗时 70.06 秒；
  - Session 从 `version=3/evaluating` 推进到 `version=6/waiting_for_answer`，共 3 turns。
- 生产切换到镜像 `opencareer-backend:alpha-retry-fixed`
  (`sha256:cc807d48…06b8`)；公网与直连 health 均为
  `storage.mode=postgres / postgres=ready / redis=ready`，restart count 为 0。
  原 `opencareer-alpha-backend-pg-1` 保持 stopped，原数据卷和恢复点
  `20260819T103248Z` 未删除。启动日志无 traceback、数据库或 Redis 错误。
- 剩余风险：本轮消除了无限/多次 validation retry，但真实单轮仍约 70 秒。下一步应
  让模型首次生成的每个维度对象稳定包含
  `name/level/evidence/missing_evidence`，并减少两次 `load_skill` 所占的模型迭代。
  本机无 Docker CLI，Compose `config` 未执行；生产编排文件本轮未修改。

## 2026-08-19：模拟面试 Skill 预加载与首次 Schema 成功

- 强制运行的 Skill 现在由 Server 在首轮上下文中直接预加载，不再要求模型先调用
  `load_skill`。Skill frontmatter 新增 `preload-skills`，`mock-interview` 同时加载
  `career-interview-evaluation`；两份 Skill 的内容 SHA 继续写入 Session Skill
  State，禁用后的 countermand 也能识别预加载标记。
- Answer Workflow 在 GUI 内部 Prompt 已携带权威 `expected_version`。新请求直接调用
  `submit_interview_answer`，只有旧请求缺少版本时才读取 Session。评价 Skill 复用提交
  回答返回的完整 Session，不再重复调用 `get_interview_session`。
- 模型只提交各评价维度的 `level/evidence/missing_evidence`。服务端按照正式
  `question_type` 模板和固定顺序补充维度名；只有维度数量完全匹配时才补充，其他输入
  仍由领域校验拒绝，没有放宽评价边界。
- TDD 与构建证据：
  - GUI 聚焦 `20 passed`；
  - Python 聚焦 `132 passed`，仅有 1 条既有 Starlette warning；
  - TypeScript、`compileall`、`git diff --check` 和 Alpha build 全部通过；
  - Alpha build 产物为 `assets/index-C7pYKC8w.js`。构建仍报告既有 8 个 npm
    漏洞、混合导入和大 chunk 警告，本轮未执行破坏性依赖升级。
- 生产 PostgreSQL/Redis 旁路真实模型 Gate 使用 Conversation `2si6lj8oaq4`：
  - 模型迭代由 6 次降为 3 次；
  - 工具调用由 6 次降为 2 次；
  - `load_skill` 由 2 次降为 0；
  - 前置 `get_interview_session` 由 1 次降为 0；
  - 工具序列仅为
    `submit_interview_answer -> get_next_interview_question`；
  - `get_next_interview_question` 首次 Schema 调用成功；
  - 总耗时由 70.06 秒降为 47.89 秒，下降约 31.6%。
- 受控生产切换于 `2026-08-19T13:06:29Z` 完成。新容器
  `opencareer-alpha-backend-skill-preload` 使用镜像
  `sha256:11651d68…f248672`，实际 UID 为 10001、restart count 为 0，
  `storage.mode=postgres / postgres=ready / redis=ready`。公网已加载
  `index-C7pYKC8w.js`，后端启动日志无 traceback、数据库或 Redis 错误。
- 切换期间 Caddy 有约 4 秒上游不可达窗口并记录 3 次 502，其中一次为浏览器
  WebSocket 重连；新后端 ready 后公网 health 和静态资源立即恢复。旧
  `opencareer-alpha-backend-retry-fixed` 保持 stopped，原数据卷、发布前前端、
  发布目录 `/opt/opencareer-releases/20260819T130629Z-skill-preload` 和最终恢复点
  `20260819T103248Z` 均保留。
- SQL 复核 Interview `311f8603-635a-4362-94c1-caefd369784f` 已从 `version=6`
  推进到 `version=8 / phase=waiting_for_answer`，第 4 个 Turn 已生成。旁路容器、
  独立 `/data`、临时 env 和临时归档均已删除。

## 2026-08-19：岗位雷达收藏箱、单 JD 与测试 Catalog 清理

- 岗位雷达顶部新增“全部岗位 / 收藏箱”分段入口，删除重复的“仅看收藏”复选框。
  收藏数量由现有 filters 接口返回：SQLite 统计本地 `job_tracking`，PostgreSQL 在
  请求 Principal 的 RLS 事务内统计当前用户收藏。收藏成功后前端立即更新数量，失败
  仍沿用既有 CAS 回滚和版本冲突刷新。
- 岗位详情删除“职位职责”和“职位要求”两个重复展示区块，只显示原始 `JD`。
  `description_raw`、`responsibilities` 和 `requirements` 的 API/数据库字段均保留，
  岗位匹配、申请包、定制简历和模拟面试的结构化输入没有改变。
- 生产库确认存在 33 个 PostgreSQL 集成测试残留岗位：`API Company` 1 个、
  `Flow Company` 1 个、`Packet Co` 10 个、`Tailored Co` 21 个。所有目标均为
  `test/integration` Source，Career 引用、Catalog Version/Event 和正式 Crawl Source
  引用均为 0。
- 新增 fail-closed 清理脚本 `deploy/sql/cleanup_test_catalog_20260819.sql`：
  - 最新生产 dump 的隔离恢复库正常路径从 `10802` 清理到
    `10769 active / 34 crawl sources / 0 test companies`；
  - 对抗路径人为给 `api-job` 增加 1 条 Career 引用，脚本以
    `cleanup targets have 1 career references` 拒绝，33 个岗位全部保留；
  - 生产执行后为 `10769 active / 10769 total / 34 crawl sources /
    0 test companies / 0 duplicate keys`。
- 清理审计目录为
  `/opt/opencareer-releases/20260819T145632Z-job-radar-cleanup`，保存目标 ID、
  SQL、执行日志和前后计数。原 PostgreSQL 恢复点未删除。
- PostgreSQL 集成测试新增数据库名硬门禁，只允许 `opencareer_gate`、
  `opencareer_gate_fresh` 或 `*_test`，显式拒绝 `opencareer_prod` 和默认
  `postgres`。三组会写共享 Catalog 的测试均接入 teardown，清理失败会使测试失败。
- TDD 与回归：
  - GUI RED 精确命中缺少顶部收藏箱、重复 JD 区块和移动端固定桌面列；
  - Python 聚焦 `47 passed`，另有测试数据库防护 `10 passed`；
  - GUI 聚焦先为 `24 passed`，移动端修复后为 `17 passed`；
  - TypeScript、`compileall`、Alpha build 和 `git diff --check` 通过；
  - 构建保留既有 8 个 npm 漏洞、混合导入和大 chunk 警告。
- 真实浏览器完成一次可逆收藏：数量 `0 -> 1`，收藏箱只显示该岗位，取消收藏后
  数量与列表恢复为 0。公司筛选只剩 DeepSeek、字节跳动、小米、小红书、快手、
  智谱 AI、月之暗面、滴滴出行、美团、腾讯和阿里巴巴。
- 首次 375×812 Gate 发现原五列筛选和左右详情仍按桌面宽度布局。修复为移动端单列
  筛选、纵向 list/detail、详情操作换行和响应式信息栏后：
  `clientWidth=scrollWidth=375`，可见控件越界数为 0，双入口位于
  `x=17..241`，截图为 `/tmp/opencareer-job-radar-375x812.png`。
- 正式后端镜像为 `sha256:4167e8b7…572079b`，前端 bundle 为
  `index-9PTp9h-T.js`。公网 health 为 PostgreSQL/Redis ready，后端和 Caddy
  restart count 均为 0，后端日志无 traceback、数据库或 Redis 错误。旧后端、
  两版发布前静态前端、原卷和恢复点继续保留。

## 2026-08-20：GUI npm 依赖漏洞清零

- `npm audit` 从 `3 moderate / 4 high / 1 critical` 共 8 个漏洞降为 0。
  Vite、Vitest、PostCSS、NanoID 和 esbuild 分别更新到 `7.3.6`、`3.2.7`、
  `8.5.26`、`3.3.18` 和 `0.28.2`。
- npm registry 的 `xlsx` 停留在有已知公告的 `0.18.5`，改用 SheetJS 官方发布的
  `0.20.3` tarball，并固定到 `surfaces/gui/vendor/xlsx-0.20.3.tgz`，避免构建时
  依赖外部 CDN。文件 SHA-256 为
  `8dc73fc3b00203e72d176e85b50938627c7b086e607c682e8d3c22c02bb99fe8`。
- 回归证据：`npm ci` 和完整 `npm audit` 均报告 0 vulnerabilities；GUI 全量
  `49 files / 268 tests passed`；TypeScript 与 Alpha build 通过。SheetJS
  Node/浏览器 smoke 均能正确读写二维表格。
- 新 Alpha 产物为 `assets/index-Dgak5WmV.js` 和
  `assets/xlsx-CKwrMZHi.js`。桌面 `1440×900` 与移动 `375×812` 公网浏览器
  Gate 均无横向溢出、page error 或非预期失败，XLSX chunk 返回 HTTP 200。
- 静态发布目录为
  `/opt/opencareer-releases/20260820T024916Z-npm-security`，发布前前端保留在
  `/opt/opencareer/deploy/web.pre-npm-security-20260820T024916Z`。后端镜像未变，
  PostgreSQL/Redis 均 ready，后端和 Caddy restart count 均为 0；Origin、Token、
  数据库和容器配置均未修改。

## 2026-08-20：Career-first 暖色编辑台界面

- 主界面改为 Career-first 信息架构：左侧只保留“新建对话、岗位雷达、我的求职档案、
  最近对话、设置”。移除 OpenWorker Cloud 登录、账户状态、收件箱、连接器、自动任务、
  活动记录、Agent 选择和 Agent 分组入口；Sidebar 不再轮询 Cloud、Inbox 解锁状态或
  Automations。
- 安全边界未删除：当前 Conversation 内的 Approval、Plan、Directory、ask_user 和
  pending Inbox mirror 仍按原逻辑展示，后端 Inbox/Connector/Automation/Audit API 与
  历史数据均未修改。
- 方案 B“暖色编辑台”视觉系统落地：
  - `paper=#f7f4ed`、`panel=#fffdf8`、`sidebar=#eee9df`、
    `accent=#b65f42`；
  - 标题使用本地中文衬线 fallback，正文继续使用系统无衬线；
  - 对话、Composer、岗位、档案、匹配、定制简历和面试进度统一使用语义令牌，清除
    Career 页面硬编码蓝色。
- Career 首页从 5 个重复入口收敛为 3 个直接动作：发现岗位、建立求职档案、分析 JD。
  岗位雷达与求职档案由一级导航直接进入。
- TDD 在真实浏览器 Gate 中额外修复两项移动端问题：
  - 桌面 `nav-peek` 类不再应用到移动视口，抽屉关闭后 Sidebar 为
    `left=-264 / right=0`；
  - 求职档案在移动端改为单列，`lg` 才恢复 `240px + detail` 双栏，页头、详情操作和
    页签均可换行或滚动。
- 自动化证据：
  - GUI 全量 `50 files / 268 tests passed`；
  - TypeScript、Alpha build、`npm audit` 0 vulnerabilities 和
    `git diff --check` 通过；
  - 最终 bundle 为 `assets/index-DkqJdPt8.js`，CSS 为
    `assets/index-Bd_fNi9d.css`；
  - Playwright 在 `1440×900`、`1024×768`、`375×812` 下验证岗位与档案可达，
    三个 surface 均 `clientWidth=scrollWidth`，page error 为 0；
  - OpenWorker Cloud、收件箱、连接器、自动任务、活动记录、未登录六类文案均不在
    DOM；截图为 `/tmp/opencareer-career-first-{desktop,tablet,mobile}.png`。
- 发布过程第一次使用目录级 `mv` 替换 Caddy bind mount，校验清单先因错误的
  `deploy/` 前缀 fail-closed；修正后替换导致容器仍绑定旧 inode，根页面短暂返回
  404。立即重启一次 Caddy 重新绑定目录，随后改为“先复制新哈希资源、最后原子替换
  `index.html`”的无重启发布方式。最终 Caddy/后端均 running、restart count 0，
  PostgreSQL/Redis ready，WS 101。
- 最终发布目录为
  `/opt/opencareer-releases/20260820T051156Z-career-first-ui-profile-mobile`；
  初始发布前静态回滚目录为
  `/opt/opencareer/deploy/web.pre-career-first-20260820T045902Z`。后端镜像
  `sha256:4167e8b7…572079b`、Origin、Token 和数据库配置均未改变。
- Alpha 控制台仍会记录既有预期 403：`/v1/settings`、
  `/v1/workspaces/recent`、`/v1/connectors`。Career 数据、Sessions 和 WebSocket
  均正常；后续可单独减少 App/RightRail 对这些桌面接口的 Alpha 请求。

## 2026-08-20：JD 确认直启面试与字节全量续跑代码 Gate

- 手动 JD/公开岗位链接改为两阶段确认：预览返回稳定 SHA-256 `preview_hash`，
  只有用户点击“确认并开始面试”并提交同一原文与 hash 后才入库、匹配简历和创建
  InterviewSession；取消路径不写岗位。
- Alpha 只新增 `preview_public_job_url` 与 `import_manual_jd` 两个 Career 工具，
  未开放通用 web fetch，未修改 Origin、Token 或 WebSocket 安全边界。
- 字节新增中国大陆社招/校招 resumable scope。PostgreSQL/SQLite 保存 cycle、
  shard checkpoint、暂存岗位和 pass；单批最多 20 页，首遍后至少一遍校验，最多
  三遍。冲突、10,000 上限或不收敛标记 degraded，禁止 missing/offline。
- 完整轮次的 Catalog transition、crawl run 和 `cycle=committed` 已收敛到同一
  Repository 事务。每日 crawler 在常规来源后按
  `CRAWL_RESUMABLE_BATCHES` 独立预算续跑；MCP 来源列表和全来源 cursor 已包含新
  scope，`running` 时 cursor 不推进。
- 自动化证据：crawler/PostgreSQL/工具 81 passed，JD/URL/Skill/Alpha 28 passed，
  后续聚焦回归 40 passed；`compileall`、TypeScript、Alpha build 和
  `git diff --check` 通过，npm audit 为 0。
- 本机没有 Docker CLI，且 `TEST_DATABASE_URL` 未配置，因此 0006/0007 的真实
  PostgreSQL 16 migration、真实官网完整 cycle、375×812 确认卡和公网 Alpha 点击
  Gate 尚未执行。公开 URL 的 2 MiB 限制仍在完整响应读取后判断；统一 SSRF guard
  尚无流式逐跳接口，后续必须在 guard 层补齐，不能在业务层绕过。

## 2026-08-20：本地 PostgreSQL 16 与字节官网续跑 Gate

- 通过 Homebrew 安装 Docker CLI、Compose 与 Colima；本地 runtime 为
  `linux/arm64`，PostgreSQL 16 和 Redis 仅绑定 `127.0.0.1:55432/56379`。
- 测试连接使用非 superuser `opencareer_app`。真实 migration 1–7 成功，全部
  PostgreSQL、resumable crawler、CLI 和工具回归为 `118 passed`。
- 真实数据库 Gate 暴露并修复：
  - FastAPI PostgreSQL Job repository session 未接受 `write=`，岗位 API 返回 409；
  - Catalog 测试清理在 Packet/Tailored/Interview 子记录之前删除 Job，触发外键失败；
  - Interview 集成测试错误依赖上一测试遗留的 `api-job`；
  - 首遍官网 count 漂移被过早 degraded。
- 数据库按职责拆分：`opencareer_gate` 只跑集成测试，`bytedance_test` 只保存官网
  cycle，避免权威 crawler 岗位改变 legacy migration 测试前提。
- 官网证据：
  - 正式社招/校招各完成 20 页、200 条暂存，Catalog 均为 0；
  - 校招游戏策划 26 条完成两次完整两遍 cycle，分别为 `created=26` 和
    `unchanged=26`；
  - duplicate key 0，事件只有 26 个 created，running cycle 未产生 missing/offline。
- 两份 Compose config 使用临时虚拟环境值通过，临时 `deploy/.env` 已删除。
  本地两个测试容器继续运行，便于后续从 checkpoint 推进全量 cycle。

## 2026-08-20：字节中国大陆社招/校招完整隔离轮次

- 从 `bytedance_test` 的 PostgreSQL checkpoint 继续真实官网分页，最终完成：
  - 社招 `cycle=9f770e7e…`：pass 3 committed，11,634 created；
  - 校招 `cycle=75de7a4f…`：pass 3 committed，7,423 created。
- 数据审计：19,057 active，来源内重复键 0，社招/校招跨来源 external ID 重复 0，
  invalid 0；两个 crawl run 均 succeeded，事件只有 created，没有
  missing/offline。
- 长轮次暴露并通过 TDD 修复三项问题：
  - `ensure_crawl_source()` 重复 company upsert 导致两个来源事务串行；
  - pass 2 count 漂移进入 pass 3 后沿用旧 count，导致确定性误降级；
  - 同一岗位在后续 pass 的正常 JD 更新被误判为同遍冲突。
- pass 3 改为允许实时 count 漂移，但只有全部暂存岗位均在当前 pass 重见时才提交；
  同一 pass 内同 ID 不同内容仍降级。相关聚焦回归为 66 passed。
- 社招结束时 6 条岗位未在 pass 3 重见。官方详情页逐条确认 4 条已下线、2 条仍在线；
  隔离 Gate 对这 6 条执行一次性尾部对账后提交。该过程尚未自动化，生产发布前必须
  补齐或保留受控人工 Gate。
- 项目 Gate：TypeScript、Alpha build、两套 Compose config、server help、
  crawler list、`git diff --check` 通过；`npm audit` 为 0。临时虚拟
  `deploy/.env` 已删除。
- 本轮没有连接或修改线上生产数据库，公网 Alpha health 仍为 PostgreSQL/Redis
  ready，线上字节岗位仍为旧来源 220 条。

## 2026-08-21：字节 stale 岗位详情尾部自动核验

- 第三遍完整列表仅剩 1–20 条 stale 岗位时，Runner 自动调用字节官方详情页
  verifier；明确在线才更新 `last_pass`，明确下线才删除 staging，未知、超时、
  重定向或结果 ID 不完整均将 cycle 标记为 degraded。
- SQLite 与 PostgreSQL Repository 均先验证待对账 ID 精确匹配 stale 行，再执行
  同事务更新/删除；Runner 对账后重新读取 staging，全部收敛才提交 Catalog。
- 聚焦回归 `49 passed`。真实 PostgreSQL 16 临时 cycle 验证
  `active=2 / offline=4 / remaining=2` 后整体回滚。
- 真实官网 6 URL 自动 Gate 返回 2 条 active、4 条 offline，与人工证据完全一致；
  Gate 只读且未修改已提交 cycle。隔离 Catalog 保持社招 11,634、校招 7,423。
- 本轮未连接或修改线上 Alpha；生产仍需备份、部署代码并重新运行完整 cycle。

## 2026-08-21：字节全量来源生产部署

- 建立恢复点 `20260821T032119Z`，PostgreSQL dump、旧后端镜像、Alpha 数据卷、
  Caddy 卷、静态前端和加密配置均进入 SHA-256 清单；服务器与离机副本验证通过。
- 新后端/抓取镜像分别为 `sha256:468d6b66…a3e1584` 和
  `sha256:560a3ab6…284def`。切换后 migration 7、REST、WebSocket、PostgreSQL、
  Redis 与容器 restart/OOM Gate 通过，旧容器和卷保留。
- 已将隔离三遍 Gate 的 19,057 条完整快照作为生产初始 Catalog seed：
  社招 11,634、校招 7,423。总 active 为 29,612，字节 active 为 19,063，
  active external ID 重复 0，新来源 invalid 0。
- 214 条被全量校招覆盖的旧 Seed/前沿岗位标记为 `superseded`，6 条未覆盖岗位保留，
  两个旧来源停用。用户数据计数不变，新增 2 个共享 Blob 为两份来源原始快照。
- 线上官网复核使用来源独立 runner 串行续跑，受限后冷却 5 分钟；当前校招
  checkpoint 1,996、社招 checkpoint 200，正式 Catalog 不暴露 staging。

## 2026-08-21：PostgreSQL 岗位雷达查询优化

- TDD 将岗位列表改为 14 列摘要 projection，删除 Repository 对
  `career.job_visible_to_user()` 的重复调用；岗位详情仍读取完整 JD。
- migration 8 增加 `catalog.jobs.visibility_user_id`，由
  `career.manual_job_owners` 触发器同步。安全视图和写入守卫统一检查该列。
  隔离 Gate 曾证明直接从安全视图查询强制 RLS owner 表会让 Bob 误见 Alice 的
  手工岗位，因此该不安全方案未部署。
- 筛选接口把公司、地点、招聘类型和状态聚合为一个 materialized CTE 查询，收藏数
  继续按当前租户单独查询；API 字段、排序和 exact count 未改变，也未增加缓存。
- 29,826 条生产快照的 SQL 基线/优化结果：
  - count：`1328ms -> 123ms`；
  - 首屏：`1137ms -> 395ms`（冷读）；
  - 公司 facets：`524ms -> 110ms`；
  - 地点 facets：`583ms -> 267ms`；
  - 合并后的完整共享 facets：`363ms`。
- 候选容器连接隔离库采样：列表 P95 `412.76ms`，筛选 P95 `384.25ms`。
  最终生产容器经 Caddy 采样：列表 P95 `157.88ms`，筛选 P95 `138.77ms`。
  当前开发机到北京公网链路 health P50 为 `872.41ms`，导致外部 keep-alive
  列表/筛选 P95 分别为 `1796.66ms / 1753.42ms`；该尾延迟来自网络链路，不是
  PostgreSQL 或应用处理。
- 恢复点 `20260821T075235Z` 在服务器与离机副本均通过 SHA-256；停写 18 秒。
  新镜像 `sha256:4c5f4d68…079f2`、新容器
  `opencareer-alpha-backend-job-radar-final` 已切流，旧容器和镜像保留。
- 生产 Gate：migration 8 幂等、Alice/Bob 手工岗位隔离通过、active `29,612`、
  active external ID 重复 0、REST/WS/PostgreSQL/Redis 正常、restart count 0。
  聚焦回归 `56 passed, 1 skipped`；TypeScript、Alpha build、Crawler CLI、
  两套 Compose config 和 `git diff --check` 通过。

## 2026-08-24：AI 简历诊断与面试准备对话

- 岗位详情的用户入口由证据矩阵收敛为“AI 分析与改简历”：用户单选一份已确认
  简历后进入标准 Career Conversation，系统自动且仅发送一次诊断请求。
- 新流程只向 Agent 传递 `job_id` 与 `resume_id`。新增只读
  `get_confirmed_resume` MCP 工具，复用现有 SQLite/PostgreSQL 租户隔离与敏感
  字段遮罩；不调用岗位匹配 API、匹配快照、关键词评分或脚本分析。
- 新增 `career-resume-coach` Skill，固定按项目、实习/工作、基础能力、教育门槛顺序
  诊断；先追问缺失事实，用户确认后再输出保留/删除/补充/重写/加粗建议及针对性
  面试问题。旧 `career-tailored-resume` 前端入口和 Skill 已移除，后端
  Match/Application Packet/Tailored Resume 服务暂留给兼容流程和后续独立清理。
- 自动发送队列绑定目标 Conversation ID；切换会话时丢弃失配消息，简历诊断与
  模拟面试启动时互相清理残留队列。主线程审查补充了旧简历选择清理和三类队列
  竞态回归。
- 自动化 Gate：
  - Python 聚焦 `23 passed, 14 skipped`；跳过项均因本机未配置
    `TEST_DATABASE_URL`，未声称真实 PostgreSQL Gate 通过；
  - GUI 全量 `48 files / 268 passed`，TypeScript 通过；
  - alpha build 通过（392 modules），Server CLI 与 36 来源 Crawl CLI 通过；
  - IP Compose 使用临时非敏感变量通过；域名 Compose 因本机缺少服务级
    `deploy/.env` 无法按原命令渲染，`--no-env-resolution` 语法校验通过；
  - Playwright 桌面与 `375×812` 共 `2 passed`，弹层无越界或横向滚动，提交后
    Conversation 中只有一条“开始 AI 简历诊断”，console/page error 为 0。
- 已提交设计/计划、MCP、Skill、消息契约、独立启动器、状态修复和 E2E 测试：
  `7bc5c2a`、`beff5b2`、`7768d18`、`28ca047`、`297922e`、`69b2ba3`、
  `2904801`、`2df1ef2`。Task 5 与既有移动端/面试改动位于相同文件，为避免把
  用户的无关工作一起提交，当前保持未暂存。
- 本轮未部署、未修改 Origin/Token/Alpha 安全边界，线上 alpha 不受影响。下一
  独立任务是设计并删除 Application Packet、旧匹配兼容依赖和 PDF/DOCX 后端链路。

## 2026-08-24：旧匹配与文件生成链路退出运行时

- 模拟面试改为在当前 Principal 范围内直接读取 `job_id + resume_id`，新会话不再
  创建或读取匹配快照；历史会话继续保留 immutable blueprint。
- 删除 Match、Application Packet、Tailored Resume Draft、DOCX/PDF 导出的
  HTTP、MCP、Alpha allowlist、Skill、GUI、服务与仓储运行时入口。旧 HTTP 路径由
  FastAPI 返回标准 `404`；Career Vault 的 PDF/DOCX 导入、OCR、原件预览/下载、
  普通 Conversation PDF 和面试 Artifact 保持不变。
- SQLite schema 升至 v13，使历史面试先解除匹配表外键。新增显式只读归档和
  retirement 命令；破坏性 SQL 未注册到应用启动 migration。PostgreSQL 归档使用
  `REPEATABLE READ, READ ONLY` 一致性事务，归档和删除均要求 superuser 或
  `BYPASSRLS`，并使用外部 manifest SHA-256 复验。
- 后端镜像移除只服务于旧导出链路的 `libreoffice-writer` 和
  `fonts-noto-cjk`；crawler Chromium 与 OCR extra 未改。
- 自动化 Gate：
  - Career Python 全量 `443 passed`；
  - 旧运行时/面试/简历/迁移聚焦 `126 passed, 1 skipped`；
  - 归档与 retirement `15 passed`；
  - core suite 排除 Bedrock 和一个已知挂起用例后
    `1306 passed, 25 skipped, 1 deselected`；
  - GUI 全量 `48 files / 267 passed`，TypeScript、Alpha build、compileall、
    Server CLI、36 来源 Crawl CLI、两套 Compose config 和
    `git diff --check` 通过。
- 本机未配置 `TEST_DATABASE_URL`，真实 PostgreSQL 16 archive/retirement
  destructive Gate 未执行。`tests/test_bedrock_provider.py` 因本机缺少可选
  `boto3/botocore` 为 `16 passed, 7 failed`。另有既有
  `test_ws_skill_message_accepts_safe_custom_display` 在临时 workspace 中被 Skill
  预加载拒绝后仍等待 `turn_done`，会挂起全量 core suite；该共享测试/生命周期
  问题不属于本次 retirement，未顺手修改。
- 残留审计仅命中历史 migration、显式归档/retirement、测试数据库清理和 absence
  断言；运行时与 GUI 无旧入口。此次只完成本地代码与验证，未部署、未修改线上
  alpha，也未执行生产归档或物理删除。

## 2026-08-25：旧生成链路运行时生产部署

- 将提交 `e367b34` 同步到独立 release
  `/opt/opencareer-releases/20260824T162922Z-legacy-retirement`，在服务器使用中国
  内地依赖源构建镜像
  `opencareer-backend:alpha-legacy-retirement-20260824`
  (`sha256:651a37b3…e65ad`)。镜像 UID 为 `10001`，LibreOffice 不存在，
  pypdf、pypdfium2 和 python-docx 可导入。
- 切换前建立恢复点
  `/opt/opencareer-backups/20260824T162922Z-legacy-retirement`，包含 PostgreSQL
  custom dump、旧镜像、旧应用目录、数据卷、容器元数据和加密 `.env`，共 12 个
  文件、439 MiB。服务器与离机副本
  `.local-state/backups/server/20260824T162922Z-legacy-retirement` 的 SHA-256
  全部通过；离机密钥权限为 `0600`，解密后 `.env` 哈希与服务器当前配置一致。
- PostgreSQL dump 已恢复到临时隔离库并完成关键业务计数比对，随后删除临时库。
  切换前后保持：29,621 个 active 岗位、3 份简历导入、5 场面试、15 个 turn、
  14 个 Conversation、308 条 Message、85 个 Blob。
- 停写窗口约 30 秒。新容器
  `opencareer-alpha-backend-legacy-retirement` 监听 `172.18.0.1:18768`，
  Caddy 已切换到该上游；旧容器
  `opencareer-alpha-backend-job-radar-final` 停止保留。新后端和 Caddy restart
  count 均为 0，PostgreSQL 与 Redis 均为 ready。
- 生产 Gate：health、岗位、简历为 200；Alpha 设置接口为 403；旧 Match 和
  Tailored Resume 路径为标准 404；缺失岗位的新面试契约返回
  `JOB_NOT_FOUND`；WebSocket events 和带 Career workspace 的 Session 均完成
  101/ready。
- 新前端 bundle 为 `assets/index-CuWJNaIe.js`。真实浏览器岗位雷达显示 29,621
  个岗位和“AI 分析与改简历”入口，无横向溢出、console error 或页面错误。
- 本次只部署运行时下线，不执行物理 retirement。生产中四张旧表仍存在，
  `legacy_career_retirement` marker 为 0，旧 Blob 未删除；后续必须单独完成专项
  archive、隔离 retirement 演练和明确批准后才能物理清理。

## 2026-08-25：Alpha 简历诊断读取权限热修

- 生产重放 `career-resume-coach` 时确认 `get_confirmed_resume` 已注册到 Career
  MCP，但遗漏于 Alpha Conversation allowlist，导致模型只能列出简历而不能读取
  选定的脱敏确认简历。提交 `02479e2` 以测试先行方式只增加该只读工具：
  RED 精确失败，随后聚焦回归 `34 passed`。
- 新 release 为
  `/opt/opencareer-releases/20260825T025723Z-confirmed-resume-allowlist`，镜像
  `opencareer-backend:alpha-confirmed-resume-20260825`
  (`sha256:a38d28d…329e50`)。候选端口 `18769` 通过 health 后，在原
  `172.18.0.1:18768` 替换后端；新后端和 Caddy restart count 均为 0，旧
  `opencareer-alpha-backend-skill-sync` 停止保留。
- 公网 Gate：health 为 PostgreSQL/Redis ready，Alpha settings 仍为 `403`，
  旧 Match 路由为 `404`；`career-resume-coach=1`，
  `career-tailored-resume=0`，`career-application-packet=0`。
- 删除并重建先前中断的诊断 Conversation 后，真实模型仅调用
  `get_job` 与 `get_confirmed_resume`，完成“项目与实习证据、基础能力覆盖、
  JD 缺失项、需要用户补充的真实事实”四段诊断。未调用确认、导出、草稿、文件
  写入或旧匹配工具；缺失事实尚未由用户确认，因此未生成改写 proposal。
- 首个命令行 WebSocket 探针在收到审批卡后主动断开，服务端记录一次
  `WebSocketDisconnect 1006`；会话通过持久 Inbox 恢复并完成，容器未重启。

## 2026-08-25：裸 URL 中文标点渲染修复

- 真实对话中的裸官网 URL 紧邻 `）。以下是诊断。` 时，`remark-gfm` 将整段中文
  解析进链接，实际 `href` 末尾出现对应百分号编码。新增截图原句回归测试，RED
  精确复现该错误。
- `Markdown` 渲染器现在只处理源码中的裸 `http(s)` 链接：在中文句末标点处结束
  URL，并将其前面的中文闭合括号一并恢复为普通文本。显式 Markdown 链接、
  `artifact:` 链接和代码内容不受影响。
- 提交 `ed6b8b7`。GUI 全量 `48 files / 268 tests`、TypeScript、Alpha build、
  `npm audit` 和 `git diff --check` 通过；仅保留既有 Vite 大 chunk 警告。
- 静态前端以“先复制哈希资源、最后原子替换 index”方式上线，bundle 为
  `assets/index-XrtHYZM6.js`。生产原对话 DOM 验证链接文本和 `href` 均精确结束于
  `/detail`，后续 `）。以下是诊断。` 为独立文本节点；浏览器控制台无错误，
  Caddy 与后端 restart count 均为 0。

## 2026-08-25：AI 简历分析会话按岗位命名

- 新建 AI 简历分析会话使用确定性标题 `公司 · 岗位名称`。岗位页只把公司名和
  岗位名作为前端显示元数据传给 `App`；Agent Prompt 仍只携带 `job_id` 和
  `resume_id`，没有新增简历正文或岗位显示文本。
- 标题在首个 `turn_start` 时通过既有会话重命名接口写入，因此模型仍在分析或
  等待只读工具审批时，顶部栏和最近对话就已显示岗位标题，不再短暂暴露
  `Use the preloaded skill ...` 内部指令。
- TDD 先复现启动 payload 缺少显示字段及 `turn_start` 不触发重命名，随后完成
  最小实现。聚焦测试 `20 passed`，GUI 全量 `48 files / 268 tests`、TypeScript、
  Alpha build、`npm audit` 和 `git diff --check` 通过。
- 提交 `98ad963` 与 `6a5bc43` 已推送。静态 release 为
  `/opt/opencareer-releases/20260825T072154Z-resume-coach-title-start`，线上
  bundle 为 `assets/index-p76hYlGW.js`；浏览器实测在分析进行中同时显示正确的
  顶部标题和侧栏标题。
- 截图对应历史会话通过唯一官网 URL 精确定位为 `oaigkyplbae`，其标题从
  `项目与实习证据分析` 更新为
  `字节跳动 · 开放平台运营（短剧方向）实习生 - TikTok产品`。对比修改前后的
  会话清单，原有 17 条中仅该会话标题变化。
- 浏览器验收创建的临时会话 `sf1n2m606fl` 已拒绝剩余工具调用并归档。尝试使用
  现有 DELETE API 清理时发现 PostgreSQL `inbox_resolutions` 到 `inbox_items`
  的外键阻止删除并返回 `500`；该问题与标题功能无关，本次未扩大范围修改。
- 最终 PostgreSQL/Redis ready，后端与 Caddy restart count 均为 0。

## 2026-08-25：PostgreSQL 会话删除 Inbox 外键修复

- 根因是 `agent.inbox_resolutions(user_id, inbox_item_id)` 到
  `agent.inbox_items(user_id, id)` 的组合外键仍为默认 `NO ACTION`。删除
  Conversation 时，`inbox_items` 虽会随 Conversation 级联删除，但已解决的
  Inbox 记录会阻止这一级联并使 DELETE API 返回 `500`。
- 新增不可变 migration `0009_inbox_resolution_cascade.sql`，只重建该组合外键并
  增加 `ON DELETE CASCADE`；未修改已发布的 `0001_initial.sql`，也未改变 Origin、
  token、Alpha 能力限制或旧 Career 表。
- TDD 增加 migration 序列/SQL 回归和真实 PostgreSQL Conversation 删除集成测试。
  本地聚焦结果为 `11 passed, 7 skipped`；7 项因本机未配置
  `TEST_DATABASE_URL` 跳过。服务器一次性 PostgreSQL 16 数据库已完整应用
  migration 1–9，并验证 resolved Inbox 随 Conversation 删除。
- 生产变更前建立 PostgreSQL custom dump 恢复点
  `/opt/opencareer-backups/20260825T074818Z-inbox-fk/postgres.dump`，SHA-256
  校验通过。生产 schema 从 8 升至 9，外键 `confdeltype` 从 `a`
  (`NO ACTION`) 变为 `c` (`CASCADE`)。
- 原失败请求 `DELETE /v1/sessions/sf1n2m606fl` 重放返回 `200` 和
  `{"ok": true, "session_id": "sf1n2m606fl"}`。随后确认 Conversation、
  Inbox 行和消息均为 0。
- 提交 `a00fc67` 已部署为镜像
  `opencareer-backend:alpha-inbox-delete-20260825`
  (`sha256:14e6dcf6d1c23e28f16f815b46d1c064df78d8523d9884f2decb1817244e6c5b`)；
  正式容器 `opencareer-alpha-backend-inbox-delete` 继续监听
  `172.18.0.1:18768`，旧 `opencareer-alpha-backend-confirmed-resume` 停止保留。
  候选容器和候选临时卷已删除。
- 最终公网 health 为 `200`，PostgreSQL/Redis ready，后端与 Caddy restart
  count 均为 0，后端无新增 Traceback/ERROR。切换窗口内活跃页面轮询短暂产生
  12 个 `502`，服务就绪后恢复；未执行旧 Career 四表的物理 retirement。

## 2026-08-27：Authing 云端参数预配置

- Authing 自建应用 `OpenCareer Web` 已取得 OIDC Issuer 与 App ID；真实 App Secret
  仅写入服务器 `/opt/opencareer/deploy/.env`，未写入仓库或日志。
- 服务器 `BASE_DOMAIN` 已从占位值更新为 `opencareer.online`，并补齐
  `OPENCAR_AUTH_ISSUER`、`OPENCAR_AUTH_CLIENT_ID`、
  `OPENCAR_AUTH_CLIENT_SECRET` 与随机 64 字符
  `OPENCAR_AUTH_STATE_SECRET`；`.env` 权限验证为 `600`。
- 写入前恢复点为
  `/opt/opencareer/deploy/.env.backup-authing-20260827T094605Z`。现有
  `docker-compose.ip.yml` 配置校验通过，18080 health 仍为 `ok`，PostgreSQL、
  Redis 均为 `ready`。
- 本次未重启容器、未同步尚未提交的域名登录代码、未切换 DNS，也未启用备案中
  的域名入口。用户明确决定暂不轮换已在截图中出现的 App Secret；上线前仍建议
  刷新密钥并替换服务器配置。

## 2026-08-31：备案通过后启用单域名与 Authing 登录

- 阿里云备案控制台确认网站备案号 `京ICP备2026055760号-1`、状态“管局审核通过”；
  新增 `app` A 记录到 `203.0.113.10`，保留既有 `@` 与 `www` 记录。
- 上线前备份 PostgreSQL、`data-a`、部署目录和 Caddy 卷至
  `/opt/opencareer-backups/20260831T033559Z-domain-authing`（90 MiB，含 SHA-256
  清单）。生产配置从现有容器安全复用真实 `DATABASE_URL`，未使用过期的
  `POSTGRES_PASSWORD`，也未启动空的容器数据库。
- 候选镜像 `opencareer-backend:domain` 在 18769 验证 health 与 Authing session，
  PostgreSQL schema 由 9 升至 10；正式后端随后继续绑定 `172.18.0.1:18768`。
- Caddy 首次用 `host.docker.internal` 时错误指向 `172.17.0.1` 并产生短暂 502；
  核对 Compose 网关后改为 `172.18.0.1:18768`。最终三个域名证书签发成功，
  正式 health 200、匿名 sessions 401、登录跳转 Authing 302、根域名与 www 301，
  18080 health 继续为 200。
- 浏览器实际看到 OpenCareer 登录页、Authing 验证码登录页和页面底部备案号。
  剩余 Gate 是双账号交叉数据隔离与历史 `local` 数据处置；用户此前决定暂不轮换
  已出现在截图中的 Authing App Secret，该风险继续保留。

## 2026-09-01：Authing 重复授权码回调容错

- 排查朋友邮箱验证后看到的通用登录错误：云端日志显示首次授权码回调已返回 `307`
  并签发浏览器会话，约 0.09 秒后同一一次性授权码被重复访问，第二次按协议返回
  `OAuthError`。这不是邮箱字段、用户资料或数据隔离写入失败。
- 回调路由现在仅在浏览器已经带有有效 `opencar_session` Cookie 时，将重复且失败的
  回调安全重定向到首页；无有效会话的真正认证失败仍返回脱敏的 `400`。因此不会接受
  无效登录，也不会泄露授权码或令牌。
- TDD 新增“首次成功、第二次同码失败”回归。聚焦认证测试 `20 passed`，Python
  compileall 与 `git diff --check` 通过。后端已重建，health 为 `ok`；浏览器直接访问
  重复回调入口后回到首页。
- 待朋友从首页重新发起一次新的邮箱验证码登录，并完成虚构数据的双账号隔离验收。

## 2026-09-01：云端 BYOK 模型凭据（代码完成，待部署）

- 规格见 `docs/superpowers/specs/2026-09-01-cloud-byok-model-config-design.md`。
  用户决策：密钥用每用户文件 SecretStore（0600，与桌面一致，不进数据库备份）；
  未配置 BYOK 的用户回退服务器默认模型。
- 后端三处最小改动：`SessionManager.__init__` 接受可选 `secrets` 注入；
  `run.py` `manager_for` 为每个 principal 构造
  `state_dir()/users/<uid>/secrets.json`；`alpha.py` 放行 `/v1/providers*` 与
  精确路径 `/v1/settings/default-model`，其余 `/v1/settings` 与
  `/v1/chat/completions` 维持 403。Provider Router/Engine 零改动。
- GUI：alpha 模式 `loadSettings` 改为 `getProviders()` 推导模型列表 +
  `getHealth()` 刷新默认模型；`ModelsTab` 不再因 settings 403 卡"正在加载…"，
  新增「默认模型」卡片（POST default-model，datalist 来自已配置 provider 的
  建议模型）；`composerModelPolicy` alpha 分支支持 BYOK 模型列表，
  backendModel 保持首位。
- 测试：新增 `tests/test_cloud_model_credentials.py`（4 passed：闸门精确边界、
  HTTP 级放行与 key 不泄漏、双 principal secrets 隔离与删除互不影响、桌面默认
  行为不变）；alpha/identity/storage/cloud 回归 38 passed；GUI 全量
  49 files / 274 passed（策略测试 +3）；TypeScript、alpha 与桌面 production
  build、Python compileall、`git diff --check` 均通过。
- 尚未部署到 203.0.113.10；生产 Gate 为真实浏览器配置 key、Test 校验、切换默认
  模型并确认对话走用户自己的 provider，以及双账号隔离复核。

### 同日追加：云端模型页中文重构与密钥管理卡

- 用户反馈模型页英文混杂、桌面专属卡片干扰、缺少密钥管理与明确的测试反馈。
- GUI 层翻译后端 registry 展示字符串（标题/字段 label/help/blurb 映射表，核心
  registry 未改）；provider 状态、按钮、保存徽标、相对时间、测试错误全部中文。
- 云端模型页减法：Token 节省/上下文压缩（桌面 403 死 UI）alpha 不渲染；
  provider 画廊精选 9 家（DeepSeek/Kimi/Qwen/Z.ai/MiniMax/OpenAI/Anthropic/
  Gemini/OpenRouter），已配置项移入顶部「已配置的密钥」管理卡（测试/更换/删除，
  测试用存储密钥做只读校验并就地显示「连接成功」或具体错误）。
- 线上部署同前述流程：新 bundle `index-DJ5rJ2qJ.js`，health ok，后端 restart 0。

### 同日追加：密钥管理卡来源区分与选择器自定义模型入口

- 修复"删除密钥后仍显示已配置"：服务器 env 内置 key 使 provider 恒为
  configured，删除只移除用户个人 profile。`get_providers` 新增
  `source: "store" | "env"`（用户自己的 key vs 服务器内置），管理卡只列
  store 来源；env 来源显示「服务器提供」状态与说明行（配置自己的 Key 后
  优先使用自己的）。用户 key 优先于 env 的既有语义由 `_openai_compat` 保证。
- 输入框模型选择器底部新增「配置自定义模型」入口（Dropdown footer，
  模仿 WorkBuddy 交互），点击直达设置 → 模型。
- 测试：credentials 聚焦 5 passed（含 source 翻转回归）、alpha/identity/
  storage/cloud 38 passed；GUI 50 files / 276 passed（新增 Dropdown footer
  测试）；TSC 与 alpha 构建通过。部署后线上 DeepSeek 显示
  `configured=True source=env`，新 bundle `index-BOzlwBHo.js`。

### 同日追加：「配置自定义模型」就地弹窗交互

- 采纳用户参考的 WorkBuddy 交互：输入框模型选择器底部入口不再跳转设置页，
  云端改为原地弹窗（QuickModelSetup）——精选 provider 画廊（带 ✓ 已连接/
  服务器提供/未配置状态）→ 点卡片填 Key → 测试通过即自动保存、自动选中该
  provider 推荐模型、约 1 秒后自动关闭回到对话；失败错误就地显示且不保存。
- 与设置页双联动：弹窗保存实时刷新选择器列表（onSaved → loadSettings）；
  弹窗底部「管理已配置的密钥与默认模型 →」深链设置 ▸ 模型；桌面模式保持
  原跳转（其模型流依赖 /v1/settings）。CLOUD_PROVIDERS 移入
  composerModelPolicy 供画廊与弹窗共享。
- 测试：新增 QuickModelSetup 4 项（画廊状态、表单往返、成功保存并选中推荐
  模型、失败不保存不切换）；GUI 全量 52 files / 280 passed；TSC 与 alpha
  构建通过。线上 bundle `index-Qn_IQja-.js`，health 200。

### 同日追加：修复「配置自定义模型」点击无反应

- 用户报告点击后无任何反应。本地 alpha 环境（vite dev + 真实浏览器）复现：
  菜单收起但弹窗不出现。根因是 Dropdown 的 footer 包裹层用了
  `onClickCapture` 关闭菜单——capture 阶段的 setState 触发重渲染并在真实
  DOM 中先卸载菜单子树，footer 按钮目标阶段的 onClick 被吞掉；jsdom 测试
  不做真实派发无法暴露。修复为 bubble 阶段关闭（按钮先执行、菜单后收起）。
- 真实浏览器验证完整链路：菜单 → footer → 弹窗画廊（选择服务商 + provider
  状态）→ 点卡片进入 Key 表单 → 测试/返回/管理链接/完成按钮齐全。
- GUI 全量 51 files / 280 passed；线上 bundle `index-CuspEoD6.js`，health 200。

## 2026-09-02：岗位评估与面试准备 Skill 升级（来源：高星开源项目实证调研）

- 调研并源码核查 career-ops（69.8k）、ai-job-search（39.9k）、Resume-Matcher、
  Reactive Resume、ResumeSkills 等。事实修正：AIHawk 仓库已 404 且在"不自动投
  递"红线内，剔除；Reactive Resume 有 MCP/Skill 但无申请跟踪功能。规格见
  `docs/superpowers/specs/2026-09-02-career-fit-interview-upgrade-design.md`。
- 新增 `career-job-fit`：单岗位结构化评估，固定契约（岗位画像+原型归类 → 硬门
  槛先行 → 五维匹配 → 真实缺口表三态 → JD 可信度独立呈现 → 四档结论，硬门槛
  不符直接"不建议投递"且不展开润色），结论经确认写 update_job_tracking note。
- 新增 `career-interview-prep`：六章节面试准备包（问题四级优先、STAR 锚定简历
  原文、一致性简报逐条标"经不起追问"、刁钻问题桥接式、反问清单、衔接
  mock-interview）+ 复盘教训回流规则。
- `career-job-search` 增加已确认简历下的三档粗标（对口/疑似对口/缺口明显），
  深评引导 career-job-fit，不自动批量。Persona `career.md` 写入四条真实性红线
  （用过≠做过；关键词重组不发明；宁缺不编；换重点可以改事实不行）。
- 过程中发现并修复真实后端回归：无 auth 的本地后端对代理浏览器（恒发
  `["openworker"]` 子协议）的 WS 握手不回子协议导致浏览器断开、turn 静默丢失
  （Authing 上线后掩盖）。两处 accept 改为客户端提供 openworker 即 echo；
  新增回归测试。另修 run_alpha_local.sh 缺 alpha UI origin（1421）导致 WS 403。
- 验收：本地 alpha 真实浏览器三场景全过（评估六章节契约+结论"补充事实后再判
  断"；硕士硬门槛岗位"不建议投递"且零改写建议；面试准备六章节+衔接模拟）。
  identity/deploy/alpha 回归 17 passed。部署后线上 8 个 Skill 全部激活，匿名
  边界（401/302/health）不变。

### 同日追加：career-resume-coach 结构化诊断契约

- 用户确认岗位雷达"AI 分析/改简历"入口的 coach Skill 此前未升级，本次补齐
  （吸收 Resume Reviewer 与 resume-craft）：诊断输出按四维度（成果量化/机器可
  读性/表达清晰度/结构篇幅）点名最弱行；修订清单按 严重/重要/打磨 分级且每条
  必须引用简历原行；仅重写最弱 2–3 条为 before→after，缺数字用【X%】占位由用
  户填；防注水六律（角色不膨胀、规模需澄清、抽象需支撑、功能非平台、技能需
  实践、每条改写附追问）；中文措辞（禁"负责…工作"、XYZ 中文版）；响应尾部必
  须给 可以投递/补充后投递/不建议投递 三选一结论。
- 既有工具链与确认流不变（get_job + get_confirmed_resume、保留/删除/补充/重
  写/加粗、禁文件生成）。本地 SkillLoader 解析通过；部署后线上容器 SKILL.md
  含全部新契约段（grep 3 处命中），health ok、匿名 401、0 重启。

### 同日追加：coach 输出必须自带 JD 要求清单

- 用户线上实测反馈：诊断通篇引用"要求 1/加分项 2"但对话里看不到编号对应
  的要求原文——模型内部编号却不展示清单，用户无法解析引用。
- coach 契约新增第一个章节「岗位要求清单」：要求 1…N（必备，标核心/硬性）与
  加分项 1…M 逐条附 JD 原文；后文所有"要求 N/加分项 N"引用必须与该清单编号
  一致；明确规则——用户看不到工具返回值，编号必须自含原文。
- 部署后线上容器 SKILL.md 含新章节，health ok、0 重启。另提醒用户：截图中
  的 401 来自其自配 BYOK key（尾号 f7eb）无效，需在设置→模型更换或删除。

### 同日追加：AI 简历诊断 kickoff 改为脚本确定性岗位信息卡

- 用户线上实测指出：诊断引用"要求 N"但对话里看不到编号对应内容，且不希望
  依赖模型自觉展示。落实确定性方案：`careerResumeCoach.ts` 新增
  `buildCareerJobSheet`——纯脚本从岗位记录生成信息卡（岗位名称/公司/地点/
  招聘类型/官网链接/job_id + 编号【要求清单】【职责清单】），优先用结构化
  requirements/responsibilities 数组，缺失时 `parseJdSections` 按
  职责/要求段落确定性解析，再缺失回退 JD 原文逐行编号；全程无模型参与。
- kickoff 消息的 display 与 prompt 均以信息卡开头；prompt 明示"编号以此为准，
  不得重新编号"，coach Skill 对齐为沿用 kickoff 清单编号（无清单时才自建）。
- 测试：新增 sheet 生成/解析/回退与消息断言，更新启动器与 App 级断言，
  GUI 全量 51 files / 284 passed；TSC 与 alpha 构建通过。线上新 bundle
  `index-C9XxPTZl.js` 含信息卡文案，health ok。

### 同日追加：岗位信息卡三问题修复（线上真实字节岗位反馈）

- 用户线上实测字节岗位指出三问题：①要求清单只显示 1 条（爬虫把整段要求塞进
  requirements 单元素，脚本优先信数组导致漏拆）；②条目自带"1、"前缀与"要求N"
  双重编号；③招聘类型显示英文枚举 experienced。
- 修复：结构化数组与原文解析统一走归一化管线（按 1、2、3 枚举标记再拆分并剥
  前缀）；JD 无「要求：」标签但正文带枚举行时，枚举行作为要求候选；各来源取
  条目最多者；招聘类型接 careerJobTypeLabel 中文映射（experienced→社会招聘）。
- 新增字节场景回归测试（单元素数组+无标签枚举行→要求1..3 齐全、无双重编号、
  中文类型）。GUI 全量 51 files / 285 passed；TSC/构建通过；部署后 health ok。

## 2026-09-03：云端审批放宽（只读+面试工具免审批，写类保持确认）

- 用户反馈上线试用时模拟面试与 AI 分析步步弹审批。根因：career MCP server
  默认 requires_approval=True → 所有 mcp__career__* 工具判 EXTERNAL →
  interactive 模式逐次审批。
- 方案（零核心重写）：云端 alpha 会话切 Mode.CUSTOM（interactive + 白名单免
  审批，其余照常）。alpha.py 新增 AUTO_APPROVE_TOOLS 显式白名单（22 工具：
  只读 Career MCP + load_skill + 面试流程系），显式排除三个写工具
  （import_manual_jd / confirm_resume_sections / update_job_tracking 仍需用户
  批准）。manager.py/agent.py 打通 auto_allow_tools 注入链路（未注入回落
  config.auto_allow，桌面不变）。
- 关键坑：app.py WS 处理器在 get_engine 之后有 alpha 收紧逻辑会**清空
  auto_allow_tools**——首轮回种顺序错误导致白名单失效（真实浏览器复现）。
  修复为收紧后回种 `AUTO_APPROVE_TOOLS & conversation_tools()`，并加 WS 级
  回归测试。
- 安全边界保持：agent 工具面仍被 conversation_tools 白名单限定（无 shell/
  文件写/删除类工具，agent 结构上删不了服务器数据）；写类工具维持审批；管理
  面 HTTP 封禁与 REST 鉴权删除语义不变。新增 6 项测试（白名单 ⊆ 表面、不含
  写/破坏性工具、CUSTOM 放行只读、写工具 needs_user、configure_alpha 注入、
  清空后回种）。
- 验证：本地 alpha 真实浏览器新对话 AI 分析全程零审批卡，评估完整产出；云端
  相关回归 104 passed。部署后线上 health ok、匿名 401、0 重启。

### 同日追加：输入框「技能」按钮与中文技能面板

- 用户需求：技能除 / 调用外，对话框下方有独立按钮，点开列出技能的中文名称
  与使用说明；点选后技能挂在对话框左上角并区别于普通文本。
- 实现：Composer 控件行新增「⚡ 技能」按钮（与模型胶囊并排），点开面板列出
  会话可用技能——中文名称（careerSkillLabels 映射，未收录回退原名）+ 中文说
  明 + /name 标记；点选复用既有 pickSkill 机制（/ 前缀 + skill 字段随消息发
  送），并在对话框左上角渲染挂载徽章（⚡ 中文名 + 将以 /name 随消息发送 +
  ✕ 移除，移除同时剥掉前缀）。8 个 Career 技能全部有中文元数据。
- 测试：Composer.skills 新增 3 段（面板列出与 muted 过滤、中文标题/说明、徽
  章挂载与移除、skill 字段随发送）；GUI 全量 51 files / 288 passed；TSC/构建
  通过；线上 bundle `index-DdKYoL-h.js` 含中文技能文案，health ok。

### 同日追加：技能挂载改为纯徽章交互

- 用户反馈：点选技能后输入框内出现 "/name" 前缀文本，与徽章重复。改为纯徽
  章模式——点选技能后输入区保持干净（光标在徽章右侧闪烁），技能只体现在左
  上角徽章；发送时技能仍作为独立字段随消息走。手敲 "/" 视为改用斜杠调用，
  自动解除当前徽章；✕ 按钮解除挂载。三个旧前缀断言测试按新契约重写。
- GUI 全量 51 files / 288 passed；TSC/构建通过；线上 bundle
  `index-Beq0lsB4.js`，health ok。

### 同日追加：技能徽章嵌入输入框左上角（与光标同行）

- 用户反馈：徽章不应在输入框上方单独一行，应在输入框内部左上角、光标紧挨
  徽章右侧闪烁，且支持 Delete 键删除技能。
- 实现：徽章与 textarea 放入同一 flex 行（flex-wrap，技能菜单展开时占满换
  行）；徽章 shrink-0 对齐首行，textarea 挂载时去掉左内边距、光标紧随徽章；
  空输入时 Backspace/Delete 解除徽章（onKey 顶部拦截）。斜杠弹层与徽章互斥
  语义不变（手敲 "/" 解除挂载并进入斜杠调用）。新增 Backspace/Delete 解挂
  测试。GUI 全量 51 files / 289 passed；TSC/构建通过；线上 bundle
  `index-CNUJ6iYb.js`，health ok。

### 同日追加：豆包式行内徽章对齐与删除后裁切修复

- 用户对照豆包交互：技能徽章应与输入文本/光标同字号同行高。徽章改为无边框
  无底色的行内样式（⚡ + 中文名，14.5px/22px 行高，accent 色），textarea 挂
  载态行高对齐 22px；✕ 改为悬停显示（默认视图仅图标+名称）。
- 修复 Delete 解挂后占位文字被裁半：自动增高 effect 只依赖 text，解挂不改
  变文本导致挂载态内联高度（24px）残留，而类恢复后需 41px。依赖加入
  pendingSkill。数值验证：挂载态 chipTop==taTop（854）、同行高 22/24；解挂
  后 textarea 41px、scrollHeight==clientHeight 无裁切。GUI 全量 289 passed。

### 同日追加：技能面板关闭语义与 diamond 图标

- 用户反馈两点：面板内部点击会消失（应保持打开）；⚡ emoji 图标不好看。
- 修复：技能面板加 document pointerdown 捕获监听——面板与按钮以外点击关闭，
  内部点击保持打开；⚡ 替换为 Icon 组件的 diamond 图标（按钮胶囊与挂载徽章
  同步），✕ 移除按钮改为悬停显示。新增关闭语义测试。
- GUI 全量 51 files / 290 passed；TSC/构建通过。

### 同日追加：技能按钮移至控件行左侧 + 输入框盒高恒定

- 用户反馈：技能按钮应在控件行左侧；选技能时输入框会变高，需要恒定。
- 实现：技能按钮移至控件行最左（附件菜单之前）；盒高恒定修复——外层容器
  两态均提供 pt-2.5/pb-2（补偿挂载行高差），textarea 两态均无上下内边距、
  行高 22px；真实浏览器三态测量（未挂载/挂载/删除后）composer 盒高均为
  87px 恒定。
- GUI 全量 51 files / 290 passed；TSC/构建通过。

### 同日追加：技能按钮移至权限模式选择器右侧

- 用户明确位置：不在控件行最左，而在「权限模式」下拉的右侧。
- 实现：技能按钮从控件行最左移至 ModeMenu 之后（权限模式 ⌄ · ◇技能 · …）。
- GUI 全量 51 files / 290 passed；TSC/构建通过。

### 同日追加：/ 弹层与技能面板样式统一

- 用户要求 / 呼出的列表与技能按钮面板一致。统一为：表头「可用技能」+ 每行
  中文名（skillZhTitle，回退原名）+ /name 标记 + 中文说明
  （skillZhDescription，回退原描述）；scope 徽章移除。键盘上下选择/回车
  挂载、输入过滤行为不变。
- GUI 全量 51 files / 290 passed；TSC/构建通过。

### 同日追加：输入框空态最小高度调高

- 用户要求输入框高度调高一点。自动增高最小值 24px → 40px（约两行留白），
  挂载/未挂载两态一致。真实浏览器验证：盒高 87 → 103px，两态恒定。
- GUI 全量 51 files / 290 passed；TSC/构建通过。

## 2026-09-09：启用线上岗位每日定时更新（crawler 容器）

- 用户需求：线上约 2.96 万岗位（信息与 URL）定时自动更新。核实现状：无任何
  定时任务在跑，活跃岗位 max(last_seen_at) 停在 2026-08-21。项目已有专用
  方案 deploy/crawler（独立容器、每天 CRAWL_AT 增量抓全部来源、fetch/persist
  两阶段写 PostgreSQL 共享目录、统一 offline 判断），但生产从未启动，镜像
  也未构建（compose profile 未激活）。
- 实施：部署前 PG 恢复点
  `/opt/opencareer-backups/20260909T112850Z-crawler-on/postgres.dump`
  （SHA-256 9e34bf0f…a2a97）；服务器构建 `opencareer-crawler:domain`
  （e5e00064fb15，SSH 长连接两次被办公网掐断，改 nohup 脱离会话完成）；
  单源验证 `once --only tencent-wxg-experienced`：FETCH 264 条 / 62s，
  WRITE postgres changed=122 created=36 unchanged=106 missing=54。
- 启用：`docker compose --profile crawl up -d crawler`；日志确认「调度已启
  动：每天 04:00（+0~25min 抖动），Asia/Shanghai」，下一轮 2026-09-10 04:17。
  容器 restart: unless-stopped、mem_limit 700m、host 网络直连 PG。
- 结果：活跃岗位 29,657 条，max(last_seen_at)=2026-09-09（今天）。观察项：
  明晨 04:17 全来源轮次的成功率与 ByteDanceAccessRestricted（该源本轮
  RESUME FAIL，属既有间歇性限制）；once 的 --rm 容器自行清理。

## 2026-09-10：OpenCareer 启动图标更新

- 使用白底、暖陶土橙棕和深墨灰的 OpenCareer 标识替换桌面启动图标；图形以
  “C 形职业路径 + 向上导航箭头”为核心，在 32 px 下仍保持可辨识轮廓；
  `surfaces/gui/assets/icon.png` 是后续重新生成平台图标的唯一母版。
- 通过 Tauri 官方 icon 生成器重建 macOS `icon.icns`、Windows `icon.ico`、
  通用 PNG 与 Windows Store 尺寸资源；菜单栏托盘继续使用原有单色
  `tray.png` / `tray.rgba`，避免白底彩色图在系统菜单栏失真。
- Web 端新增 `./icon.png` favicon，并确认 Alpha 构建产物包含该文件和相对路径
  引用。验证：`npx tsc --noEmit`、GUI 全量 `51 files / 290 tests passed`、
  Alpha production build、`git diff --check` 通过；产物不含
  `127.0.0.1:8765`。尝试 `npx tauri build --debug --no-bundle` 时被已有环境缺口
  阻断：`src-tauri/binaries/sidecar` 不存在；因此本轮未生成或发布新的桌面安装包，
  也未部署线上站点。


## 2026-09-11 — 小红书产品介绍视频

- 本地独立演示环境使用 1421 / 8766 端口；通过现有预览—确认接口准备 3 条虚构岗位和 1 份虚构简历。原启动脚本 seed 缺少 preview_hash，未改产品源码，分别启动后端与前端。
- 浏览器验证首页、岗位选择、收藏、申请进度保存、求职档案、分析简历选择及面试设置。默认模型返回 403 route_resolution_failed，因此视频仅展示真实界面与能力说明，未编造诊断和面试结果。
- 新增 `videos/opencareer-intro/` 视频源文件及 `artifacts/opencareer-video-20260911/` 成片、无口播字幕版、口播稿、字幕、封面、发布文案与验收记录。两版均为 75 秒、1080×1920、30 fps、2250 帧，无音轨。
- 执行 HyperFrames 0.7.48 `lint`、`validate`、`inspect`、`snapshot`、`render --quality high --fps 30`：运行和排版检查通过；带字幕源仅剩字幕轨道密度编辑提示，无字幕版零提示。`ffprobe` 核对参数，`ffmpeg -v error -i <mp4> -f null -` 两版完整解码通过，成片抽帧目视检查与源文件 ZIP 完整性通过。
- 未发布到外部平台；下一最小任务：真人配音后校准字幕及镜头节奏。如需完整实时 AI 演示，先处理模型权限。

## 2026-09-14 — 退出登录跳转修复

- 问题根因：云端用户点击“退出登录”后，前端只把 React 会话状态改为
  未登录，但没有启动托管登录跳转；Authing 已有单点登录状态也可能导致静默重新登录。
- 修复：等待 `POST /auth/logout` 成功撤销服务器会话并清除 HttpOnly Cookie
  后，导航到 `GET /auth/login`，保留当前站内路径作为重新登录后的回跳地址；
  Authing 授权请求增加 OpenID Connect `prompt=login`，防止复用上一个用户的
  单点登录状态而跳过登录/注册页。退出请求失败时仍留在当前页并显示重试。
- 验证：修复前聚焦测试稳定红灯（跳转调用 0 次），修复后前端聚焦 7 项、
  身份后端 19 项通过；GUI 全量 `51 files / 291 tests passed`，TypeScript、Alpha
  生产构建、Python compileall、`git diff --check` 与产物 localhost 护栏通过。
  本地真实 Chromium 确认请求顺序为 `logout -> login`，最终 URL 携带
  `/career/jobs?tab=favorites` 回跳地址和 `prompt=login`，模拟托管页显示登录/注册
  内容；浏览器后退返回 `about:blank`，未恢复旧的私有页面。
- 2026-09-16 已随模拟面试与输入框修复部署到生产环境；仍需用两个虚构账号
  完成“A 退出 → 显示 Authing 登录/注册页 → B 登录”的最终换账号验收。


## 2026-09-14 真人配音产品介绍视频

用户提供 70.784 秒真人录音，要求剪入此前 75 秒产品视频。新增独立工程 `videos/opencareer-voiceover-20260914/` 与交付目录 `artifacts/opencareer-voiceover-20260914/`，保留原录音和 9 月 11 日视频。按七段录音重排页面切换；保留 1 倍语速，整理首尾空白和段间停顿，规范音量；33 条录音对齐字幕；末页改为已上线与第一轮内测邀请。

验收命令：HyperFrames 0.7.48 `lint` / `validate` / `inspect` / `snapshot --at 4,12,22,34,44,56,69` / `render --quality high --fps 30`；`ffprobe -show_entries stream=codec_type,codec_name,width,height,sample_rate,channels,duration,nb_frames -show_entries format=duration,size -of json`；`ffmpeg -v error -i <mp4> -f null -`；对成片音轨本地 faster-whisper small 转写复核。画面 1080×1920、2250 帧、75.000 秒；容器 75.029333 秒（音频编码帧尾差）；H.264 与 AAC，完整解码通过，音量 -16.62 LUFS / 真峰值 -4.48 dBTP。静态检查只有字幕轨道密度提示，运行与布局检查无错误；七页预览及成片抽帧人工视觉检查通过；转写确认七段与内测结尾完整。未声称真人试听。

工具边界：最新版升级探测因 Node.js 20.20.2 不符合新版 >=22 要求失败，保留原 0.7.48；本次未改产品依赖。录音在本机转写，未上传，未发布。下一步由用户播放成片确认配音节奏。

## 2026-09-16 — 模拟面试与输入框技能体验修复

- 生产问题定位：小米「AI 产品经理（B 端方向）」岗位的结构化
  `requirements` 数量为 0，但原始 JD 有 647 个字符且包含完整“任职要求”，导致
  面试蓝图校验直接返回“模拟面试参数无效”。修复仅在结构化要求为空时，从公开
  JD 的明确要求章节做确定性回退解析，并在职责、部门、日期、编码、学历、工作年限、
  招聘人数、优先条件、岗位亮点等元数据边界前停止；不调用模型、不补写岗位事实。
- 输入框修复：空态仍保留 40 px 呼吸空间，输入首字后立即收回到单行 24 px，消除
  首字下方多余留白。技能入口改为无边框的书本线性图标；展开后的技能列表位于输入区
  上方并以细分割线区隔，选中后收拢为顶部上下文栏，正文输入保持完整宽度。
- 真实验收顺带发现面试设置仍把 15/20 分钟标成 8/10 题，而当前标准流程固定五轮；
  已将三个时长选项统一显示 5 题并补回归，避免设置弹窗与会话进度不一致。
- 回归：面试聚焦套件 `86 passed`；要求解析文件 `48 passed`；GUI 全量
  `51 files / 292 tests passed`；TypeScript、Alpha 构建、Python compileall、
  `git diff --check` 与产物 localhost 护栏通过。代码审查发现并补齐无冒号标题、
  元数据边界和“工作年限3年以上”等前缀误判回归，最终无 P1/P2 问题。
- 发布：恢复点 `/opt/opencareer-backups/20260916T065646Z-interview-composer`
  的 PostgreSQL dump 为 142 MiB，SHA-256
  `362e9f61f7bd538e733b106037b457f95f48a32ef753f2b98f4ea549cca5c21f`；
  使用干净暂存目录构建并发布，最终前端 bundle `index-V4RdzwO6.js`，后端镜像清单
  `sha256:8bc6274e0c67436aaed4dd0aa3fecf70ef58bbd54b611a32d789d7ba2780893d`。
  公网 health、PostgreSQL、Redis 均 ready，后端 healthy，Caddy 与抓取器保持运行。
- 线上真实浏览器验收：技能列表和已选技能顶部栏的分割线可见；同一小米岗位已成功
  创建模拟面试并进入会话/工具授权步骤，不再出现“参数无效”。为避免额外模型消耗，
  验收到授权步骤即停止，未生成首题。下一最小任务是由用户继续授权并体验完整五轮。

## 2026-09-16 — 默认自动审批与模式入口（本地）

- 根因：PostgreSQL 模拟面试预创建 Career 对话只含 agent 元数据，加载时回退
  Interactive，覆盖云端经理的 Custom 默认值。云端 WebSocket 首次接入引擎现在
  收敛为安全 Custom；同一运行引擎中后续手动切换保留，服务重启后恢复默认。
- 沿用显式安全工具白名单，不改核心权限引擎、不绕过工作区信任。历史 Auto、
  Discuss、Plan 模式请求收敛为 Custom；重要数据写入和未知工具不自动放行。
- 模式菜单显示“自动审批”和“执行前询问”，移除“仅讨论”和“完全访问”。
  修改 app.py、App.tsx、Composer.tsx 与对应测试，并新增本轮设计说明。
- RED → GREEN：历史对话接入默认模式和菜单名称先失败，修复后权限相关
  27 项通过；包括真实 WebSocket 下脚本化面试工具调用无 permission_required，
  手动模式可询问、旧 Auto 不能绕过重要写入。GUI 51 文件 / 293 项通过；
  TypeScript、Alpha build、compileall 和 diff 检查通过。完整 server.py 测试在
  原有 shell 线程相关用例等待，已中止，不能计为全量通过。
- 真实浏览器确认默认中文标签、菜单两种模式与选中 Custom，窄屏标签不换行。
  本地 1421/8766 已启动。本轮未部署线上；下一最小任务是本地体验后发布。

## 2026-09-16：公网安全缺口修复（本地完成，发布等待备份导出授权）

- 设计见 `docs/superpowers/specs/2026-09-16-cloud-security-hardening-design.md`。
  新增 `coworker/server/cloud_security.py`，改动 `alpha.py`、`app.py`、`manager.py`、
  `coworker/providers/registry.py`：公网方法/路径白名单默认拒绝；共享技能只读；
  所有技能工作区查询固定在部署工作区；个人会话技能开关保留；Persona 仅返回 Career。
  HTTP/WebSocket 配置 Authing 时不再接受旧共享 Token。所有引擎构建都裁剪工具、
  清除历史授权；删除任意网址读取工具，常规读取与面试自动审批，关键写入继续确认。
- 模型提供方只允许固定官方 HTTPS 地址，禁用服务器程序、本机模型和宿主云凭据。
  保存、验证、历史配置加载均校验；不探测禁用的程序或本机服务；字段限定为有界字符串。
  请求体最多 16 MiB（含分块传输），每用户每分钟 180 请求/30 写请求；
  每用户 8 WebSocket/2 运行回合，全进程 32 连接/4 回合；事件流也限速。
  云端不启动桌面消息网关和自动任务调度；拒绝日志仅记录分类，不记录私密内容。
- 改动 `deploy/Caddyfile`、两份 Compose、`deploy/sync-to-server.sh` 与
  `scripts/run_alpha_local.sh`：域名编排删除 18080 映射及 Token 注入；维护编排仅
  绑定 127.0.0.1；后端只读根文件系统、移除 Linux capabilities、禁止提权、限制
  进程数，数据卷保留可写。发布默认正式域名，并通过域名检查健康与重新加载代理。
  本地 Alpha 默认 DeepSeek 官方提供方，不再默认禁用的 Aiden。
- 验收：新增 `tests/test_cloud_security.py` 从 18 项失败到通过，扩充至 23 项；
  最终 `.venv/bin/python -m pytest` 的云安全/自动审批/身份/Compose/模型/租户/
  运行态/面试 12 个相关文件共 **171 passed**。GUI `npx tsc --noEmit`、
  `npx vitest run`（51 文件/293 项）、Alpha build、compileall、bash -n、
  git diff --check 通过。线上现有 Caddy 2.8.4 对新配置 `caddy validate` 通过。
  真实本地浏览器确认首字无异常缩进、8 项技能在上方展开并带分割线、自动审批标签。
  不宣称项目全量测试、真人双账号人工验收或第三方渗透测试已完成。
- 发布恢复点：服务器 `/opt/opencareer-backups/20260916T124309Z-security`，267 MiB；
  PostgreSQL 超级用户 custom dump、旧镜像、前端、配置、数据/Caddy 卷与 SQLite
  Online Backup 完成并校验。隔离数据库 `opencareer_security_restore_20260916`
  成功恢复，业务计数一致。配置加密，密钥仅在本地，未打印。
  离机复制因包含生产用户数据被安全审批拒绝，已向用户请求明确导出目的地授权；
  未尝试绕过拒绝、未同步或重启生产。当前线上仍是旧版本，不能对外宣称已安全修复。
  待授权后复制并校验离机副本，再发布和核验旧入口不可达与 Cookie-only API 拒绝。
- 仍需真人双账号验收、上线并发/持续存储观察；本轮限流是单进程实现，不能替代
  上游抗流量攻击保护或完整用户存储配额。能力约束不保证模型输出不会被提示词攻击影响。

## 2026-09-17：授权离机恢复点与安全版本发布

- 用户明确允许向 `.local-state/backups/server/20260916T124309Z-security/`
  导出生产恢复点；链路中断后断点续传，最终离机 SHA-256 清单全部通过，配置
  解密到 `/dev/null` 校验通过，目录禁止其他用户访问。密钥仅在本地；未输出凭据。
- 维护窗口停止后端与采集，另存 `postgres-final.dump`、最终数据文件和 SQLite
  Online Backup；在独立数据库 `opencareer_security_restore_final_20260917`
  恢复，全部应用表行数一致、Blob 内容指纹一致。最终恢复点也已完整离机校验；
  保留原始备份、旧镜像、生产卷与隔离恢复数据库，没有删除生产数据。
- 补充认证先于请求体缓冲，分块请求体读取最多 30 秒；新增回归后相关 12 文件
  共 **172 passed**，核心 5 文件 **56 passed**；GUI TypeScript 和 Vitest
  **51 文件 / 293 passed**，compileall、bash -n、diff 检查通过。
  同步脚本额外排除 `.local-state`、`.zcode`、`.env`，防止同步本机生产备份或秘密。
  域名手册明确历史公网 18080 操作已失效，回滚不得重新开放免登录入口。
- 新镜像先在无网络、只读且不挂生产数据的容器中通过纯安全策略检查，再发布。
  线上后端镜像 `sha256:4e66643a972af6c2278b5ff4980dc07facb464e4ddc6ae42621559de227edf7b`；
  健康且重启次数 0，非 root、只读根、移除全部 Linux 能力、禁止提权设置生效。
  Caddy 重新创建及加载，采集原服务恢复运行；没有删除数据卷或旧镜像。
- 生产域名 health 200，匿名身份为未登录；agents/providers/sessions 匿名读取
  401，共享技能 POST/DELETE 和未知路径 403。容器内使用真实旧 Token 验证
  HTTP 401、WebSocket 403，未输出 Token。宿主机无 18080 监听，公网连接拒绝，
  Caddy 仅映射 80/443。真实浏览器首页显示登录入口，点击后进入 Authing。
- 复查发现云端 Markdown 外链图片自动加载仍可能成为私密内容外传通道。
  尚未修改图片行为；已请求用户确认“云端图片不自动加载、普通链接仍可手动打开、
  桌面图片不变”的新增界面验收边界，等待回复。不能宣称全部外传风险消除。
  真人双账号与五轮面试、容量/压力和第三方渗透仍未完成。

## 2026-09-17：用户确认云端回复图片保护并上线

- 用户确认关闭云端回复图片自动加载，保留普通链接手动打开及桌面图片行为。
  更新安全规格，修改 `surfaces/gui/src/components/Markdown.tsx` 及对应测试。
  云端图片节点替换为固定隐私提示，无 img/src、无图片地址残留；非 Alpha
  模式仍渲染图片。没有新增依赖，没有改变网站正常图标等界面资源。
- 测试驱动：Alpha 真实构建模式下图片保护先失败，最小修复后通过。构建模式
  被测试工具静态处理，不能用运行时环境替身切换，最终按真实模式分别验收，
  没有模拟内部 API。`npx vitest run --mode alpha src/components/Markdown.test.tsx`
  为 6 passed / 1 个桌面专属 skipped；`npx tsc --noEmit && npx vitest run`
  为 51 文件 / 294 passed / 2 个云端专属 skipped，两种模式的新增用例均执行。
- 隔离虚构浏览器页面使用真实 Markdown 组件，确认行内及引用式图片均显示
  “图片未自动加载”，岗位官网链接仍保留；没有读取用户资料、调用模型或点击
  外部测试链接。人工复核本次 diff，无内部模块替身及自动恢复图片入口。
- 仅前端发布：在服务器 `/opt/opencareer-backups/20260917T-image-privacy/`
  保存旧前端归档并通过 SHA-256 校验，先上传新资源，再切换 index.html。
  保留旧资源及既有恢复点；不重启后端，不改业务数据和数据库。
  构建执行 `VITE_ICP_NUMBER=京ICP备2026055760号-1 SKIP_NPM_CI=1 bash deploy/build-frontend.sh`
  （隔离发布目录），类型、Alpha 构建及 localhost 护栏通过；存在既有 chunk
  大小与静态/动态导入提示，不影响成功构建。
- 正式域名返回首页与 `index-DeK2qwgD.js` 的 SHA-256 和本地发布构建完全一致；
  health 为 ok，真实浏览器生产首页登录入口正常。已同步本次源码和测试，
  未发布隔离验收页。已打开的旧页面需刷新才能加载新保护。
- 图片自动请求这条外传通道已收敛；用户主动打开不可信链接仍可能泄露链接中
  的信息，不能把 noreferrer 或图片拦截视为所有提示词攻击的完整防御。
  下一最小任务仍为真人双账号隔离与完整面试验收。

## 2026-09-18 — 三阶段支持模块本地实现与验收

- 用户确认公开边界后按顺序实施诊断基础、用户反馈、管理员问题中心及基础告警。
  新模块位于 `extensions/support/`，不重写 Agent 循环、权限或核心会话；管理
  能力不进入工具注册表。云端仅使用现有 PostgreSQL，默认无人有管理权限、不
  外发日志。批准规格与运维说明分别见本日 feedback-support 规格、文档 20。
- 诊断：随机服务器编号、白名单元数据、HTTP/实时模型错误、浏览器错误边界和
  网络错误限频上报；不保存请求/模型/异常正文。云端运行日志仅固定级别/组件，
  无访问日志/堆栈正文。技术记录有容量和留存上限；存储故障不阻止原业务。
- 用户反馈：侧栏、登录前、窄屏及报错入口，受控文本提交、幂等重试、自己的
  历史和回复；关联前验证编号可用性与所有权。真实浏览器发现安全拒绝请求编号
  未持久化导致提交失败，已修复；没有有效编号仍可提交。失败不丢草稿。
  补测诊断过期后的重复提交：原反馈可幂等返回，但新反馈不能关联过期编号。
- 管理：仅服务端编号白名单赋权，列表/详情/回复/状态/单层重复问题合并和无
  正文审计；合并同步回复，不泄漏另一用户描述/编号。迁移 11–18 强制支持表
  行级隔离，匿名仅查询/插入，管理员上下文事务局部。独立运维检查健康、内存/
  磁盘、可选重启；告警去重与 15 分钟冷却，测量失败不视为恢复；数据库故障
  暂存有界类别。独立主机任务模板已提供，未在生产启用或接外部通知。
- 本地隔离 PostgreSQL 16 角色非超级用户、无绕过行级权限；迁移和数据库回归
  8 passed。独立检查重复运行证明通知冷却和测量失败保留活动告警，单连接
  复用后普通账号不能读取管理员数据。全部虚构账号，未访问生产数据库。
- 真实浏览器 Alice 提交→管理员回复→Alice 刷新查看；Bob 无该反馈和管理入口。
  登录前匿名提交成功；实际 390×844 视口无横向溢出。隔离测试端口 1423–1426/
  18790，没有替换原 localhost:1421。未调用外部模型或发送真实用户材料。
- 验收：后端支持/安全/身份/审批相关 pytest 72 passed；会话和主机检查 57
  passed。旧技能会话测试改为真实技能文件和工作区，解决菜单虚构却不能预载
  导致等待的问题。GUI `npx vitest run` 56 文件、301 passed / 2 skipped；真实
  Alpha 模式支持相关 12 passed / 1 skipped。`npx tsc --noEmit`、Python
  compileall、`git diff --check`、隔离目录 `vite build --mode alpha` 通过；
  产物无本机后端地址和虚构凭证。已有大文件、导入和客户端弃用提示保留。
- 保留现有未提交改动，无提交/发布/生产权限变更；测试数据库保留，临时服务
  收尾停止。下一最小任务：确认实际管理员编号及告警目标，按文档 18/20 备份、
  发布、启用监控并做真实 Authing 多账号验收。匿名容量、异地监控、压力及真人
  面试 Gate 仍待完成，不作绝对安全保证。

## 2026-09-20 — 用户反馈、诊断与问题中心发布生产

- 用户确认一名管理员账号及“暂不外发消息、由管理员主动查看问题中心”的运营
  方式。发布时在服务端将该账号唯一映射到稳定应用用户编号；邮箱和内部编号均未
  写入仓库。监控定时器保持未安装、未启用，没有接入邮件、短信或飞书等外部渠道。
- 发布前 Python 支持/安全/身份/会话/面试相关套件 `191 passed`；GUI 全量
  `56 files / 301 passed / 2 skipped`。TypeScript、Python compileall、Alpha
  生产构建、同步脚本语法、`git diff --check` 与本机地址护栏通过。候选镜像先在
  无网络、只读根、移除全部 Linux capabilities、禁止提权的环境完成策略检查；
  PostgreSQL 候选库成功应用迁移 11–18，五张支持表均开启强制行级安全隔离。
- 发布恢复点为服务器
  `/opt/opencareer-backups/20260920T090325Z-support`，停写最终数据库已在独立库
  完整恢复；46 张原应用表行数、426 个 Blob 大小与内容指纹、259 个约束全部一致。
  恢复点 SHA-256 清单通过，并同步到本机私有目录
  `.local-state/backups/server/20260920T090325Z-support`；配置仅保存加密副本，
  本机密钥权限 600，解密哈希核对通过。发布中间产生的服务器明文环境副本已删除，
  加密恢复点与旧镜像、旧静态资源继续保留。
- 生产发布标识 `20260920T090325Z-support`；后端镜像
  `sha256:8df16222200638b4ad32b3b9c85375224cc751b78548b2c4dcd50baec9d8f1be`；
  前端 `index-C7Kso1l8.js`。数据库迁移为 1–18，支持表初始为空；发布前已有
  业务表精确行数与全部 Blob 内容指纹在发布后保持不变。后端 healthy、三容器
  restart 0；根文件系统只读、非 root、禁止提权、capabilities 全移除，宿主机
  18080 无监听。
- 公网真实代理路径 health 200、未登录会话 200/未认证、私有会话和管理接口 401、
  非法 Origin 403、未知 Shell 路径 403；匿名反馈用不足五个字符的无写入请求
  返回 422。生产首页及 JavaScript 文件 SHA-256 与发布构建一致。真实浏览器确认
  首页登录入口进入 Authing“验证码登录 / 登录注册”页；未发送验证码或提交账号。
  运行日志汇总无 error/traceback，后端保持零重启。
- 仍需管理员本人登录后确认问题中心入口、完成一次“用户提交→管理员回复→用户
  查看”的生产闭环，以及双真人账号隔离、容量/压力、异地可用性和完整五轮面试
  Gate。当前边界降低私密日志与 Agent 越权风险，但不宣称绝对安全或提示词攻击
  完全消除。
- 发布后双轴代码审查发现并修复三项：合并工单不再把主问题的定制回复复制给其他
  用户，仅同步固定无用户内容的状态提示；16 MiB 写请求新增每用户 2 个、全进程
  4 个在途缓冲上限并在所有返回路径释放；生产同步脚本必须先验证完整恢复点及
  前后端发布标识，前端候选资源最后原子替换入口文件，失败自动恢复旧镜像、代理
  配置与静态入口。路由与独立检查的 Python 类型标注同时补齐。
- 热修复相关安全/支持回归 43 passed / 1 skipped，最终聚焦回归仍为
  `191 passed / 1 skipped`；候选镜像再次在无网络、只读、无生产数据容器中验证
  跨用户回复隔离和并发准入。复审后进一步拆分匿名与登录用户的请求体容量池；
  合并到已解决主问题会立即显示固定的已解决提示；同步脚本还会确认恢复点对应
  当前镜像/代理/前端，跳过前端构建时核对版本，检测到新迁移则拒绝一键发布。
  当前生产镜像为
  `sha256:65957aaff887980380acf5d08cadde37e2f4ddce428207f11d4ba71d2529ec30`，
  初始及上一热修复镜像均保留。热更新未迁移数据库、未改
  前端；公网边界、全表行数、Blob 指纹、管理员映射与发布标识复验通过，三容器
  restart 0，日志无 error/traceback。

## 2026-09-20 — 管理员 Authing 回调失败诊断与本地修复

- 生产截图显示管理员登录后停在回调接口的原始 JSON 400 错误页。
  未复用或记录截图中的一次性授权码和 state。生产只读探测确认
  Authing 元数据和令牌端点可达、Issuer/回调地址一致、客户端与状态密钥
  已配置；登录入口正常下发 1,042 字节的 HttpOnly/Secure/SameSite=Lax
  流程 Cookie。管理员近两小时没有新会话，故失败发生在 Authing 返回后、
  应用会话创建前；当前白名单日志不保留异常类别，无法对该次历史回调
  进一步区分状态丢失与令牌交换失败。
- 先建立精确失败用例：回调供应方拒绝时，旧行为稳定返回 JSON 400。
  修复后仍严格拒绝无法验证的 state/令牌，但清空短期 OIDC 流程状态并
  跳回产品登录页；页面显示“登录没有完成”与“重新登录”，新流程不会
  携带旧 `auth_error`，不自动无限重试，不暴露授权码、state 或内部异常。
- 聚焦验收：后端回调/重复回调 `2 passed`，GUI 登录门 `4 passed`；
  Python compileall 与本轮 diff 检查通过。本轮尚未发布；发布后需用全新登录
  流程验证会话创建与管理员问题中心入口。

## 2026-09-21 — 登录回调恢复页已上线

- 用户明确授权将完整生产恢复点复制到项目私有的
  `.local-state/backups/server/20260920T101438Z-auth-callback/`。服务器与
  离机副本逐文件 SHA-256 通过，加密配置解密哈希一致，离机密钥权限
  600，服务器临时密钥已删除。授权后发现线上 Blob 由 426 增至 455，
  因此再次停写 47 秒刷新数据库与数据卷快照；隔离恢复复验 51 张表、
  455 个 Blob 的大小/内容指纹、175 个约束完全一致，5 张支持表仍强制
  行级隔离。离机副本刷新后再次通过全部校验，约 324 MiB。
- 首次发布暴露了同步脚本的原子性缺口：前端候选目录位于带 `--delete`
  的源码同步根下，会在后端构建前被删除；错误陷阱也没有穿透远程函数。
  以失败测试锁定后，候选目录改到 `REMOTE_DIR` 同级的独立发布目录，Shell
  启用 `errtrace`。先用已验证恢复点切回旧后端镜像，确认健康后重新完整
  发布。回归 `1 passed`、Shell 语法和 diff 检查通过。
- 当前生产后端镜像
  `sha256:19d0813ee61d5306dd93836ce14c397bce73eb62876d2a13394a425826acb3d0`，
  前端 `index-CG8VUjXg.js`；本地/服务器 index 和 bundle 哈希完全一致。
  真实失败回调链路用无效诊断授权码验证为 307 跳转，清理流程 Cookie，
  Location 不含 code/state，不再返回 JSON。真实浏览器可见“登录没有完成”
  和“重新登录”，新链接不携带旧错误参数。
- 发布后身份/编排聚焦回归 `30 passed`，GUI 身份 `8 passed`；TypeScript、
  compileall、Shell 语法和全库 diff 检查通过。三容器 restart 0，health
  200，匿名私有/管理接口 401，migration 18，近 30 分钟脱敏日志无 error/
  traceback，隔离临时库已清理。仍需管理员本人点击“重新登录”完成
  真实验证码登录和问题中心权限 Gate；本轮没有代输验证码或复用原回调参数。

## 2026-10-12 — Authing 免费用户池切换，邮件登录仍待供应商生效

- 用户提供新用户池个人实名认证完成截图。只读确认新应用的 Issuer、App ID、
  登录/登出回调与现有网站匹配，原线上后端健康但仍指向已停用旧池。
- 切换前建立 `/opt/opencareer-backups/authing-login-20261012-v1` 服务器恢复点：
  PostgreSQL 超级用户 custom dump、Compose、Caddyfile、加密 `.env`；逐文件
  SHA-256 通过，`pg_restore --list` 在服务器通过。离机副本位于
  `.local-state/backups/server/authing-login-20261012-v1/`，逐文件 SHA-256 通过，
  解密密钥仅在离机副本且权限 600。旧数据、镜像与容器卷未删除。
- 仅替换服务器 `.env` 的三项 Authing 连接参数并重建 `backend-a`；
  `docker compose config --quiet`、线上 health 200、匿名会话
  `authenticated=false`、登录 302 指向新用户池，均通过。没有同步本地脏工作树。
- 真实浏览器新登录页可打开，但发送邮箱验证码返回 Authing 错误：
  “使用邮箱服务前，请联系管理员完成实名认证”。这与控制台完成状态矛盾；
  因此尚不能宣称登录已修复，真实回调与管理员权限未验收。后续需等供应商
  邮件额度生效或联系 Authing 排查，再做完整登录测试。当前保留新池连接配置，
  旧加密配置可恢复。

## 2026-10-12 — 更正新用户池邮件与访问授权配置，恢复登录

- 更正上条“等待供应商邮件额度”的推断：新用户池个人实名认证已完成，
  但用户池级“开启邮件服务”实际为关闭。开启后重新登录控制台，开关保持开启；
  经用户明确允许，本轮仅主动向指定管理员邮箱发送一次验证码，原“完成实名认证”
  发码错误未再出现，页面进入倒计时，用户收到验证码。
- 首次提交后 Authing 提示“无权限登录”。检查同一应用的“访问授权”发现
  已启用的“所有人：拒绝”规则。用户确认公开注册/登录目标后，将该规则改为
  “所有人：允许”；控制台显示修改成功并刷新为允许，用户用已有验证码完成
  登录，回到 `https://app.opencareer.online/`，首页显示其账号。
- 更换用户池后，Authing 身份在 OpenCareer 获得新的内部用户编号，而生产
  `OPENCAR_SUPPORT_ADMIN_IDS` 仍指向旧编号。先在 Authing 用户详情核对邮箱
  与主体，再通过生产 `identity.external_identities` 表核对新主体、邮箱和应用
  内部编号，仅精确替换该环境变量；`docker compose config --quiet` 通过，
  仅重建 `backend-a`。后端健康、运行时白名单匹配；重新打开“帮助与反馈”后
  出现“问题中心”，问题列表可读。旧编号不再保留管理员权限；除正常登录创建的
  身份与会话记录外，未手工修改数据库、前端或其他环境变量，也未在仓库记录邮箱
  和用户编号。
- 本地身份回归：`.venv/bin/python -m pytest tests/test_authing_provider.py
  tests/test_server_identity.py -q` 为 `20 passed`；支持模块回归：
  `.venv/bin/python -m pytest tests/test_support_feedback.py
  tests/test_support_diagnostics.py -q` 为 `15 passed`；两组均有同一个现有
  Starlette 废弃警告。`git diff --check` 通过。本轮未验证第二个真人账号的
  跨账号隔离，也未新建反馈或更改用户业务数据。

## 2026-10-16 — 独立开源候选与本地启动验收

- 用户确认旧维护仓库继续私有，新仓库使用脱敏干净历史；审查范围为 `9854532`
  后的修复与本次发行配置。新增独立 `start_local.py`、本地前端模式、安装与来源
  说明，保留 MIT 许可；未操作线上部署、容器或数据库。
- 无虚拟环境、前端依赖和用户数据的新源码副本，默认命令已完成首次安装、构建、
  启动并打开页面。按两轴审查补齐模型环境隔离和旧部署补丁导出排除。
- 真实浏览器发现技能选择清空普通草稿，最小修复后保留草稿；本地设置说明不再
  误称使用线上共享密钥。审查与边界见 `23_OPEN_SOURCE_REVIEW.md`。
- `OPENCAR_TEST_LOCAL_BROWSER=1 OPENCAR_TEST_LOCAL_INSTALL=1 .venv/bin/python
  -m pytest tests/test_local_browser.py tests/test_local_installation.py
  tests/test_local_launcher.py -q`：5 passed。虚构模型密钥仅用于本地接口及外部
  HTTP 拦截测试，无真实模型调用。
- `npx tsc --noEmit` 通过；`npx vitest run --maxWorkers=2`：56 files、303 passed、
  2 skipped。默认高并发曾在本机高负载超时，降并发后完整用例通过，未删除断言。
  alpha 构建到隔离临时目录通过，无开发后端地址；compileall 和 diff 检查通过。
- 此前本轮后端 1410 passed / 28 skipped、领域 452 passed；最终后端增量回归、
  归档扫描与远端状态在后续记录。旧英文桌面浏览器套件有失效项，保留手动工作流，
  不声称全部通过；首版不发布桌面安装包、Docker 包或 Windows 验收声明。

### 最终本地回归与快照检查

- 后端完整回归：`.venv/bin/python -m pytest tests -q` 为 1411 passed、29 skipped，
  仅现有 Starlette 废弃警告。公开候选从已提交源码 `git archive HEAD` 导出；
  Gitleaks v8.30.1 当前源码扫描约 9.27 MB，未发现密钥，旧部署补丁不在归档中。
- 现有私有仓库 `cloud-alpha` 已推送并核对远端提交。生产域名只读请求 HTTP 200；
  没有执行部署。新仓库最终可见性应以 GitHub 当前页面为准。

### 远端 Linux 首轮验收修正

- GitHub 首轮源码扫描、前端测试和真实本地浏览器通过；后端暴露两个问题：
  新模型库使用 HTTPx2，测试原仅拦截 HTTPx，虚构密钥请求被官方服务以 401 拒绝。
  已补齐双传输层拦截并禁止测试 socket/DNS 访问；没有真实用户数据或有效密钥发送。
  开发环境与全新模型库环境的目标地址测试均通过。
- 原定时任务测试在 Linux 发现等待审批恢复后 run_count=2 的竞态：旧 due 快照
  被排队后才检查运行状态，可能错过刚结束的任务。仅在排队前增加运行中检查，
  保留原执行入口防重叠保护；38 项相关回归通过，不重写调度器或 Agent 循环。
- 按依赖审计升级 Vitest 到 4.1.12、应用兼容补丁；Audio 构造器测试适配函数写法。
  剩余 Tailwind 3 构建链 7 项拒绝服务告警及使用边界已公开记录在 SECURITY.md，
  不宣称所有依赖漏洞清零，不在本轮扩展到 Tailwind 大版本迁移。

### 2026-10-17 — 可选识别测试分类与公开前核验

- 远端第二轮后端为 1411 passed / 29 skipped，前端、本地隔离、真实浏览器和
  源码扫描通过。领域基础套件中的实际 OCR 安装验证漏标可选验收标记，已补齐；
  不删减识别或脱敏断言，安全失败用例继续在基础套件运行。
- 本地安装验证器 2 passed；不安装可选组件的领域测试范围为 447 passed /
  5 deselected。文档明确提供可选识别验收命令；等待本次远端全绿才公开新仓库。
- 原私有仓库和干净历史候选分别同步，生产服务仍未部署、重启或修改数据。

## 2026-10-19 — 构建依赖修复与图文安装文档

- 用户确认本次同时升级样式工具并做界面回归，不部署线上。开始时工作树干净，
  维护基线为 `a248379`；未修改 Python 核心、生产配置或用户数据。
- 原完整 `npm audit --json` 为 7 项（5 high、2 moderate），来自 braces 和
  postcss-selector-parser 两个根因及其依赖链。Tailwind 3.4.19 升级至 4.3.3，
  添加同版本 PostCSS 适配器并移除不再需要的 autoprefixer；完整审计与
  `npm audit --omit=dev --json` 均为 0 项。`npm ls` 确认旧受影响链已移除，
  没有用忽略项或关闭检查来降低计数。
- 依官方迁移规则把 `outline-none` / `shadow-sm` 分别迁移为 `outline-hidden` /
  `shadow-xs`，保留强制颜色模式下的焦点轮廓。主题变量改为原生颜色值；保持
  utilities 与旧 styles.css 的无层叠分层优先级，避免大量旧组件被覆盖。
- 重新运行 `npm ci`、`npx tsc --noEmit` 通过；`npx vitest run --maxWorkers=2`
  为 56 files / 303 passed / 2 skipped。`OPENCAR_TEST_LOCAL_BROWSER=1
  OPENCAR_TEST_LOCAL_INSTALL=1 .venv/bin/python -m pytest tests/test_local_browser.py
  tests/test_local_installation.py tests/test_local_launcher.py -q` 为 5 passed。
- standalone 与 alpha 均构建到独立临时目录，通过；alpha 无 `127.0.0.1:8765`。
  构建仍有既有大体积 chunk 和静态/动态混合导入提示，它们不是本次依赖安全告警。
- 独立空数据目录中的真实浏览器验证首页、技能保留草稿、岗位详情、模型配置，
  以及深色和 1024 像素宽配置页。前后首页截图一致，模型配置布局保持；岗位表单
  有少量像素差异，未发现控件丢失或遮挡。页面无 JavaScript 错误，未填真实密钥，
  未调用付费模型。截图等待技能加载后保存，避免把加载中误判为样式回归。
- README 重写为环境准备、启动、模型密钥、首次求职流程、可选 OCR/语音、备份
  与故障处理；新增 5 张真实界面 PNG（合计约 568 KiB），仅虚构岗位与空密钥表单。
  本地 Markdown 渲染确认 5 张截图、图标和徽章均加载，14 个本地引用无缺失。
- CI 的前端 Node 版本统一为 22，加入包含开发依赖的中等级别审计门槛；安全说明
  保留旧告警历史并追加已修复状态。新的浏览器版本要求已在 README 和本地指南说明。
- 限制：本次未重新执行全量 Python 后端/领域套件；业务 Python 未修改，已有本地
  端到端覆盖通过。真人模型/麦克风、原生 Windows 与旧系统桌面壳仍未验收。
  本次依赖零告警不是整个项目的绝对安全保证。远端同步需按用户选择另行核对。

## 2026-10-19 — 按公开 README 复验新用户安装与首次使用

- 用户授权发现问题后直接修复并同步公开仓库，禁止影响线上。以公开 `703f69f`
  匿名克隆到独立临时目录；使用 Python 3.12.13、官方校验通过的隔离 Node.js
  22.23.3、全新 `.venv-local` / node_modules / 数据目录，不读取维护者密钥。
  未改变系统默认版本，没有执行部署、生产配置或数据库操作。
- 真实执行 `python3.12 start_local.py` 复现 ensurepip 失败：启动器默认复制管理器
  符号链接后的 Python，但 pyvenv.cfg 的 home 指向 shim 目录，找不到标准库。
  改用解析后的解释器路径运行标准 `-m venv`；检测 pip 是否可用，在安装中断后
  原地补齐环境并失效安装标记，不删除用户数据。补充完整 Python/venv 的错误指引。
- 回归先失败：`OPENCAR_TEST_LOCAL_BOOTSTRAP=1 .venv/bin/python -m pytest
  tests/test_local_bootstrap.py -k True -q` 报 `No module named pip`；修正后两种
  全新源码安装路径（首次安装、已有 Python 但缺 pip）均通过，`2 passed`。
  测试复制 Git 跟踪源码，不复制工作区环境或数据；CI 新增同一真实安装门槛。
- 空白浏览器发现未配置密钥仍显示默认模型，发送后仅显示通用失败。仅 standalone
  构建按所选服务商实际配置判断可用性；托管 alpha 保持原模型策略。复用模型配置
  弹窗引导，关闭后保留草稿；简历暂存前也检查配置。弹窗在本地模式明确密钥存于
  本机，避免沿用“服务器私人目录”的误导文案。聚焦回归修正前 4 失败，修正后通过。
- README / 本地指南补齐终端打开、环境版本确认、安装中断重试，以及文件简历、
  粘贴简历和“PDF（仅用于对话）”三种入口差别；不再把文件上传等同于已确认档案。
- 验收：`npx vitest run --maxWorkers=2` 为 309 passed / 2 skipped；
  `npx tsc --noEmit`、`python -m py_compile start_local.py tests/test_local_bootstrap.py`
  和 `git diff --check` 通过。`OPENCAR_TEST_LOCAL_BROWSER=1 OPENCAR_TEST_LOCAL_INSTALL=1
  .venv/bin/python -m pytest tests/test_local_browser.py tests/test_local_installation.py
  tests/test_local_launcher.py -q` 为 5 passed。真实 standalone 启动和独立 alpha
  构建通过，alpha 产物无 `127.0.0.1:8765`。
- 实际浏览器核对首页、空岗位、空档案、导入菜单、无密钥配置与草稿保留；正常停止
  和重启后本次测试对话仍在，页面无 JavaScript 异常。测试服务已停止，临时证据保留。
  未使用真实模型密钥；付费模型回答、真实简历确认、真人麦克风和原生 Windows
  不计入本次通过项。后续发布只同步源码，远端结果以本次提交的 Actions 为准。

## 2026-10-22 — 本地真实简历验收缺陷修复（未发布）

- 用户批准仅本地修复 DOCX 原件预览、字段中文标签和失败后的加载状态。未部署、
  重启或修改线上服务，也未推送 GitHub；本轮没有再次调用付费模型。
- `ResumeService._docx_html` 对缺失默认段落样式回退为普通段落。新增真实 DOCX
  回归用例，修复前稳定触发 `AttributeError`，修复后保留标题结构及 HTML 转义。
- 原文件预览失败使用独立错误状态与“重新加载预览”入口；取消过期请求结果，
  释放迟到的二进制预览地址，防止切换简历时串用旧结果。新增失败、重试、元信息
  异常和切换简历回归。导入、确认、权限和数据库内容不变。
- 地址、城市、目标岗位中文化；`name` 按基本信息/项目/技能分别显示“姓名”、
  “项目名称”、“技能名称”，仅修改标签，不改原始字段和事实值。
- 后端修复后实际侧边浏览器仍出现 blob HTML 框空白，直接访问相同 HTML 内容正常。
  DOCX 改用 `sandbox=""` 的 `srcDoc` 预览，禁用脚本与同源权限，内容仍由后端
  转义生成；PDF 保持二进制 URL 路径。接口测试覆盖启动令牌与错误正文不作预览。
- 命令与结果：`.venv/bin/python -m pytest extensions/career_mcp/tests/test_resume_service.py
  extensions/career_mcp/tests/test_resume_tools.py -q` → **35 passed**；
  `npx tsc --noEmit` 通过；`npx vitest run --maxWorkers=2` → **317 passed / 2 skipped**；
  `.venv/bin/python -m compileall -q coworker extensions`、`git diff --check` 通过。
  隔离副本 `python3.12 start_local.py --no-browser` 的 standalone 构建通过，仍有既存
  分包体积提示；未改变依赖。
- 真实浏览器复验：同一份虚构 DOCX 的预览接口由 409 恢复为 200，正文五区块实际
  可见；中文标签正确。停止隔离服务模拟连接失败，页面显示失败和重试、不残留加载
  提示；恢复服务后无须刷新，点击重试成功显示正文。原始文件、版本 1 和档案仍在。
- 差异自审：仅涉及领域渲染、前端预览/标签和对应测试，无核心引擎、模型、部署或
  权限修改。PDF/扫描件、原生 Windows 和云端表现未纳入此次实测；下一步是独立
  PDF 导入验收。截图与详细记录保存在忽略的 `artifacts/` 和本地验收目录中。

### 2026-10-22 — 公开源码同步准备

- 用户批准将上述修复同步至公开仓库，仅更新源码；不部署或重启线上服务。
- 在公开仓库的全新副本应用修复，未复制私有历史、运行数据或模型密钥。
  发布前扫描未发现密钥。依赖审计发现新增 Vite 告警，按建议从 7.3.6
  最小升级至 7.3.7；重新安装后审计为 0 项漏洞，未关闭任何安全检查。
- 公开副本的 35 项后端聚焦测试、前端测试、类型检查和 standalone 构建通过；
  GitHub 自动测试结果以本次同步提交对应的 Actions 记录为准。
