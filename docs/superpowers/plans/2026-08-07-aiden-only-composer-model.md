# Aiden-only Composer Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Composer 只显示并使用 Aiden DeepSeek V4 Flash，同时保留 Settings 中的其他模型配置。

**Architecture:** 新增 GUI 纯函数输出固定的 Composer 模型策略，App 在展示、会话绑定和发送消息时应用该策略。OpenWorker 通用 Server 默认值保持不变；当前本地 prefs 使用现有设置接口迁移为 Aiden。

**Tech Stack:** React, TypeScript, Vitest, Python, pytest

---

### Task 1: Composer 单模型策略

**Files:**
- Create: `surfaces/gui/src/composerModelPolicy.ts`
- Create: `surfaces/gui/src/composerModelPolicy.test.ts`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest";
import { AIDEN_MODEL, composerModelPolicy } from "./composerModelPolicy";

describe("composerModelPolicy", () => {
  it("only exposes Aiden even when other configured models exist", () => {
    expect(composerModelPolicy([
      "ep-20260806151220-8km7l",
      AIDEN_MODEL,
      "gpt-5.6-sol",
    ])).toEqual({ model: AIDEN_MODEL, models: [AIDEN_MODEL] });
  });
});
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `npm test -- src/composerModelPolicy.test.ts`

Expected: FAIL，因为 `composerModelPolicy` 模块尚不存在。

- [ ] **Step 3: 写最小实现并接入 App**

```typescript
export const AIDEN_MODEL = "aiden:deepseek-v4-flash";

export function composerModelPolicy(_configuredModels: string[]) {
  return { model: AIDEN_MODEL, models: [AIDEN_MODEL] };
}
```

`App.tsx` 仅在向 `Composer` 传递 `model` 与 `models` 时使用该结果；Settings 继续读取完整 `models`。

- [ ] **Step 4: 运行聚焦测试并确认转绿**

Run: `npm test -- src/composerModelPolicy.test.ts`

Expected: PASS。

### Task 2: Aiden 本地默认模型

**Files:**
- Modify: `.local-state/prefs.json`（通过现有设置 API）

- [ ] **Step 1: 迁移当前本地默认值**

通过 `/v1/settings/default-model` 设置
`aiden:deepseek-v4-flash`，不修改 Server 默认构造值或 Provider Router。

- [ ] **Step 2: 运行聚焦与全量回归**

Run: `.venv/bin/python -m pytest -q tests/test_settings.py tests/test_provider_router.py tests/test_aiden_provider.py`

Expected: 全部 PASS，现有 Provider 首次配置规则不变。

Run: `npm test && npm run build`

Expected: GUI 全部 PASS，production build 成功。

- [ ] **Step 3: 验证本地默认值**

检查 `.local-state/prefs.json` 和 `/v1/health` 均返回
`aiden:deepseek-v4-flash`。
