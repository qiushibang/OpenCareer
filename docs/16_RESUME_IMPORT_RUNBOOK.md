# 简历导入与 Career Vault 运行说明

## 范围

首版支持单一候选人主档案：

- 粘贴文本；
- 文字型 PDF，最大 10 MB、20 页；
- DOCX，最大 10 MB；
- basic、education、experience、project、skill 五类分项确认；
- 本地版本化事实库；
- 默认敏感字段遮罩；
- 完整删除。

扫描 PDF/OCR、图片简历、旧版 DOC、岗位匹配和申请材料生成不在本阶段。

## 私人数据位置

```text
.local-state/career-private/resumes/
```

数据库位于：

```text
career/career.sqlite3
```

两个目录均已由仓库 `.gitignore` 排除。数据库 schema 为 v4。

## GUI 使用

在 Career 会话中点击 `+`：

- `Import resume PDF/DOCX`：选择文件；
- `Import pasted resume`：先把完整简历文本粘贴到输入框，再选择该操作。

上传成功后 GUI 只向会话发送 upload token、文件名、格式和
`career-resume-import` Skill，不把文件字节或完整文本放入普通用户消息。

## 确认流程

1. Agent 调用 `get_resume_import_text`，明确把本地提取文本发送给当前模型。
2. Agent 只按原文生成五类结构化候选事实。
3. `preview_resume_import` 校验并返回遮罩预览、缺失字段和冲突。
4. 用户按分项确认或修正。
5. Agent 只有在明确确认后才能调用 `confirm_resume_sections`。
6. 每次确认生成不可变 profile version。
7. `get_candidate_profile()` 默认返回遮罩数据。

未确认 preview 不能用于申请材料。

## 敏感字段

普通查询默认遮罩：

- 姓名；
- 手机号；
- 邮箱；
- 详细地址按已解析粒度返回。

`get_candidate_profile(include_sensitive=true)` 会把明文送入当前模型上下文，
仅在用户明确要求时使用。

## 删除

完整删除必须调用：

```text
delete_candidate_profile("DELETE MY CAREER PROFILE")
```

删除范围包括：

- candidate profile；
- confirmed facts；
- profile versions；
- resume previews；
- resume imports；
- 本地原件。

删除不可恢复。

## 错误恢复

- `NO_EXTRACTABLE_TEXT`：PDF 可能为扫描件，请换用文字型 PDF、DOCX 或粘贴文本。
- `PDF_PAGE_LIMIT`：PDF 超过 20 页。
- `FILE_TOO_LARGE`：文件超过 10 MB。
- `UPLOAD_EXPIRED` / `PREVIEW_EXPIRED`：24 小时 token 已过期，重新导入。
- `CONFIRMATION_REQUIRED`：操作缺少明确确认，或试图丢弃已确认 import。

错误和日志不得包含完整简历、明文联系方式或私人绝对路径。

## 真实验收

2026-08-06 使用完全合成简历完成：

```text
本地 HTTP 上传
-> 真实 stdio MCP
-> preview
-> basic 确认（version 1）
-> 其余四类确认（version 2）
-> masked profile
-> 完整删除
```

验收结果：

- Career MCP 工具数 16；
- 简历工具数 6；
- confirmed facts 5；
- profile versions 2；
- 删除后私人原件 0；
- 当前默认模型 `ep-20260806151220-8km7l`。
