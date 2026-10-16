# 岗位筛选、简历库与侧栏搜索优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆分多城市筛选、中文化岗位类型标签、支持切换多份已确认简历，并将会话搜索移到品牌栏图标。

**Architecture:** 城市解析由 Career Domain 纯函数统一，Repository 在读取现有数据时兼容拆分，crawler normalize 对新数据写入规范数组。简历库复用现有 `resume_imports`、`resume_previews` 和 `profile_versions`，以 import UUID 作为文档 ID，不复制候选人事实库。GUI 使用小型 label helper 和现有页面组件，不改 OpenWorker 核心。

**Tech Stack:** Python 3.12、SQLite、FastAPI、React 18、TypeScript、Vitest、Testing Library、pytest。

---

### Task 1: 城市拆分纯函数

**Files:**
- Create: `extensions/career_mcp/domain/locations.py`
- Create: `extensions/career_mcp/tests/test_locations.py`
- Modify: `extensions/career_mcp/crawler/normalize.py`
- Modify: `extensions/career_mcp/tests/test_crawler_normalize.py`

- [ ] **Step 1: 写失败测试**

覆盖：

```python
assert split_job_locations(["北京、深圳、广州"]) == ["北京", "深圳", "广州"]
assert split_job_locations(["北京市，上海市", "北京"]) == ["北京", "上海"]
assert split_job_locations(["浙江 拱墅区"]) == ["浙江 拱墅区"]
```

并为 `normalize_snapshot()` 增加多城市输入断言。

- [ ] **Step 2: 运行红灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_locations.py \
  extensions/career_mcp/tests/test_crawler_normalize.py
```

Expected: FAIL，因为 `split_job_locations` 尚不存在，normalize 仍保留组合字符串。

- [ ] **Step 3: 最小实现**

实现：

```python
_LOCATION_SEPARATOR = re.compile(r"[、，,；;/]+")

def split_job_locations(values: Iterable[str]) -> list[str]:
    # 按输入顺序拆分、规范简单城市名并去重。
```

只对不含空格且以“市”结尾的简单名称去掉后缀。`normalize_snapshot()` 调用该函数生成 `locations`。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 2: 城市筛选元数据和匹配

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/tests/test_jobs_service.py`
- Modify: `tests/test_career_jobs_api.py`

- [ ] **Step 1: 写失败测试**

插入一条 `locations_json='["北京、深圳、广州"]'` 的岗位，断言：

```python
assert {"value": "北京", "count": 1} in filters["locations"]
assert {"value": "深圳", "count": 1} in filters["locations"]
assert {"value": "广州", "count": 1} in filters["locations"]
assert all("、" not in item["value"] for item in filters["locations"])
```

分别用北京、深圳、广州搜索，均命中同一岗位。

- [ ] **Step 2: 运行红灯**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_jobs_service.py \
  tests/test_career_jobs_api.py
```

Expected: FAIL，筛选仍返回组合地点。

- [ ] **Step 3: 最小实现**

`get_job_filters()` 对每个岗位的 locations 调用 `split_job_locations()`，每个岗位内用集合去重后计数。`search_jobs()` 的地点参数继续绑定 SQL，并同时兼容规范值和带“市”原值，使现有组合 JSON 可被任一城市命中。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 3: 招聘类型中文标签

**Files:**
- Create: `surfaces/gui/src/careerJobLabels.ts`
- Create: `surfaces/gui/src/careerJobLabels.test.ts`
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [ ] **Step 1: 写失败测试**

断言 `experienced` 和 `social` 均显示“社会招聘”，未知值显示“类型未标注”。组件测试断言卡片中不存在 `experienced`，并存在带 `data-job-type="experienced"` 的“社会招聘”标签。

- [ ] **Step 2: 运行红灯**

```bash
cd surfaces/gui
npm test -- --run src/careerJobLabels.test.ts src/components/CareerJobsView.test.tsx
```

Expected: FAIL，因为 helper 和标签尚不存在。

- [ ] **Step 3: 最小实现**

导出：

```typescript
export function careerJobTypeLabel(value: string | null): string;
export function careerJobTypeClass(value: string | null): string;
```

列表和详情复用 helper。卡片将纯文本改为胶囊标签，状态改为独立状态标签。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 4: 多简历 Repository 和 Service

**Files:**
- Modify: `extensions/career_mcp/database/resume_repository.py`
- Modify: `extensions/career_mcp/services/resumes.py`
- Modify: `extensions/career_mcp/tests/test_resume_repository.py`
- Modify: `extensions/career_mcp/tests/test_resume_service.py`

- [ ] **Step 1: 写失败测试**

创建两次不同内容的已确认导入，断言：

```python
documents = service.list_resume_documents()
assert [item["filename"] for item in documents] == ["产品经理简历.docx", "通用简历.pdf"]
assert service.get_resume_document(documents[0]["id"])["sections"]["basic"]["name"]
assert service.get_resume_document_versions(documents[0]["id"])
```

文档详情只包含该 preview 已确认章节；不存在 ID 返回 `RESUME_NOT_FOUND`。

- [ ] **Step 2: 运行红灯**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_resume_repository.py \
  extensions/career_mcp/tests/test_resume_service.py
```

Expected: FAIL，列表和按 ID 读取方法尚不存在。

- [ ] **Step 3: 最小实现**

Repository 新增：

```python
def list_resume_documents(self) -> list[dict]: ...
def get_resume_document(self, resume_id: str) -> dict | None: ...
def list_resume_document_versions(self, resume_id: str) -> list[dict]: ...
def get_resume_original(self, resume_id: str) -> dict | None: ...
```

查询仅返回状态为 `partially_confirmed` 或 `confirmed` 的 import。Service 负责敏感字段遮罩、UUID 读取错误和私有路径校验。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 5: 多简历 HTTP API

**Files:**
- Modify: `coworker/server/app.py`
- Modify: `tests/test_career_profile_api.py`

- [ ] **Step 1: 写失败测试**

覆盖列表、详情、版本、原文件元数据、预览、下载和 404 中文错误。断言响应中没有 `private_path`、`upload_token`。

- [ ] **Step 2: 运行红灯**

```bash
.venv/bin/python -m pytest -q tests/test_career_profile_api.py
```

Expected: FAIL，新路由返回 404。

- [ ] **Step 3: 最小实现**

添加 `/v1/career/resumes` 路由组，复用 `_content_disposition()`。错误映射新增：

```python
"RESUME_NOT_FOUND": "未找到这份简历。"
```

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 6: GUI 简历库

**Files:**
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/components/CareerProfileView.tsx`
- Modify: `surfaces/gui/src/components/CareerProfileView.test.tsx`

- [ ] **Step 1: 写失败测试**

模拟两份简历，断言页面自动选择第一份，点击第二份后调用对应 ID 的详情和原文件 API，标题按钮为“新增简历”。

- [ ] **Step 2: 运行红灯**

```bash
cd surfaces/gui
npm test -- --run src/components/CareerProfileView.test.tsx
```

Expected: FAIL，API 与简历选择器尚不存在。

- [ ] **Step 3: 最小实现**

新增 `CareerResumeDocument` 类型和六个请求函数。页面改为左侧简历列表、右侧三个页签；切换简历时释放旧 blob URL 并重新读取所选简历。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 7: 品牌栏搜索图标

**Files:**
- Modify: `surfaces/gui/src/components/Sidebar.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.test.tsx`

- [ ] **Step 1: 写失败测试**

断言 `OpenCareer` 品牌行中存在 `aria-label="搜索对话"` 的按钮，侧栏不存在文本导航项“搜索”，点击图标后搜索弹窗出现。

- [ ] **Step 2: 运行红灯**

```bash
cd surfaces/gui
npm test -- --run src/components/Sidebar.test.tsx
```

Expected: FAIL，搜索仍是独立行。

- [ ] **Step 3: 最小实现**

把现有 `setSearchModalOpen(true)` 按钮移到品牌行，使用 `ml-auto` 对齐标题右侧，删除独立搜索块。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 8: 全量验收和记录

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: 后端回归**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py \
  tests/test_mcp.py \
  tests/test_builtin_personas.py
```

- [ ] **Step 2: GUI 回归和构建**

```bash
cd surfaces/gui
npm test
npm run build
```

- [ ] **Step 3: 静态检查**

```bash
git diff --check
```

- [ ] **Step 4: 浏览器验收**

验证多城市选项已拆分、中文类型标签、两份简历切换、品牌栏搜索图标和控制台 0 error。

- [ ] **Step 5: 更新日志**

记录修改文件、验收结果、测试数量、保留风险和下一最小任务。
