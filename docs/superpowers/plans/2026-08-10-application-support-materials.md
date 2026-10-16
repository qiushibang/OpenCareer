# Application Support Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing validated application packet with an evidence-bound self-introduction, referral/HR messages, and a deterministic application checklist.

**Architecture:** Keep `ApplicationPacketService`, MCP tools, GUI entry, artifact path, validation, and idempotency unchanged. Add three fixed sections in the pure application-packet compiler, deriving every candidate claim from existing `direct` or `related` evidence and leaving human application actions unchecked.

**Tech Stack:** Python 3.12, pytest, deterministic Markdown compiler, existing Career MatchService and ApplicationPacketService

---

## File Map

**Modify**

- `extensions/career_mcp/domain/application_packets.py`: add three headings and pure render helpers.
- `extensions/career_mcp/tests/test_application_packets.py`: prove section order, evidence boundaries, and checklist truthfulness.
- `.coworker/skills/career-application-packet/SKILL.md`: document the eleven-section output.
- `tests/test_skills.py`: enforce the expanded Skill contract.
- `docs/11_DEVELOPMENT_LOG.md`: record commands and acceptance evidence after implementation.

No database, HTTP, MCP registration, GUI, or file-service change is required.

### Task 1: RED Tests For The Three New Sections

**Files:**

- Modify: `extensions/career_mcp/tests/test_application_packets.py`

- [x] **Step 1: Expand the expected headings**

Replace `HEADINGS` with:

```python
HEADINGS = [
    "## 岗位与官方来源",
    "## 使用的简历",
    "## 岗位要求证据矩阵",
    "## 建议重点强调的已确认经历",
    "## 暂无佐证与待确认问题",
    "## 简历调整建议",
    "## 自我介绍",
    "## 内推与 HR 沟通文本",
    "## 面试准备问题",
    "## 申请 Checklist",
    "## 数据版本与生成时间",
]
```

- [x] **Step 2: Add a RED evidence-bound content test**

Add:

```python
def _section(markdown: str, heading: str, next_heading: str) -> str:
    return markdown.split(heading, 1)[1].split(next_heading, 1)[0]


def test_support_materials_use_only_traceable_evidence():
    markdown = compile_application_packet(
        _match_result(),
        generated_at=NOW,
    )["markdown"]

    introduction = _section(
        markdown,
        "## 自我介绍",
        "## 内推与 HR 沟通文本",
    )
    messages = _section(
        markdown,
        "## 内推与 HR 沟通文本",
        "## 面试准备问题",
    )

    for section in (introduction, messages):
        assert "DeepSeek" in section
        assert "大模型算法工程师" in section
        assert "使用 Python 构建服务" in section
        assert "具有三年分布式系统经验" not in section
        assert "13800001234" not in section
        assert "secret@example.com" not in section
```

- [x] **Step 3: Add a RED checklist-state test**

Add:

```python
def test_application_checklist_separates_proven_and_human_actions():
    markdown = compile_application_packet(
        _match_result(),
        generated_at=NOW,
    )["markdown"]
    checklist = _section(
        markdown,
        "## 申请 Checklist",
        "## 数据版本与生成时间",
    )

    assert "- [x] 已选择并确认简历：算法简历" in checklist
    assert "- [x] 匹配快照仍为 fresh：`snapshot-1`" in checklist
    assert "- [x] 官方岗位来源已记录" in checklist
    assert "- [x] 申请准备包已通过确定性编译" in checklist
    assert "- [ ] 核对官网岗位状态和截止时间" in checklist
    assert "- [ ] 检查定制简历中的联系方式" in checklist
    assert "- [ ] 完成官网投递" in checklist
    assert "- [ ] 在岗位雷达更新申请状态" in checklist
```

- [x] **Step 4: Add a RED no-evidence fallback test**

Add:

```python
def test_support_materials_do_not_turn_none_into_candidate_claims():
    result = _match_result()
    result["results"][0]["requirements"][0]["status"] = "none"
    result["results"][0]["requirements"][0]["evidence"] = []
    result["results"][0]["summary"] = {
        "hard_direct": 0,
        "direct": 0,
        "related": 0,
        "none": 2,
        "target_role_overlap": True,
    }

    markdown = compile_application_packet(
        result,
        generated_at=NOW,
    )["markdown"]
    support = _section(
        markdown,
        "## 自我介绍",
        "## 面试准备问题",
    )

    assert "当前没有可用于自我介绍的已确认证据" in support
    assert "使用 Python 构建服务" not in support
    assert "具有三年分布式系统经验" not in support
```

- [x] **Step 5: Run RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_application_packets.py -q
```

Expected: failures because the three headings and render helpers do not exist.

- [x] **Step 6: Commit RED**

```bash
git add extensions/career_mcp/tests/test_application_packets.py
git commit -m "test(application): require support materials"
```

### Task 2: GREEN Deterministic Rendering

**Files:**

- Modify: `extensions/career_mcp/domain/application_packets.py`

- [x] **Step 1: Add the three headings**

Set:

```python
_HEADINGS = (
    "## 岗位与官方来源",
    "## 使用的简历",
    "## 岗位要求证据矩阵",
    "## 建议重点强调的已确认经历",
    "## 暂无佐证与待确认问题",
    "## 简历调整建议",
    "## 自我介绍",
    "## 内推与 HR 沟通文本",
    "## 面试准备问题",
    "## 申请 Checklist",
    "## 数据版本与生成时间",
)
```

- [x] **Step 2: Add a structured support-evidence helper**

Add:

```python
def _support_evidence(results: list[dict]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for result in results:
        resume_name = _inline(result["resume"].get("display_name"))
        for requirement in result["requirements"]:
            if requirement["status"] not in {"direct", "related"}:
                continue
            for evidence in requirement["evidence"]:
                key = (
                    resume_name,
                    _inline(requirement["requirement"]),
                    _inline(evidence["excerpt"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        "resume_name": key[0],
                        "requirement": key[1],
                        "excerpt": key[2],
                    }
                )
    return items
```

- [x] **Step 3: Add self-introduction rendering**

Add:

```python
def _self_introduction(job: dict, results: list[dict]) -> list[str]:
    company = _inline((job.get("company") or {}).get("name"))
    title = _inline(job.get("title"))
    evidence = _support_evidence(results)[:3]
    if not evidence:
        return [
            f"我正在申请 {company} 的{title}岗位。",
            "当前没有可用于自我介绍的已确认证据；请先补充并确认真实经历。",
        ]
    lines = [f"我正在申请 {company} 的{title}岗位。"]
    lines.append("与岗位相关的已确认经历包括：")
    lines.extend(f"- {item['excerpt']}" for item in evidence)
    lines.append(
        "面试时请按背景、个人行动和可验证结果展开，只使用以上已确认事实。"
    )
    return lines
```

- [x] **Step 4: Add referral and HR message rendering**

Add:

```python
def _communication_messages(job: dict, results: list[dict]) -> list[str]:
    company = _inline((job.get("company") or {}).get("name"))
    title = _inline(job.get("title"))
    source_url = _inline(job.get("source_url"))
    evidence = _support_evidence(results)[:2]
    if not evidence:
        return [
            "当前没有可用于沟通文本的已确认证据；请先补充并确认真实经历。"
        ]
    proof = "；".join(item["excerpt"] for item in evidence)
    return [
        "### 内推沟通",
        "",
        (
            f"你好，我正在关注 {company} 的{title}岗位（{source_url}）。"
            f"我的已确认经历包括：{proof}。如方便，想请你帮忙了解或内推该岗位；"
            "未覆盖的要求我会如实说明。"
        ),
        "",
        "### HR 沟通",
        "",
        (
            f"您好，我希望申请 {company} 的{title}岗位。"
            f"与岗位相关的已确认经历包括：{proof}。"
            f"官方岗位链接：{source_url}。期待进一步沟通。"
        ),
    ]
```

- [x] **Step 5: Add checklist rendering**

Add:

```python
def _application_checklist(job: dict, results: list[dict]) -> list[str]:
    lines: list[str] = []
    for result in results:
        lines.extend(
            [
                (
                    "- [x] 已选择并确认简历："
                    f"{_inline(result['resume'].get('display_name'))}"
                ),
                (
                    "- [x] 匹配快照仍为 fresh："
                    f"`{_inline(result.get('snapshot_id'))}`"
                ),
            ]
        )
    lines.extend(
        [
            "- [x] 官方岗位来源已记录",
            "- [x] 申请准备包已通过确定性编译",
            "- [ ] 核对官网岗位状态和截止时间",
            "- [ ] 检查定制简历中的联系方式",
            "- [ ] 确认所有材料均未新增或夸大事实",
            "- [ ] 完成官网投递",
            "- [ ] 在岗位雷达更新申请状态",
        ]
    )
    return lines
```

- [x] **Step 6: Insert the sections into `_render`**

After the existing resume-adjustment section, render:

```python
    lines.extend(["", _HEADINGS[6], ""])
    lines.extend(_self_introduction(job, results))
    lines.extend(["", _HEADINGS[7], ""])
    lines.extend(_communication_messages(job, results))
    lines.extend(["", _HEADINGS[8], ""])
    lines.extend(_interview_questions(results))
    lines.extend(["", _HEADINGS[9], ""])
    lines.extend(_application_checklist(job, results))
    lines.extend(["", _HEADINGS[10], ""])
```

Remove the old `_HEADINGS[6]` and `_HEADINGS[7]` insertion so every heading appears exactly once.

- [x] **Step 7: Run GREEN**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_application_packets.py \
  extensions/career_mcp/tests/test_application_packet_service.py -q
```

Expected: all tests pass; the service remains byte-idempotent.

- [x] **Step 8: Commit GREEN**

```bash
git add extensions/career_mcp/domain/application_packets.py
git commit -m "feat(application): add support materials"
```

### Task 3: Skill Contract And Regression

**Files:**

- Modify: `.coworker/skills/career-application-packet/SKILL.md`
- Modify: `tests/test_skills.py`
- Modify: `docs/11_DEVELOPMENT_LOG.md`

- [x] **Step 1: Add RED Skill assertions**

In the Career application packet Skill test, require:

```python
for heading in (
    "## 自我介绍",
    "## 内推与 HR 沟通文本",
    "## 申请 Checklist",
):
    assert heading in packet
assert "人工动作保持未勾选" in packet
assert "不得把 none 要求写入自我介绍或沟通文本" in packet
```

- [x] **Step 2: Run RED**

```bash
.venv/bin/pytest tests/test_skills.py -q
```

Expected: fail because the Skill still documents eight sections.

- [x] **Step 3: Update the Skill**

Replace its fixed section list with the eleven headings and add:

```text
“自我介绍”和“内推与 HR 沟通文本”只能使用工具根据 direct/related
证据编译出的正文，不得由对话记忆补写。不得把 none 要求写入自我介绍或沟通文本。
Checklist 中只有工具可证明的状态可以标记完成，官网核对、投递和申请状态更新等
人工动作保持未勾选。
```

- [x] **Step 4: Run the focused regression**

```bash
.venv/bin/pytest \
  tests/test_skills.py \
  extensions/career_mcp/tests/test_application_packets.py \
  extensions/career_mcp/tests/test_application_packet_service.py \
  extensions/career_mcp/tests/test_resume_tools.py -q
```

Expected: all pass.

- [x] **Step 5: Run integrity checks**

```bash
.venv/bin/python -m compileall -q \
  extensions/career_mcp/domain/application_packets.py
git diff --check
```

Expected: both succeed.

- [x] **Step 6: Record evidence**

Append the exact commands and test counts to `docs/11_DEVELOPMENT_LOG.md`.

- [x] **Step 7: Commit**

```bash
git add \
  .coworker/skills/career-application-packet/SKILL.md \
  tests/test_skills.py \
  docs/11_DEVELOPMENT_LOG.md
git commit -m "docs(application): require support materials"
```
