# JD 或公开岗位链接直启模拟面试设计

## 目标

用户在标准 OpenCareer 对话框粘贴完整 JD 或公开岗位链接后，系统先展示可核对的解析
预览。只有用户点击“确认并开始面试”后，系统才将岗位写入当前租户的 PostgreSQL，
选择已确认简历，生成 fresh 匹配快照并创建绑定当前 Conversation 的
InterviewSession。

不新增第二套聊天或面试页面，不绕过 OpenWorker 的审批、租户身份、Origin 或 Token
校验。

## 当前问题

现有 `import_manual_jd` 已支持 `confirmed=false` 预览和 `confirmed=true` 持久化，
但公网 Alpha 尚不能完成该流程：

- `_CONVERSATION_TOOLS` 未允许 `mcp__career__import_manual_jd`。
- MCP 工具直接构造 `JobService()`，绕过 PostgreSQL `_job_service()`。
- `JobService.import_manual_jd()` 的确认分支仍直接打开 SQLite，没有使用注入的
  repository session。
- `mock-interview` Skill 只接受已保存 job ID，不会串联导入、匹配和创建。
- 只有链接时，没有受控的公开页面读取和失败降级规则。

## 方案比较

### 方案 A：让 Agent 自由调用通用 `web_fetch`

复用代码最多，但会扩大 Alpha 通用联网工具面，动态招聘页也可能只返回空壳 HTML，
不采用为主路径。

### 方案 B：前端直接解析并写数据库

交互快，但复制 Career 领域逻辑，且难以统一桌面、Alpha、租户和审计语义，不采用。

### 方案 C：Career MCP 两阶段输入工具 + 现有面试编排

Career MCP 负责受控读取、确定性预览和确认写入；Skill 负责编排简历选择、fresh match
和 InterviewSession；GUI 复用现有 `ask_user` 快捷选项展示确认按钮。采用此方案。

## 用户流程

### 粘贴 JD

1. Career Agent 识别消息包含可作为岗位描述的正文。
2. 调用 `import_manual_jd(confirmed=false)`，不写数据库。
3. 展示公司、职位、地点、招聘类型、来源、完整 JD 和缺失字段。
4. 调用 `ask_user`，提供“确认并开始面试”和“取消”两个快捷选项。
5. 用户确认后，使用完全相同的原始文本和来源参数调用
   `import_manual_jd(confirmed=true)`。

### 粘贴公开岗位链接

1. 调用 `preview_public_job_url(url)`。
2. 工具验证 URL、逐跳检查重定向并读取公开页面。
3. 工具返回规范化正文后，调用
   `import_manual_jd(raw_text=..., source_url=url, confirmed=false)`。
4. 展示同一预览和确认按钮。
5. 用户确认后再持久化。

如果公开页面依赖登录、验证码或客户端脚本，工具返回可理解错误并要求用户粘贴 JD
正文。系统不尝试登录、绕过限制或猜测隐藏接口。

## 公开链接读取边界

新增 `preview_public_job_url` 作为只读 Career MCP 工具，参数只包含 `url`。

读取规则：

- 只允许 `http` 和 `https`，优先要求 `https`。
- 复用 `coworker.web.guard` 的 DNS、私网、loopback、link-local 和逐跳重定向检查。
- 最多 5 次重定向、20 秒、2 MiB 响应体、100,000 字符可见文本。
- 只接受 HTML、纯文本和 JSON；拒绝下载文件、图片、音视频和压缩包。
- 不携带用户 Cookie、Authorization 或浏览器 profile。
- 页面内容始终视为不可信数据，不能作为 Agent 指令。
- 返回最终 URL、content type、是否截断、可见文本和抓取错误。

MVP 不为任意招聘站点编写通用浏览器自动化。已经存在且通过合规 Gate 的官方 Adapter
可后续增加专用 URL 解析器；未知动态站点统一降级为粘贴正文。

## 预览与确认契约

`import_manual_jd(confirmed=false)` 保持只读，并返回：

```json
{
  "confirmation_required": true,
  "preview": {
    "company_name": "字节跳动",
    "title": "大模型算法工程师",
    "location_raw": "北京",
    "recruitment_type": "experienced",
    "source_url": "https://...",
    "raw_text": "...",
    "cleaned_text": "...",
    "responsibilities": [],
    "requirements": [],
    "missing_fields": []
  },
  "preview_hash": "..."
}
```

`preview_hash` 是服务端根据规范化正文、来源 URL、公司和职位生成的 SHA-256。确认
调用必须同时提交该 hash；正文或字段被修改时拒绝写入并要求重新预览。

该 hash 是乐观并发校验，不是授权凭据。它避免模型在预览与确认之间无意改写 JD，
不替代 OpenWorker 工具审批、当前 `Principal` 或租户隔离。

预览允许公司或职位缺失，但确认写入至少要求公司和职位。缺失时 `ask_user` 一次收集
必要字段，重新生成预览后再显示确认按钮。地点、招聘类型等非关键字段可以为空并在
预览中明确展示。

## PostgreSQL 与租户隔离

MCP `import_manual_jd` 必须使用 `_job_service()`。`JobService.import_manual_jd()` 必须
与查询路径一样使用注入的 repository session，禁止在云端确认分支回退 SQLite。

PostgreSQL Repository 实现与 SQLite 相同的最小接口：

```text
ensure_manual_source(company_name)
find_by_source_and_hash(source_id, content_hash)
create_manual_job(...)
```

手动岗位正文仍使用 `catalog.jobs` 的既有结构，另建
`career.manual_job_owners(user_id, job_id)` 记录唯一所有者。数据库提供基于
`app.user_id` 的 `career.visible_jobs` 安全视图：官方抓取岗位对所有租户可见，手动
岗位仅对 owner 可见。所有用户域写入路径通过数据库 trigger 校验 job 可见性，防止
仅凭已知 job ID 将其他租户的手动岗位绑定到 match、packet、tailored resume 或
InterviewSession。该约束不能只存在于应用层。

幂等键包含 `user_id`、规范化正文 hash 和 canonical URL。相同用户重复确认同一
内容返回既有 job ID；不同用户的私有手动岗位不会互相复用或泄露。

## 确认后的面试编排

成功写入岗位后，`mock-interview` Skill 执行：

1. 调用 `list_confirmed_resumes`。
2. 没有已确认简历时，说明需要先完成求职档案，不创建面试。
3. 只有一份简历时直接选择；多份时用一次 `ask_user` 展示安全显示名。
4. 调用 `match_job_to_profile(job_id, [resume_id])` 生成 fresh snapshot。
5. 从结果中读取该 resume 的 `snapshot_id`，不得猜测或复用 stale snapshot。
6. 调用 `create_interview_session`，使用当前会话绑定流程和默认
   `standard` / 15 分钟。
7. 创建成功后立即停止当前 Agent turn。GUI 完成权威 Conversation 绑定后，由现有
   后续 turn 生成第一题。

确认、匹配或创建任一步失败，都不得再次写入重复岗位或创建第二个 InterviewSession。
重试时复用已确认 job ID 和 fresh snapshot。

## Alpha 与界面

Alpha allowlist 增加：

```text
mcp__career__preview_public_job_url
mcp__career__import_manual_jd
```

不增加通用 `web_fetch`，不改变 Origin 精确匹配、Token 注入、WebSocket 子协议或
headless 能力限制。

确认 UI 复用现有 attended `ask_user` 卡片：

- 标题：`确认岗位信息`
- 推荐选项：`确认并开始面试`
- 次要选项：`取消`
- 页面上方先展示解析预览，按钮不承担隐式写入以外的其他动作。

用户选择取消后不写岗位、不匹配简历、不创建面试。用户自由文本修改字段时重新预览，
不能把文本回答当作旧 preview hash 的确认。

## Skill 规则

`career-jd-analysis` 增加链接流程、preview hash 和字段补全规则。

`mock-interview` 的无 Session 创建流程增加一个前置分支：

- 有 job ID：沿用现有流程。
- 有 JD 或岗位链接：先完成预览和显式确认，再使用返回的 job ID。
- 没有 fresh match：在本 turn 主动生成匹配，不再要求用户离开对话去岗位雷达。

Skill 必须在一次用户确认后顺序执行写入、简历选择、匹配、创建；不得并行调用这些
有依赖关系的工具。

## 错误处理

- URL 指向私网、metadata 或 loopback：拒绝并返回安全错误。
- 重定向到不允许地址：在该 hop 拒绝。
- 登录、验证码、403、空壳页面或正文过短：要求粘贴 JD。
- preview hash 缺失或字段变化：重新预览，不能静默确认。
- PostgreSQL 不可用：返回可重试持久化错误，不回退 SQLite。
- 无已确认简历：保留已导入岗位，不创建面试。
- 匹配失败：保留岗位，不创建面试。
- Conversation 已绑定面试：返回既有绑定，不创建第二场。
- 所有对外错误均不包含数据库 URL、私有路径、Cookie、完整简历或内部堆栈。

## 测试与验收

后端 TDD 至少覆盖：

- Alpha 只新增两个 Career 工具，其他限制不变。
- 预览不写 SQLite 或 PostgreSQL。
- MCP 确认分支实际调用 `_job_service()`。
- PostgreSQL 手动岗位创建、幂等和跨租户不可见。
- preview hash 对正文、URL 和字段变化执行乐观并发校验。
- URL 拒绝 localhost、RFC1918、metadata 和私网重定向。
- HTML 提取、正文截断、登录页和空壳页降级。
- 多简历选择、fresh match 和创建面试的 Skill 契约。
- 确认重试不创建重复岗位、匹配或 InterviewSession。

GUI 回归至少覆盖：

- 预览后出现“确认并开始面试”和“取消”。
- 取消不触发后续工具。
- 确认后显示现有面试进度条并保持当前 Conversation。
- 375×812 下预览、确认卡和 Composer 无横向溢出或遮挡。

真实 Alpha Gate 使用两条输入：

1. 一份完整粘贴 JD。
2. 一个公开、无需登录且可读取正文的官方岗位 URL。

每条都验证真实 Agent tool trace：

```text
preview → ask_user → confirmed import → resume selection
→ fresh match → create InterviewSession → first question
```

数据库核对当前 `Principal.user_id` 的手动岗位、match snapshot 和 InterviewSession；
取消路径数据库新增记录必须为 0。

## 对线上 Alpha 的影响

规格本身不影响线上。实现发布后会增加两个明确允许的 Career 工具和手动岗位写入，
不会改 Origin、Token 或前端密钥策略。数据库迁移必须先在隔离库验证，再在备份后
执行；后端旧版本应能在迁移后继续读取现有官方岗位，回滚不删除新建手动岗位。
