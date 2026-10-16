# OpenCareer

面向中国 AI / 互联网岗位的开源求职助手，基于 [OpenWorker](https://github.com/andrewyng/openworker) 二次开发。

[在线体验](https://app.opencareer.online) · [本地安装](#本地一键启动) · [问题反馈](https://github.com/qiushibang/OpenCareer/issues) · [文档](docs/README.md)

## 能做什么

- **找岗位**：查看公开官方招聘信息，筛选、收藏和记录申请进度。
- **整理简历**：导入多份简历，确认真实经历，再针对岗位分析与改写。
- **准备面试**：根据岗位描述和已确认简历开展多轮模拟面试，保留复盘记录。

不自动投递、不登录招聘网站、不绕过验证码，也不替用户编造简历经历。
招聘来源可能调整或下线，可使用手动岗位描述；新安装不会复制线上岗位数据库或用户数据。

## 在线使用与本地使用

| | 在线版 | 本地网页版 |
|---|---|---|
| 入口 | [app.opencareer.online](https://app.opencareer.online) | 本机浏览器 |
| 账号 | 网站注册／登录 | 不需要网站或 Authing 账号 |
| 数据 | 托管服务中按用户隔离 | 本机独立目录 |
| 模型 | 用户配置自己的模型密钥 | 用户配置自己的模型密钥 |

两种方式默认不互相同步。**本地部署不是完全离线**：使用云端模型时，所选对话、岗位或简历内容会发送给该模型服务商；抓取公开招聘信息也需要联网。模型服务商可能收费，开源软件本身不收取许可费。

## 本地一键启动

首版提供**源码本地网页版测试版**。先安装 Git、Python **3.12** 和 Node.js **22 LTS**（含 npm）。macOS / Linux 使用以下命令；Windows 建议先使用 WSL，原生 Windows 和桌面安装包尚未完成验收。

```bash
git clone https://github.com/qiushibang/OpenCareer.git
cd OpenCareer
python3 start_local.py
```

最后一条命令会创建独立 Python 环境、安装依赖、构建网页、启动服务并打开
**http://127.0.0.1:1422**。第一次需要联网下载依赖，之后依赖未变更时会复用。
请使用启动器打印的地址，不要把 `127.0.0.1` 改成其他域名。

打开后，在输入框的模型选择处点击“配置自定义模型”，填写自己的服务商密钥。
不需要开发者的企业账号、登录令牌或生产数据库。

```bash
# 不自动打开浏览器
python3 start_local.py --no-browser

# 端口冲突时指定另一组端口；不会停止现有程序
python3 start_local.py --port 1423 --backend-port 8768

# 将数据放在自己指定的空目录（后续启动保持相同参数）
python3 start_local.py --data-dir /path/to/opencareer-data
```

按 **Ctrl+C** 停止服务，数据不会删除。默认目录为项目下的 `.local-state/local-user/`：
`state/` 保存会话、设置和模型密钥，`career/` 保存岗位等业务数据，`private/` 保存简历原件。
这些目录已被 Git 忽略；仍请保护本机账号和备份文件，不要分享整个数据目录。

本地版仅监听本机回环地址，保留受限 Career 工具和关键写入审批。
**不要用隧道、端口转发或反向代理把免登录本地版暴露到公网。**

## 升级、备份与能力边界

停止服务后备份整个数据目录，再更新源码并重新运行启动命令。数据库可能迁移，回退时应同时恢复旧版本源码和对应数据备份，不能只回退代码。详见 [本地部署指南](docs/22_LOCAL_QUICKSTART.md)。

基础安装支持文字、文本 PDF 和 DOCX 简历。扫描版 PDF 的离线文字识别需要额外的 OCR（Optical Character Recognition，光学字符识别）组件与模型，基础启动器不自动下载；见 [简历导入手册](docs/16_RESUME_IMPORT_RUNBOOK.md)。语音输入依赖单独配置，未配置时仍可正常使用文字输入。

暂不提供已签名的 OpenCareer 桌面安装包或经过验收的 Docker 一键包。不要使用上游 OpenWorker 安装包替代本项目；本项目暂时关闭上游自动更新地址。

## 开发与贡献

先阅读 [AGENTS.md](AGENTS.md)、[CODEX_START_HERE.md](CODEX_START_HERE.md) 和 [贡献指南](CONTRIBUTING.md)。
求职能力位于 `extensions/career_mcp/`；复用 OpenWorker 的会话、工具、权限、模型路由及技能机制。
本地启动配置与 `deploy/` 中的托管配置分开，普通用户不应运行生产同步脚本。

欢迎提交问题和改进建议。请使用虚构数据复现，不要上传简历、验证码、模型密钥或完整日志。
安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## 许可证与来源

代码沿用 [MIT 许可证](LICENSE)，保留上游版权说明；第三方依赖、模型和素材遵循各自许可证。
OpenCareer 是独立的社区衍生项目，不代表上游官方发行版。
上游来源、固定基线和修改边界见 [UPSTREAM.md](UPSTREAM.md)。
