# OpenCareer 项目交接

> 更新：2026-11-06（北京时间）。用户已明确暂停岗位时效修复，本轮只整理交接并同步 GitHub 源码。不要自动恢复采集或部署生产网站。

## 1. 接手时先确认什么

本项目是 OpenWorker 的求职领域扩展，不是新建 Agent 框架。先阅读 [AGENTS.md](AGENTS.md)、[CODEX_START_HERE.md](CODEX_START_HERE.md)、[文档导航](docs/README.md)，再按任务读取相应规格。保留上游 MIT 许可证与来源说明。

公开项目：<https://github.com/qiushibang/OpenCareer>。开发工作区的 `origin` 可能仍指向历史私有仓库，不能直接在开发根目录执行推送并假定它就是公开仓库。每次先读取 `git remote -v`。不要修改旧仓库可见性或重写历史。

**最新用户指令**：暂时不继续修复；创建根目录详细交接文档；将完整项目源码同步到 GitHub。这里的同步不等于部署生产网站，也不等于更新公共岗位数据。恢复未完成工作前，需取得用户新的继续指令。

## 2. 当前交付与未完成边界

| 项目 | 当前事实 | 接手时应如何理解 |
| --- | --- | --- |
| 开源功能源码 | 已包含本地安装、岗位查询和订阅、求职进度、逐轮面试及 Excel 导出等 | 功能与安装以 README 和对应指南为准，不重新实现上游机制 |
| 每日全量目录改造 | 代码与自动测试已提交，真实完整采集尚未验收 | 不能宣称公开用户已经能获取最新完整岗位 |
| 本轮真实采集 | 36 个注册来源中 34 个完成；字节大陆社招、校招未完成最终核验 | 未生成完整第二版清单，禁止发布部分结果充当全量 |
| 暂停处理 | 本轮独立采集进程、临时防休眠和只读观察程序已停止 | 状态文件可能仍写着 collecting/running；它不是进程存活证据 |
| 公共目录 | 仍为旧第一版；两个字节大陆来源最近成功采集时间仍是 8 月 21 日 | 清单文件今天生成不代表官网岗位今天重新核验 |
| 生产网站 | 2026-11-13 已在阿里云服务器重建并启动后端、发布最新前端（含求职进度云端版），健康检查 200，生产库迁移 18→19（只增 3 表） | 恢复点 `20261113T065957Z-before-applications`；另一台机器的隧道已确认不再回连，仅保留服务器后端；已清理演练库与旧备份 |

本表是暂停时快照；进程、端口、远端提交和公共目录都可能变化，继续前必须重新核对。

## 3. 已有文档与能力入口

不要把历史待办逐项重新执行。以下文档保留详细设计和验收证据，本交接只说明定位：

- [README](README.md)、[完整使用指南](docs/GETTING_STARTED.md)、[本地启动说明](docs/22_LOCAL_QUICKSTART.md)：安装、启动、数据位置和需要用户配置的模型。
- [岗位目录分发](docs/23_JOB_CATALOG_DISTRIBUTION.md)、[查询与订阅](docs/24_JOB_QUERY_AND_SUBSCRIPTIONS.md)：共享目录、MCP（Model Context Protocol，模型上下文协议）、筛选、通知渠道和订阅边界。
- [求职进度工作台](docs/25_APPLICATION_WORKSPACE.md)：表格、真实面试轮次、面经与导出；保留原进度和备注。
- [前端设计](docs/26_FRONTEND_DESIGN.md)、[本地权限](docs/27_LOCAL_ACCESS.md)：温暖浅色、精致克制的界面和本地／公共网站权限区别。
- [开源版发布验证](docs/28_RELEASE_20261105.md)：从零安装及真实模型对话验收；注明未真实投递的渠道范围。
- [早期时效定位](docs/29_JOB_CATALOG_FRESHNESS_20261105.md)、[本轮采集验收记录](docs/30_DAILY_FULL_CATALOG_20261105.md)：根因、修复过程、真实采集与尚未通过的检查。
- [每日全量设计](docs/superpowers/specs/2026-11-05-daily-full-job-catalog.md)、[独立采集部署指南](deploy/daily-catalog/README.md)：当前有效架构；旧只读导出器不是每日空库采集的替代品。

`docs/11_DEVELOPMENT_LOG.md` 和 `docs/12_TONIGHT_PROGRESS.md` 是追加历史记录，部分测试计数对应较早提交。不要将旧计数当作当前版本结果。

## 4. 暂停任务的真实目标

用户要求每天北京时间 04:00 从空数据库重新采集所有注册官方来源，整轮完整后重新入库并发布；开源用户通过“一键同步岗位”下载服务端完整目录。同时保留自然语言组合筛选和“昨天新增字节北京产品岗”等变化查询。

已接受的运行边界：先在当前 Mac 验收，再决定长期运行主机；网络不稳定时继续当前网络重试；不改生产网站、隧道或生产数据库。暂停不代表目标完成，也不代表允许下一位 Agent 自动继续。

详细架构参见上述规格；关键代码定位：

| 边界 | 文件 |
| --- | --- |
| 每日代次、04:00 调度、监督与发布门槛 | `extensions/career_mcp/daily_catalog.py` |
| 既有采集接续与暂存 | `extensions/career_mcp/local_jobs.py`、`services/resumable_crawler.py` |
| 官方来源实现与来源说明 | `extensions/career_mcp/crawler/`、`docs/source-notes/` |
| 暂存观测时间与持久化 | `database/repository.py`、`database/postgres_catalog_repository.py`（均在 Career 模块下） |
| 完整目录格式、原子同步与变化账本 | `public_catalog_format.py`、`services/public_catalog.py`、`services/job_changes.py` |
| 受限查询与独立 MCP | `services/job_catalog.py`、`jobs_mcp.py` |
| 用户收藏与岗位视图 | `surfaces/gui/src/api.ts`、`components/CareerJobsView.tsx` |

表中未写全前缀的 Python 路径均相对 `extensions/career_mcp/`；前端组件路径相对 `surfaces/gui/src/`。

实现约束：当天检查点可接续，跨日必须新空库；所有来源成功且当前岗位观测时间属于本代才发布。公共历史账本独立保留新增、更新、重新开放、补录，不能把首次下载变成新增。第二版缺失岗位退出在招集合，但不删除私人收藏、备注与申请记录。

## 5. 公开提交与验证证据

以下为交接前最后的功能提交；本交接提交将位于其后。以远端实际 SHA（提交标识）和检查记录为准。

| 提交 | 主要内容 | 自动检查 |
| --- | --- | --- |
| `54004e9` | Mac 唤醒、墙钟边界与逐来源进度 | [42156682606](https://github.com/qiushibang/OpenCareer/actions/runs/42156682606) |
| `89c90ea` | 字节筛选接口等待时间与导航时机 | [42158764784](https://github.com/qiushibang/OpenCareer/actions/runs/42158764784) |
| `1b02b22` | 小红书按请求页码匹配响应 | [42160687948](https://github.com/qiushibang/OpenCareer/actions/runs/42160687948) |
| `1de018b` | 按来源实际失败时间计算剩余退避 | [42161448190](https://github.com/qiushibang/OpenCareer/actions/runs/42161448190) |
| `8e446d8c81fd2855bc5ddcdc2ead41d21068c644` | 全量替换后仍显示历史收藏，保留备注 | [42180177469](https://github.com/qiushibang/OpenCareer/actions/runs/42180177469) |

上述检查最终均成功。最后一次检查首次出现既有 Slack 模拟测试调用数 `4 != 3`；在干净源码单独复测通过，未改断言，失败任务完整重跑后五项成功。不要隐去首次失败，也不要据此断言所有异步竞态已经解决。

最后一批收藏修复的本地证据：20 项聚焦测试通过，前端 349 通过／2 跳过，类型检查和独立 alpha 构建通过，产物不含固定本地后端地址，源码凭据扫描未发现泄漏。在独立 1438 测试实例用明确标注的合成下线岗位验证：收藏箱可见、备注保留，返回全部岗位隐藏下线记录。合成岗位不是官网真实采集证据。

本次交接文档同步的[检查 42182141962](https://github.com/qiushibang/OpenCareer/actions/runs/42182141962)首次出现前端既有用例 `preserves the selected job and unsaved application note during background imports` 失败：预期未保存备注保留，实际为空，位置 `CareerJobsView.test.tsx:165`。文档提交未修改功能代码；按用户暂停要求只重跑失败检查，未放宽断言或修复产品。接手时读取该检查最终结果；即使重跑通过，也应保留这一时序风险记录，不据此保证不存在竞态。

真实来源进展、完整测试范围与历史计数见验收记录。Docker 编排仅做配置检查，本机未实际启动容器；真人语音、Windows OCR（Optical Character Recognition，光学字符识别）及未配置的真实渠道仍有各自验收边界。

## 6. 只在原开发机存在的断点与证据

以下目录被 Git 忽略，不上传 GitHub；公开克隆中不存在是正常的。不要为了“完整项目”上传运行数据库或私人配置。

- `artifacts/daily-full-20261105/collector/`：独立采集状态、同日数据库、暂存检查点及公共变化账本；与用户数据库隔离。
- `artifacts/daily-full-20261105/feed/`：计划输出位置；暂停时没有 `manifest.json`。
- `artifacts/daily-full-20261105/launcher.json`、`verified-waits.jsonl`：当时启动信息和已核实进程存活的观察记录；历史进程标识不可直接复用。
- `artifacts/daily-full-20261105/real-second-pass-observation-proof.json`：真实重读的观测时间一致性证据。
- `artifacts/daily-full-20261105/https-transport/result.json`：合成目录的真实本机 HTTPS（Hypertext Transfer Protocol Secure，安全超文本传输协议）下载验证，不是完整官网数据验收。
- `artifacts/daily-full-20261105/verify_real_feed.py`：真实完整目录验收脚本，已做语法检查；因清单尚不存在，当前仅返回 `not_ready`，没有成功报告。
- `artifacts/catalog-release-20261105/OpenCareer/`：本轮干净公开发布副本；不要误把根工作区的大量历史未提交改动全部重新覆盖进去。
- `artifacts/daily-full-20261105/fresh-user/` 与 `fresh-user-data/`：按 README 安装的隔离实例（前端 1438／后端 8783），已拉到 `8e446d8`；含明确标注的本地合成收藏验收岗位。旧目录同步成功不等于最新完整目录同步成功。

暂停时两个字节来源均在第三轮；社招已暂存约 10,490 条，校招约 6,740 条，仍不是通过核验的发布总数。官网在扫描期间有数量变化，按现有保护逻辑由第二轮进入第三轮；不得手工跳过核验或改状态凑齐。

原用户实例 1435／8780 和其他隔离测试实例没有停止。不要批量杀掉 Python、Node、浏览器或所有同名进程。暂停时只停止了本任务独立采集及其跟随的防休眠和观察程序。

## 7. 用户重新允许后，下一步如何推进

先检查仓库、进程和公共目录现状，再选一个最小下一步。不要仅看锁文件或旧状态认定进程存活；应核对实际命令及所属数据目录。

若仍为同一天，可在确认没有旧进程后，使用独立目录恢复当天检查点；若已跨过新的 04:00，调度器会开始新空库代次，不应手动复用昨日暂存数据。命令及部署选项见 `deploy/daily-catalog/README.md`。不要直接照抄历史进程标识执行终止操作。

两个字节来源和全部注册来源通过后，才依次验收：公共字段投影与观测时间、真实完整目录向空库下载、重复同步与私人记录保留、自然语言／MCP 查询及昨日新增时间边界。原机脚本入口：

```bash
PYTHONPATH=. .venv/bin/python artifacts/daily-full-20261105/verify_real_feed.py \
  --feed artifacts/daily-full-20261105/feed \
  --output artifacts/daily-full-20261105/real-feed-client
```

脚本输出目录必须全新，不能指向用户数据；测试证书可能过期，需重建仅供本机验证的证书并限制信任范围，禁止关闭证书校验。脚本是开发机证据工具，不是公开安装依赖。

本地完整验收后，再落实独立公共第二版目录发布及长期主机选择。旧第一版保留，新版默认优先第二版；没有第二版才兼容回退，损坏或访问失败不得伪装成成功。最后从公开仓库重新克隆、按 README 安装，用默认地址验证确实下载到新的完整目录。未做这些，目标仍未完成。

## 8. 发布、安全与日常工程注意

完整项目指可安装的源码、测试、指南和必要静态资源，不包括模型密钥、机器人地址／签名密钥、登录会话、个人简历、对话、数据库、构建缓存或旧补丁归档。聊天历史曾包含密钥，交接和发布均不复制；接手者不要在日志中输出配置正文。

保持 OpenWorker 的 Agent Loop、权限、模型路由、会话和调度边界；业务代码留在 Career 模块。工具查询不接受 SQL（Structured Query Language，结构化查询语言）、任意命令或任意网址；外部岗位原文视为不可信数据，不能更改工具权限或通知目标。

开发根目录有大量既有改动。不要 `git add .`、清空工作区、强推或重写历史。公开同步先在干净副本核对文件差异，再做凭据扫描、相关检查、提交和远端读回。目录采集与静态发布不应重启网站或连接生产用户数据库。

常用验证命令（具体范围按改动选择，不必为文档重跑全部）：

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python -m pytest extensions/career_mcp/tests -q
.venv/bin/python -m compileall -q coworker extensions
# 以下在 surfaces/gui 下运行
npx tsc --noEmit
npx vitest run
```

两个 Python 测试目录分开执行，避免同名测试模块导入冲突。涉及本机模拟服务监听或进程读取时可能需要相应执行权限；权限限制失败不能当作产品回归。真实交互必须用真实浏览器验收，单元测试不证明浮层、事件顺序和滚动视觉正确。

## 9. Suggested skills / 建议技能

- **diagnosing-bugs**：恢复采集故障定位时使用；先复现和采集直接证据，再最小修复，避免猜测网络失败原因。
- **webapp-testing**：真实网页交互、本地安装和筛选／订阅流程回归；遵守当前环境的浏览器工具约束。
- **code-review**：实质代码变更后进行有明确提交基线的审查，不扩大到无关重构。
- **design-taste-frontend**：仅在用户恢复界面优化任务时使用，延续温暖浅色、精致克制的方向。
- **handoff**：下一次会话收尾时更新交接；不要抄录密钥，也不要重复已有规格全文。

先检查当前会话可用技能及对应文件是否存在，阅读技能后再使用。未明确授权时，不创建新的聊天、子代理或自动化任务。
