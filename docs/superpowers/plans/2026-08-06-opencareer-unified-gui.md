# OpenCareer Unified GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic OpenWorker/Coworker first-run experience with an OpenCareer-branded, Career-first welcome experience while preserving existing personas and session restoration.

**Architecture:** Add one presentational `CareerWelcome` component that emits prompt-prefill intents and has no API dependencies. `App.tsx` selects it only for idle Career sessions and uses Career as the no-history initial persona; existing session restoration remains authoritative. Sidebar branding and Composer placeholder changes stay local to their existing components.

**Tech Stack:** React 18, TypeScript, Tailwind/existing GUI CSS, Vitest, Testing Library, Vite.

---

### Task 1: Career Welcome Component

**Files:**
- Create: `surfaces/gui/src/components/CareerWelcome.tsx`
- Create: `surfaces/gui/src/components/CareerWelcome.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/styles.css`

- [ ] **Step 1: Write the failing component tests**

Create tests that render `CareerWelcome` with `onPrefill={vi.fn()}` and assert:

```tsx
expect(screen.getByText("今天从哪里开始？")).toBeTruthy();
expect(screen.getByText("建立求职档案")).toBeTruthy();
expect(screen.getByText("发现合适岗位")).toBeTruthy();
expect(screen.getByText("分析一份 JD")).toBeTruthy();
expect(screen.queryByText("Run the test suite and summarize any failures.")).toBeNull();
```

Add one test per action. Click the action and assert the emitted text contains its required intent:

```tsx
expect(onPrefill).toHaveBeenCalledWith(expect.stringContaining("简历"));
expect(onPrefill).toHaveBeenCalledWith(expect.stringContaining("求职目标"));
expect(onPrefill).toHaveBeenCalledWith(expect.stringContaining("JD"));
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/CareerWelcome.test.tsx
```

Expected: FAIL because `./CareerWelcome` does not exist.

- [ ] **Step 3: Implement the minimal presentational component**

Create:

```tsx
import { Icon } from "./Icon";

const ACTIONS = [
  {
    icon: "file",
    title: "建立求职档案",
    description: "导入简历并逐项确认经历",
    prompt: "我想建立求职档案。请提示我通过附件菜单上传 PDF/DOCX 简历，或粘贴简历文本。",
  },
  {
    icon: "search",
    title: "发现合适岗位",
    description: "从官网岗位中按目标公司、城市和方向搜索",
    prompt: "我想搜索合适岗位。请先询问我的目标公司、城市和职位方向。",
  },
  {
    icon: "fileCode",
    title: "分析一份 JD",
    description: "粘贴职位描述，查看要求、匹配点和风险",
    prompt: "我想分析一份 JD。请等我粘贴职位描述后再开始分析。",
  },
] as const;

export function CareerWelcome({ onPrefill }: { onPrefill: (text: string) => void }) {
  return (
    <div className="career-welcome">
      <div className="career-eyebrow">你的求职 Agent</div>
      <h1>今天从哪里开始？</h1>
      <p>我会基于已确认的真实经历，帮你发现岗位、判断匹配并准备申请材料。</p>
      <div className="career-actions">
        {ACTIONS.map((action) => (
          <button key={action.title} type="button" onClick={() => onPrefill(action.prompt)}>
            <span className="career-action-icon"><Icon name={action.icon} size={18} /></span>
            <span>
              <strong>{action.title}</strong>
              <small>{action.description}</small>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
```

Add these focused styles after the existing idle hero styles:

```css
.career-welcome { max-width: 720px; margin: 6vh auto 0; }
.career-eyebrow {
  color: var(--accent); font-size: 12px; font-weight: 650;
  letter-spacing: .08em; text-transform: uppercase;
}
.career-welcome h1 {
  margin: 8px 0 10px; font-family: var(--serif);
  font-size: 40px; line-height: 1.1;
}
.career-welcome > p {
  max-width: 580px; color: var(--muted); font-size: 15px; line-height: 1.55;
}
.career-actions { display: grid; gap: 10px; margin-top: 30px; }
.career-actions button {
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 13px 14px; border: 1px solid var(--line); border-radius: 12px;
  background: var(--panel); color: var(--ink); text-align: left;
}
.career-actions button:hover { border-color: var(--accent); background: var(--paper); }
.career-actions button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.career-action-icon {
  display: grid; place-items: center; width: 32px; height: 32px;
  border-radius: 9px; background: var(--accentSoft); color: var(--accent); flex: none;
}
.career-actions strong { display: block; font-size: 14px; }
.career-actions small { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
@media (max-width: 640px) {
  .career-welcome { margin-top: 3vh; }
  .career-welcome h1 { font-size: 32px; }
}
```

In `App.tsx`, import `CareerWelcome` and insert this branch before the generic hero:

```tsx
agent === "career" ? (
  <CareerWelcome onPrefill={prefillComposer} />
) : agent === "cowork" ? (
  <SessionIntro ... />
) : (
  <div className="hero">{/* retain the existing Chat/Code/other Persona hero */}</div>
)
```

- [ ] **Step 4: Run the component test and verify GREEN**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/CareerWelcome.test.tsx
```

Expected: all `CareerWelcome` tests PASS.

- [ ] **Step 5: Commit the isolated welcome component**

```bash
git add surfaces/gui/src/components/CareerWelcome.tsx \
  surfaces/gui/src/components/CareerWelcome.test.tsx \
  surfaces/gui/src/App.tsx surfaces/gui/src/styles.css
git commit -m "feat(gui): add OpenCareer welcome"
```

### Task 2: OpenCareer Brand, Default Persona, and Composer Copy

**Files:**
- Modify: `surfaces/gui/src/components/Sidebar.test.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.tsx`
- Modify: `surfaces/gui/src/components/Composer.resume.test.tsx`
- Modify: `surfaces/gui/src/components/Composer.tsx`
- Modify: `surfaces/gui/src/App.tsx`
- Create: `surfaces/gui/src/personaDefaults.test.ts`
- Create: `surfaces/gui/src/personaDefaults.ts`

- [ ] **Step 1: Write failing brand, placeholder, and default tests**

Add a Sidebar test:

```tsx
render(<Sidebar {...baseProps} />);
expect(screen.getByText("OpenCareer")).toBeTruthy();
expect(screen.queryByText("OpenWorker")).toBeNull();
```

Update the Career Composer lookup and add a non-Career assertion:

```tsx
expect(screen.getByPlaceholderText("告诉我你的求职目标，或直接导入简历…")).toBeTruthy();
expect(
  screen.getByPlaceholderText("Ask the coworker…  (drop or paste files)"),
).toBeTruthy();
```

Create `personaDefaults.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { DEFAULT_PERSONA_ID } from "./personaDefaults";

describe("default persona", () => {
  it("starts first-run users in Career", () => {
    expect(DEFAULT_PERSONA_ID).toBe("career");
  });
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/Sidebar.test.tsx \
  src/components/Composer.resume.test.tsx \
  src/personaDefaults.test.ts
```

Expected: FAIL for missing `OpenCareer`, missing Career placeholder, and missing `personaDefaults`.

- [ ] **Step 3: Implement the minimal changes**

Create:

```ts
export const DEFAULT_PERSONA_ID = "career";
```

Use it in `App.tsx`:

```tsx
const [agent, setAgent] = useState(DEFAULT_PERSONA_ID);
```

Keep the existing `if (last.agent) setAgent(last.agent);` restoration branch unchanged.

Change the Sidebar wordmark to:

```tsx
<div className="brand-wordmark text-[15px]">
  OpenCareer<span className="beta-tag">BETA</span>
</div>
```

Make `Composer` own the persona fallback:

```tsx
const placeholder =
  props.placeholder ||
  (props.personaId === "career"
    ? "告诉我你的求职目标，或直接导入简历…"
    : "Ask the coworker…  (drop or paste files)");
```

Pass no explicit `placeholder` from `App.tsx` for Career; retain the existing Code, Chat, and Coworker strings for every other persona.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the same Vitest command from Step 2.

Expected: all selected tests PASS.

- [ ] **Step 5: Commit the branding and copy changes**

```bash
git add surfaces/gui/src/App.tsx \
  surfaces/gui/src/personaDefaults.ts \
  surfaces/gui/src/personaDefaults.test.ts \
  surfaces/gui/src/components/Sidebar.tsx \
  surfaces/gui/src/components/Sidebar.test.tsx \
  surfaces/gui/src/components/Composer.tsx \
  surfaces/gui/src/components/Composer.resume.test.tsx
git commit -m "feat(gui): make OpenCareer the default experience"
```

### Task 3: Full GUI Regression and Browser Acceptance

**Files:**
- Update: `docs/11_DEVELOPMENT_LOG.md`

- [ ] **Step 1: Run the complete GUI test suite**

```bash
cd surfaces/gui
npm test
```

Expected: all tests PASS with no unhandled errors.

- [ ] **Step 2: Run the production build**

```bash
cd surfaces/gui
npm run build
```

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 3: Run formatting and diff checks**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; unrelated pre-existing changes remain untouched.

- [ ] **Step 4: Perform browser smoke acceptance**

Open the running GUI and verify:

1. Sidebar says `OpenCareer BETA`.
2. A fresh Career session says `今天从哪里开始？`.
3. The three actions appear and prefill without sending.
4. Composer says `告诉我你的求职目标，或直接导入简历…`.
5. Switching to Coworker keeps its existing intro and generic Composer copy.
6. Opening an existing non-Career conversation restores its original Persona.

- [ ] **Step 5: Record and commit acceptance**

Append the implemented scope, commands, test totals, and residual risk to
`docs/11_DEVELOPMENT_LOG.md`, then commit only this task's files:

```bash
git add docs/11_DEVELOPMENT_LOG.md
git commit -m "docs(career): record OpenCareer GUI acceptance"
```
