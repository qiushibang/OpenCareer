# 定制简历 DOCX/PDF 导出设计

## 1. 目标

让用户从一个目标岗位和一份已确认简历出发，获得可直接投递的单栏 ATS
定制简历：

- Career Agent 只在已确认事实范围内提出措辞调整。
- 每条建议都保留原事实、来源路径和关联 JD 要求。
- 用户逐条确认、编辑或省略后，系统才允许正式导出。
- 同一冻结版本同时生成可编辑 DOCX 和定稿 PDF。
- 正式文件可下载、可校验、可追溯，不包含未确认模型内容。

本阶段不生成求职信，不复刻原简历版式，也不开始 OCR。

## 2. 第一性原理

1. 定制简历的核心交付物是招聘方可接收的简历，不是内部申请分析报告。
2. 模型可以改善表达，但无法通过确定性规则证明所有同义改写都没有改变事实。
3. 因此正式材料必须同时具备来源绑定、确定性越界检查和用户逐条确认。
4. 联系方式是投递文件所需信息，但不是模型改写所需信息，不应进入模型上下文。
5. DOCX 和 PDF 必须来自同一冻结内容版本，不能成为两份独立编辑的事实副本。
6. 导出失败必须无半成品：不能只发布 DOCX 或只发布 PDF。

## 3. 采用方案

采用“结构化改写提案 → 逐条确认 → 确定性双格式导出”。

不采用只重排原文，因为它无法满足已确认的“证据内改写”产品目标。

不采用模型自由生成整份简历后一次审阅，因为来源追溯弱，且无法可靠阻止跨简历、
跨事实或 `none` 要求注入。

不在 Career Domain Service 内直接调用模型。模型工作继续由 OpenWorker
TurnEngine、Career Persona、Skill 和 MCP 工具循环承载。

## 4. 范围与用户流程

### 4.1 前置条件

- 目标岗位存在。
- 用户选择恰好一份未删除、已确认的简历。
- 岗位与该简历存在指定的 fresh match snapshot。
- snapshot 对应当前岗位 content hash 和当前简历 revision。

多简历比较仍用于帮助用户选择简历，但一份正式定制简历不能混合多份简历的事实。

### 4.2 正常流程

1. 用户在 fresh 匹配结果中点击“生成定制简历建议”。
2. GUI 新建 Career 会话，只预填 job、resume 和 snapshot ID，不自动发送。
3. Career Skill 调用 `prepare_tailored_resume`，获得 draft ID 和脱敏事实包。
4. Agent 生成带来源绑定的结构化条目并调用
   `submit_tailored_resume_proposals`。
5. 用户返回岗位匹配弹窗，打开最新“定制简历草稿”。
6. 用户逐条查看原事实、建议措辞、来源和关联 JD，并确认、编辑或省略。
7. 所有条目处理完后，用户点击“确认并导出”。
8. Service 冻结当前版本，生成 DOCX，再从同一 DOCX 转换 PDF。
9. 两种文件全部校验通过后，原子发布版本目录并返回下载入口和 SHA-256。

Agent 不能替用户确认，MCP 工具不能直接生成正式投递文件。

## 5. 领域模型

### 5.1 Draft

每个 draft 绑定：

- `job_id`
- `resume_import_id`
- `snapshot_id`
- `job_content_hash`
- `resume_revision_at`
- `template_id = ats_single_column_zh_v1`
- `status`
- `version`
- `items`
- `created_at`
- `updated_at`

状态：

```text
draft → review → confirmed → exported
                  ↘ stale
```

规则：

- Agent 首次提交合法 proposals 后进入 `review`。
- 全部条目为 `confirmed` 或 `omitted` 后，用户可冻结为 `confirmed`。
- 岗位 hash、简历 revision 或 snapshot 变化后，任何非 exported 当前草稿变为
  `stale`。
- 未导出的 confirmed draft 被编辑时，CAS version 增加，该条回到 `pending`，
  整份确认失效。
- 已导出 draft 不可原地修改；新改动复制为新的 draft 行，使用新的 ID、version 1
  和新导出目录，旧行及其 export metadata 保持不可变。

### 5.2 Draft Item

每条 item 包含：

```text
id
section
source_path
source_text
proposed_text
linked_requirement
evidence_status
decision
order
entry_path
field
editable
required
```

`decision` 只能是：

- `pending`
- `confirmed`
- `omitted`

`evidence_status` 只能是 `source`、`direct` 或 `related`：

- `source` 表示原样保留的已确认简历事实，没有绑定 JD 要求。
- `direct/related` 表示 Agent 针对 fresh match evidence 提出的改写。
- `none` 要求不能绑定简历条目。

`prepare` 必须先把所选简历的所有可展示已确认事实建立为 `source` item，使用
`proposed_text=source_text` 和 `decision=confirmed`。Agent 提交的是这些 item 的
改写子集，不得用 proposal 列表替换整份简历。没有被 Agent 改写的学校、公司、
职位、日期、技能和其他事实继续原样保留。

`entry_path` 表示所属结构化条目，例如 `experience[0]`；`field` 表示
`company/title/start_date/highlights[0]` 等字段。Exporter 按 `entry_path` 和
`field` 重建教育、工作、项目和技能结构，不能把所有叶子值降级为无上下文 bullet。

核心结构字段（学校、学位、公司、职位、项目名和日期）标记为 `required=true`、
`editable=false`，继续沿用用户在 Career Vault 中已确认的原值，不需要重复确认，
也不能在定制流程中删除。可改写的 summary、highlight、description、evidence 等
文本字段标记为 `editable=true`；Agent 改写后 decision 回到 `pending`，必须逐条确认。
仍为 `source` 状态的 item 不能在定制流程中直接改写；非 required source item
可以省略。用户若要改变原始事实，应回到“我的求职档案”修订并重新匹配，而不是在
导出草稿中绕过事实库。

一条 item 只能引用当前 `resume_import_id` 的一个实际事实路径。
`source_text` 必须与该路径的权威事实归一化文本一致。

### 5.3 确定性越界检查

Agent 提案和用户对可编辑字段的编辑都执行相同检查：

- 不得为空或超过 500 字。
- 不得新增 source text 中不存在的数字、日期、百分比、金额或 URL。
- 不得新增 source fact 和其结构化技能字段均未出现的显式技能词。
- 不得包含手机号、邮箱、微信、身份证、私人路径或 upload token。
- 不得包含匹配率、录用概率、资格结论或推导工作月数。
- 不得引用另一份简历的 source path。
- 不得把 `none` 要求绑定到简历事实。
- Agent 不得修改 `editable=false` 的结构字段，也不得提交新的 source path。

规则无法证明所有同义改写的语义等价，因此原文并排展示和用户逐条确认是正式导出的
不可绕过门槛。产品不得声称模型建议已经被自动证明为真实。

## 6. 输出内容

固定单栏 ATS 模板包含：

1. 姓名与联系方式。
2. 目标岗位。
3. 教育经历。
4. 工作经历。
5. 项目经历。
6. 技能。

仅渲染有内容的章节。首版不输出：

- 照片。
- 年龄、性别、出生日期和身份证。
- 婚育情况。
- 期望薪资。
- 未经用户确认的 summary 或自我评价。
- `pending` 或 `omitted` 条目。

Exporter 按 entry 分组：学校/学位/日期、公司/职位/日期和项目名作为结构行，
confirmed 的可编辑内容作为其下 bullet。它不能把公司、职位、学校或日期渲染成脱离
所属 entry 的独立 bullet。

联系方式只在最终导出进程中从本地已确认事实读取，不出现在 MCP proposal 响应、
Agent prompt、draft item 或日志中。

PDF 必须为 1–2 页。超过两页返回 `PAGE_LIMIT_EXCEEDED`，不静默删除、缩小到不可读
字号或截断内容。

## 7. 数据库

schema 从 v7 升级到 v8。

### 7.1 `tailored_resume_drafts`

```sql
CREATE TABLE tailored_resume_drafts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    resume_import_id TEXT NOT NULL REFERENCES resume_imports(id),
    snapshot_id TEXT NOT NULL REFERENCES job_resume_matches(id),
    job_content_hash TEXT NOT NULL,
    resume_revision_at TEXT NOT NULL,
    template_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'draft', 'review', 'confirmed', 'exported', 'stale'
    )),
    items_json TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT,
    exported_at TEXT
);

CREATE INDEX tailored_resume_drafts_lookup
    ON tailored_resume_drafts(
        job_id,
        resume_import_id,
        updated_at DESC,
        id DESC
    );
```

### 7.2 `tailored_resume_exports`

```sql
CREATE TABLE tailored_resume_exports (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES tailored_resume_drafts(id),
    draft_version INTEGER NOT NULL,
    directory_path TEXT NOT NULL,
    docx_path TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    docx_sha256 TEXT NOT NULL,
    pdf_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(draft_id, draft_version)
);
```

只保存工作区相对路径。数据库和 API 不返回绝对路径。

v8 DDL 必须使用事务内逐条 `execute()`，不得使用会隐式提交的 `executescript()`。
中途失败后不能留下部分表或 schema version 漂移，并且必须可重试。

## 8. 模块边界

### 8.1 Domain

新增 `domain/tailored_resumes.py`：

- 定义状态、section 和 decision 常量。
- 校验和归一化 proposal items。
- 比对 source path 与权威事实。
- 检查新增数字、日期、URL、技能和敏感值。
- 构建冻结的渲染模型。

Domain 不访问数据库、文件系统、网络、模型或 LibreOffice。

### 8.2 Repository

新增 `database/tailored_resume_repository.py`：

- 创建和读取 draft。
- 按 job/resume 查询最新 draft。
- 使用 `WHERE id = ? AND version = ?` 更新 draft。
- 标记 stale、confirmed 和 exported。
- 幂等保存 export metadata。

Repository 只负责 SQL 和行映射，不执行领域校验或文件转换。

### 8.3 Draft Service

新增 `services/tailored_resumes.py`：

- 验证 job、resume 和 snapshot 精确关联。
- 从整份已确认简历构造完整 baseline items 和不含敏感值的 Agent source bundle。
- 提交和校验 proposal。
- 执行 CAS 编辑、逐条 decision 和整份确认。
- 每次读取时检查 job hash 和 resume revision，过期即拒绝确认或导出。

所有写入使用短 `BEGIN IMMEDIATE` 事务。Repository 初始化和 migration 在业务锁前
完成。

### 8.4 Export Service

新增 `services/tailored_resume_exports.py`：

- 只接受 `confirmed` draft 的精确 version。
- 在本地读取最终联系方式和冻结 items。
- 用 `python-docx` 构造 `ats_single_column_zh_v1` DOCX。
- 使用固定 argv、独立临时 profile、超时和无用户输入的 `soffice --headless`
  转换 PDF。
- 重读 DOCX 并验证必需文本。
- 使用 `pypdf` 验证 PDF 可读取且页数为 1–2。
- 计算两个 SHA-256。
- 原子发布整个版本目录。

调用方不能提供 executable、命令参数、模板路径、输出目录或文件名。

## 9. 文件布局与原子性

正式目录：

```text
artifacts/tailored-resumes/
└── <company>-<job>-<resume>-v<draft_version>-<fingerprint>/
    ├── resume.docx
    └── resume.pdf
```

`artifacts/tailored-resumes/` 必须保持 Git 忽略，因为文件包含私人联系方式。

导出步骤：

1. 在正式目录同级创建随机临时目录。
2. 在临时目录写 DOCX。
3. 在临时目录转换和验证 PDF。
4. 计算哈希并 fsync 文件。
5. 开启短 `BEGIN IMMEDIATE`，重新检查 draft version、confirmed 状态和 freshness。
6. 将完整临时目录原子重命名为确定性版本目录。
7. 在同一数据库事务保存 export metadata 并将 draft 标记 exported。
8. fsync 正式父目录；成功后 commit 并返回结果。

SQLite commit 和文件系统 rename 不能组成真正的跨系统原子事务，因此失败路径必须
显式补偿：rename 后若 metadata 写入或 commit 失败，Service rollback 并删除刚发布的
完整目录；若删除本身失败，则将目录重命名为 `.orphan-*`，下载 API 和幂等查找都
忽略 orphan，下一次 Service 初始化时清理。任何 orphan 清理错误只记录稳定内部日志，
不得把路径返回给客户端。

若正式版本目录已经存在，Service 校验两个文件哈希与 metadata；一致则幂等返回，
不一致则返回 `PERSISTENCE_ERROR`，不得覆盖未知内容。

任一步失败必须清理临时目录和本次发布目录，且不得保留 export metadata 或把 draft
标记 exported。

## 10. MCP、HTTP 与 GUI

### 10.1 Career MCP

新增受保护工具：

```text
prepare_tailored_resume(job_id, resume_id, snapshot_id)
submit_tailored_resume_proposals(
    draft_id,
    expected_version,
    items
)
```

两者是本地业务状态写操作，继续经过 OpenWorker 现有审批。响应使用稳定
`ok/error/meta` 包装。

`prepare_tailored_resume` 返回：

- draft ID 和 version。
- 岗位标题、公司和结构化要求。
- 当前简历的脱敏、带 path、entry、field 和 editable 标记的完整事实。
- fresh match evidence。

它不得返回 basic section 的联系方式值、private path、原文件字节或 upload token。

### 10.2 HTTP

新增：

```text
GET   /v1/career/jobs/{job_id}/tailored-resumes
GET   /v1/career/tailored-resumes/{draft_id}
PATCH /v1/career/tailored-resumes/{draft_id}
POST  /v1/career/tailored-resumes/{draft_id}/confirm
POST  /v1/career/tailored-resumes/{draft_id}/export
GET   /v1/career/tailored-resume-exports/{export_id}/docx
GET   /v1/career/tailored-resume-exports/{export_id}/pdf
```

PATCH 接受 `expected_version` 和 item decisions/edits。confirm 和 export 都要求精确
`expected_version`。

下载继续要求 sidecar token，使用 attachment Content-Disposition，不接受任意路径。

### 10.3 GUI

岗位匹配弹窗在恰好一份 fresh 结果时显示“生成定制简历建议”。

最新 draft 面板显示：

- 原事实。
- 建议措辞。
- 来源章节和路径。
- 原样保留或关联 JD 要求及 source/direct/related 标签。
- 编辑、确认、省略动作。
- 待确认数量和 stale/conflict 中文提示。

“确认并导出”只在没有 pending item、至少有一个 confirmed item、草稿为当前版本且
未 stale 时启用。

导出成功显示 DOCX/PDF 下载按钮、draft version、生成时间和短哈希。GUI 不读取
绝对路径，不将文件正文发给模型。

## 11. 错误契约

| code | 含义 |
|---|---|
| `INVALID_INPUT` | ID、version、条目结构或状态不合法 |
| `JOB_NOT_FOUND` | 岗位不存在 |
| `RESUME_NOT_FOUND` | 简历不存在、未确认或已删除 |
| `SNAPSHOT_MISMATCH` | snapshot 不属于该 job/resume 或已变化 |
| `STALE_DRAFT` | 岗位、简历或 snapshot 已变化 |
| `VERSION_CONFLICT` | Agent 与 GUI 或两个 GUI 写入发生 CAS 冲突 |
| `PROPOSAL_VALIDATION_FAILED` | 提案违反来源或内容边界 |
| `CONFIRMATION_REQUIRED` | 仍有 pending item 或没有 confirmed item |
| `PDF_CONVERTER_UNAVAILABLE` | LibreOffice 不可用 |
| `PAGE_LIMIT_EXCEEDED` | PDF 超过两页 |
| `PERSISTENCE_ERROR` | SQLite 或安全目录内写入/发布失败 |

错误响应不包含联系方式、简历正文、绝对路径、SQL、命令输出或堆栈。

## 12. 测试与验收

### 12.1 Domain 与 Migration

- prepare 为整份已确认简历建立完整 source baseline，核心结构字段保持原样。
- 合法 direct/related proposals 只更新 baseline 的可编辑子集。
- 跨简历 path、错误 source text 和 `none` 绑定被拒绝。
- Agent 修改 required/non-editable 结构字段被拒绝。
- 新增数字、日期、百分比、URL、技能和敏感值被拒绝。
- 用户编辑执行与 Agent proposal 相同规则。
- v7→v8 保留所有岗位、简历、匹配和 tracking 数据。
- v8 DDL 中途失败无残留、version 不前移且可重试。

### 12.2 Repository 与 Draft Service

- prepare 只接受精确 fresh snapshot。
- source bundle 不含敏感 basic 值、私人路径或 token。
- 同一输入复用当前 draft；变化后创建新版本或 stale。
- Agent submit、GUI edit、decision 和 confirm 全部使用 CAS。
- 未被改写的 source items 原样保留；pending 不能确认，omitted 不进入冻结输出。
- inactive 岗位可继续查看历史 draft，但新确认前仍检查 snapshot freshness。
- 任何失败完整 rollback。

### 12.3 Export Service

- synthetic confirmed draft 生成可重读 DOCX 和 1–2 页 PDF。
- 两种文件包含相同冻结条目和目标岗位。
- 联系方式出现在正式文件，但不出现在 draft/MCP 响应。
- 相同 draft version 幂等返回相同目录和哈希。
- converter 缺失、超时、非零退出、损坏 PDF 和三页 PDF 均不发布目录。
- symlink、路径逃逸、预存冲突目录和单文件发布被拒绝。
- metadata 或 commit 失败时不得把 draft 标记 exported，正式版本目录必须被删除或
  隔离为不可下载的 orphan。

### 12.4 MCP、HTTP 与 GUI

- 两个 MCP 工具可发现、参数完整透传且保持审批属性。
- Agent 不能通过 MCP 确认或导出。
- HTTP 非对象请求返回稳定错误。
- GUI 展示原文、建议、来源、原样保留/JD 要求和待确认数。
- 编辑后回到 pending，冲突后刷新，不自动覆盖。
- 未确认和 stale 草稿不能导出。
- DOCX/PDF 下载经过 token，文件名中文兼容。
- 所有用户可见文案为中文，DOCX、PDF、ATS 等专有词保留。

### 12.5 真实验收与对抗审查

- 使用隔离 Career 数据库导入 synthetic 中文简历，选择一个真实入库岗位完成
  Agent proposal、逐条确认、DOCX/PDF 导出和下载。
- 用 LibreOffice 打开 DOCX，用 PDF renderer 截图检查中文、分页、重叠和截断。
- 提取 DOCX/PDF 文本，与冻结 confirmed items 和本地联系方式逐项核对。
- 正式工作数据库不写入 synthetic resume 或虚构 facts。
- 完整后端、GUI、production build、schema v8、外键和 `git diff --check` 通过。
- 独立对抗审查覆盖跨简历引用、数字/技能注入、确认绕过、CAS、stale、PII、
  converter 和原子发布。

默认自动测试不得访问公网。

## 13. 阶段门

1. Gate A：Domain、schema v8 和迁移故障恢复通过。
2. Gate B：Draft Repository/Service、CAS、stale 和逐条确认通过。
3. Gate C：ATS DOCX、PDF 转换、两页限制和原子发布通过。
4. Gate D：MCP、HTTP、Skill 和岗位雷达 GUI 贯通。
5. Gate E：隔离真实浏览器验收、完整回归和对抗审查通过。

Gate E 通过前不开始 OCR。

## 14. 明确不做

- 求职信、邮件正文或其他投递套件。
- 多语言简历。
- 多模板和双栏模板。
- 复刻原简历样式。
- 照片和图形化技能条。
- 扫描简历 OCR。
- 自动投递、登录招聘网站或验证码处理。
- 让模型读取最终含联系方式文件。
- 自动宣称语义改写已经被证明真实。
- 修改 OpenWorker Agent Loop、Provider Router、权限核心或通用文件工具。
