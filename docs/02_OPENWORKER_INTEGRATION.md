# 02 — OpenWorker 二次开发与集成规范

> 本文的 OpenWorker-first 边界继续有效。示例 Manifest 和最小 MCP 工具属于项目
> 启动阶段；当前能力清单与 schema 见 `docs/README.md` 和
> `05_DATA_MODEL_AND_MCP_TOOLS.md`。

## 1. 基线

- 上游：`andrewyng/openworker`
- 固定提交：`01b6f83b3927e02912dda84bb392942c13ca70d1`
- 提交日期：`2026-08-01`

OpenWorker 处于快速开发阶段。MVP 先固定提交，避免上游变化打断。完成首个稳定里程碑后再通过单独分支评估上游同步。

## 2. 复用边界

### 原样复用或仅修复必要 Bug

- `coworker/engine.py`
- `coworker/agent.py`
- `coworker/providers/` 的 Router 和既有 Provider 语义
- `coworker/permissions.py`
- `coworker/mcp/`
- `coworker/memory.py`
- `coworker/automation/`
- `coworker/server/`
- `surfaces/gui` 的通用会话、审批、设置页面

### 允许新增或小范围修改

- `coworker/personas/builtin/career.md`
- Persona 图标映射或选择器展示的最小改动
- Career 相关测试
- `.coworker/skills/`
- `.coworker/mcp.json`
- `extensions/career_mcp/`
- 后续最小 Career 专用页面
- 独立的新 Provider 适配器及其最小注册代码；不得重写 Router

## 3. Career Persona

建议文件：

```text
coworker/personas/builtin/career.md
```

建议 Manifest：

```markdown
---
id: career
name: Career Agent
icon: briefcase
tagline: Discover jobs, analyze JDs, prepare applications
family: knowledge
tools: [files, search, shell, todo]
messaging: false
connectors: true
recommended_models: [openai:gpt-5.6-sol]
default_permission_mode: interactive
description: A career coworker for Chinese AI and internet job discovery and application preparation.
recommends:
  - mcp: career
    reason: search official jobs, import JDs, and manage job records
    tier: core
---
你是 Career Agent，面向中国 AI 和互联网岗位求职者。

你的职责：
- 使用 Career MCP 搜索和读取岗位，而不是凭记忆编造。
- 分析用户粘贴的 JD，并明确缺失字段。
- 生成可保存、可追溯的岗位分析交付物。
- 后续生成简历内容时，只能使用用户确认过的真实经历。
- 所有岗位信息保留官方来源和抓取时间。

工作方式：
- 有工具任务时先维护 todo。
- 优先读取，修改或外部动作遵守审批。
- 不执行自动投递或招聘网站登录。
- 完成任务时提供实际生成文件的链接。
```

Codex 应以当前 Persona Manifest schema 为准，并为解析和注册新增测试。

## 4. Career Skills

OpenWorker 基线会从全局 Skill 目录和工作区 `.coworker/skills` 加载 Skill。MVP 推荐工作区 Skill，便于与项目一起版本控制。

目录：

```text
.coworker/skills/
├── career-jd-analysis/SKILL.md
├── career-job-search/SKILL.md
└── career-application-packet/SKILL.md
```

### Skill 职责

- 描述领域步骤和输出规范。
- 告诉 Agent 何时调用哪个 MCP 工具。
- 指定事实约束和用户确认节点。
- 不直接实现数据库或爬虫。

### `career-jd-analysis` 最小内容

- 判断输入是原始文本、URL 还是岗位 ID。
- 原始文本使用 `import_manual_jd`。
- 已存在岗位使用 `get_job`。
- 输出职责、要求、地点、招聘类型、关键词、缺失信息。
- 不把“优先”“加分”误判为硬性要求。

## 5. Career MCP

### 目录

```text
extensions/career_mcp/
├── pyproject.toml
├── README.md
├── server.py
├── career_mcp/
│   ├── __init__.py
│   ├── config.py
│   ├── domain/
│   ├── tools/
│   ├── crawler/
│   ├── database/
│   └── schemas/
└── tests/
```

也可使用当前仓库已有 Python packaging 方式，但必须保持该模块可独立导入和测试。

### MCP 传输

个人 MVP 优先 stdio：

```text
OpenWorker
  └── 启动本地 Python Career MCP 进程
          └── 访问本地 SQLite 和爬虫模块
```

不需要额外端口、认证或云服务。

### 工作区配置

OpenWorker 使用标准 `mcpServers` JSON。工作区配置路径：

```text
<workspace>/.coworker/mcp.json
```

配置只有在用户信任工作区后才会加载。示例：

```json
{
  "mcpServers": {
    "career": {
      "command": ".venv/bin/python",
      "args": ["-m", "extensions.career_mcp.server"],
      "enabled": true
    }
  }
}
```

Windows 或实际虚拟环境路径不同，Codex 应根据上游配置解析器和跨平台需求调整。不得绕过 WorkspaceTrustStore。

## 6. 为什么使用 MCP 而不是修改 Tool Catalog

Career 业务包含岗位数据库、抓取器、版本状态和后续申请数据。这些能力属于垂直领域，不应加入 OpenWorker 平台维护的通用 Tool Catalog。

MCP 的好处：

- 与 OpenWorker 核心解耦。
- 工具 schema 明确。
- 便于单元测试。
- 未来可独立部署为 HTTP MCP。
- 即使替换 Agent Harness，Career 业务仍可复用。

## 7. MVP 贯通测试

### 工具

`get_mock_jobs` 返回固定两条岗位：

- AI 产品经理实习生。
- Agent 全栈开发实习生。

### 流程

1. 用户创建 Career 会话。
2. Agent 加载 job-search Skill。
3. Agent 调用 `get_mock_jobs`。
4. MCP 返回结构化结果。
5. Agent 写入 `artifacts/mock-job-brief.md`。
6. GUI 展示工具调用与文件链接。

### 验收

- 工具确实由 MCP 调用，不是 Agent 编造。
- 关掉 MCP 后有清晰错误。
- 未信任工作区时 MCP 不自动启动。
- 信任后工具可见。
- 文件写入仍遵守 OpenWorker 权限和根目录范围。

## 8. 上游同步策略

- `upstream/main` 只做跟踪。
- Career 开发在独立分支。
- 不把格式化整个仓库、无关重构和 Career 功能混在同一提交。
- 每次同步上游前先运行 OpenWorker 原测试与 Career 测试。
- 若上游改变 Persona/Skill/MCP schema，更新本文件和开发日志。
