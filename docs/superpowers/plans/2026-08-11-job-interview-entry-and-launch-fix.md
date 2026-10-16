# 岗位模拟面试双入口与启动修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 为每个岗位增加列表与详情双入口，自动补齐 fresh 简历匹配，并修复 Career Session 因 workspace 被清空而无法发送首题的问题。

**Architecture:** `CareerJobsView` 统一持有面试设置和自动匹配状态，列表项与详情头部只触发同一入口；`CareerJobMatchPanel` 删除重复入口。`App` 在创建 Conversation 时校验并保留可信 workspace；`InterviewView` 为首题启动提供即时状态反馈。

**Tech Stack:** React 18、TypeScript、Vitest、Testing Library、OpenWorker Session/WebSocket、现有 Career HTTP API。

---

### Task 1: 统一设置与双入口

**Files:**
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [x] **Step 1: 写双入口失败测试**

断言两条岗位各有带岗位名的“模拟面试”按钮，详情头部有当前岗位入口；点击列表入口后当前详情不切换，并打开标题为“模拟面试设置”的同一弹层。

- [x] **Step 2: 运行测试并观察 RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/components/CareerJobsView.test.tsx
```

Expected: FAIL，当前列表和详情头部不存在独立入口。

- [x] **Step 3: 实现最小双入口与共享弹层**

在 `CareerJobsView` 增加 `interviewJob`、简历、时长、难度、loading 和 error 状态。
列表按钮使用 `event.stopPropagation()`；详情按钮调用同一 `openInterviewSetup(job)`。

- [x] **Step 4: 运行测试并观察 GREEN**

Run 同 Step 2。Expected: 新增入口测试 PASS。

### Task 2: 自动生成 fresh 匹配

**Files:**
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [x] **Step 1: 写自动匹配失败测试**

设置 `getCareerJobMatches()` 返回空数组、`getCareerResumes()` 返回一份 confirmed 简历；
提交设置后断言调用：

```ts
createCareerJobMatches("job-1", ["resume-1"])
```

并用返回 bundle 的 fresh snapshot 调用 `onStartInterview`。另写无 confirmed 简历和
匹配失败时显示中文错误、不调用 `onStartInterview` 的断言。

- [x] **Step 2: 运行定向测试并观察 RED**

Expected: FAIL，当前 `CareerJobsView` 不编排匹配。

- [x] **Step 3: 实现最小自动匹配**

打开设置时并行读取简历与历史匹配，只允许 confirmed 简历；提交时复用所选简历的
fresh snapshot，否则调用 `createCareerJobMatches`，严格检查 bundle、resume ID 和
`snapshot_status === "fresh"` 后发出 payload。loading 时禁用入口和提交。

- [x] **Step 4: 运行定向测试并观察 GREEN**

Expected: 双入口、自动匹配、错误与重复点击测试全部 PASS。

### Task 3: 移除匹配面板重复入口

**Files:**
- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.tsx`
- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`

- [x] **Step 1: 更新契约测试并观察 RED**

断言匹配结果弹层不再渲染“模拟面试”或“模拟面试设置”，其他申请包和定制简历操作
保持存在。

- [x] **Step 2: 删除面试专属状态、表单和回调**

从 `CareerJobMatchPanel` 移除 `onStartInterview`、面试候选、时长、难度和设置 UI；
`InterviewLaunchPayload` 移至 `CareerJobsView` 可复用导出。

- [x] **Step 3: 运行两个组件测试**

```bash
cd surfaces/gui
npm test -- --run src/components/CareerJobMatchPanel.test.tsx src/components/CareerJobsView.test.tsx
```

Expected: PASS。

### Task 4: 修复 workspace 与首题反馈

**Files:**
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/App.interview.test.tsx`
- Modify: `surfaces/gui/src/components/InterviewView.tsx`
- Modify: `surfaces/gui/src/components/InterviewView.test.tsx`

- [x] **Step 1: 写真实 family 回归测试并观察 RED**

把 App 测试中的 Career Persona 改为 `family: "code"`，提供默认/近期 workspace，
捕获传给 `Session` 的 workspace。断言岗位启动后新 Career Session 使用该路径并能
发送 `mock-interview` turn；无 workspace 时不调用创建 API并显示中文错误。

- [x] **Step 2: 最小修复 App**

`startMockInterview` 在调用创建 API 前校验 `workspace`；成功后不再
`setWorkspace(null)`。其余 Conversation ID、CAS 绑定和 TurnEngine 路径保持不变。

- [x] **Step 3: 写并实现首题即时反馈**

在 `InterviewView` 测试点击后立即断言按钮显示“面试官正在准备第一题…”且禁用；
最小实现复用 `pendingTurnId === "start"`，不新增计时器或后端协议。

- [x] **Step 4: 运行 App 与 InterviewView 测试**

```bash
cd surfaces/gui
npm test -- --run src/App.interview.test.tsx src/components/InterviewView.test.tsx
```

Expected: PASS。

### Task 5: 回归、浏览器验收与记录

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`

- [x] **Step 1: 运行 GUI 全量测试与构建**

```bash
cd surfaces/gui
npm test
npm run build
```

Expected: 全部 PASS，production build 成功。

- [x] **Step 2: 浏览器真实验收**

验证列表与详情均有入口；无历史匹配可自动匹配；点击提交后显示准备状态；进入
`InterviewView` 后点击开始产生 Career Session turn 并显示第一题。检查 console 和
network 没有新增错误。

- [x] **Step 3: 更新开发日志并检查 diff**

记录根因、RED/GREEN 命令、浏览器证据和残余风险，运行：

```bash
git diff --check
```

- [x] **Step 4: 审查提交边界**

目标文件在本任务前已有未提交的录音波形和提前结束改动。为避免把历史工作树误归入
当前提交，本轮不创建混合 implementation commit；设计和实施计划保持独立提交，
实现与验收记录留在当前工作树。
