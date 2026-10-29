# 本地部署指南

## 安装与首次使用

安装 Git、Python 3.12、Node.js 22 LTS，克隆源码后运行 `python3 start_local.py`。
浏览器使用当前稳定版；样式最低要求 Chrome / Edge 111、Firefox 128 或 Safari 16.4。
无需 Docker、PostgreSQL、Redis、Authing 或维护者的企业账号。
首次安装需要访问 Python 包源、GitHub 和 npm。失败后可重新执行，不会删除数据。
启动器支持通过 Python 管理器的符号链接入口创建环境；中断后会检测并补齐缺失的 pip。
若创建失败，确认使用完整 Python 3.12，Linux 安装对应 venv/ensurepip 组件后重试。
不要从陌生人获取所谓“共享模型密钥”。

启动器使用 `.venv-local/`，不会替换开发者的 `.venv/`。
前端构建位于数据目录的 `web/`，不写入 `deploy/web/`。
不要手工把文件放入 `web/`；它是每次启动可重新生成的网页目录。

使用 `http://127.0.0.1:1422`，在模型菜单配置自己的服务商和模型。第一版保持与
托管 Career 模式相同的工具和服务商安全范围；尚不承诺任意自定义模型地址或 Ollama
兼容性。岗位雷达默认后台下载服务器的完整公共岗位快照，不需要网站登录、模型密钥
或生产数据库连接串。运行中每 24 小时检查更新，未变化来源不重复下载；失败保留
本机数据并在 15 分钟后重试。页面显示同步进度、发布时间及官网最近更新失败的来源。
快照发布时间和实际官网确认时间不同；岗位详情保留原始时间与在招／下线状态。
同步只下载公开岗位，不上传简历、对话、收藏、申请记录或模型配置。

`python3 start_local.py --job-source local` 可切换为本机独立采集，包含字节大陆全量
社招／校招，运行中每 12 小时更新；首次可能需要数十分钟。`--no-job-sync` 关闭
本次所有后台岗位更新，可离线查看已有数据。两种模式使用同一岗位身份并保留用户记录。

独立采集模式的安装器启用已有 browser 可选依赖（Playwright 浏览器自动化库）并准备 Chromium，
用于快手等浏览器来源。下载失败不阻断其他来源和网页；恢复网络后重启启动器会重试，
也可运行 `.venv-local/bin/python -m playwright install chromium`（Windows 使用
`.venv-local/Scripts/python.exe`）。Linux 如提示缺少系统库，请按浏览器安装提示补齐。
更新请求只写本地标记，所有采集按固定官方来源运行；页面不能指定任意网址或命令。
默认共享模式不安装浏览器组件。自托管共享服务可使用
`--job-feed-url https://你的域名/public/jobs/v1/`；禁止嵌入凭据、查询参数和跨来源跳转。
详细设计见 `23_JOB_CATALOG_DISTRIBUTION.md`，导出部署见 `deploy/public-catalog/README.md`。
新安装显示「未连接模型」，点击后在弹窗中配置自己的密钥；关闭弹窗不清空草稿。
简历文件使用「＋ → 导入简历到求职档案（PDF/DOCX）」；文本先粘贴到输入框，
再选择「＋ → 导入已粘贴的简历」。「PDF（仅用于对话）」不会建立求职档案。

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
# Fresh tracked-source copy, real dependency install and interrupted-setup retry (requires network)
OPENCAR_TEST_LOCAL_BOOTSTRAP=1 python -m pytest tests/test_local_bootstrap.py -q
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
