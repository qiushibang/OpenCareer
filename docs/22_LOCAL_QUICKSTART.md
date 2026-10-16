# 本地部署指南

## 安装与首次使用

安装 Git、Python 3.12、Node.js 22 LTS，克隆源码后运行 `python3 start_local.py`。
无需 Docker、PostgreSQL、Redis、Authing 或维护者的企业账号。
首次安装需要访问 Python 包源、GitHub 和 npm。失败后可重新执行，不会删除数据。
不要从陌生人获取所谓“共享模型密钥”。

启动器使用 `.venv-local/`，不会替换开发者的 `.venv/`。
前端构建位于数据目录的 `web/`，不写入 `deploy/web/`。
不要手工把文件放入 `web/`；它是每次启动可重新生成的网页目录。

使用 `http://127.0.0.1:1422`，在模型菜单配置自己的服务商和模型。第一版保持与
托管 Career 模式相同的工具和服务商安全范围；尚不承诺任意自定义模型地址或 Ollama
兼容性。初始岗位列表可能为空，可在对话中粘贴公开岗位描述并批准导入。

## 数据生命周期

默认数据目录为 `.local-state/local-user/`。可以用 `--data-dir` 选择一个空目录，
后续每次启动使用同一目录。启动器拒绝覆盖未标记的已有目录。

停止服务后复制整个数据目录作为备份，包含会话、简历、业务数据库与模型配置。
备份含敏感内容，请加密保存，不要上传到 GitHub。恢复时使用与备份匹配的源码版本。
升级前先停止并备份，然后 `git pull --ff-only`，再次运行启动器。
停止服务不清空数据。若要彻底移除，先确认备份，再手工删除你确认的本地数据目录；
启动器不提供自动递归删除命令。

## 安全与故障处理

- 只接受回环地址访问，后端另有随机启动令牌，跨站来源请求被拒绝。
- 端口被占用：用 `--port` 和 `--backend-port` 指定两个不同的空闲端口，不需要杀进程。
- 模型未配置／余额不足：检查自己的模型服务商设置，和网站账号无关。
- 依赖安装失败：检查网络和 Python / Node 版本。基础安装不包含扫描 PDF 的 OCR 组件。
- 页面无法打开：检查启动终端是否仍在运行，使用终端打印的精确地址。

`--skip-install` 仅用于已有依赖的开发／测试环境，会使用当前 Python，不是新用户的安装路径。
浏览器本地版以 Vite 的本地预览服务器提供构建产物；它不是公网生产服务器。
不要把端口转发到公网，不要复用线上 `.env` 或用户数据库。

## 验收命令（开发者）

```bash
python -m pytest tests -q
python -m pytest extensions/career_mcp/tests -m 'not ocr_acceptance' -q
OPENCAR_TEST_LOCAL_INSTALL=1 python -m pytest tests/test_local_installation.py -q
# Optional browser-test tools (not runtime dependencies)
python -m pip install playwright
python -m playwright install chromium
OPENCAR_TEST_LOCAL_BROWSER=1 python -m pytest tests/test_local_browser.py -q
cd surfaces/gui
npx tsc --noEmit
npx vitest run --maxWorkers=2
```

两套 Python 测试包含同名模块，请分别运行。OCR 离线测试会检查工作区残留，
不要与写入工作区的其他任务并行运行。真实模型、真人麦克风及 Windows 安装验收
与不联网的回归测试是不同层面的证据。

扫描件文字识别（Optical Character Recognition，OCR）是可选组件；基础安装的
测试不要求该组件。在支持的环境中安装 `python -m pip install -e '.[ocr,dev]'`
后，运行 `python -m pytest extensions/career_mcp/tests -m ocr_acceptance -q`
单独验证实际识别和安装验证器，或去掉 `-m` 运行完整领域测试。

当前自动化发布门槛使用真实本地 Career 页面测试。继承的 `surfaces/gui/e2e/`
桌面模拟测试仍含旧英文选择器，不能代表中文版产品全部通过；保留为手动
`Legacy desktop browser suite` 工作流，待单独迁移，不删除原用例。
