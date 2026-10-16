# CODEX_START_HERE.md

你正在维护一个已经完成多阶段开发的 OpenWorker Fork。不要把它当作空白项目，也
不要从 Stage 0、Persona、MCP mock 或第一个招聘源重新开始。

## 开始前必须阅读

1. `AGENTS.md`
2. `docs/README.md`
3. 当前任务对应的最新规格、运行手册或来源说明
4. `docs/06_IMPLEMENTATION_PLAN.md`
5. `docs/09_CODEX_TASK_BACKLOG.md`

需要追溯历史时再读取 `docs/11_DEVELOPMENT_LOG.md` 和
`docs/superpowers/plans/`，不要默认加载全部历史计划。

## 当前基线

- 产品：OpenCareer / OpenWorker Career。
- 上游固定基线：`01b6f83b3927e02912dda84bb392942c13ca70d1`。
- Career 数据库：schema v13。
- GUI：React + Tauri。
- 后端：OpenWorker Python Server。
- Career 领域：`extensions/career_mcp`，通过可信工作区 MCP 接入。
- 模型默认：本地 Aiden 登录下的 `aiden:deepseek-v4-flash`。

已实现的 Persona、Skill、MCP、招聘源、岗位雷达、Career Vault、OCR、AI 简历
诊断、直读 JD/简历的模拟面试和全局语音输入均属于当前基线，不得重复实现。
旧岗位匹配、Application Packet 和定制简历生成已退出运行时。

## 每个任务的工作方式

1. 先检查工作树，保留所有既有改动。
2. 从 `docs/README.md` 确认权威文档和当前 Gate。
3. 阅读任务涉及的代码和最新规格，明确最小修改边界。
4. 功能和 Bug 修复执行 RED → GREEN → 重构。
5. 运行聚焦测试；涉及共享行为时运行全量回归和生产构建。
6. 把准确命令、结果和剩余风险追加到：
   - `docs/11_DEVELOPMENT_LOG.md`
   - `docs/12_TONIGHT_PROGRESS.md`

## 当前优先事项

1. 真人麦克风与完整标准 Conversation 模拟面试体验 Gate。
2. 降低真实模型生成复合首题后的重试次数。
3. Windows x64 OCR 离线打包 Gate。
4. 官方招聘源稳定性观察和覆盖矩阵维护。

不要根据历史计划中的未勾选项自行恢复已经完成或已被后续方案取代的工作。
