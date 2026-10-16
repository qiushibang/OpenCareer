# OpenCareer Career-first Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visible OpenWorker shell with the approved Career-first warm editorial interface while preserving in-conversation approvals and all existing career workflows.

**Architecture:** Keep the current React surface state and backend APIs intact, but make `Sidebar` a Career-only navigation shell and remove its Cloud, Inbox, Automation, and Persona polling. Drive the visual change through shared CSS/Tailwind tokens, then apply small component-level corrections only where hard-coded blue styles bypass those tokens.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 3, Vitest, Testing Library, Vite, Playwright.

---

### Task 1: Lock the Career-only navigation contract

**Files:**
- Modify: `surfaces/gui/src/components/Sidebar.test.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: Write the failing Sidebar test**

Add a test that renders `Sidebar`, opens no secondary menu, and asserts:

```tsx
expect(screen.getByRole("button", { name: /新建对话/ })).toBeTruthy();
expect(screen.getByTestId("nav-career-jobs")).toBeTruthy();
expect(screen.getByTestId("nav-career-profile")).toBeTruthy();
expect(screen.getByTestId("nav-settings")).toBeTruthy();
expect(screen.queryByText("OpenWorker Cloud")).toBeNull();
expect(screen.queryByText("收件箱")).toBeNull();
expect(screen.queryByText("连接器")).toBeNull();
expect(screen.queryByText("自动任务")).toBeNull();
expect(screen.queryByText("活动记录")).toBeNull();
expect(screen.queryByText("未登录")).toBeNull();
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/Sidebar.test.tsx
```

Expected: FAIL because the account row and Automation navigation are still visible.

- [ ] **Step 3: Implement the minimal Career-only Sidebar**

Remove Cloud, Inbox and Automation API imports, state, effects and menu rendering. Remove their
props from `Sidebar`, render a direct settings row, and keep session search plus existing recent
conversation actions. Keep attention badges on conversation rows because they indicate an inline
approval in that conversation.

- [ ] **Step 4: Simplify App wiring**

Remove obsolete Sidebar props and callbacks. Keep old surface render branches for compatibility;
no backend API or persisted data is deleted.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/Sidebar.test.tsx src/App.interview.test.tsx
```

Expected: all selected tests pass.

### Task 2: Reduce the Career home to three direct actions

**Files:**
- Modify: `surfaces/gui/src/components/CareerWelcome.test.tsx`
- Modify: `surfaces/gui/src/components/CareerWelcome.tsx`
- Modify: `surfaces/gui/src/styles.css`

- [ ] **Step 1: Write the failing action-count test**

Assert that the home exposes exactly:

```tsx
expect(screen.getByRole("button", { name: /发现合适岗位/ })).toBeTruthy();
expect(screen.getByRole("button", { name: /建立求职档案/ })).toBeTruthy();
expect(screen.getByRole("button", { name: /分析一份 JD/ })).toBeTruthy();
expect(screen.queryByText("查看岗位雷达")).toBeNull();
expect(screen.queryByText("查看求职档案")).toBeNull();
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
cd surfaces/gui
npx vitest run src/components/CareerWelcome.test.tsx
```

Expected: FAIL because five actions are currently rendered.

- [ ] **Step 3: Implement the three-action editorial list**

Keep the existing import and prompt callbacks. Remove duplicate radar/profile actions and use a
single divided action list rather than repeated cards.

- [ ] **Step 4: Verify GREEN**

Run the same Vitest command and expect all tests to pass.

### Task 3: Apply the warm editorial design system

**Files:**
- Modify: `surfaces/gui/src/styles.css`
- Modify: `surfaces/gui/tailwind.config.js`

- [ ] **Step 1: Add static token assertions**

Create a raw-CSS test in `surfaces/gui/src/interfaceTheme.test.ts` that checks the approved core
tokens and the serif heading stack:

```ts
expect(css).toContain("--paper: #f7f4ed");
expect(css).toContain("--accent: #b65f42");
expect(css).toContain('"Songti SC"');
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
cd surfaces/gui
npx vitest run src/interfaceTheme.test.ts
```

Expected: FAIL against the current cool gray and cobalt tokens.

- [ ] **Step 3: Update shared light/dark tokens**

Apply the approved warm paper, warm panel, terracotta accent, semantic status colors and warm dark
theme. Add `--sidebar` and `--display` variables and map the Tailwind font families to them.

- [ ] **Step 4: Restyle shell, transcript and Composer**

Update sidebar width/background, topbar, main reading width, user bubble, Composer border/shadow,
focus states and mobile drawer. Keep stable dimensions and existing interaction selectors.

- [ ] **Step 5: Verify GREEN**

Run the theme test and the Sidebar/CareerWelcome tests.

### Task 4: Remove hard-coded blue from Career surfaces

**Files:**
- Modify: `surfaces/gui/src/components/ConversationInterviewBar.tsx`
- Modify: `surfaces/gui/src/components/CareerProfileView.tsx`
- Modify: `surfaces/gui/src/components/InterviewProgressPanel.tsx`
- Test: existing component tests

- [ ] **Step 1: Add raw-source regression assertions**

Extend `interfaceTheme.test.ts` to assert that Career UI sources do not contain
`bg-blue-*`, `text-blue-*`, `border-blue-*` or `text-slate-*`.

- [ ] **Step 2: Run and verify RED**

Expected: FAIL on the interview bar and profile badges.

- [ ] **Step 3: Replace hard-coded colors with semantic tokens**

Use `accent`, `accentSoft`, `ok`, `okSoft`, `line`, `ink` and `muted`. Preserve the progress state
calculation and all button behavior.

- [ ] **Step 4: Run focused tests**

```bash
cd surfaces/gui
npx vitest run \
  src/components/ConversationInterviewBar.test.tsx \
  src/components/InterviewProgressPanel.test.tsx \
  src/components/CareerProfileView.test.tsx \
  src/components/CareerJobsView.test.tsx
```

Expected: all tests pass.

### Task 5: Full regression and Alpha build

**Files:**
- Modify only files required by failures caused by this change.

- [ ] **Step 1: Run the full GUI suite**

```bash
cd surfaces/gui
npm test
```

Expected: all tests pass.

- [ ] **Step 2: Run TypeScript and Alpha build**

```bash
cd surfaces/gui
npx tsc
cd ../..
bash deploy/build-frontend.sh
```

Expected: both commands exit 0 and the bundle uses Alpha mode.

- [ ] **Step 3: Run security and formatting checks**

```bash
cd surfaces/gui
npm audit --json
cd ../..
git diff --check
```

Expected: zero npm vulnerabilities and no whitespace errors in touched files.

### Task 6: Browser visual and interaction Gate

**Files:**
- Create temporary Playwright evidence under `/tmp`; do not commit screenshots.

- [ ] **Step 1: Start the local Alpha frontend**

Run the existing app/backend if available; otherwise use the published Alpha endpoint only after a
local production build has passed.

- [ ] **Step 2: Inspect three viewports**

Use Playwright at `1440×900`, `1024×768` and `375×812`. For each viewport verify:

```text
document.documentElement.scrollWidth === document.documentElement.clientWidth
page errors === 0
OpenWorker Cloud / 收件箱 / 连接器 / 自动任务 / 活动记录 absent
岗位雷达 / 求职档案 / 新建对话 reachable
```

- [ ] **Step 3: Exercise real workflows**

Open Job Radar, Favorites, Career Profile and a conversation. On mobile open/close the navigation
drawer. For an active mock interview, verify the progress panel/drawer and Composer do not overlap.

- [ ] **Step 4: Fix and repeat until clean**

Any overflow, clipping, inaccessible control, console error or unexpected request failure is a
blocking defect.

### Task 7: Document and publish the static frontend

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Append exact verification evidence**

Record test counts, bundle names, viewport dimensions, screenshots, expected Alpha 403s and any
remaining risk.

- [ ] **Step 2: Preserve rollback assets**

Copy the existing server `deploy/web` to a timestamped pre-redesign directory and generate
SHA-256 checksums for the new release.

- [ ] **Step 3: Atomically publish static assets**

Replace only the Caddy-served frontend directory. Do not restart or rebuild the backend.

- [ ] **Step 4: Run production smoke**

Verify public health, new bundle/chunks, desktop/mobile browser behavior, PostgreSQL/Redis ready,
and unchanged backend/Caddy restart counts.

- [ ] **Step 5: Commit scoped implementation**

Commit only the interface files, tests, plan and appended evidence. Do not include unrelated dirty
worktree changes.
