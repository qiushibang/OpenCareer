# 简历元数据与安全删除实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每份简历增加可编辑名称和目标岗位标签，并支持保留共享事实的单份安全删除。

**Architecture:** schema v5 在现有 `resume_imports` 增加轻量元数据和软删除标记。Repository 维护持久化和引用完整性，Service 负责输入规范化、精确确认和私有文件删除，FastAPI 提供薄 PATCH/DELETE 路由，GUI 在现有简历库页面增加编辑与删除弹窗。

**Tech Stack:** Python 3.12、SQLite、FastAPI、React 18、TypeScript、Vitest、Testing Library、pytest。

---

### Task 1: schema v5 迁移

**Files:**
- Modify: `extensions/career_mcp/database/migrations.py`
- Create: `extensions/career_mcp/tests/test_migrations.py`

- [ ] **Step 1: 写失败测试**

构造 schema v4 数据库，执行 `migrate()` 后断言：

```python
assert schema_version(connection) == 5
row = connection.execute(
    "SELECT display_name, target_roles_json, deleted_at FROM resume_imports"
).fetchone()
assert row["display_name"] == "resume.pdf"
assert row["target_roles_json"] == "[]"
assert row["deleted_at"] is None
```

- [ ] **Step 2: 运行红灯**

```bash
.venv/bin/python -m pytest -q extensions/career_mcp/tests/test_migrations.py
```

Expected: FAIL，字段不存在且 schema 仍为 4。

- [ ] **Step 3: 最小迁移**

将 `SCHEMA_VERSION` 改为 5，执行：

```sql
ALTER TABLE resume_imports ADD COLUMN display_name TEXT;
ALTER TABLE resume_imports ADD COLUMN target_roles_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE resume_imports ADD COLUMN deleted_at TEXT;
UPDATE resume_imports SET display_name = original_filename WHERE display_name IS NULL;
```

新建 schema v4 表定义保持不变，由 v5 迁移统一添加字段。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 2: 元数据 Repository 与 Service

**Files:**
- Modify: `extensions/career_mcp/database/resume_repository.py`
- Modify: `extensions/career_mcp/services/resumes.py`
- Modify: `extensions/career_mcp/tests/test_resume_repository.py`
- Modify: `extensions/career_mcp/tests/test_resume_service.py`

- [ ] **Step 1: 写失败测试**

断言列表和详情返回 `display_name`、`target_roles`，并验证：

```python
updated = service.update_resume_document(
    resume_id,
    display_name=" AI 产品经理简历 ",
    target_roles=["AI 产品经理", " AI 产品经理 ", "Agent 产品经理"],
)
assert updated["display_name"] == "AI 产品经理简历"
assert updated["target_roles"] == ["AI 产品经理", "Agent 产品经理"]
```

空名称、超过 80 字、超过 10 个标签、标签超过 30 字均返回 `INVALID_INPUT`。

- [ ] **Step 2: 运行红灯**

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_resume_repository.py \
  extensions/career_mcp/tests/test_resume_service.py
```

Expected: FAIL，更新方法和字段尚不存在。

- [ ] **Step 3: 最小实现**

Repository 的列表和详情排除 `deleted_at IS NOT NULL`，名称使用 `COALESCE(display_name, original_filename)`。新增：

```python
def update_resume_document_metadata(
    self,
    resume_id: str,
    *,
    display_name: str,
    target_roles: list[str],
    now: str,
) -> dict | None: ...
```

Service 增加确定性校验与去重，再调用 Repository。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 3: 单份安全删除

**Files:**
- Modify: `extensions/career_mcp/database/resume_repository.py`
- Modify: `extensions/career_mcp/services/resumes.py`
- Modify: `extensions/career_mcp/tests/test_resume_repository.py`
- Modify: `extensions/career_mcp/tests/test_resume_service.py`

- [ ] **Step 1: 写失败测试**

建立两份简历并确认事实，删除其中一份后断言：

```python
assert deleted["original_removed"] is True
assert service.list_resume_documents()[0]["id"] == other_id
assert candidate_fact_count > 0
assert profile_version_count > 0
assert deleted_import["extracted_text"] == ""
assert deleted_import["deleted_at"] is not None
assert deleted_preview_count == 0
```

确认名不一致返回 `CONFIRMATION_REQUIRED`。

- [ ] **Step 2: 运行红灯**

Run 同 Task 2 Step 2，Expected: FAIL，删除方法不存在。

- [ ] **Step 3: 最小实现**

Repository 新增 `soft_delete_resume_document()`：删除 previews，清空全文并写 `deleted_at`。Service 在事务前校验名称，事务提交后通过现有私有路径边界函数删除文件。

- [ ] **Step 4: 运行绿灯**

Run 同 Task 2 Step 2，Expected: PASS。

### Task 4: PATCH/DELETE HTTP API

**Files:**
- Modify: `coworker/server/app.py`
- Modify: `tests/test_career_profile_api.py`

- [ ] **Step 1: 写失败测试**

验证：

```python
patched = client.patch(
    f"/v1/career/resumes/{resume_id}",
    json={"display_name": "产品简历", "target_roles": ["AI 产品经理"]},
)
deleted = client.request(
    "DELETE",
    f"/v1/career/resumes/{resume_id}",
    json={"confirm_name": "产品简历"},
)
```

并断言非法输入 400、错误确认 409、删除后详情 404、共享 profile 仍为 200。

- [ ] **Step 2: 运行红灯**

```bash
.venv/bin/python -m pytest -q tests/test_career_profile_api.py
```

Expected: FAIL，新方法路由不存在。

- [ ] **Step 3: 最小实现**

添加 PATCH 和 DELETE 路由。`career_resume_error()` 将 `INVALID_INPUT` 映射 400，`RESUME_NOT_FOUND` 映射 404，其余业务冲突映射 409。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 5: GUI 编辑元数据

**Files:**
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/components/CareerProfileView.tsx`
- Modify: `surfaces/gui/src/components/CareerProfileView.test.tsx`

- [ ] **Step 1: 写失败测试**

模拟 `updateCareerResume()`，点击“编辑信息”，填写名称和逗号分隔标签并保存，断言：

```typescript
expect(api.updateCareerResume).toHaveBeenCalledWith("resume-1", {
  displayName: "AI 产品经理简历",
  targetRoles: ["AI 产品经理", "Agent 产品经理"],
});
expect(await screen.findByText("AI 产品经理简历")).toBeTruthy();
```

- [ ] **Step 2: 运行红灯**

```bash
cd surfaces/gui
npm test -- --run src/components/CareerProfileView.test.tsx
```

Expected: FAIL，编辑按钮与 API 不存在。

- [ ] **Step 3: 最小实现**

扩展 `CareerResumeSummary`，新增 PATCH 请求函数。在页面加入编辑弹窗，前端只做输入拆分，最终校验以后端为准。

- [ ] **Step 4: 运行绿灯**

Run 同 Step 2，Expected: PASS。

### Task 6: GUI 单份删除

**Files:**
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/components/CareerProfileView.tsx`
- Modify: `surfaces/gui/src/components/CareerProfileView.test.tsx`

- [ ] **Step 1: 写失败测试**

选择第一份简历，点击“删除此简历”，输入当前名称，断言调用 DELETE；成功后第一份从列表移除并自动选中第二份。

- [ ] **Step 2: 运行红灯**

Run 同 Task 5 Step 2，Expected: FAIL，单份删除交互不存在。

- [ ] **Step 3: 最小实现**

新增 `deleteCareerResume(resumeId, confirmName)`。删除弹窗明确“共享事实会保留”；成功后更新本地列表并选择相邻简历。

- [ ] **Step 4: 运行绿灯**

Run 同 Task 5 Step 2，Expected: PASS。

### Task 7: 全量验收与记录

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

- [ ] **Step 2: GUI 回归与构建**

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

在真实简历上打开编辑和删除弹窗，验证现有名称、标签输入、精确确认和中文提示；不提交真实删除。使用隔离测试数据库验证实际文件删除和事实保留。

- [ ] **Step 5: 更新日志**

记录 schema v5、API、GUI、测试数量、真实验收和保留风险。
