# 求职档案页面与全局中文界面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加可直接查看档案、原始简历和版本记录的一级页面，并把 OpenCareer GUI 的交互文案统一为中文。

**Architecture:** Career Vault 继续由现有 Repository 和 ResumeService 负责；OpenWorker Server 增加只读页面 API 和受确认保护的删除 API。GUI 新增独立 `CareerProfileView` surface，复用现有简历导入 nonce。中文化采用显式中文文案、Persona 显示映射和确定性排序，不改协议字段。

**Tech Stack:** Python 3.12、FastAPI、SQLite、python-docx、React 18、TypeScript、Vitest

---

### Task 1: 档案页面查询服务

**Files:**
- Modify: `extensions/career_mcp/database/resume_repository.py`
- Modify: `extensions/career_mcp/services/resumes.py`
- Test: `extensions/career_mcp/tests/test_resume_repository.py`
- Test: `extensions/career_mcp/tests/test_resume_service.py`

- [ ] **Step 1: 写失败测试**

测试已确认档案能够返回版本摘要和关联原文件元数据，且不暴露 `private_path`、upload token。

- [ ] **Step 2: 确认红灯**

Run: `.venv/bin/python -m pytest -q extensions/career_mcp/tests/test_resume_repository.py extensions/career_mcp/tests/test_resume_service.py`

Expected: FAIL，查询方法不存在。

- [ ] **Step 3: 最小实现**

Repository 新增：

```python
def list_profile_versions(self) -> list[dict]: ...
def get_profile_original(self) -> dict | None: ...
```

Service 新增：

```python
def get_profile_versions(self) -> list[dict]: ...
def get_profile_original(self) -> dict: ...
def read_profile_original(self) -> dict: ...
```

返回 `filename/source_kind/size/content`，路径只在 Service 内部解析并校验。

- [ ] **Step 4: 确认转绿**

运行同一测试命令，Expected: PASS。

### Task 2: 档案 HTTP API

**Files:**
- Modify: `coworker/server/app.py`
- Test: `tests/test_career_profile_api.py`

- [ ] **Step 1: 写失败测试**

覆盖：

```text
GET /v1/career/profile
GET /v1/career/profile/versions
GET /v1/career/profile/original
GET /v1/career/profile/original/content
GET /v1/career/profile/original/download
DELETE /v1/career/profile
```

断言默认脱敏、PDF 内容类型、下载文件名、DOCX 安全 HTML、错误码和删除确认。

- [ ] **Step 2: 确认红灯**

Run: `.venv/bin/python -m pytest -q tests/test_career_profile_api.py`

Expected: FAIL，路由返回 404。

- [ ] **Step 3: 最小实现**

路由复用 `ResumeService`。文件内容使用 `Response`，下载设置安全
`Content-Disposition`。Service 错误映射为稳定中文 JSON，不返回堆栈。

- [ ] **Step 4: 确认转绿**

运行同一测试命令，Expected: PASS。

### Task 3: 档案 React 页面与入口

**Files:**
- Create: `surfaces/gui/src/components/CareerProfileView.tsx`
- Create: `surfaces/gui/src/components/CareerProfileView.test.tsx`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.tsx`

- [ ] **Step 1: 写失败测试**

覆盖无档案空状态、已确认档案、三个页签、脱敏切换、原文件预览、版本记录、删除确认和导入回调。

- [ ] **Step 2: 确认红灯**

Run: `npm test -- src/components/CareerProfileView.test.tsx`

Expected: FAIL，组件不存在。

- [ ] **Step 3: 最小实现**

新增 API 类型和请求函数。App 增加 `profile` surface；Sidebar 增加固定
“我的求职档案”入口；导入/更新复用 `resumeImportNonce` 并返回会话页。

- [ ] **Step 4: 确认转绿**

运行同一测试命令，Expected: PASS。

### Task 4: Persona 中文名称和排序

**Files:**
- Modify: `surfaces/gui/src/personaScope.ts`
- Create or Modify: `surfaces/gui/src/personaScope.test.ts`
- Modify: `surfaces/gui/src/components/Sidebar.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.test.tsx`

- [ ] **Step 1: 写失败测试**

断言：

```text
career → 职业 Agent
cowork → 通用 Agent
code → 编程 Agent
ops → 运维 Agent
chat → 聊天 Agent
```

新建对话列表固定 `career` 第一，未知 Persona 保持相对顺序。

- [ ] **Step 2: 确认红灯**

Run: `npm test -- src/personaScope.test.ts src/components/Sidebar.test.tsx`

- [ ] **Step 3: 最小实现**

新增纯函数 `personaDisplayName` 和 `sortPersonasForNewSession`，仅修改显示和菜单排序。

- [ ] **Step 4: 确认转绿**

运行同一测试命令，Expected: PASS。

### Task 5: 全局中文交互文案

**Files:**
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/components/*.tsx`
- Modify: `surfaces/gui/src/components/connectors/*.tsx`
- Modify: `surfaces/gui/src/providers/ProviderSetup.tsx`
- Test: `surfaces/gui/src/uiChineseAudit.test.ts`

- [ ] **Step 1: 建立失败审计**

审计源码中的按钮、菜单、标题、placeholder、`title` 和 `aria-label`，白名单只允许
OpenCareer、Aiden、DeepSeek、Skill、MCP、API、品牌和模型标识。

- [ ] **Step 2: 确认红灯**

Run: `npm test -- src/uiChineseAudit.test.ts`

Expected: FAIL，列出剩余英文交互文案。

- [ ] **Step 3: 分页面翻译**

依次完成主导航与 Composer、审批与右侧栏、设置与 Persona、连接器、自动任务、收件箱和错误/空状态。内部 key、API 枚举、用户内容和 Agent 输出保持原样。

- [ ] **Step 4: 确认转绿**

Run: `npm test -- src/uiChineseAudit.test.ts`

Expected: PASS。

### Task 6: 完整验收

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: 全量测试**

```bash
.venv/bin/python -m pytest -q extensions/career_mcp/tests tests/test_career_profile_api.py tests/test_mcp.py tests/test_builtin_personas.py
cd surfaces/gui && npm test && npm run build
git diff --check
```

- [ ] **Step 2: 浏览器验收**

检查职业 Agent 第一、档案空状态/已有状态、三个页签、中文设置、审批和菜单；控制台 0 errors。

- [ ] **Step 3: 记录结果**

开发日志写入文件、验收项、测试结果、风险和下一最小任务。
