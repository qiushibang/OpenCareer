# 阶段验收罗盘

> 文件名为项目早期冲刺阶段的历史遗留。本文现在记录累计 Stage Gate，不表示这些
> 条目仍是“今晚”待办。当前任务以 `docs/README.md` 和
> `docs/09_CODEX_TASK_BACKLOG.md` 为准。

| 阶段 | 状态 | 目标 | 证据链接/命令 | 阻塞与决策 | 下一步 |
|---|---|---|---|---|---|
| 仓库初始化 | 通过 | 固定基线并恢复资料 | `git rev-parse HEAD` = `01b6f83b3927e02912dda84bb392942c13ca70d1`；资料 SHA-256 校验通过 | 同级备份目录被沙箱拒绝，改为根目录临时备份并记录 | 完成 Stage 0 环境安装 |
| Stage 0 | 通过 | 环境、后端、GUI、最小测试 | 后端相关测试 `28 passed`；GUI `108 passed`；token 鉴权 `/docs` 返回 `200` | Rust 缺失，仅跳过 Tauri desktop smoke | Stage 1A |
| Stage 1A | 通过 | Persona 可解析、可见、可启动 | Persona 回归 `42 passed`；`career.md` 由内建目录自动注册 | GUI 实际选择器需与模型演示一起手工确认 | Stage 1B |
| Stage 1B | 通过 | Skill + MCP mock + 交付物 | stdio/bridge 回归通过；GUI 已由 Career Agent 调用 mock MCP 并经审批写入 `artifacts/gui-mock-job-brief.md` | 无 | Stage 2 |
| Stage 2 | 通过 | 手动 JD 预览、确认入库、详情、搜索与交付物 | GUI MCP 读取岗位后，经写入审批生成 `artifacts/stage2-gui-job-brief.md`；完整回归 `46 passed` | 无 | Stage 4 合规调研 |
| Stage 3 | 通过 | crawler framework | FakeAdapter 状态机、已有库无写差异预览、只读 MCP 查询、审批保护的 `crawl_source`；stdio SDK 发现 8 个 Career MCP 工具 | 状态机与持久化继续由通用 pipeline 管理 | 由 Stage 4 真实 Adapter 驱动首次线上 crawl |
| Stage 4 | 两个生产来源通过，DeepSeek 正式入库待审批 | 稳定官方来源 Adapter | 小米 2522 个唯一岗位；DeepSeek 32 个唯一岗位；GUI `list_sources` 显示双来源，DeepSeek dry run 显示 `created=32`；后端 `86 passed`、GUI `109 passed` | 百度因 SSR 异常、MiniMax 因短期签名、智谱因会话状态禁用 | 调查字节跳动；DeepSeek 先保持 dry run，不绕过正式写入审批 |
| Stage 5 | 通过，正式入库待审批 | 第三个稳定生产来源 | `bytedance-seed-campus` 限定官方 Seed 项目；85 条唯一岗位；live 30.51 秒；MCP 与 GUI dry run 均为 `created=85`；GUI 显示三个来源 | 全量社招/校招超过时限；不复用动态签名，使用无状态 Playwright 公开页面 | 保持 dry run，正式写入走审批；下一步完善三来源查询与事件体验 |
| 多公司整晚扩张 | 通过，34 来源 Automation 完整轮次完成 | 11 家目标公司准入、正式入库、游标批量续跑、每小时自动推进 | 34/34 最新 run succeeded；10,067 jobs、10,013 active；53 created、340 changed、23 missing；cursor 已归零 | 每次正式抓取仍需 Inbox 审批；美团需连接复用避免多页 TLS 握手放大 | 下一阶段生成来源健康与岗位变化摘要，并验证每日只读 Automation |
| 每日岗位雷达摘要 | 通过，真实 artifact 已生成 | 完整 24 小时聚合、真实 Skill、每日 Automation、Markdown + 会话 | `task-7a4f067305`；10,560 events；34/34 healthy；`artifacts/job-radar-daily/2026-08-06.md`；业务表计数零变化 | 方舟最终总结偶发 request-burst 保护，artifact 不受影响 | 运行 7 天稳定性观察，再决定进入简历与申请材料 P1 |
| Stage 9 简历导入 | 通过，synthetic 端到端验收完成 | 文本/PDF/DOCX、本地私有原件、五类分项确认、版本化 Career Vault、敏感字段遮罩、完整删除 | schema v4；16 MCP tools；versions 1→2；5 confirmed facts；删除后私人原件 0；模型 `ep-20260806151220-8km7l` | 用户选择提前进入 P1；扫描 PDF/OCR、岗位匹配和申请材料仍未实现 | 下一最小任务：基于 confirmed profile 实现确定性岗位匹配证据模型 |
| Career 入口与简历导入修复 | 通过 | 区分普通对话 PDF 与 Career Vault 导入，并暴露岗位雷达/档案入口 | 首页 5 个动作；专用 PDF/DOCX importer；后端 208 passed；GUI 124 passed；production build 通过 | 岗位雷达和档案仍以对话结果展示，尚无独立岗位 Dashboard | 下一最小任务：设计并实现最小岗位列表、筛选和详情页面 |
| Aiden 单模型 Composer | 通过 | 对话只显示并使用 DeepSeek V4 Flash · Aiden，其他配置仅在 Settings 保留 | `composerModelPolicy`；本地默认值与 `/v1/health` 均为 `aiden:deepseek-v4-flash`；GUI 126 passed；后端 92 passed | Aiden 不可用时不自动降级，需恢复本机 Aiden 登录 | 下一最小任务：完成岗位 Dashboard 设计 |
| 求职档案页面与全局中文界面 | 通过 | 一级档案入口、三个档案页签、原文件安全预览、版本记录、全 GUI 中文化、职业 Agent 第一 | 真实档案/原文件/版本 API 200；中文 PDF blob 预览；Career/OpenWorker 后端 210 passed；GUI 137 passed；production build 与 `git diff --check` 通过；干净浏览器控制台 0 error | 扫描 PDF/OCR 仍后置；构建保留既有 chunk 警告；岗位仍缺少独立列表与详情页面 | 下一最小任务：独立岗位列表、筛选和岗位详情页面 |
| 独立岗位雷达页面 | 通过 | 一级岗位入口、列表详情同屏、五类筛选、20 条分页、完整岗位详情、档案内部字段中文化 | 浏览器显示 10,013 个 active 岗位；DeepSeek 32 条；`Code Agent` 组合筛选 2 条；后端 214 passed；GUI 145 passed；production build 通过 | 707 个地点标签存在“北京/北京市”等同义值；保留既有构建警告 | 下一最小任务：地点规范化规则与迁移预览 |
| 岗位与简历体验优化 | 通过 | 多城市独立筛选、中文招聘类型标签、多简历库、品牌栏搜索图标 | 336 个独立地点且组合项 0；广州筛选 492 条并命中“广州、深圳”岗位；双简历端到端测试；后端 221 passed；GUI 148 passed；build 和浏览器控制台通过 | 当前真实库只有 1 份确认简历；尚无简历重命名、目标岗位标签和单份删除 | 下一最小任务：简历名称与目标岗位元数据 |
| 简历元数据与单份安全删除 | 通过 | schema v5、独立名称、目标岗位标签、精确确认软删除、共享事实保留、同文件可重新导入 | PATCH/DELETE API；隔离库验证全文和 preview 清理、原文件删除、facts/versions 保留；后端 227 passed；GUI 150 passed；production build 与 `git diff --check` 通过；真实浏览器只读验收通过 | 真实简历未执行删除；构建保留既有 TestClient、混合导入和大 chunk 警告 | 下一最小任务：简历与岗位关联及多简历对比 |
| 岗位匹配闭环 | 通过 | 1–5 份简历证据矩阵、多简历比较、schema v6 快照、stale、HTTP/MCP/GUI、真实申请准备包 | 正式岗位可分析 10,056/10,067（99.89%）；真实 DeepSeek fresh snapshot；后端 263 passed；GUI 155 passed；build、外键和 diff 检查通过；`artifacts/application-packets/deepseek-agi管培生-申请准备包-20260809.md` | 对抗审查确认并修复 4 项：嵌套敏感字段、同时间快照顺序、snapshot ID 混用、Agent 越过 none；另阻止 sensitive profile 请求。剩余 11 条 JD 无可靠要求边界，保守拒绝 | 下一最小任务：申请包确定性校验器，然后设计岗位收藏与申请状态 |
| 申请包确定性校验器 | 通过 | 结构化八章节编译、失败阻止写入、原子持久化、重新编译与 SHA-256 完整性验证 | 真实 DeepSeek artifact `valid=true`；SHA-256 `392d965c…48ff70f`；隐私与 symlink 双重对抗审查无 major；后端 318 passed；schema v6、外键 0、单一正式文件和 `git diff --check` 通过 | 默认 shell 需显式设置 `CAREER_DATA_DIR=$PWD/career` 才与运行态数据库一致；保留既有 Starlette/httpx 弃用警告 | 下一最小任务：岗位收藏与申请跟踪 |
| 岗位收藏与申请跟踪 | 通过 | schema v7、收藏与申请阶段分离、追加时间线、事务 Service、CAS、HTTP/MCP、SQL 前置筛选、岗位雷达 GUI | 后端 345 passed；GUI 162 passed；build、Python 编译、schema v7、外键 0、diff 检查通过；真实 DeepSeek 和 Playwright 隔离岗位流程均完成并恢复当前状态；浏览器 0 HTTP/console/page error；两路修复后窄复核均为 `major_remaining:false` | 首轮对抗审查的 5 个 Major 已用 RED 测试修复；历史申请事件按不可变规则保留；保留既有 TestClient 和 Vite 构建警告 | 下一最小任务：定制材料导出 |
| 定制材料导出 | 通过 | schema v8、完整脱敏 baseline、证据内 proposal、逐条确认、CAS/stale、固定 ATS DOCX、同源 PDF、双文件补偿发布、HTTP/MCP/Skill/岗位雷达 GUI | 后端 413 passed；GUI 170 passed；production build、Python compile、schema v8、外键 0、24 个 MCP 工具、diff/ignore 检查通过；真实浏览器生成 DOCX 36,975 bytes 与 1 页 PDF 42,632 bytes，下载和 hashes 通过，0 HTTP/console/page error | Agent 无 confirm/export/download 工具；正式目录 Git ignore；对抗修复结构化技能白名单、stale 只读重开、exported 不可编辑、下载反馈、目录命名、profile 泄漏和文件篡改；保留既有 TestClient 与 Vite 警告 | 下一最小任务：OCR 规格与实施计划 |
| 扫描 PDF 本地 OCR | Gate B/C/D 与 macOS packaging 完成 | RapidOCR/ONNX 本地离线、页级 fallback、schema v9 provenance、私有 staging 补偿、HTTP/MCP/Skill/GUI 与真实 fixture | 四份 fixture 完成断网 staging、确认、删除和残留审计；production sidecar 与 DMG 内 sidecar 均禁网 OCR 成功；三模型各唯一且 hash 精确一致；`OpenWorker_0.1.7_aarch64.dmg` 236,235,577 bytes，SHA-256 `c5f83e73…c49f8ae`；packaging/acceptance `6 passed` | macOS 产物为 ad-hoc、未 notarize 的本机验收包，不能公开发布；Windows x64 production NSIS/MSI Gate 尚未执行 | 镜像 staged verifier 到 Windows packaging，再进行全量、浏览器与对抗验收 |
| 申请支持材料 | 通过 | 现有申请准备包增加自我介绍、内推/HR 沟通文本和申请 Checklist，不新增重复 Service | 十一章固定编译；direct/related 证据边界；`none` 不进入能力声明；申请包/匹配回归 `75 passed` | 无新增阻塞；继续沿用现有原子发布与校验器 | 与 Mock Interview 一并完成最终 Gate 记录 |
| Mock Interview | 原始规格 23/23 项全部通过 | schema v10、五轮自适应 Career Agent、单问题强校验、MCP/HTTP/InterviewView、GUI 权威 conversation CAS 绑定、Tauri capture、豆包 ASR/TTS 2.0、完整 Transcript 分析和三份私有 Artifact | 真实五轮文本 Aiden Session `01b29b0c…`；真实对话绑定 Interview `baaad67b…`；真实五轮云端语音 Interview `24c52cb6…`，动作 `FOLLOW_UP → FOLLOW_UP → SWITCH_TOPIC → FOLLOW_UP → WRAP_UP`，终态 completed；后端 78 passed、GUI 202 passed、Rust 6 passed、build/schema/外键/privacy 通过；逐项矩阵见 `docs/17_MOCK_INTERVIEW_COMPLETION_AUDIT.md` | 无功能阻塞；五轮云端音频为自动验收，物理麦克风由 Rust/GUI 自动化覆盖，本轮未做真人现场朗读 | 进入下一阶段前保留凭证在 SecretStore，并按需要做一次真人桌面体验抽查 |
| 模拟面试入口与启动体验 | 通过 | 每个 JD 列表与详情双入口、统一设置、无 fresh 匹配自动生成、可信 workspace 保留、面试页原地权限审批、首题持续轮询 | TDD 相关 30 passed；GUI 全量 40 files / 206 passed；production build 通过；真实 Interview `dc6fbc46…` 经两次标准 MCP 审批后在专用页展示第一题并完成 TTS，控制台 0 error | 交互模式下首次 MCP 工具仍需用户审批，这是既有安全机制，不自动绕过 | 下一最小任务：用户继续完成一轮真实回答，抽查提交回答后的动态追问体验 |
| 浏览器模拟面试录音 | 工程 Gate 通过，真人设备 Gate 待确认 | Browser `getUserMedia + AudioWorklet` 内存采集、16 kHz mono PCM16 WAV、5 分钟自动停止、既有豆包 ASR、可编辑草稿、Browser/Tauri 共用波形与完整清理 | 音频/UI 定向 38 passed；GUI 全量 42 files / 230 passed；production build 与 diff check 通过；真实 Interview `6a79aeaf…` 显示浏览器录音按钮，安全上下文和全部 Web Audio 能力门禁通过 | IDE 托管浏览器停在系统麦克风授权，不能代替用户允许权限或提供真人语音；未将 fake 音频记为真实通过 | 在当前面试页允许麦克风，朗读一句中文并停止，确认豆包 transcript 进入可编辑草稿且未自动提交 |
| JD/简历驱动面试智能 | 真实三岗位与单维度质量 Gate 通过 | Blueprint v2、确定性 role tracks、脱敏 evidence cards、岗位差异 probe plan、schema v11 Turn 元数据、连续深挖、问题文本单维度校验、Persona/Skill/GUI Prompt | 算法/研发/产品真实 5 轮均通过；单维度修复后算法 Session `ee8bd4b7…` 首题只询问 context，后续命中 evaluation 与 inference；真实生成触发过维度冲突拒绝；三份 Artifact 和 privacy 通过；详细哈希见 `docs/11_DEVELOPMENT_LOG.md` | 非法问题不会持久化；模型仍偶尔先生成复合问题、读取源码或额外传 `_raw`；完整通用测试仍有 7 项因缺少 `boto3/botocore` 失败 | 下一最小任务：限制真实验收 Agent 的通用源码工具，并为未知工具参数返回结构化提示 |
| 标准对话内模拟面试（方案 A） | 工程与真实一轮迁移 Gate 通过 | 面试进入标准 Career Conversation、最近会话恢复、紧凑状态条、内部 Prompt/可见回答隔离、标准 Composer 文字与语音、同会话复盘 | 后端集中 `92 passed`；GUI 45 files / `244 passed`；production build 通过；真实 Conversation `91f26765-2d1` / Interview `c6f1f47e…` 完成首题、原文回答、隐藏评价、FOLLOW_UP 第二题、刷新/新标签恢复；冷启动控制台 0 error | 首题第 9 次才通过单维度门禁，模型稳定性仍需优化；旧 `InterviewView` 无生产引用但因共享工作树改动暂保留；真人麦克风与完整五轮/同会话复盘仍待设备 Gate | 在当前第二题继续真人回答，完成麦克风转写、五轮结束和复盘追问 |
| 全局 Conversation 语音输入 | 工程与浏览器 UI Gate 通过，真人设备 Gate 待确认 | 所有 Agent 共用语音入口；浏览器豆包 ASR、Tauri 本地 Whisper；权限/录音/识别即时中文状态；识别只填草稿；暂停面试问题播报 | TDD 聚焦 `44 passed`；GUI 全量 47 files / `256 passed`；跨会话旧 transcript 防污染测试通过；production build、Python compileall、diff check 通过；模拟面试与普通新 Conversation 均显示入口；点击立即显示“正在请求麦克风权限…”；0 console error；100 条网络请求无 `/voice/synthesize` | IDE 托管浏览器不能代替用户批准系统麦克风权限；旧 `InterviewView` 无生产引用但因共享工作树改动暂保留 | 用户允许麦克风后朗读一句中文，确认“正在录音 → 正在识别…”且 transcript 只进入草稿、不自动发送 |
| 文档治理与清理 | 通过 | 建立权威文档入口、同步当前架构/范围/backlog、区分当前与历史、删除无证据临时文件 | 新增 `docs/README.md`；更新根入口和 00–10 基础文档；读者测试 6 项歧义全部修复；相对链接、过时语句、残留引用和 `git diff --check` 通过 | 历史 specs/plans/source notes 保留为设计、合规和验收证据，不做激进删除 | 后续文档从 `docs/README.md` 进入；执行 OC-101 真人麦克风 Gate |
| M1a-1 请求身份上下文 | 代码与自动化 Gate 通过，服务器 Gate 待执行 | HTTP/WS 统一 Principal；桌面 local、legacy sidecar token、多用户静态 token 表；错误配置与重复 token fail-closed | TDD 5 类 RED 均命中；身份/Alpha/Cloud/Server `76 passed`；Alpha 前端构建、Crawler CLI、compileall、diff check 和安全不变量扫描通过 | 尚未按用户切分 Career/私有目录或 SessionManager；公网 18080 health 探测超时，SSH 主机可达但当前无认证；未修改服务器 | 获得 SSH 授权或确认服务器入口后完成 M0 Gate，再执行 M1a-2 |
| 隔离式浏览器 Alpha | 工程通过，公网 Tunnel 待本机终端验收 | 独立 state/data/workspace、Career-only、无工具的 Conversation、阻止本机管理 API、Vite 同源 API/WS 代理和 Quick Tunnel 启动脚本 | Alpha/Server `54 passed`；Alpha production build、shell syntax、Python compile、diff check 通过；`cloudflared 2026.8.1` 已安装 | 受控 Agent 运行环境终止 `cloudflared` 长连接，未生成 URL；Quick Tunnel 仍是公开随机地址，不具备邮箱白名单 | 在 Mac 自己的终端运行 `bash scripts/run_alpha_quick_tunnel.sh`，用蜂窝网络验证后仅发给信任测试者；持续测试改用 Named Tunnel + Cloudflare Access |
| Alpha 合规调整 | 通过 | 保留隔离 localhost Alpha，移除 Cloudflare 启动入口 | `scripts/run_alpha_local.sh` 不调用 Cloudflare；README 已同步；未生成或分享公网 URL | 仍未确定公司批准的跨设备测试渠道 | 由负责人提供获批的内网、测试服务器或分发方式后，再接入该渠道 |
| M0 云端 Alpha 真实 Gate | 通过 | 阿里云 IP Compose、DeepSeek 直连会话、Alpha 安全门禁、真实岗位抓取 | 后端/Caddy healthy；health/REST 200；本机控制 API 403；`/ws/session` accepted；模型 `deepseek:deepseek-v4-flash`；浏览器真实回复“DeepSeek 最终验收通过”；腾讯公开源 283 条；GUI 48 files / 259 passed；alpha build 与 diff check 通过 | 原简历上传发生在消息未到后端的故障窗口，需要在修复版页面重新触发导入；IP 入口为明文 HTTP 且无登录，自测后必须关闭 18080 | 重新上传脱敏简历完成 Career Vault smoke，然后关闭公网 18080，再进入 M1a-2 |
| 云端简历五段预览与隐私 Gate | 预览通过，等待用户确认 | DeepSeek DSML 工具恢复、Alpha Career 工具 allowlist、真实简历读取与五段掩码预览、工具参数与用户气泡脱敏 | 真实工具序列包含 `load_skill`、`get_resume_import_text`、`preview_resume_import`；`resume_previews=1`、`profile_versions=0`、确认调用 0；文字回复与 286 岗位雷达通过；GUI 48 files / 263 passed，后端聚焦 47 + 105 passed | 用户尚未批准任何分区；模拟面试因此正确禁用，不能用未确认 preview 绕过事实门禁 | 用户逐区审核 basic/education/experience/project/skill；明确批准后再确认并完成真实面试文字问答 |
| 云端真实五轮模拟面试与稳定性优化 | 通过 | 已确认简历驱动五轮文字面试、网络中断恢复、官方报告、模糊回答对抗、首题与追问决策优化 | Interview `f770e140…` 完成 5 题和三份 Artifact；报告识别指标口径与证据风险；TDD 面试聚焦 67 passed、共享回归 104 passed；部署后低证据 `evidence=2` 触发同 target FOLLOW_UP；最终首题三步一次保存 | 五轮流程仍有较多工具调用并触发一次 Conversation context compaction；两场用于复测的短面试会话保留为验收证据 | 下一最小任务：单独评估每轮重复 `load_skill/get_session` 的上下文与延迟成本，不改 InterviewService 事实边界 |
| PostgreSQL Exact Origin 基础 | 代码 Gate 通过，服务器 Gate 待执行 | HTTP/WS 共用 scheme + host + port 精确策略；数据库 Origin 与应急环境项；拒绝任意 localhost 端口 | RED 命中 `localhost:1421` 被旧正则放行；Origin/PostgreSQL 19 passed、Identity/Alpha 10 passed、Server 53 passed；compileall 与 diff check 通过 | PostgreSQL Adapter 已实现但尚未由云端 storage factory 注入；未部署，不影响当前公网 Alpha | 接入云端 storage factory 和 migration CLI 后，在真实 PostgreSQL 验证 Origin 读取及数据库故障回退 |
| PostgreSQL Resume 与共享 Catalog Gate | 进行中，核心写链与三源真实回放通过 | 云端 Resume/Profile 全生命周期、MCP Principal 固定边界、SQLite 幂等迁移、单 PostgreSQL Catalog | Resume/迁移/REST 聚焦 31 passed；真实来源 5,417 条；同机回放 31 秒，复跑 8 秒且 5,417 unchanged；Gate 库 5,420 active、重复键 0、Raw Blob SHA 错误 0 | 滴滴 180 秒超时；腾讯等来源尚未回放；Application Packet/Tailored Export 与 Context 历史迁移未闭合；线上未切换 | 补齐剩余 PostgreSQL Adapter 与历史迁移，运行全来源，再启动隔离后端执行真实浏览器五轮对抗 Gate |
| Context 历史迁移与 Application Packet 入库 | 代码与真实 PostgreSQL Gate 通过，线上未切换 | Context JSONL/SQLite/JSON 历史完整迁移、聚合 SHA 幂等账本、Packet 记录与用户 Markdown Blob、租户组合外键、MCP 固定 Principal | 生产 Repository 恢复 Message/Compaction/Memory/Inbox/Automation；Alice/Bob 隔离、Blob SHA 和篡改拒绝通过；宽回归 103 passed；Schema + Packet 9 passed；Context CLI 3 passed；TypeScript 与 alpha build 通过 | 旧 Packet 无 Blob 的行保留 `blob_id=NULL`，新写入强制提供 Blob；本机无 Docker CLI，Compose config 未执行；线上 Alpha 未重启 | 下一最小任务：Tailored Resume/Export 接入 PostgreSQL/Blob，并在隔离后端执行真实浏览器申请包与五轮面试 Gate |
| Tailored Resume 与 Export PostgreSQL/Blob | 代码与真实 PostgreSQL Gate 通过，线上未切换 | Draft CAS 状态机、双 Blob 原子 Export、请求级 Principal、组合租户外键、SQLite/文件兼容与历史导出迁移 | `0005` RLS/外键通过；Alice REST 导出/下载、Bob 隔离、篡改拒绝、元数据失败双 Blob 回滚、并发幂等和迁移 SHA 通过；聚焦 84 passed，宽回归 171 passed；TypeScript 与 alpha build 通过 | 后端镜像已声明 LibreOffice/Noto CJK，但本机无 Docker CLI，未做真实镜像构建；线上 Alpha 未重建或重启 | 下一最小任务：在隔离服务器构建新 backend，执行真实 LibreOffice PDF、Packet/Tailored 下载与五轮面试浏览器 Gate |
| 四计划隔离服务器最终 Gate | 通过，线上 Alpha 未切换 | PostgreSQL Foundation、Agent Context/Exact Origin、共享 Catalog/Crawler、面试评价/进度，以及 Tailored 双 Blob 的真实闭环 | 隔离镜像 `sha256:9e2e9f8a…8d3cf`、UID 10001、LibreOffice 可用、0 restart；Catalog `10802 active / 34 sources / 0 duplicate`；Interview `f76888e4…` 为 completed/version 14/5 turns，分数 `31/31/44/38/56`；三份面试 Blob 与 DOCX/PDF Blob 重算 SHA 全匹配；375x812 五题抽屉与 Composer 无重叠；GUI `49 files / 267 passed`，Python `179 passed, 9 skipped` + `35 passed, 4 skipped`，TypeScript/Alpha build/compileall/diff check 通过 | 线上 `opencareer-alpha-backend-a-1` 保持原镜像 healthy、0 restart；`xlsx` 仍有 1 个无现成修复的 high npm 公告，需独立替换评估；本轮不把隔离 Gate 自动切为公网生产 | 在正式切换窗口执行数据备份、迁移校验、回滚演练与受控切流；在此之前继续保持隔离 Gate |
| 正式备份与隔离回滚演练 | 通过 | SQLite Online Backup、PostgreSQL 全租户 dump、加密配置、镜像与 Caddy/前端完整恢复点；临时卷/库恢复；新后端失败后旧镜像接管 | 恢复点 `20260819T072425Z`；服务器与离机副本 SHA 全通过；45 个文件、3/3 SQLite integrity；两个 PostgreSQL 库各 40/40 表计数一致；Gate 7 Blob、Catalog 218 Blob 内容指纹一致；恢复后 PostgreSQL/Redis ready；旧镜像恢复 health ok；Catalog `10802/34/0 duplicate` | 9 条隐藏测试租户篡改 Blob 为源库既有对抗数据，恢复精确保留，应用可见 79 Blob 无 SHA 错误；密钥仅离机保存、服务器不保留；正式流量切换仍需维护窗口 | 按 `docs/18_BACKUP_AND_ROLLBACK_RUNBOOK.md` 在受控窗口完成最终停写备份和生产切流 |
| PostgreSQL 生产切流 | 通过 | 最终停写冷备、SQLite/Context 迁移、共享 Catalog 只读、RLS/Blob Gate、新后端与 Caddy 原子切换、真实浏览器验收 | 恢复点 `20260819T103248Z`；离机 209 MiB/28 文件 SHA 全通过；新镜像 `sha256:9e2e9f8a…8d3cf`；health 为 PostgreSQL/Redis ready；Catalog `10802/34/0 duplicate`；Career `2 resumes / 5 facts / 3 sessions / 8 turns / 1 match`；Context `10 conversations / 158 messages / 1 compaction`；Blob mismatch 0；跨租户读取 0；REST/WS/原件下载和公网浏览器岗位/档案/面试通过 | 旧 SQLite 有两个冲突活动面试，迁移保留全部历史并取消较旧会话；282 个旧岗位只映射、4 个无引用旧/演示岗位跳过；旧容器和原卷停止保留为即时回滚点；CLI 主动断开 WS 留下一条 benign `1006` 日志 | 观察新后端稳定性并按 Runbook 执行一次 PostgreSQL 生产备份恢复抽检；旧容器和原卷在观察窗口结束前不得删除 |
| 模拟面试评价重试风暴熔断 | 通过，延迟仍待优化 | 暴露严格评价 schema；最多一次 validation 修复重试；禁止无关 Career 工具探索参数；真实 PostgreSQL 会话恢复 | FastMCP schema 固定 `version=2`、7 题型、26 维度、5 动作并拒绝额外字段；Engine/stop `27 passed`、面试/Skill/API `89 passed`、Server 聚焦 `14 passed`；真实 Session `2si6lj8oaq4` 从 `version=3/evaluating` 推进到 `version=6/waiting_for_answer`；`get_next_interview_question` 从 4 次收敛为 2 次且第二次成功；公网/直连 PostgreSQL/Redis ready；生产镜像 `sha256:cc807d48…06b8`、0 restart | 真实单轮仍为 70.06 秒；首次严格 schema 调用漏传四个维度对象的 `name`，由唯一一次修复重试成功；本机无 Docker CLI，Compose config 未执行；旧 `alpha-next` 容器和原卷继续保留 | 让首次维度对象稳定包含四个必填键，并减少重复 `load_skill` 模型迭代；观察新容器后再继续 JD/登录/视觉改造 |
| 模拟面试 Skill 预加载 | 通过并已发布 | 强制 Skill 与评价依赖首轮预加载；Answer Prompt 携带 CAS 版本；服务端确定性补评价维度名；首次 Schema 调用成功 | 真实模型迭代 `6 -> 3`、工具 `6 -> 2`、`load_skill 2 -> 0`、前置 Session 读取 `1 -> 0`、耗时 `70.06s -> 47.89s`；GUI `20 passed`、Python `132 passed`，TypeScript/compileall/diff/Alpha build 通过；生产镜像 `sha256:11651d68…f248672`、UID 10001、0 restart；公网加载 `index-C7pYKC8w.js`；Interview `311f8603…` 为 `version=8/waiting_for_answer` | 切换有约 4 秒上游不可达窗口并产生 3 次 502，随后自动连接恢复；仍需三次真实模型推理，总耗时约 48 秒；8 个既有 npm 漏洞独立治理；旧容器、原卷和恢复点继续保留 | 观察新容器稳定性；下一最小任务是在不暴露隐藏推理的前提下展示阶段耗时，再处理 JD 展示、登录托管和全站视觉改造 |
| 岗位雷达收藏箱与 Catalog 清理 | 通过并已发布 | 顶部“全部岗位/收藏箱”、租户收藏计数、详情只显示 JD、移除生产测试公司、阻止测试再次污染生产、375×812 响应式修复 | 生产 33 个无引用测试岗位事务清理后为 `10769 active / 34 sources / 0 test companies / 0 duplicate`；对抗引用使整单回滚；Python `47 passed` + 防护 `10 passed`，GUI `24 passed` 后移动端聚焦 `17 passed`，TypeScript/compileall/build/diff 通过；真实收藏 `0 -> 1 -> 0`；375×812 `clientWidth=scrollWidth=375`、越界 0；镜像 `sha256:4167e8b7…572079b`、bundle `index-9PTp9h-T.js`、0 restart | 原 10,802 口径包含 33 个测试岗位，正式岗位基线应更新为 10,769；Alpha 对 settings/cloud 等桌面专属接口仍会产生预期 403；8 个既有 npm 漏洞独立治理；旧容器、静态前端、原卷和恢复点保留 | 观察岗位雷达与每日抓取是否维持 10,769 正式基线；下一项处理 OpenCareer 登录托管或安全阶段耗时展示 |
| GUI npm 依赖安全修复 | 通过并已发布 | 清除 8 个 npm audit 漏洞；升级构建与测试依赖；用可复现的官方 SheetJS 安全版本替换 registry 旧版 | `npm audit: 8 -> 0`；Vite `7.3.6`、Vitest `3.2.7`、PostCSS `8.5.26`、NanoID `3.3.18`、esbuild `0.28.2`、xlsx `0.20.3`；vendored tarball SHA-256 `8dc73fc3…99fe8`；GUI `49 files / 268 passed`、TypeScript/Alpha build 通过；桌面与 375×812 公网 Gate 无溢出、page error 或非预期失败；bundle `index-Dgak5WmV.js`，XLSX chunk 200 | `xlsx` 安全版由 SheetJS 官方 CDN 而非 npm registry 分发，因此仓库固定 tarball 和 SHA；后续升级需同时核验官方公告、文件哈希和读写 smoke；后端、Origin、Token 和数据库配置未改 | 继续按锁文件执行 `npm audit`；下一项由产品优先级选择登录托管移除或安全阶段耗时展示 |
| Career-first 暖色编辑台界面 | 通过并已发布 | 移除 Cloud 登录、收件箱和通用管理入口；保留对话内审批；方案 B 暖色纸张、衬线标题、陶土强调色；岗位/档案/面试统一视觉；移动端完整适配 | GUI `50 files / 268 passed`，TypeScript/Alpha build/npm audit/diff 通过；`1440×900`、`1024×768`、`375×812` 岗位与档案真实 Gate 均无横向溢出、page error 0；移动 Sidebar 关闭后 `left=-264/right=0`，档案单列可读；六类隐藏入口 DOM 为 0；bundle `index-DkqJdPt8.js`、CSS `index-Bd_fNi9d.css`；PostgreSQL/Redis ready、WS 101、后端/Caddy 0 restart | 初次目录级替换破坏 Caddy bind mount，根页面短暂 404，重启 Caddy 后恢复；发布方式已改为复制哈希资源后原子替换 index。Alpha 仍有 settings/workspaces/connectors 预期 403；旧后端 API 和 Inbox 历史数据刻意保留 | 下一最小任务：减少 Alpha 对隐藏桌面管理 API 的请求，或实现不暴露隐藏推理的阶段耗时展示 |
| JD 确认直启面试与字节全量续跑 | 隔离 Gate 通过，生产部署见下一行 | JD/公开链接预览 hash 与显式确认；确认后 fresh match + InterviewSession；字节中国大陆社招/校招 20 页有界续跑、三遍覆盖校验、原子 Catalog 提交 | 社招 pass 3 committed `11,634 created`，校招 pass 3 committed `7,423 created`；合计 19,057 active、来源内和跨范围重复 0、invalid 0、无 missing/offline；stale 自动尾部 Gate 为 `2 active / 4 offline`，真实 PostgreSQL 临时 cycle 回滚验证通过；聚焦回归 `49 passed`，TypeScript/Alpha build/Compose/diff 通过，npm audit 0 | 公开 URL 2 MiB 仍为读取后限制 | 生产结果与后续动作见下一行 |
| 字节全量来源生产部署 | 已上线，生产官网复核 cycle 续跑中 | 备份、migration 7、新后端/抓取镜像、19,057 条完整来源 seed、旧来源去重与可恢复切换 | 恢复点 `20260821T032119Z` 两端 SHA 通过；生产 `29612 active / 19063 ByteDance / 0 active external duplicates / 0 invalid new`；REST、WS、PostgreSQL/Redis ready，后端 restart 0；用户数据计数不变 | 官网访问限制使三遍生产复核需要后台冷却续跑；当前校招 checkpoint 1,996、社招 200，但正式 Catalog 已由隔离三遍 Gate 快照完整上线 | 观察两个生产 cycle 最终 committed 和 stale 自动核验结果，再执行真实 Alpha JD“预览→确认→首题/取消零写入” |
| PostgreSQL 岗位雷达性能 | 已上线，服务器侧 P95 通过 | 轻量列表 projection、单次可见性判断、owner 可见性键、合并 facets、active feed 索引 | migration 8；生产 `29612 active / 0 duplicate`；Alice/Bob 隔离与 WS 通过；服务器经 Caddy 列表/筛选 P95 `157.88ms / 138.77ms`；候选隔离库 P95 `412.76ms / 384.25ms`；恢复点 `20260821T075235Z` 两端 SHA 通过；新镜像 `sha256:4c5f4d68…079f2` | 当前开发机到北京公网 health P50 `872.41ms`，网络抖动使外部 P95 超过 1.7s；应用服务器侧已低于 500ms，未加缓存 | 观察真实用户网络；若同地域监控的服务端 P95 回升到 500ms 以上，再单独设计缓存 |
| AI 简历诊断与面试准备对话 | 已上线，真实模型完整诊断待人工验收 | 单选已确认简历后自动进入 Career Conversation；AI 直接读取完整 JD 与脱敏简历；先诊断/追问，再逐段改写和生成针对性面试追问；不调用脚本匹配或生成文件 | 本地 MCP/Skill/Python `23 passed, 14 skipped`、GUI `48 files / 268 passed`；生产 REST/WebSocket 与真实浏览器入口通过，新 bundle `assets/index-CuWJNaIe.js` | 本次未消耗模型额度执行完整诊断对话；仍需人工检查首轮诊断结构、追问和后续改写是否符合批准策略 | 使用一份已确认脱敏简历执行一次完整“诊断→追问→改写→面试准备”验收 |
| 旧匹配与文件生成链路下线 | 运行时已上线，物理 retirement 未执行 | 面试直读 JD/已确认简历；删除 Match、Application Packet、Tailored Resume 与导出运行时；增加只读归档和显式 retirement；移除后端 LibreOffice/Noto CJK | 提交 `e367b34`；恢复点 `20260824T162922Z-legacy-retirement` 两端 SHA 与临时库恢复通过；镜像 `sha256:651a37b3…e65ad`、后端/Caddy 0 restart；数据计数不变；REST、WebSocket、旧接口 404 和真实浏览器岗位/AI 简历分析入口通过 | 4 张旧表和旧 Blob 仍保留，retirement marker 为 0；真实 PostgreSQL destructive retirement 尚未演练或执行；本地 Bedrock 依赖和一个 Skill 预加载测试挂起问题仍独立存在 | 在专用 PostgreSQL 16 恢复库完成 archive/retirement 演练，审查 Blob 删除范围后再申请生产物理清理 |
| Alpha 简历诊断读取权限热修 | 已上线并完成真实诊断 | 将只读脱敏工具 `get_confirmed_resume` 加入 Alpha Conversation allowlist，保留旧匹配/草稿/导出禁用边界 | 提交 `02479e2`；聚焦回归 `34 passed`；镜像 `sha256:a38d28d…329e50`；公网 health、403、旧路由 404、Skill absence Gate 通过；真实模型仅调用 `get_job` 与 `get_confirmed_resume` 并输出四段诊断 | 缺失事实尚未由用户确认，按 Skill 规则未生成改写 proposal；物理 retirement 仍未执行 | 用户逐项确认缺失事实后，在同一 Conversation 生成带来源路径的改写建议与面试准备 |
| 对话裸 URL 中文标点修复 | 已上线 | 防止 GFM 将官网 URL 后的中文右括号、句号和正文吞入链接 | 提交 `ed6b8b7`；GUI `48 files / 268 tests`、TypeScript、Alpha build、npm audit、diff check 通过；bundle `index-XrtHYZM6.js`；生产 DOM 的链接文本与 `href` 均精确结束于 `/detail`，后续中文为独立文本节点，console error 0 | 仅修复裸 `http(s)` 链接；显式 Markdown 和 artifact 链接保持原行为 | 继续观察其他中英文混排 URL，如发现新终止符再以真实样例补充回归 |
| AI 简历分析岗位标题 | 已上线 | 新会话在分析开始时显示 `公司 · 岗位名称`，不再暴露预加载 Skill 指令 | 提交 `98ad963`、`6a5bc43`；GUI `48 files / 268 tests`、TypeScript、Alpha build、npm audit、diff check通过；bundle `index-p76hYlGW.js`；浏览器实测分析进行中顶部与侧栏标题正确；历史会话 `oaigkyplbae` 单条修正 | 临时验收会话因既有 Inbox 外键问题无法通过 DELETE 清理，已归档；需要单独修复会话删除顺序 | 为 PostgreSQL Conversation 删除增加 Inbox resolution 级联清理的独立 TDD 修复 |
| PostgreSQL 会话删除 Inbox 外键修复 | 已上线 | resolved Inbox 随 Inbox item 和 Conversation 级联删除，恢复既有会话 DELETE API | migration 9；提交 `a00fc67`；本地 `11 passed, 7 skipped`；PostgreSQL 16 临时库真实删除 Gate；生产 schema `8 -> 9`、FK `NO ACTION -> CASCADE`；原失败会话 `sf1n2m606fl` 删除返回 200 且 Conversation/Inbox/Message 均无残留；镜像 `sha256:14e6dcf6…e6c5b`；后端/Caddy restart 0 | 切换窗口内活跃页面轮询短暂产生 12 个 502，随后恢复；本机未配置 `TEST_DATABASE_URL`；旧正式容器与恢复点保留，旧 Career 四表未物理 retirement | 观察删除接口与新容器稳定性；物理 retirement 继续作为独立任务，需恢复库演练和明确批准 |
| Authing 云端参数预配置 | 配置就绪，未启用 | 在备案审批期间提前保存正式域名与 OIDC 服务端凭据，不改变现有 IP Alpha | 服务器 `.env` 权限 `600`；Issuer、App ID、App Secret、64 字符状态密钥均已配置；`docker-compose.ip.yml config --quiet` 通过；health 为 ok、PostgreSQL/Redis ready；恢复点 `.env.backup-authing-20260827T094605Z` | App Secret 曾在用户截图中完整出现，用户明确暂不轮换；本地域名登录改动尚未发布；备案中不得切 DNS 或开放域名入口 | 备案通过后先轮换 Secret（建议），再发布已验证代码、配置 DNS/HTTPS，并执行双账号数据隔离 Gate |
| Authing 单域名正式上线 | 已上线，双账号隔离待人工 Gate | 备案后启用 `app.opencareer.online`、自动 HTTPS、Authing OIDC 登录与 PostgreSQL 用户身份映射；保留 18080 回滚入口 | 备案号 `京ICP备2026055760号-1`；DNS `app/@/www -> 203.0.113.10`；migration 10；HTTPS health 200、匿名会话 401、Authing 302、根域名与 www 301；备份 `/opt/opencareer-backups/20260831T033559Z-domain-authing`；本地后端/部署 42 passed、AuthGate 3 passed、前端构建通过 | 首次 Caddy 使用 `host-gateway` 指到 172.17.0.1 导致短暂 502，改为 Compose 网关 172.18.0.1 后恢复；截图中旧 App Secret 仍按用户决定暂不轮换；历史 `local` 数据未迁移 | 使用两个独立虚构账号完成对话、简历、收藏与申请进度的交叉隔离；30 日内完成公安联网备案 |
| Authing 重复回调容错 | 已上线，待朋友复测 | 邮箱客户端或内置浏览器在首次成功后约 0.09 秒重复访问同一授权码时，不以错误页覆盖已建立的登录态 | 首次回调 `307`、同码第二次为 `OAuthError` 的云端日志；TDD 认证 `20 passed`；浏览器级重复回调回首页；production health `ok` | 仅对已持有有效 HttpOnly 会话的浏览器容错；无会话认证错误保持脱敏 `400`；仍需双账号隔离人工 Gate | 朋友重新从首页发起一轮邮箱验证码登录，再做虚构对话、简历、收藏与申请进度交叉隔离 |
| OpenCareer 启动图标 | 本地 Gate 通过，未发布 | 白底暖陶土色品牌标识统一桌面启动器、macOS/Windows 安装包资源与 Web favicon；托盘保留单色资源 | `assets/icon.png` 为唯一母版；Tauri 官方 icon 生成器；32/128/256/512 px、ICNS、ICO 和 Store PNG 格式检查通过；GUI `51 files / 290 tests passed`、TypeScript、Alpha build、localhost 护栏与 diff check 通过 | Tauri desktop build 被已有缺失的 `src-tauri/binaries/sidecar` 阻断；当前母版为生成式位图，尚未在 Dock/开始菜单人工确认 | 下一最小任务：补齐目标平台 sidecar 后构建安装包，人工确认 Dock/开始菜单显示，再决定是否发布 |


## 2026-09-11 — 小红书产品介绍视频

- 本地独立演示环境使用 1421 / 8766 端口；通过现有预览—确认接口准备 3 条虚构岗位和 1 份虚构简历。原启动脚本 seed 缺少 preview_hash，未改产品源码，分别启动后端与前端。
- 浏览器验证首页、岗位选择、收藏、申请进度保存、求职档案、分析简历选择及面试设置。默认模型返回 403 route_resolution_failed，因此视频仅展示真实界面与能力说明，未编造诊断和面试结果。
- 新增 `videos/opencareer-intro/` 视频源文件及 `artifacts/opencareer-video-20260911/` 成片、无口播字幕版、口播稿、字幕、封面、发布文案与验收记录。两版均为 75 秒、1080×1920、30 fps、2250 帧，无音轨。
- 执行 HyperFrames 0.7.48 `lint`、`validate`、`inspect`、`snapshot`、`render --quality high --fps 30`：运行和排版检查通过；带字幕源仅剩字幕轨道密度编辑提示，无字幕版零提示。`ffprobe` 核对参数，`ffmpeg -v error -i <mp4> -f null -` 两版完整解码通过，成片抽帧目视检查与源文件 ZIP 完整性通过。
- 未发布到外部平台；下一最小任务：真人配音后校准字幕及镜头节奏。如需完整实时 AI 演示，先处理模型权限。

## 2026-09-14 — 退出登录跳转修复

- 本地 Gate 通过：退出成功后清除应用会话并立即进入 Authing 登录/注册流程，
  同时保留当前站内回跳路径；`prompt=login` 防止单点登录静默复用上一用户。
- 证据：GUI `51 files / 291 tests passed`，身份聚焦后端 `19 passed`，TypeScript、
  Alpha build、Python compileall、diff/localhost 护栏通过；真实 Chromium 确认
  `logout -> login` 顺序、`prompt=login` 参数和后退不恢复私有页面；本地托管页
  以模拟内容验证。
- 本轮未部署。下一最小任务：发布后使用两个虚构账号完成退出与换账号 Gate。


## 2026-09-14 真人配音产品介绍视频

用户提供 70.784 秒真人录音，要求剪入此前 75 秒产品视频。新增独立工程 `videos/opencareer-voiceover-20260914/` 与交付目录 `artifacts/opencareer-voiceover-20260914/`，保留原录音和 9 月 11 日视频。按七段录音重排页面切换；保留 1 倍语速，整理首尾空白和段间停顿，规范音量；33 条录音对齐字幕；末页改为已上线与第一轮内测邀请。

验收命令：HyperFrames 0.7.48 `lint` / `validate` / `inspect` / `snapshot --at 4,12,22,34,44,56,69` / `render --quality high --fps 30`；`ffprobe -show_entries stream=codec_type,codec_name,width,height,sample_rate,channels,duration,nb_frames -show_entries format=duration,size -of json`；`ffmpeg -v error -i <mp4> -f null -`；对成片音轨本地 faster-whisper small 转写复核。画面 1080×1920、2250 帧、75.000 秒；容器 75.029333 秒（音频编码帧尾差）；H.264 与 AAC，完整解码通过，音量 -16.62 LUFS / 真峰值 -4.48 dBTP。静态检查只有字幕轨道密度提示，运行与布局检查无错误；七页预览及成片抽帧人工视觉检查通过；转写确认七段与内测结尾完整。未声称真人试听。

工具边界：最新版升级探测因 Node.js 20.20.2 不符合新版 >=22 要求失败，保留原 0.7.48；本次未改产品依赖。录音在本机转写，未上传，未发布。下一步由用户播放成片确认配音节奏。

## 2026-09-16 — 模拟面试、退出登录与输入框体验上线

- 已修复生产岗位“结构化要求为空、原始 JD 有完整任职要求”时模拟面试被判定参数无效；
  回退解析严格限定在 JD 明确要求章节，并有元数据边界和误判回归测试。
- 输入首字后多余留白已消除；技能按钮改为轻量书本图标，技能列表在输入区上方展开并
  带分割线，选中后显示为顶部上下文栏；面试时长选项也已统一为真实的五轮标准。
  退出登录跳转修复随本轮上线。
- 验收：Python 相关套件 `86 passed`，GUI `51 files / 292 tests passed`，TypeScript、
  Alpha build、compileall、diff/localhost 护栏通过；生产 PostgreSQL/Redis ready。
  真实账号已从小米岗位成功进入模拟面试会话并停在授权步骤，未继续消耗模型生成首题。
- 恢复点：`/opt/opencareer-backups/20260916T065646Z-interview-composer`。下一步由用户
  继续该会话体验五轮面试，并用第二个虚构账号完成退出换号验收。

## 2026-09-16 — 默认自动审批（本地待发布）

- 已修复历史模拟面试对话覆盖云端自动审批默认值的问题。常规求职读取与面试
  流程默认自动通过；岗位入库、简历事实确认、申请进度写入保留确认。
- 模式菜单新增“自动审批”，移除“仅讨论”和无限制“完全访问”。同一运行
  引擎可切换“执行前询问”；服务重启后恢复自动审批默认。
- 权限与基础会话回归 27 项、界面 293 项通过；类型、构建、编译检查通过。
  真实浏览器已确认菜单与默认标签。完整 server.py 套件在 shell 相关线程等待，
  已停止，未宣称全量通过。
- localhost:1421 可测试；本轮尚未上线。下一步体验完整面试后发布本轮改动。

## 2026-09-16 — 公网安全收敛（待发布）

- 服务端补齐显式路由/工具白名单、共享技能只读、Cookie-only 云身份、官方模型
  地址校验与历史配置复验；禁止用户指定服务器程序和任意网址读取。
- 域名编排删除免登录 18080；维护编排仅回环；容器只读根、禁止提权并移除能力。
  增加请求体/请求速率、每用户与全局连接/运行回合上限，关闭云端桌面调度入口。
- 最终后端相关回归 171 项，GUI 293 项；类型、Alpha build、编译、配置校验通过。
  真实本地技能面板和自动审批标签验证通过，localhost:1421 可查看。
- 服务器完整 267 MiB 恢复点和隔离数据库恢复已核验，原数据/旧镜像未删。
  离机备份导出被安全审批拦截，等待用户明确授权生产用户数据的本机目的地；
  未上线，旧公网入口尚未关闭，暂勿扩大发链接范围。
- 下一步：授权离机复制后校验恢复点、发布、线上验证；真人双账号和容量/压力
  验收仍未完成，不作“绝对安全”保证。

## 2026-09-17 — 公网安全版本已发布

- 用户授权的离机副本已完成，全部 SHA-256 与加密配置解密校验通过。停写后的
  最终数据库在隔离环境恢复，全表数量和 Blob 内容指纹一致；最终副本也已离机
  校验。原备份、旧镜像及业务数据卷保留，未删除生产数据。
- 补充先认证再读取请求体、30 秒读取超时和本机备份/秘密同步排除规则。后端
  相关回归 172 项，GUI 51 文件/293 项，类型与编译检查通过；新镜像在无网络、
  不挂生产数据的只读容器中通过纯策略检查后上线。
- 正式域名健康 200；匿名私有接口 401，技能写入与未知接口 403，真实旧 Token
  的 HTTP/WebSocket 分别 401/403。18080 无监听且公网连接拒绝，后端只读、
  非 root、禁止提权且重启次数 0；岗位采集已恢复。浏览器登录跳转 Authing 正常。
- 仍待用户确认云端回复图片防自动外传的界面验收范围，当前外链图片行为尚未
  改动。真人双账号、完整面试、容量/压力测试未完成；暂勿据此宣称绝对安全。
- 下一最小任务：确认并关闭云端回复的自动图片加载，再做真人双账号隔离验收。

## 2026-09-17 — 回复图片防自动外传已上线

- 用户确认后，云端回复图片改为固定“图片未自动加载”提示，无自动图片请求；
  普通链接仍可手动打开，桌面图片和网站正常界面图标不受影响。
- 两种真实构建模式分别验收：云端 Markdown 6 passed / 1 个桌面用例 skipped；
  GUI 全量 51 文件 / 294 passed / 2 个云端用例 skipped。类型、生产构建、
  localhost 护栏通过；虚构浏览器页确认行内/引用式图片和普通链接行为正确。
- 旧前端恢复点单独保存并校验；只更新静态前端及对应源码，不重启后端，
  不改用户数据。正式域名首页与 JS 指纹匹配发布构建，health ok、登录入口正常。
  已打开的页面需要刷新；未发布虚构验收页。
- 图片自动加载风险已收敛，但手动打开不可信链接和模型输出受提示词影响的
  风险仍在。下一步为真人双账号隔离及完整面试验收，不作绝对安全保证。

## 2026-09-18 — 用户反馈、诊断与问题中心本地完成

- 三阶段代码按确认的隐私与权限边界实现：固定元数据诊断、站内反馈和个人
  回复历史、指定管理员问题中心与基础告警。不新增 Agent 管理工具，不自动
  采集正文/密钥，不默认外发；生产管理员默认空。规格与运维说明见文档 20。
- 真实虚构账号浏览器验证提交→回复→查看及另一账号隔离，登录前匿名提交
  和实际 390×844 窄屏无横向溢出。存储损坏不阻止原业务，反馈失败保留草稿。
- 后端安全支持 72 passed，会话/健康检查 57 passed；真实非超级用户 PostgreSQL
  迁移、隔离及独立检查冷却 8 passed。GUI 全量 301 passed / 2 skipped，Alpha
  支持相关 12 passed / 1 skipped；类型、编译、构建及 diff 检查通过。
- 未发布生产、未安装监控任务、未配置外部通知或授予生产管理员；当前不应
  认为线上已有该入口。模板已提供，需确认身份、备份后发布和真实 Authing
  验收；原 localhost:1421 服务不替换，虚构环境收尾停止并保留测试数据库。
- 下一最小任务：确认管理员账号及提醒目的地，再按文档 18/20 安全上线。
  匿名容量、异地可用性监控、压力及真人面试验收仍待完成。

## 2026-09-20 — 用户反馈、诊断与问题中心已上线

- 已按用户确认的管理员账号完成服务端稳定用户编号映射；未在仓库保存邮箱或编号。
  当前不配置外部提醒，管理员主动打开问题中心查看；主机监控模板保持未安装、未启用。
- 发布前 Python 聚焦回归 `191 passed`，GUI `301 passed / 2 skipped`；类型、编译、
  Alpha 构建、脚本语法和 diff 检查通过。迁移 11–18 已在候选库和生产库执行，
  五张支持表全部强制行级隔离。
- 最终恢复点已在独立数据库恢复并同时保存到服务器和本机私有目录，原应用表行数
  与 426 个 Blob 内容指纹发布前后一致。配置加密保存，本机密钥权限 600；服务器
  临时明文副本已删除，旧镜像和旧前端保留作回滚。
- 生产 health 200，未登录私有及管理接口 401，非法 Origin 和未知 Shell 路径
  403；后端 healthy、三容器 restart 0、18080 无监听。首页与 JavaScript 指纹
  匹配发布构建，真实浏览器进入 Authing“验证码登录 / 登录注册”页。
- 下一最小任务：管理员本人登录确认问题中心入口，并用一个普通账号完成生产反馈
  闭环。双真人账号隔离、容量/压力、异地监控和完整五轮面试仍是上线后 Gate。
- 发布后审查补齐跨用户合并回复隔离、请求体并发内存上限和发布脚本恢复点/
  版本一致/自动回滚门槛。最终聚焦回归 `191 passed / 1 skipped`，候选容器隔离
  Gate 通过。复审后拆分匿名/登录用户容量池，补齐合并到已解决主问题和发布恢复点
  对应当前版本的校验；一键脚本遇到新迁移会拒绝并要求维护窗口流程。最终镜像
  `sha256:65957aaff887980380acf5d08cadde37e2f4ddce428207f11d4ba71d2529ec30`
  已上线，旧镜像保留。热更新后数据与 Blob 指纹不变、容器 restart 0、无错误堆栈。

## 2026-09-20 — 登录回调失败恢复（本地待发布）

- 生产管理员登录回调返回原始 JSON 400。只读检查确认 Authing
  元数据、服务端配置、回调地址与流程 Cookie 正常，且本次没有创建应用会话。
- 修复后不降低 OIDC/PKCE 安全校验：失败会清理旧流程状态，回到友好登录页并
  提供一次明确的“重新登录”；不展示、复用或保存授权码/state，不无限自动重试。
- 验收：后端 `2 passed`，GUI `4 passed`，compileall 和 diff 检查通过。
  本轮未发布；下一步是备份当前线上版本、发布该修复，再由管理员从新登录页验收。

## 2026-09-21 — 登录回调恢复已上线

- 已使用完整恢复点发布；服务器与用户明确授权的项目私有离机副本
  均通过 SHA-256，加密配置解密哈希一致，密钥权限 600，服务器临时密钥已删除。
  发现恢复点后新增数据后又刷新快照；隔离恢复最终为 51 张表、455 个 Blob、
  175 个约束全部一致，5 张支持表强制行级隔离。
- 发布过程发现并修复前端候选目录被源码 `rsync --delete` 误删、回滚陷阱不穿透
  函数的脚本缺口。先恢复发布前镜像并验证健康，再用修复脚本完整重发。
- 生产现为新后端镜像和 `index-CG8VUjXg.js`，前后端指纹与本地一致。
  失败回调会 307 转到友好页、清理旧流程 Cookie，不返回 JSON 且不泄露
  code/state；真实浏览器已显示“登录没有完成 / 重新登录”。
- 发布后聚焦回归 `30 passed`，GUI 身份 `8 passed`；类型、编译、Shell 和 diff
  检查通过。health 200，三容器 restart 0，脱敏日志无错误。下一步仅剩
  管理员本人点击“重新登录”，完成真实验证码登录与问题中心权限验收。

## 2026-10-12 — 新 Authing 用户池已接入，邮件验证码仍被供应商拦截

- 新池实名认证截图已确认；切换前完成最新服务器及离机加密恢复点，数据库
  custom dump 可列出，全部备份文件 SHA-256 校验通过。
- 线上只改 Authing Issuer、App ID、App Secret，重建后端；health 200、匿名
  未登录、登录跳转新池均通过，旧数据及恢复点保留。
- 新池真实登录页发送验证码时仍返回“请联系管理员完成实名认证”。登录尚未
  端到端通过，需 Authing 邮件额度生效/客服同步后重测验证码、回调、管理员权限。

## 2026-10-12 — 新池登录与管理员权限修复完成

- 上条“需供应商邮件额度生效”是过早归因：新用户池“开启邮件服务”原为关闭；
  开启且重新登录控制台复核后，原验证码发送错误消失。用户收到验证码。
- Authing 应用原有“所有人：拒绝”规则导致提交后“无权限登录”。按用户明确
  选择改为“所有人：允许”，用户完成登录并回到生产网站。
- 新池账号的 OpenCareer 内部编号与旧管理员白名单不匹配。经 Authing 用户详情
  和生产身份表双重核对后，仅更新服务端管理员白名单、重建后端；健康检查通过，
  真实页面“问题中心”入口及列表可用。账号编号与邮箱不写入仓库。
- 身份聚焦回归 `20 passed`，支持模块回归 `15 passed`，文档差异检查通过；
  尚需另一真人账号验证跨账号隔离，以及完整的
  用户提交反馈→管理员回复→用户查看闭环。

## 2026-10-16 — 开源源码与本地版候选

- 隔离一键启动、独立数据、默认本机访问、服务商环境隔离已完成；无依赖源码副本
  首次安装通过，5 项真实本地与浏览器验收通过。
- 前端类型检查、303 项单元测试和隔离 alpha 构建通过；审查发现的遗漏已修复。
  详见 `23_OPEN_SOURCE_REVIEW.md`。旧英文桌面浏览器套件保留手动验收。
- 旧仓库保持私有，新仓库先私有。公开仅使用提交后的归档，不带旧历史和部署补丁；
  远端同步、最终扫描及公开状态另行核对。本轮不操作线上服务。

## 2026-10-19 — 本地版说明与构建工具安全维护

- Tailwind 4.3.3 迁移完成，原 7 项构建依赖告警已消除：完整依赖和仅运行依赖
  的 npm 审计均为 0 项；CI 增加完整审计门槛，不隐藏开发依赖。
- README 已含 5 张实机截图，覆盖环境安装、启动、模型密钥与默认模型、可选
  文字识别/语音、数据备份和故障处理。截图只使用独立本地虚构数据。
- 类型检查、303 项前端用例、5 项真实本地验收、standalone / alpha 构建通过。
  已人工核对升级前后浅色、深色及紧凑窗口的主要页面，没有部署线上。
- 兼容边界：更新浏览器版本；旧系统桌面壳、原生 Windows、真人语音与模型调用
  保持独立验收。详情见 `11_DEVELOPMENT_LOG.md` 与 `SECURITY.md`。

## 2026-10-19 — 新用户从零安装复验

- 从公开仓库全新克隆，复现并修复 Python 管理器符号链接下的环境创建失败，以及
  安装中断后缺 pip 无法重试；新增两条真实安装回归并纳入 CI。
- 本地版未配置模型时明确引导配置，保留草稿，简历导入不再绕过配置检查；
  本机密钥文案与 README 的操作入口同步澄清，托管模型策略保持不变。
- 2 项全新安装、5 项本地/浏览器验收、309 项前端用例通过，2 项原有用例跳过；
  类型检查、standalone / alpha 构建、重启保留测试对话通过。
- 只同步公开源码，不部署线上；真实模型/麦克风与原生 Windows 仍需独立验收。

## 2026-10-22 — DOCX 预览与中文标签本地回归

- 修复无段落样式的 DOCX 预览异常；保留标题与安全转义。侧边浏览器 HTML blob
  空白改为隔离的内嵌 HTML 预览，禁用脚本；PDF 路径不变。
- 预览失败结束加载并提供重试，迟到请求不会覆盖其他简历；地址、城市、目标岗位、
  项目名称与技能名称显示正确。
- 35 项后端聚焦测试、317 项前端测试通过，2 项原有用例跳过；类型检查、编译检查、
  standalone 构建和差异检查通过。侧边浏览器同一虚构 DOCX 正文显示与故障恢复重试通过。
- 本轮仅本地修改与验证，未推送仓库、未部署线上、未新增模型调用；PDF/扫描件仍待
  单独验收，不将 DOCX 通过推广为所有格式通过。

## 2026-10-28 — 本地版岗位雷达补齐

- 一键启动默认后台采集全部已注册官方来源，字节全量来源使用既有 SQLite 断点
  续跑；每 12 小时更新，成功源分批显示、失败保留数据。无需模型密钥或线上账号。
- 雷达增加来源进度、自动刷新和重试，补齐 browser 可选依赖与安装说明。
- 本地限定接口不允许传入任意网址或命令；默认托管模式不可访问。新增离线和浏览器
  用例验证失败隔离、重启跳过、申请记录保留、续跑入库、自动显示与访问边界。
- 有限官网验收 DeepSeek／小米共 3,746 条，浏览器列表、筛选与完整 JD 可见。
  全量来源当日完整抓取和原生 Windows 仍需独立观察；本次不部署线上服务。

## 2026-10-29 — 默认共享公共岗位，保留独立采集

- 采用集中采集／静态分发默认方案。服务器只读导出公共爬虫岗位，客户端完整下载后
  每 24 小时检查，失败保留数据并 15 分钟重试；本机独立采集仍可通过参数选择。
- 公网真实新库验收得到 36 来源、34,476 条记录／30,481 条在招，数量与公共目录
  一致；重复同步和用户跟踪记录保持通过。无需网站登录、模型密钥或生产数据库凭据。
- 独立导出定时器已实际成功触发，原线上三个容器身份和启动时间不变、health 为 ok。
- 后端 1414、领域 476、前端 321 项回归通过；真实浏览器 3 项与可选公网端到端
  1 项通过。跳过／排除项未计入通过。规划与运维见文档 23 和公共目录部署指南。

## 2026-10-29 — 通用查询与每日群推送（开源本地版）

- 已完成领域查询、新 MCP 工具／独立入口、Skill、对话卡片与雷达组合筛选，以及
  订阅设置、停用草稿、页面启用、每日刷新发送、运行记录和三种官方机器人适配器。
- 后端1420、领域503、前端323项通过；真实浏览器3项、安装／续装／重启9项通过。
  已用真实 DeepSeek 验证对话岗位查询和单候选语义判断／缓存，无真实群外发。
- 真实群渠道尚未配置，不能宣称真实投递或对话订阅已验收。部分官网源较旧，查询会
  提醒实际确认时间；不把公共快照发布时间冒充官网更新时间。详见文档24与开发日志。
- 仅更新开源源码与本地预览，生产网站保持现有版本。下一最小任务：在测试群配置
  一个官方机器人，完成一次页面预览／启用、对话草稿和真实日报的人工验收。
