# AGENTS.md — OpenWorker Career MVP 开发总约束

本文件位于仓库根目录，是 Codex、Claude Code、Cursor Agent 或其他编码 Agent 在本项目中的最高优先级项目说明。开始任何修改前必须先阅读本文件，再阅读 `CODEX_START_HERE.md` 与 `docs/` 中对应阶段文档。

## 1. 项目身份

本项目不是从零开发一个 Agent 框架，而是对开源项目 **OpenWorker** 进行垂直领域二次开发。

- 上游仓库：`https://github.com/andrewyng/openworker`
- MVP 基线提交：`01b6f83b3927e02912dda84bb392942c13ca70d1`
- 基线日期：`2026-08-01`
- 上游许可证：MIT；保留原许可证与版权声明。
- 产品名：`OpenCareer`，仓库仍保留 `openworker-career` 技术命名。
- 产品定位：面向中国 AI/互联网岗位的统一求职 Agent。

## 2. 强制架构原则

必须复用 OpenWorker 已有能力，不得重复实现：

1. Agent Loop / TurnEngine。
2. 多模型 Provider Router。
3. Tool Registry 与工具调用循环。
4. 权限审批与风险分级。
5. Conversation、Memory、Todo、Automation。
6. Persona、Skill 加载机制。
7. MCP Client、MCP 配置与连接管理。
8. OpenWorker 桌面 GUI、Tauri 壳、本地 Server 的基础生命周期。

求职领域能力必须主要通过以下扩展点实现：

- Career Persona。
- Career Skills。
- Career MCP Server。
- 独立的 Career Domain Service、岗位数据库和爬虫模块。
- 必要且最小化的 GUI 增量。

除非现有 OpenWorker 机制存在可复现的阻塞，否则不得重写 `coworker/engine.py`、`coworker/permissions.py`、Provider Router、MCP Client 或核心会话管理。

## 3. 当前产品范围

当前基线已经包含：

- Career Persona、Skills、可信工作区 MCP 和标准 Conversation。
- 手动 JD 与公开官方招聘源的采集、标准化、去重、版本和下线判断。
- 岗位雷达、筛选、详情、收藏与申请进度。
- 多简历 Career Vault、离线 OCR、事实确认与安全删除。
- AI 读取 JD 与脱敏简历完成诊断、追问、改写建议和面试准备。
- JD/已确认简历直读的多轮模拟面试、复盘和历史记录。
- 所有 Conversation 的语音输入；浏览器豆包 ASR，桌面端本地 Whisper。
- 云端生产：`https://app.opencareer.online`（阿里云 203.0.113.10）。PostgreSQL 多租户、
  Authing OIDC 登录、per-user Principal/SessionManager 已上线；用户自带 API Key 与自选
  模型（BYOK）凭据存于每用户 `state_dir()/users/<uid>/secrets.json`。

当前仍明确不做：

- 科研、论文、导师、申博、申硕、夏令营。
- 海外岗位。
- 自动投递、自动登录招聘网站、验证码绕过。
- 视频模拟面试、表情或诚信判断。
- 支付、会员、企业招聘端。
- 向量数据库、复杂推荐模型、微服务拆分、Kubernetes。
- 大规模重做 OpenWorker UI。

## 4. 简化目录示意

以下只展示架构边界，不是当前文件的完整清单：

```text
openworker-career/
├── coworker/                         # OpenWorker 原核心，尽量少改
│   └── personas/builtin/career.md    # 新增 Career Persona
├── surfaces/gui/                     # 仅做必要增量
├── .coworker/
│   ├── mcp.json                      # 工作区 Career MCP 配置
│   └── skills/
│       ├── career-jd-analysis/SKILL.md
│       ├── career-job-search/SKILL.md
│       ├── career-resume-coach/SKILL.md
    │   ├── career-resume-import/SKILL.md
    │   └── mock-interview/SKILL.md
├── extensions/
│   └── career_mcp/
│       ├── server.py
│       ├── domain/
│       ├── tools/
│       ├── crawler/
│       ├── database/
│       └── tests/
├── tests/career/
├── docs/
├── AGENTS.md
└── CODEX_START_HERE.md
```

如果 OpenWorker 当前代码结构要求不同路径，可做最小适配，但必须保持“OpenWorker 核心”和“Career 领域模块”边界清晰。

## 5. 数据与安全规则

- 仅抓取无需登录、公开可访问的官方招聘信息。
- 不绕过验证码、登录、签名、访问控制或平台限制。
- 所有岗位必须保存原始来源 URL、首次发现时间和最近确认时间。
- 用户简历与经历不得用于生成虚构事实。
- 外部发送、写入关键业务状态或执行 Shell 时继续遵守 OpenWorker 审批机制。
- `.coworker/mcp.json` 只有在工作区被 OpenWorker 标记为可信后才会加载；不得规避该安全门。

## 6. 工程规则

- Python 代码要求类型标注、清晰错误信息和可测试的纯函数。
- 抓取器必须有本地 fixture 测试，测试不得默认访问公网。
- 每个公司 Adapter 与标准化、持久化、版本比较解耦。
- 不得在 Adapter 中直接生成简历、调用 Agent 或操作 GUI。
- 模型只用于规则无法可靠完成的语义抽取；普通抓取、哈希、去重不得调用模型。
- 新增依赖前先说明用途；MVP 避免 Redis、Celery、Kafka、Elasticsearch。
- 每次变更尽量小、可回滚，并运行相关测试。

### 6.1 工程环境速查

- **Python**：测试用 `.venv/bin/python -m pytest tests/<file> -q`（本机无全局
  python/pytest）。编译检查 `.venv/bin/python -m compileall -q coworker extensions`。
- **GUI**：在 `surfaces/gui/` 下执行 `npx tsc --noEmit`、`npx vitest run`、
  `npx vite build --mode alpha --outDir ../../deploy/web --emptyOutDir`。alpha 产物
  必须不含 `127.0.0.1:8765`（build-frontend.sh 的护栏）。
- **部署**：`VITE_ICP_NUMBER="京ICP备2026055760号-1" SKIP_NPM_CI=1
  COMPOSE_FILE=docker-compose.yml bash deploy/sync-to-server.sh root@203.0.113.10`。
  SSH 密钥 `~/.ssh/opencareer_deploy`；线上编排是域名版 `docker-compose.yml`（非
  ip 版）。部署前按 `docs/18_BACKUP_AND_ROLLBACK_RUNBOOK.md` 先建 PostgreSQL
  恢复点（宿主机 `sudo -u postgres pg_dump`，应用账号会被 RLS 拒绝）。
- **本地复现**：`scripts/run_alpha_local.sh` 起 localhost alpha（seed 步骤可能因
  fixture 失败，可跳过 seed 手动起后端与 vite）。交互类 bug 必须用真实浏览器验
  证——jsdom 不做真实事件派发，测不出 capture/bubble 卸载竞态（教训见提交
  87a197c）。
- **已知坑**：开发机办公网到服务器 443/22 长连接不稳定（TCP 通、握手超时），
  诊断走 SSH 重试或换网络；服务器仅 2 GiB 内存，曾发生 OOM 假死（控制台重启恢
  复），所有容器 `restart: unless-stopped`，旧容器/卷为回滚点，观察期结束前不得
  删除。

## 7. Codex 工作协议

每个任务开始时：

1. 阅读本文件。
2. 阅读 `CODEX_START_HERE.md`。
3. 根据当前阶段阅读对应文档。
4. 检查当前仓库与基线是否有差异。
5. 先给出 2–5 项简短执行计划，再修改代码。

每个任务结束时必须报告：

- 修改了哪些文件。
- 完成了哪些验收项。
- 运行了哪些命令和测试。
- 还有哪些阻塞或风险。
- 下一项最小任务是什么。

## 8. 当前首要里程碑

当前不是早期 MCP 贯通阶段。最新状态和优先级以 `docs/README.md` 为准。

近期 Gate：

1. 云端双账号数据隔离人工验收（含朋友邮箱验证码登录复测）与 30 日内公安联网备案。
2. 真人麦克风与完整五轮标准 Conversation 模拟面试体验验收。
3. Windows x64 OCR 离线打包验证。
4. 服务器 2 GiB 内存稳定性观察（防 OOM 假死复发），官方招聘源覆盖矩阵维护。
