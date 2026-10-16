# 求职档案页面与全局中文界面设计

## 1. 目标

本阶段解决两个已经影响产品可用性的缺口：

1. 简历虽然能够导入 Career Vault，但用户无法通过稳定页面查看已确认档案、原始简历和历史版本。
2. GUI 中英文混用，主要导航、按钮、状态和设置页面缺乏一致的中文产品语言。

完成后，OpenCareer 应具备一个左侧固定入口的“我的求职档案”页面，并将整个 GUI 的用户交互文案统一为中文。新建对话菜单中的“职业 Agent”固定排在第一位。

## 2. 已确认产品决策

### 2.1 档案入口

采用左侧固定一级入口：

```text
新建对话
我的求职档案
岗位雷达 / 最近对话
自动任务
设置
```

“我的求职档案”不能通过向 Agent 发送 prompt 间接打开。它是稳定的本地产品页面，不依赖模型是否可用。

### 2.2 档案详情

采用三个页签：

1. **已确认档案**
   - 基本信息。
   - 教育经历。
   - 工作经历。
   - 项目经历。
   - 技能。
   - 默认隐藏手机号、邮箱等敏感字段。

2. **原始简历**
   - PDF 使用浏览器原生 PDF 预览。
   - DOCX 在本地解析为安全、只读的网页结构。
   - TXT 使用只读文本预览。
   - 所有格式均提供原文件下载。

3. **版本记录**
   - 版本号。
   - 创建时间。
   - 来源文件名。
   - 本次确认的章节。
   - 不在首版实现版本回滚。

### 2.3 页面操作

- `导入简历`：无档案时的主操作。
- `更新简历`：已有档案时重新走现有导入、预览、逐节确认流程。
- `显示敏感信息`：一次性读取清晰字段，不改变默认脱敏状态。
- `下载原文件`：下载已确认档案关联的原始文件。
- `删除档案`：明确二次确认后删除档案、事实、版本、预览、导入记录和私有文件。

## 3. 数据与 API 设计

### 3.1 原则

- 档案页面直接读取本地 Career Domain Service，不调用模型。
- 页面读取不通过 MCP 工具循环，不产生审批卡。
- 现有 MCP 工具继续服务 Agent；HTTP 页面 API 复用相同 Service 和 Repository。
- 不把文件系统路径、upload token、preview token 返回给 GUI。

### 3.2 只读接口

在 OpenWorker Server 下新增 Career 页面接口：

```text
GET /v1/career/profile?include_sensitive=false
GET /v1/career/profile/versions
GET /v1/career/profile/original
GET /v1/career/profile/original/content
GET /v1/career/profile/original/download
```

响应职责：

- `profile`：返回结构化档案；默认脱敏。
- `versions`：返回版本摘要，不返回完整敏感快照。
- `original`：返回文件名、格式、大小、是否可预览。
- `content`：
  - PDF 返回 `application/pdf`。
  - DOCX 返回经过受控转换的 HTML 数据。
  - TXT 返回纯文本。
- `download`：返回原始字节和安全文件名。

### 3.3 写操作

现有 `/v1/career/resumes/stage` 保持不变。新增：

```text
DELETE /v1/career/profile
```

删除请求必须携带明确确认值。GUI 先要求用户输入中文确认短语；Server 校验后调用现有 `delete_candidate_profile` 服务。不得仅依赖浏览器 `confirm()`。

### 3.4 Repository 增量

新增只读查询：

- 当前档案关联的最近 confirmed resume import。
- 当前档案的版本摘要列表。
- 原始文件的安全元数据。

查询通过数据库关系找到私有文件，不接受客户端提供的相对或绝对路径。

## 4. 原始文件预览

### 4.1 PDF

- 使用受鉴权的同源 HTTP 响应。
- `Content-Disposition: inline`。
- 不生成公开临时 URL。

### 4.2 DOCX

- 复用已经安装的 `python-docx`。
- 仅转换段落、标题、项目符号和表格。
- HTML 由 Server 生成固定结构；文本必须转义。
- 不执行宏，不解析外部对象，不加载远程资源。
- 版式不承诺与 Word 像素一致，页面需明确标注“网页预览”。

### 4.3 TXT

- UTF-8 只读展示。
- 保留换行，不执行其中的 HTML。

## 5. GUI 信息架构

### 5.1 新页面

新增 `CareerProfileView`，作为 App 的一级 surface，与 Settings、Inbox、Automations 同级。

页面状态：

- 加载中。
- 无档案。
- 已有档案。
- 档案存在但原始文件不可用。
- 读取失败。

### 5.2 左侧栏

Career 产品入口位于新建对话按钮之后、会话列表之前。仅在 OpenCareer 产品形态下显示，不改变底层 Persona/Session 数据模型。

### 5.3 导入联动

档案页的“导入简历”和“更新简历”复用现有专用 resume file input，不创建第二套上传实现。App 使用现有 nonce 机制打开 Composer importer，并返回会话页面完成确认。

## 6. 全局中文化

### 6.1 覆盖范围

翻译全部用户界面文案：

- 左侧导航、新建对话菜单、会话分组、搜索。
- Composer 模式、附件、录音、发送、模型状态。
- 审批、计划、问题、目录授权。
- 右侧进度、交付物、访问权限。
- 设置、模型、Skill、Persona、语音、外观。
- 连接器、MCP、自动任务、收件箱、活动记录。
- 引导页、空状态、加载状态、错误提示、Toast。
- Tooltip、`title`、`aria-label` 和输入框 placeholder。

### 6.2 保留原文

以下内容不翻译：

- `OpenCareer`、`Aiden`、`DeepSeek`。
- `Skill`、`MCP`、API、URL 等技术专有名词。
- 公司和产品品牌。
- 模型 ID、工具 ID、文件名、命令和代码。
- 用户输入、Agent 回答、岗位原文和外部服务返回的业务内容。

### 6.3 Agent 中文名称

用户可见名称统一为：

| Persona ID / family | 中文名称 |
|---|---|
| `career` | 职业 Agent |
| `cowork` | 通用 Agent |
| `code` | 编程 Agent |
| `ops` | 运维 Agent |
| `chat` | 聊天 Agent |

不修改 Persona ID、会话数据或内部 manifest 标识。

### 6.4 排序

新建对话菜单使用显式显示顺序：

```text
career → cowork → code → ops → chat → 其他 Persona
```

`career` 始终第一。其他未知 Persona 保持原有相对顺序。

### 6.5 实现策略

当前产品只交付中文界面，不新增国际化依赖。采用显式中文文案和集中显示映射：

- Persona 名称和顺序使用纯函数。
- 高频通用状态可放入小型 `uiCopy` 常量模块。
- 不做运行时 DOM 文本替换。
- 不修改后端协议枚举值。

## 7. 隐私与安全

- 档案接口默认脱敏。
- 显示敏感信息只影响当前页面状态，不持久化。
- 清晰敏感信息不自动进入模型上下文。
- 原始文件接口只允许访问当前 Career Vault 已确认档案关联的文件。
- 所有文件响应校验真实路径仍位于 private resume 目录。
- DOCX 文本输出必须 HTML 转义。
- 删除是本阶段唯一破坏性操作，必须二次确认。

## 8. 错误处理

GUI 为以下错误提供中文状态：

- `PROFILE_NOT_FOUND`：尚未建立求职档案。
- `ORIGINAL_NOT_FOUND`：档案存在，但原始文件已不可用。
- `UNSUPPORTED_PREVIEW`：当前格式只能下载。
- `CONFIRMATION_REQUIRED`：删除确认不匹配。
- `PERSISTENCE_ERROR`：本地档案读取失败，可重试。

未知错误显示统一中文说明并保留可复制的错误代码，不展示 Python 或 SQLite 堆栈。

## 9. 测试与验收

### 9.1 后端

- Repository：档案到 confirmed import、版本和文件元数据的关联。
- Service：脱敏/清晰档案、PDF/DOCX/TXT 预览、路径边界。
- HTTP：鉴权、内容类型、下载文件名、删除确认。
- 回归：现有 Career MCP 简历工具行为不变。

### 9.2 GUI

- 档案空状态和三个页签。
- 敏感信息默认隐藏，显式点击后显示。
- PDF、DOCX、TXT 预览分支。
- 导入/更新入口复用专用 importer。
- 删除二次确认。
- 职业 Agent 在新建对话菜单第一位。
- Persona 显示名称全部中文。

### 9.3 中文文案审计

浏览器遍历主要页面和可展开菜单，收集：

- button/link/menuitem 文本。
- placeholder。
- `title`。
- `aria-label`。

除专有名词白名单外，不得出现英文交互文案。测试不扫描用户内容、Agent 输出、岗位数据和代码块。

### 9.4 最终验收

- GUI 全量测试通过。
- Career、Server、Persona、MCP 回归通过。
- TypeScript 和 production build 通过。
- `git diff --check` 通过。
- 浏览器逐页检查无控制台错误。
- 截图覆盖：
  - 新建对话菜单，职业 Agent 第一。
  - 无档案状态。
  - 已确认档案。
  - PDF 或 DOCX 原始简历预览。
  - 版本记录。
  - 中文设置和审批菜单。

## 10. 非目标

- 不生成新的美化简历模板。
- 不实现档案版本回滚。
- 不实现多份并行求职档案。
- 不翻译 Agent 回答和岗位原文。
- 不引入完整多语言切换框架。
- 不开始岗位收藏、申请跟踪或自动投递。
