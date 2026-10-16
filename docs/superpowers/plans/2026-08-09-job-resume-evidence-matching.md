# 岗位与简历证据匹配闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在岗位详情中选择 1–5 份已确认简历，生成可追溯的要求证据矩阵、多简历比较和 Markdown 申请准备包。

**Architecture:** 匹配规则放在无数据库、无模型的纯 Domain 模块；MatchService 组合现有 JobRepository、ResumeRepository 与独立 MatchRepository；HTTP 供 GUI 直接浏览，MCP 复用同一 Service 供 Career Agent 生成交付物。匹配快照以岗位 content hash 和简历 import revision 标识版本，不输出录用概率或总百分比。

**Tech Stack:** Python 3.12、SQLite、FastAPI、FastMCP、React 18、TypeScript、Vitest、Testing Library、pytest。

---

## 文件边界

**新增文件**

- `extensions/career_mcp/domain/matching.py`：要求分类、术语归一化、非敏感证据展开、单简历匹配和稳定排序。
- `extensions/career_mcp/database/match_repository.py`：匹配快照的幂等写入和最近结果读取。
- `extensions/career_mcp/services/matches.py`：输入校验、Repository 组合、事务和 stale 状态。
- `extensions/career_mcp/tests/test_matching.py`：纯函数行为测试。
- `extensions/career_mcp/tests/test_match_repository.py`：schema v6 与快照持久化测试。
- `extensions/career_mcp/tests/test_match_service.py`：单简历、多简历、幂等和 stale 测试。
- `surfaces/gui/src/components/CareerJobMatchPanel.tsx`：简历选择、证据矩阵和多简历对比。
- `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`：GUI 交互测试。

**修改文件**

- `extensions/career_mcp/database/migrations.py`：schema v6。
- `extensions/career_mcp/database/repository.py`：提供岗位匹配输入。
- `extensions/career_mcp/database/resume_repository.py`：提供简历匹配输入；全量删除时先清理快照。
- `extensions/career_mcp/server.py`：注册 `match_job_to_profile`。
- `.coworker/skills/career-application-packet/SKILL.md`：约束申请准备包流程。
- `coworker/server/app.py`：匹配 HTTP API 和中文错误。
- `tests/test_career_jobs_api.py`：HTTP 契约。
- `extensions/career_mcp/tests/test_resume_service.py`：全量删除回归。
- `surfaces/gui/src/api.ts`：匹配类型和请求函数。
- `surfaces/gui/src/components/CareerJobsView.tsx`：挂载匹配面板。
- `surfaces/gui/src/components/CareerJobsView.test.tsx`：岗位页集成。
- `surfaces/gui/src/App.tsx`：将申请准备请求预填到新的 Career 会话。
- `tests/test_mcp.py`：MCP 工具发现。
- `docs/11_DEVELOPMENT_LOG.md`、`docs/12_TONIGHT_PROGRESS.md`：验收记录。

## Task 0：冻结当前基线

**Files:**

- Read: `git status --short`
- Test: `extensions/career_mcp/tests`
- Test: `tests/test_career_jobs_api.py`
- Test: `tests/test_career_profile_api.py`
- Test: `surfaces/gui/src`

- [ ] **Step 1: 记录当前工作树边界**

Run:

```bash
git status --short
git diff --check
git log -3 --oneline
```

Expected: `git diff --check` 无输出；设计提交 `29c89b7` 存在。不得 reset、clean 或提交 `.local-state`、`career/`、私有简历、临时截图。

- [ ] **Step 2: 运行后端基线**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py \
  tests/test_mcp.py \
  tests/test_builtin_personas.py
```

Expected: 至少 227 passed；只有已知 Starlette/httpx 弃用警告。

- [ ] **Step 3: 运行 GUI 基线**

Run:

```bash
cd surfaces/gui
npm test
npm run build
```

Expected: 至少 150 passed；build 成功，允许既有混合导入和大 chunk 警告。

- [ ] **Step 4: 建立实现检查点**

当前工作树包含此前已验证但未统一提交的改动。后续只对本计划列出的文件进行精准编辑；每个 Gate 使用测试结果和 `git diff --check` 作为检查点，不批量提交未知文件。

## Task 1：确定性证据匹配 Domain

**Files:**

- Create: `extensions/career_mcp/domain/matching.py`
- Create: `extensions/career_mcp/tests/test_matching.py`

- [ ] **Step 1: 写要求分类和术语提取红灯**

```python
from extensions.career_mcp.domain.matching import (
    classify_requirement,
    extract_terms,
)


def test_classifies_requirements_conservatively():
    assert classify_requirement("必须熟练使用 Python") == "hard"
    assert classify_requirement("有 RAG 项目经验优先") == "preferred"
    assert classify_requirement("了解产品需求分析") == "unspecified"


def test_extracts_only_explicit_terms_and_aliases():
    assert extract_terms("熟悉 LLM、RAG 和 Python") == [
        "大模型",
        "rag",
        "python",
    ]
    assert extract_terms("沟通能力强") == []
```

- [ ] **Step 2: 运行红灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_matching.py
```

Expected: FAIL，`matching` 模块不存在。

- [ ] **Step 3: 实现分类、关键词表和别名**

```python
HARD_MARKERS = ("必须", "要求", "至少", "熟练", "精通", "must", "required")
PREFERRED_MARKERS = ("优先", "加分", "preferred", "plus", "bonus")
ALIASES = {
    "llm": "大模型",
    "大语言模型": "大模型",
    "agent": "智能体",
    "检索增强生成": "rag",
}
CHINESE_TERMS = (
    "自然语言处理",
    "检索增强生成",
    "需求分析",
    "项目管理",
    "数据分析",
    "机器学习",
    "深度学习",
    "知识图谱",
    "推荐系统",
    "大模型",
    "智能体",
    "产品",
    "搜索",
    "后端",
    "前端",
    "全栈",
    "算法",
    "本科",
    "硕士",
    "博士",
)


def classify_requirement(text: str) -> str:
    lowered = text.casefold()
    if any(marker in lowered for marker in PREFERRED_MARKERS):
        return "preferred"
    if any(marker in lowered for marker in HARD_MARKERS):
        return "hard"
    return "unspecified"
```

`extract_terms()` 必须保持首次出现顺序、别名归一化和去重；不使用 fuzzy matching。

- [ ] **Step 4: 写敏感字段和证据状态红灯**

```python
from extensions.career_mcp.domain.matching import (
    build_evidence_entries,
    match_requirement,
)


def test_evidence_entries_exclude_sensitive_basic_fields():
    entries = build_evidence_entries(
        {
            "basic": {
                "phone": "13800001234",
                "email": "secret@example.com",
                "birth_date": "2000-01-01",
                "summary": "AI 产品经理",
            },
            "project": [
                {"name": "知识库", "highlights": ["使用 RAG 和 Python"]}
            ],
            "education": [],
            "experience": [],
            "skill": [{"name": "Python"}],
        }
    )
    corpus = str(entries)
    assert "13800001234" not in corpus
    assert "secret@example.com" not in corpus
    assert "2000-01-01" not in corpus
    assert "AI 产品经理" in corpus


def test_requirement_match_has_direct_related_and_none_states():
    entries = build_evidence_entries(
        {
            "basic": {"summary": ""},
            "education": [],
            "experience": [],
            "project": [
                {"highlights": ["使用 RAG 构建知识库"]},
                {"highlights": ["使用 Python 开发数据管道"]},
            ],
            "skill": [{"name": "Python"}],
        }
    )
    assert match_requirement("熟悉 Python", entries)["status"] == "direct"
    assert (
        match_requirement("熟悉 Python 和 RAG", entries)["status"]
        == "related"
    )
    assert match_requirement("熟悉 Go", entries)["status"] == "none"
```

- [ ] **Step 5: 实现证据展开和单要求匹配**

`build_evidence_entries()` 只遍历 `education`、`experience`、`project`、`skill` 和 `basic.summary`；每个字符串返回 `section`、JSON `path`、`excerpt`、`terms` 和 `skill_name`。

`match_requirement()`：

```python
def match_requirement(requirement: str, entries: list[dict]) -> dict:
    terms = extract_terms(requirement)
    category = classify_requirement(requirement)
    candidates = []
    for entry in entries:
        matched = [term for term in terms if term in entry["terms"]]
        if matched:
            candidates.append({**entry, "matched_terms": matched})
    if not terms or not candidates:
        status = "none"
        candidates = []
    elif any(len(item["matched_terms"]) == len(terms) for item in candidates):
        status = "direct"
    else:
        status = "related"
    return {
        "requirement": requirement,
        "category": category,
        "terms": terms,
        "status": status,
        "evidence": candidates,
    }
```

- [ ] **Step 6: 写并实现稳定多简历排序**

测试相同统计返回并列；否则按 `hard_direct`、`direct`、`related`、`target_role_overlap` 降序。排序结果返回 `recommended_resume_ids`，不得用名称或时间打破并列。

- [ ] **Step 7: 运行 Domain 绿灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_matching.py
```

Expected: PASS。

## Task 2：schema v6 与匹配快照 Repository

**Files:**

- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/database/repository.py`
- Modify: `extensions/career_mcp/database/resume_repository.py`
- Create: `extensions/career_mcp/database/match_repository.py`
- Create: `extensions/career_mcp/tests/test_match_repository.py`
- Modify: `extensions/career_mcp/tests/test_migrations.py`

- [ ] **Step 1: 写 schema v6 红灯**

```python
def test_schema_v6_adds_job_resume_match_snapshots(tmp_path):
    connection = connect(tmp_path / "career.sqlite3")
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert schema_version(connection) == 6
    assert "job_resume_matches" in tables
    connection.close()
```

- [ ] **Step 2: 运行迁移红灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_migrations.py
```

Expected: FAIL，schema version 仍为 5。

- [ ] **Step 3: 实现 schema v6**

将 `SCHEMA_VERSION` 改为 6，并在 v6 migration 创建：

```sql
CREATE TABLE job_resume_matches (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    resume_import_id TEXT NOT NULL REFERENCES resume_imports(id),
    job_content_hash TEXT NOT NULL,
    resume_revision_at TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(
        job_id,
        resume_import_id,
        job_content_hash,
        resume_revision_at
    )
);
CREATE INDEX job_resume_matches_job
    ON job_resume_matches(job_id, created_at DESC);
```

写入 `schema_migrations(version=6)`，再更新 `PRAGMA user_version`。

- [ ] **Step 4: 写 Repository 幂等红灯**

```python
def test_match_snapshot_is_idempotent_and_keeps_old_revisions(tmp_path):
    repository = MatchRepository(connection)
    first = repository.save_snapshot(
        job_id=job_id,
        resume_id=resume_id,
        job_content_hash="job-v1",
        resume_revision_at="2026-08-09T01:00:00Z",
        result={"summary": {"direct": 1}},
        now="2026-08-09T02:00:00Z",
    )
    duplicate = repository.save_snapshot(
        job_id=job_id,
        resume_id=resume_id,
        job_content_hash="job-v1",
        resume_revision_at="2026-08-09T01:00:00Z",
        result={"summary": {"direct": 1}},
        now="2026-08-09T03:00:00Z",
    )
    changed = repository.save_snapshot(
        job_id=job_id,
        resume_id=resume_id,
        job_content_hash="job-v2",
        resume_revision_at="2026-08-09T01:00:00Z",
        result={"summary": {"direct": 2}},
        now="2026-08-09T04:00:00Z",
    )
    assert duplicate["id"] == first["id"]
    assert changed["id"] != first["id"]
```

- [ ] **Step 5: 实现 `MatchRepository`**

提供：

```python
import json
import sqlite3
from uuid import uuid4


class MatchRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def save_snapshot(
        self,
        *,
        job_id: str,
        resume_id: str,
        job_content_hash: str,
        resume_revision_at: str,
        result: dict,
        now: str,
    ) -> dict:
        row = self.connection.execute(
            """
            SELECT *
            FROM job_resume_matches
            WHERE job_id = ?
              AND resume_import_id = ?
              AND job_content_hash = ?
              AND resume_revision_at = ?
            """,
            (
                job_id,
                resume_id,
                job_content_hash,
                resume_revision_at,
            ),
        ).fetchone()
        if row is None:
            snapshot_id = str(uuid4())
            self.connection.execute(
                """
                INSERT INTO job_resume_matches(
                    id, job_id, resume_import_id, job_content_hash,
                    resume_revision_at, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    job_id,
                    resume_id,
                    job_content_hash,
                    resume_revision_at,
                    json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    now,
                ),
            )
            row = self.connection.execute(
                "SELECT * FROM job_resume_matches WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
        return self._snapshot(row)

    def list_job_snapshots(self, job_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM job_resume_matches
            WHERE job_id = ?
            ORDER BY created_at DESC, id ASC
            """,
            (job_id,),
        ).fetchall()
        return [self._snapshot(row) for row in rows]

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> dict:
        return {
            "id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "resume_id": str(row["resume_import_id"]),
            "job_content_hash": str(row["job_content_hash"]),
            "resume_revision_at": str(row["resume_revision_at"]),
            "result": json.loads(row["result_json"]),
            "created_at": str(row["created_at"]),
        }
```

JSON 使用 `ensure_ascii=False`、稳定 key 排序和紧凑分隔符。幂等命中时返回原始快照，不覆盖历史 JSON。

- [ ] **Step 6: 增加专用匹配输入**

`JobRepository.get_job_match_input(job_id)` 返回：

```python
{
    "id": str(row["id"]),
    "title": row["title"],
    "company": {"slug": row["company_slug"], "name": row["company_name"]},
    "status": row["status"],
    "source_url": row["canonical_url"],
    "content_hash": row["content_hash"],
    "requirements": json.loads(row["requirements_json"]),
}
```

`ResumeRepository.get_resume_match_input(resume_id)` 返回：

```python
{
    "id": str(row["id"]),
    "display_name": str(row["display_name"] or row["original_filename"]),
    "target_roles": json.loads(row["target_roles_json"]),
    "revision_at": str(row["updated_at"]),
    "sections": confirmed_sections_only,
}
```

查询必须要求 `deleted_at IS NULL` 和确认状态。

- [ ] **Step 7: 保护全量删除**

在 `ResumeRepository.delete_all()` 的计数中增加 `matches`，并在删除 `resume_imports` 前执行：

```python
self.connection.execute("DELETE FROM job_resume_matches")
```

- [ ] **Step 8: 运行 Repository 绿灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_match_repository.py \
  extensions/career_mcp/tests/test_resume_repository.py
```

Expected: PASS。

## Task 3：MatchService、原子批量分析与 stale

**Files:**

- Create: `extensions/career_mcp/services/matches.py`
- Create: `extensions/career_mcp/tests/test_match_service.py`

- [ ] **Step 1: 写输入校验红灯**

```python
@pytest.mark.parametrize(
    "resume_ids",
    [[], ["one", "one"], [str(index) for index in range(6)]],
)
def test_match_service_rejects_invalid_resume_selection(
    seeded_service,
    resume_ids,
):
    with pytest.raises(MatchServiceError) as error:
        seeded_service.analyze("job-1", resume_ids)
    assert error.value.code == "INVALID_INPUT"
```

同时覆盖 `JOB_NOT_FOUND`、`RESUME_NOT_FOUND` 和无 requirements 的 `INSUFFICIENT_JOB_DATA`。

- [ ] **Step 2: 运行 Service 红灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_match_service.py
```

Expected: FAIL，`MatchService` 不存在。

- [ ] **Step 3: 实现 Service 错误与校验**

```python
class MatchServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_resume_ids(resume_ids: list[str]) -> list[str]:
    if not isinstance(resume_ids, list):
        raise MatchServiceError("INVALID_INPUT", "resume_ids must be a list")
    if not 1 <= len(resume_ids) <= 5:
        raise MatchServiceError(
            "INVALID_INPUT",
            "resume_ids must contain between 1 and 5 ids",
        )
    if not all(isinstance(value, str) and value.strip() for value in resume_ids):
        raise MatchServiceError("INVALID_INPUT", "resume ids must be strings")
    normalized = [value.strip() for value in resume_ids]
    if len(set(normalized)) != len(normalized):
        raise MatchServiceError("INVALID_INPUT", "resume ids must be unique")
    return normalized
```

- [ ] **Step 4: 写单简历和多简历红灯**

断言 `analyze()` 返回的稳定字段：

```python
result = service.analyze(job_id, [resume_id])
assert result["job"] == {
    "id": job_id,
    "title": "大模型算法工程师",
    "company": {"slug": "deepseek", "name": "DeepSeek"},
    "status": "active",
    "source_url": "https://careers.deepseek.com/jobs/one",
    "content_hash": "job-hash-1",
}
assert isinstance(result["results"][0]["snapshot_id"], str)
assert result["results"][0]["snapshot_status"] == "fresh"
assert result["results"][0]["resume"] == {
    "id": resume_id,
    "display_name": "算法简历",
    "target_roles": ["大模型算法工程师"],
}
assert result["results"][0]["requirements"][0]["status"] == "direct"
assert result["results"][0]["summary"] == {
    "hard_direct": 1,
    "direct": 1,
    "related": 0,
    "none": 0,
    "target_role_overlap": True,
}
assert result["comparison"] == {
    "recommended_resume_ids": [resume_id],
    "ranking": [resume_id],
}
```

- [ ] **Step 5: 实现原子分析**

`MatchService.analyze(job_id, resume_ids)` 使用一个 SQLite connection：

1. 先读取岗位和所有简历；任一缺失立即失败。
2. 在内存中计算所有结果。
3. `BEGIN` 后保存所有快照。
4. 任一写入失败时 rollback，不返回部分结果。
5. commit 后返回统一比较结果。

- [ ] **Step 6: 写并实现 stale 读取**

`list_latest(job_id)` 读取历史快照，再比较当前：

```python
if resume is None:
    status = "unavailable_resume"
elif snapshot["job_content_hash"] != job["content_hash"]:
    status = "stale_job"
elif snapshot["resume_revision_at"] != resume["revision_at"]:
    status = "stale_resume"
else:
    status = "fresh"
```

测试分别修改岗位 hash、简历 revision 和 `deleted_at`。

- [ ] **Step 7: 运行 Service 绿灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_matching.py \
  extensions/career_mcp/tests/test_match_repository.py \
  extensions/career_mcp/tests/test_match_service.py
```

Expected: PASS。

## Task 4：HTTP API

**Files:**

- Modify: `coworker/server/app.py`
- Modify: `tests/test_career_jobs_api.py`

- [ ] **Step 1: 写 POST/GET 红灯**

扩展测试 fixture，创建一份已确认简历：

```python
created = client.post(
    f"/v1/career/jobs/{job_id}/matches",
    json={"resume_ids": [resume_id]},
)
latest = client.get(f"/v1/career/jobs/{job_id}/matches")

assert created.status_code == 200
assert created.json()["matches"]["results"][0]["snapshot_status"] == "fresh"
assert latest.status_code == 200
assert latest.json()["matches"][0]["snapshot_status"] == "fresh"
assert "phone" not in str(created.json())
assert "private_path" not in str(created.json())
```

覆盖空列表 400、岗位 404、简历 404、无要求 409。

- [ ] **Step 2: 运行 API 红灯**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_career_jobs_api.py
```

Expected: FAIL，路由 404/405。

- [ ] **Step 3: 增加薄路由和错误映射**

新增 `career_match_service()` 和 `career_match_error()`。状态映射：

```python
{
    "INVALID_INPUT": 400,
    "JOB_NOT_FOUND": 404,
    "RESUME_NOT_FOUND": 404,
    "INSUFFICIENT_JOB_DATA": 409,
    "PERSISTENCE_ERROR": 409,
}
```

路由：

```python
@app.post("/v1/career/jobs/{job_id}/matches")
def career_job_matches_post(job_id: str, body: dict):
    try:
        result = career_match_service().analyze(
            job_id,
            (body or {}).get("resume_ids", []),
        )
        return {"ok": True, "matches": result}
    except Exception as exc:
        return career_match_error(exc)


@app.get("/v1/career/jobs/{job_id}/matches")
def career_job_matches_get(job_id: str):
    try:
        return {
            "ok": True,
            "matches": career_match_service().list_latest(job_id),
        }
    except Exception as exc:
        return career_match_error(exc)
```

这些路由必须定义在 `/v1/career/jobs/{job_id}` 通用详情路由前，避免 `matches` 被错误解析为 job ID。

- [ ] **Step 4: 运行 API 绿灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py
```

Expected: PASS。

## Task 5：GUI 单简历证据矩阵与多简历比较

**Files:**

- Modify: `surfaces/gui/src/api.ts`
- Create: `surfaces/gui/src/components/CareerJobMatchPanel.tsx`
- Create: `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.tsx`
- Modify: `surfaces/gui/src/components/CareerJobsView.test.tsx`

- [ ] **Step 1: 定义 API 类型**

```typescript
export type CareerEvidenceStatus = "direct" | "related" | "none";
export type CareerRequirementCategory = "hard" | "preferred" | "unspecified";

export interface CareerRequirementMatch {
  requirement: string;
  category: CareerRequirementCategory;
  terms: string[];
  status: CareerEvidenceStatus;
  evidence: {
    section: string;
    path: string;
    excerpt: string;
    matched_terms: string[];
  }[];
}

export interface CareerResumeMatchResult {
  snapshot_id: string;
  snapshot_status:
    | "fresh"
    | "stale_job"
    | "stale_resume"
    | "unavailable_resume";
  resume: {
    id: string;
    display_name: string;
    target_roles: string[];
  };
  requirements: CareerRequirementMatch[];
  summary: {
    hard_direct: number;
    direct: number;
    related: number;
    none: number;
    target_role_overlap: boolean;
  };
}
```

增加：

```typescript
export async function createCareerJobMatches(
  jobId: string,
  resumeIds: string[],
): Promise<CareerJobMatchesResult> {
  const res = await fetch(
    `${httpBase()}/v1/career/jobs/${encodeURIComponent(jobId)}/matches`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_ids: resumeIds }),
    },
  );
  return res.json();
}

export async function getCareerJobMatches(
  jobId: string,
): Promise<CareerJobMatchesResult> {
  const res = await fetch(
    `${httpBase()}/v1/career/jobs/${encodeURIComponent(jobId)}/matches`,
  );
  return res.json();
}
```

- [ ] **Step 2: 写简历选择红灯**

```typescript
it("selects one to five resumes before matching", async () => {
  api.getCareerResumes.mockResolvedValue({ ok: true, resumes });
  api.createCareerJobMatches.mockResolvedValue(singleMatchResponse);

  render(<CareerJobMatchPanel job={job} onGeneratePacket={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "匹配简历" }));
  fireEvent.click(screen.getByLabelText("算法简历"));
  fireEvent.click(screen.getByRole("button", { name: "开始分析" }));

  await waitFor(() =>
    expect(api.createCareerJobMatches).toHaveBeenCalledWith(
      "job-1",
      ["resume-1"],
    ),
  );
});
```

- [ ] **Step 3: 运行 GUI 红灯**

Run:

```bash
cd surfaces/gui
npm test -- --run src/components/CareerJobMatchPanel.test.tsx
```

Expected: FAIL，组件不存在。

- [ ] **Step 4: 实现选择弹窗**

`CareerJobMatchPanel`：

- 打开时调用 `getCareerResumes()`。
- 0 份时显示“前往我的求职档案导入简历”。
- checkbox 显示名称、格式、标签。
- 第 6 个选择在前端禁止，后端仍做最终校验。
- 点击开始后调用 POST，失败显示后端中文消息。

- [ ] **Step 5: 写证据矩阵红灯**

断言页面使用：

```typescript
const STATUS_LABELS = {
  direct: "有直接证据",
  related: "有相关证据",
  none: "暂无已确认佐证",
};
const CATEGORY_LABELS = {
  hard: "硬性要求",
  preferred: "优先项",
  unspecified: "未分类要求",
};
```

并验证手机号、邮箱和 `private_path` 不出现在 DOM。

- [ ] **Step 6: 实现单简历结果**

按 category 分组；每条要求显示状态、证据 section 中文名、excerpt 和 matched terms。stale 状态显示“内容已变化，请重新分析”及“重新分析”按钮。

- [ ] **Step 7: 写并实现多简历比较**

测试两份简历时显示：

- 每份简历的 `hard_direct/direct/related/none`。
- 推荐文案“可引用证据更充分”。
- `recommended_resume_ids` 多于一个时显示“并列推荐”。
- 展开按钮可查看每份完整矩阵。

- [ ] **Step 8: 挂载岗位详情**

在 `CareerJobsView` 详情头部挂载：

```tsx
<CareerJobMatchPanel
  job={detail}
  onGeneratePacket={onGeneratePacket}
/>
```

`CareerJobsView` 新增可选 prop：

```typescript
onGeneratePacket?: (payload: {
  jobId: string;
  resumeIds: string[];
  snapshotIds: string[];
}) => void;
```

- [ ] **Step 9: 运行 GUI 绿灯**

Run:

```bash
cd surfaces/gui
npm test -- --run \
  src/components/CareerJobMatchPanel.test.tsx \
  src/components/CareerJobsView.test.tsx
npm run build
```

Expected: PASS，build 成功。

## Task 6：MCP 与申请准备包

**Files:**

- Modify: `extensions/career_mcp/server.py`
- Modify: `tests/test_mcp.py`
- Modify: `.coworker/skills/career-application-packet/SKILL.md`
- Modify: `surfaces/gui/src/App.tsx`
- Modify: `surfaces/gui/src/components/CareerJobMatchPanel.test.tsx`

- [ ] **Step 1: 写 MCP 红灯**

新增直接工具测试：

```python
def test_match_job_to_profile_uses_shared_match_service(monkeypatch):
    monkeypatch.setattr(
        career_server,
        "_match_service",
        lambda: SimpleNamespace(
            analyze=lambda job_id, resume_ids: {
                "job": {"id": job_id},
                "results": [{"resume": {"id": resume_ids[0]}}],
            }
        ),
    )
    result = career_server.match_job_to_profile("job-1", ["resume-1"])
    assert result["ok"] is True
    assert result["results"][0]["resume"]["id"] == "resume-1"
```

工具发现断言包含 `match_job_to_profile`。

- [ ] **Step 2: 运行 MCP 红灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py
```

Expected: FAIL，新工具不存在。

- [ ] **Step 3: 实现并注册 MCP 工具**

```python
def _match_service() -> MatchService:
    return MatchService()


def match_job_to_profile(job_id: str, resume_ids: list[str]) -> dict:
    """Return traceable evidence matches for confirmed resume documents."""
    try:
        return _ok(_match_service().analyze(job_id, resume_ids))
    except MatchServiceError as exc:
        return _error(exc.code, str(exc))
    except sqlite3.Error:
        return _error(
            "PERSISTENCE_ERROR",
            "Career database operation failed.",
            retryable=True,
        )
```

在现有注册区执行：

```python
mcp.tool()(match_job_to_profile)
```

- [ ] **Step 4: 收紧 application packet Skill**

Skill 必须明确：

1. 先调用 `get_candidate_profile`。
2. 再调用 `match_job_to_profile(job_id, resume_ids)`。
3. 只引用工具返回的 requirement、evidence excerpt、官方 URL 和版本。
4. 固定输出八个规格章节。
5. 不重新评分、不补写经历、不自动投递。

- [ ] **Step 5: 写 GUI 预填红灯**

点击“生成申请准备包”后断言 callback 收到：

```typescript
{
  jobId: "job-1",
  resumeIds: ["resume-1"],
  snapshotIds: ["snapshot-1"],
}
```

- [ ] **Step 6: 实现 App 会话交接**

在 App 中：

```typescript
const prepareApplicationPacket = (payload: {
  jobId: string;
  resumeIds: string[];
  snapshotIds: string[];
}) => {
  startNewSession("career");
  prefillComposer(
    [
      "请使用 career-application-packet Skill 生成申请准备包。",
      `job_id=${payload.jobId}`,
      `resume_ids=${payload.resumeIds.join(",")}`,
      `match_snapshot_ids=${payload.snapshotIds.join(",")}`,
      "只使用 Career MCP 返回的岗位事实和已确认简历证据，不要编造经历。",
    ].join("\n"),
  );
};
```

传入：

```tsx
<CareerJobsView onGeneratePacket={prepareApplicationPacket} />
```

用户仍需检查预填内容并点击发送；GUI 不自动触发模型或写文件。

- [ ] **Step 7: 运行 MCP/Skill/GUI 绿灯**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_mcp.py \
  tests/test_skills.py
cd surfaces/gui
npm test -- --run \
  src/components/CareerJobMatchPanel.test.tsx
```

Expected: PASS。

## Task 7：全量验收、真实申请包与日志

**Files:**

- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`
- Create: `artifacts/application-packets/<company>-<job>-<date>.md`

- [ ] **Step 1: 后端回归**

Run:

```bash
.venv/bin/python -m pytest -q \
  extensions/career_mcp/tests \
  tests/test_career_jobs_api.py \
  tests/test_career_profile_api.py \
  tests/test_mcp.py \
  tests/test_skills.py \
  tests/test_builtin_personas.py
```

Expected: 全部通过；只允许已知 TestClient 弃用警告。

- [ ] **Step 2: GUI 回归与构建**

Run:

```bash
cd surfaces/gui
npm test
npm run build
```

Expected: 全部通过；只允许既有混合导入和大 chunk 警告。

- [ ] **Step 3: 静态与数据库检查**

Run:

```bash
git diff --check
.venv/bin/python - <<'PY'
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.migrations import connect, schema_version

connection = connect(CareerConfig.from_env().database_path)
print({"schema": schema_version(connection)})
print({"foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall())})
connection.close()
PY
```

Expected: schema 6，foreign key errors 0。

- [ ] **Step 4: 浏览器只读验收**

使用真实岗位和真实简历验证：

1. 打开匹配弹窗。
2. 选择一份简历并查看 direct/related/none。
3. 选择多份简历并查看推荐或并列。
4. 确认 DOM 不显示手机号、邮箱和私人路径。
5. 打开申请准备包预填，但不自动发送。
6. 浏览器控制台无新的应用错误。

- [ ] **Step 5: 生成真实 Markdown**

在 Career 会话中发送预填请求，批准正常工作区写入，确认 artifact 包含八个固定章节、官方 URL、岗位 ID、简历名称、snapshot ID，并逐条抽查证据可回溯。

- [ ] **Step 6: 对抗性代码审查**

审查范围固定为本计划新增/修改的匹配功能代码，不审查历史 Markdown、配置和无关 GUI 中文化 diff。重点挑战：

- 敏感字段是否能进入匹配响应。
- 删除简历和全量删除是否破坏外键。
- 多简历请求是否可能部分提交。
- stale 状态是否可能把旧结果标为 fresh。
- 无关键词要求是否被错误判为 direct。
- API 路由顺序是否产生 `/matches` 路由冲突。
- GUI 是否能绕过 1–5 份限制。
- Agent 是否能绕过证据矩阵自行编造。

发现 critical/major 问题时先补红灯、修复并重跑全部回归，再重新审查。

- [ ] **Step 7: 更新日志**

记录：

- schema v6 和新文件。
- HTTP/MCP/GUI 验收项。
- 测试数量、build 和浏览器结果。
- 对抗审查发现及修复。
- 未实现项：申请跟踪、自动改写、自动投递、向量推荐。

## 执行策略

用户已明确要求开始开发并授权自主推进，采用当前会话内联执行。每个 Task 严格遵循：

```text
写行为测试 → 观察预期失败 → 最小实现 → 聚焦转绿 → 扩大回归
```

Gate 1 未通过不进入多简历比较；Gate 2 未通过不进入 MCP/申请包；任何对抗审查确认的 critical/major 问题未修复时不得交付。
