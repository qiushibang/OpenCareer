# 独立岗位雷达页面与档案字段中文化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加列表与详情同屏的独立岗位雷达页面，并将求职档案内部字段名统一显示为中文。

**Architecture:** 现有 `JobRepository` 和 `JobService` 继续作为唯一岗位查询边界；OpenWorker Server 只增加薄 HTTP 页面 API。GUI 新增 `CareerJobsView` 一级 surface，列表只读取摘要，选择岗位后再读取详情。档案字段中文化由独立纯函数负责，不修改 Career Vault 存储字段。

**Tech Stack:** Python 3.12、FastAPI、SQLite、React 18、TypeScript、Vitest、Testing Library

---

### Task 1: 岗位筛选元数据与 HTTP 页面 API

**Files:**
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/services/jobs.py`
- Modify: `coworker/server/app.py`
- Test: `extensions/career_mcp/tests/test_jobs_service.py`
- Create: `tests/test_career_jobs_api.py`

- [ ] **Step 1: 写 Repository 与 Service 失败测试**

在 `test_jobs_service.py` 增加测试，创建多个公司、城市、招聘类型和状态的 fixture 后断言：

```python
filters = service.get_job_filters()
assert filters["companies"] == [
    {"slug": "deepseek", "name": "DeepSeek", "count": 1},
    {"slug": "xiaomi", "name": "小米", "count": 2},
]
assert filters["locations"] == [
    {"value": "北京", "count": 2},
    {"value": "上海", "count": 1},
]
assert filters["recruitment_types"] == [
    {"value": "campus", "count": 1},
    {"value": "social", "count": 2},
]
assert filters["statuses"] == [
    {"value": "active", "count": 2},
    {"value": "inactive", "count": 1},
]
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
.venv/bin/python -m pytest -q extensions/career_mcp/tests/test_jobs_service.py -k filters
```

Expected: FAIL，`JobService` 尚无 `get_job_filters`。

- [ ] **Step 3: 最小实现筛选元数据**

在 Repository 增加：

```python
def get_job_filters(self) -> dict:
    ...
```

公司按名称排序并聚合岗位数；城市展开 `locations_json` 后在 Python 中计数；招聘类型和状态使用 SQL 聚合。Service 只负责打开连接并返回 Repository 结果。

- [ ] **Step 4: 运行 Service 测试确认转绿**

Run:

```bash
.venv/bin/python -m pytest -q extensions/career_mcp/tests/test_jobs_service.py
```

Expected: PASS。

- [ ] **Step 5: 写 HTTP API 失败测试**

创建 `tests/test_career_jobs_api.py`，使用临时 Career 数据库断言：

```python
response = client.get("/v1/career/jobs")
assert response.status_code == 200
assert response.json()["jobs"]
assert all(job["status"] == "active" for job in response.json()["jobs"])

filtered = client.get(
    "/v1/career/jobs",
    params={
        "query": "大模型",
        "company_slug": "deepseek",
        "location": "北京",
        "recruitment_type": "social",
        "status": "active",
        "limit": 20,
        "offset": 0,
    },
)
assert filtered.status_code == 200

detail = client.get(f"/v1/career/jobs/{job_id}")
assert detail.json()["job"]["versions"]

options = client.get("/v1/career/jobs/filters")
assert options.json()["filters"]["companies"]
```

同时断言不存在岗位返回 HTTP 404、`JOB_NOT_FOUND` 和中文消息。

- [ ] **Step 6: 运行 HTTP 测试确认红灯**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_career_jobs_api.py
```

Expected: FAIL，路由返回 404。

- [ ] **Step 7: 最小实现 HTTP 路由**

在 `create_app()` 内增加 `career_job_service()`、稳定错误映射和三个 GET 路由。列表默认将缺失的 `status` 转为 `["active"]`：

```python
result = career_job_service().search_jobs(
    query=query or None,
    company_slugs=[company_slug] if company_slug else None,
    locations=[location] if location else None,
    recruitment_types=[recruitment_type] if recruitment_type else None,
    statuses=[status] if status else ["active"],
    limit=limit,
    offset=offset,
)
```

`LookupError` 映射为 `JOB_NOT_FOUND`；`ValueError` 映射为 `INVALID_INPUT`；未知异常记录 traceback 并返回 `PERSISTENCE_ERROR`。

- [ ] **Step 8: 运行 API 测试确认转绿**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_career_jobs_api.py extensions/career_mcp/tests/test_jobs_service.py
```

Expected: PASS。

### Task 2: GUI 岗位 API 类型和请求函数

**Files:**
- Modify: `surfaces/gui/src/api.ts`
- Create: `surfaces/gui/src/careerJobsApi.test.ts`

- [ ] **Step 1: 写失败测试**

mock `fetch` 并断言 `getCareerJobs()` 只发送非空筛选参数，`getCareerJob()` 对 ID 编码，`getCareerJobFilters()` 使用固定路径：

```typescript
await getCareerJobs({
  query: "大模型",
  companySlug: "deepseek",
  status: "active",
  limit: 20,
  offset: 0,
});
expect(fetch).toHaveBeenCalledWith(
  expect.stringContaining(
    "/v1/career/jobs?query=%E5%A4%A7%E6%A8%A1%E5%9E%8B&company_slug=deepseek",
  ),
);
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerJobsApi.test.ts
```

Expected: FAIL，请求函数不存在。

- [ ] **Step 3: 最小实现类型与请求函数**

在 `api.ts` 增加：

```typescript
export interface CareerJobSummary { ... }
export interface CareerJobDetail extends CareerJobSummary {
  description_raw: string;
  responsibilities: string[];
  requirements: string[];
  versions: CareerJobVersion[];
  events: CareerJobEvent[];
}
export interface CareerJobFilters { ... }
export async function getCareerJobs(filters: CareerJobQuery): Promise<CareerJobsResult>
export async function getCareerJob(jobId: string): Promise<CareerJobResult>
export async function getCareerJobFilters(): Promise<CareerJobFiltersResult>
```

使用 `URLSearchParams`，不发送空字符串或 `undefined`。

- [ ] **Step 4: 运行测试确认转绿**

Run:

```bash
npm test -- --run src/careerJobsApi.test.ts
```

Expected: PASS。

### Task 3: 列表与详情同屏岗位页面

**Files:**
- Create: `surfaces/gui/src/components/CareerJobsView.tsx`
- Create: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [ ] **Step 1: 写初始加载失败测试**

mock API 返回两个岗位和筛选选项，断言默认请求状态为 `active`、显示总数并自动读取第一条详情：

```typescript
render(<CareerJobsView />);
expect(await screen.findByText("大模型算法工程师")).toBeTruthy();
expect(api.getCareerJobs).toHaveBeenCalledWith(
  expect.objectContaining({ status: "active", limit: 20, offset: 0 }),
);
expect(api.getCareerJob).toHaveBeenCalledWith("job-1");
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
npm test -- --run src/components/CareerJobsView.test.tsx
```

Expected: FAIL，组件不存在。

- [ ] **Step 3: 实现最小同屏骨架**

组件维护：

```typescript
const [query, setQuery] = useState("");
const [companySlug, setCompanySlug] = useState("");
const [location, setLocation] = useState("");
const [recruitmentType, setRecruitmentType] = useState("");
const [status, setStatus] = useState("active");
const [offset, setOffset] = useState(0);
const [selectedId, setSelectedId] = useState("");
```

顶部渲染搜索框和四个中文下拉框；主体使用 `grid-cols-[minmax(300px,38%)_1fr]`；列表成功后选择首条并按 ID 读取详情。

- [ ] **Step 4: 写筛选、选择和分页失败测试**

断言：

- 提交关键词后 offset 重置为 0。
- 选择公司后重新查询。
- 点击第二条岗位调用 `getCareerJob("job-2")`。
- 下一页将 offset 改为 20。
- 最后一页禁用下一页。

- [ ] **Step 5: 最小实现交互**

筛选提交统一调用纯函数生成 `CareerJobQuery`。使用请求序号或 effect cleanup，防止较慢的旧请求覆盖新结果。详情失败只在右侧显示错误。

- [ ] **Step 6: 写详情与空状态失败测试**

断言职责、要求、完整 JD、版本、事件、HTTP 官方链接和中文空状态；`manual://` 不显示“查看官网”。

- [ ] **Step 7: 完成详情与状态渲染**

增加中文映射：

```typescript
const JOB_STATUS = { active: "在招中", inactive: "已下线" };
const RECRUITMENT_TYPE = {
  social: "社会招聘",
  campus: "校园招聘",
  internship: "实习",
};
```

未知枚举值显示原值，避免丢失业务信息。

- [ ] **Step 8: 运行组件测试确认转绿**

Run:

```bash
npm test -- --run src/components/CareerJobsView.test.tsx
```

Expected: PASS。

### Task 4: 岗位雷达一级入口和 App surface

**Files:**
- Modify: `surfaces/gui/src/components/Sidebar.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: 写 Sidebar 失败测试**

为 `baseProps` 增加 `onOpenCareerJobs` 和 `careerJobsActive`，断言：

```typescript
fireEvent.click(screen.getByTestId("nav-career-jobs"));
expect(baseProps.onOpenCareerJobs).toHaveBeenCalledOnce();
```

并断言“岗位雷达”位于“我的求职档案”之前。

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
npm test -- --run src/components/Sidebar.test.tsx
```

Expected: FAIL，入口不存在。

- [ ] **Step 3: 最小实现 Sidebar 和 App 接入**

`Sidebar.Props` 增加：

```typescript
onOpenCareerJobs: () => void;
careerJobsActive: boolean;
```

App surface union 增加 `"jobs"`；传入 `setSurface("jobs")`；在 profile 前渲染：

```tsx
{surface === "jobs" ? (
  <CareerJobsView />
) : surface === "profile" ? (
  <CareerProfileView onImportResume={openResumeImporter} />
) : ...}
```

- [ ] **Step 4: 运行 Sidebar 与岗位页面测试**

Run:

```bash
npm test -- --run src/components/Sidebar.test.tsx src/components/CareerJobsView.test.tsx
```

Expected: PASS。

### Task 5: 档案字段中文映射

**Files:**
- Create: `surfaces/gui/src/careerProfileFields.ts`
- Create: `surfaces/gui/src/careerProfileFields.test.ts`
- Modify: `surfaces/gui/src/components/CareerProfileView.tsx`
- Modify: `surfaces/gui/src/components/CareerProfileView.test.tsx`

- [ ] **Step 1: 写纯函数失败测试**

断言全部规格字段映射，并覆盖未知字段：

```typescript
expect(careerProfileFieldLabel("birth_date")).toBe("出生日期");
expect(careerProfileFieldLabel("degree")).toBe("学历");
expect(careerProfileFieldLabel("gpa")).toBe("GPA");
expect(careerProfileFieldLabel("custom_field")).toBe("custom field");
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```bash
npm test -- --run src/careerProfileFields.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 最小实现映射函数**

建立固定 `Record<string, string>`，未知字段使用：

```typescript
return key.trim().replace(/[_-]+/g, " ");
```

- [ ] **Step 4: 写组件失败测试**

扩充 profile fixture，包含 `birth_date`、`start_date`、`end_date`、`gpa`、`ranking`，断言中文标签存在，英文 snake_case 不存在。

- [ ] **Step 5: 接入递归渲染**

在 `FactValue` 的 `<dt>` 中调用 `careerProfileFieldLabel(key)`，不修改值。

- [ ] **Step 6: 运行字段和档案组件测试**

Run:

```bash
npm test -- --run src/careerProfileFields.test.ts src/components/CareerProfileView.test.tsx src/uiChineseAudit.test.ts
```

Expected: PASS。

### Task 6: 完整验收和记录

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: 后端全量相关测试**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py \
  tests/test_mcp.py \
  tests/test_builtin_personas.py
```

Expected: PASS，除既有 TestClient 弃用警告外无新增警告。

- [ ] **Step 2: GUI 全量测试和构建**

Run:

```bash
cd surfaces/gui
npm test
npm run build
```

Expected: PASS；允许既有动态/静态混合导入和大 chunk 警告。

- [ ] **Step 3: 静态检查**

Run:

```bash
git diff --check
```

Expected: 无输出，退出码 0。

- [ ] **Step 4: 浏览器验收**

验证：

- 左侧“岗位雷达”入口。
- 默认在招岗位和真实总数。
- 关键词、公司、城市、类型和状态筛选。
- 点击列表岗位后右侧详情更新。
- 官方链接、职责、要求、完整 JD、版本和事件。
- 档案基本信息和教育经历不再显示英文 snake_case 字段。
- 干净标签页控制台 0 error。

- [ ] **Step 5: 更新开发日志**

记录文件、验收项、测试数、构建结果、浏览器结果、剩余风险和下一最小任务。
