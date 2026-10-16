# OpenCareer 项目规则（给 Trae 的 AI 看的）

这份文件是 Trae 的**项目规则**（放在 `.trae/rules/` 下会自动生效）。
目的：任何一次 AI 改动，都不要把「桌面版能跑」和「云端 alpha 能跑」这两条线弄坏。

## 1. 这个项目是什么形态

- 桌面壳：Tauri（`surfaces/gui`，`src-tauri`），打包脚本在 `packaging/`。
- 后端：FastAPI（`coworker/server/`），桌面端以 sidecar 方式启动，云端以容器方式启动。
- 数据：本地 SQLite + 本地文件目录（`COWORKER_STATE_DIR` / `CAREER_DATA_DIR` / `CAREER_PRIVATE_DIR`）。
- 岗位抓取：`extensions/career_mcp/`，部分数据源依赖 Playwright + Chromium。
- 云端部署：`deploy/`（Caddy + 一人一后端容器 + 每日抓取容器），两套编排：
  - `deploy/docker-compose.yml`：域名 + 自动 HTTPS + `friend-a/b/c` 子域名（**备案通过后**用）。
  - `deploy/docker-compose.ip.yml`：无域名，`http://<公网IP>:18080`，只起 1 个后端（**当前阶段**用）。

## 2. 改代码时必须守住的不变量

1. **Origin 白名单是逐字匹配。** `coworker/server/app.py` 的 `OPENCAR_EXTRA_ORIGINS` 是逗号分隔、`re.escape`
   后精确匹配（含协议和端口）。新增部署入口时，必须同步改 compose 里的 `OPENCAR_EXTRA_ORIGINS`，
   否则表现是「页面能打开但请求全挂 + WebSocket 1008」。不要为了图方便把它改成通配。
2. **alpha 前端不带 token。** `surfaces/gui/src/api.ts` 在 alpha 模式返回空 token，邀请码由 Caddy
   注入请求头（`X-OpenWorker-Token`）和 WebSocket 子协议（`Sec-WebSocket-Protocol: openworker, <token>`）。
   不要把 token 打进前端产物。
3. **前端产物必须用 alpha 模式构建**：`bash deploy/build-frontend.sh`（内部是 `vite build --mode alpha`）。
   普通 `npm run build` 会把 `http://127.0.0.1:8765` 写进包里，浏览器版必坏。
4. **OCR/CV 依赖属于 `[ocr]` extra，不进云端镜像。** `pyproject.toml` 里 `rapidocr/onnxruntime/opencv-python/numpy`
   在 optional-dependencies 中；桌面打包脚本装 `[ocr]`，云端 `deploy/requirements-server*.txt` 不装。
   PDF 主路径是 pypdf 直接取文本，文本过少才降级（云端可走视觉模型）。
5. **两个镜像的容器 uid 必须都是 10001**（`deploy/Dockerfile`、`deploy/crawler/Dockerfile`）。
   抓取容器要写后端的数据卷，uid 不一致就是 `Permission denied`。
6. **headless 宿主上桌面专属能力要明确报错**，不要静默失败（见 `coworker/server/alpha.py` 的
   `OPENCAR_HEADLESS` 与 `coworker/server/manager.py`）。
7. **中国内地机房构建走 `deploy/requirements-server.cn.txt`**：aisuite 用 `deploy/vendor/` 里的本地 wheel，
   构建过程不连 GitHub；pip/apt/playwright 的镜像源由 compose 的 build args 传入。
   改 aisuite 版本时，`pyproject.toml` 和 vendor 的 wheel 要一起更新（做法见 `deploy/vendor/README.md`）。
8. **不要把 `deploy/.env` 提交**（里面是模型密钥和邀请码），也不要把它贴进对话或截图。

## 3. 当前阶段与下一步（M1 多租户）

已完成：M0 云端单人 alpha（IP 自测形态）、M0.5 独立每日抓取容器；
M1a-1 请求身份上下文已在代码和自动化测试中通过，但尚未部署到服务器验证。
未完成：M0 真实 Docker Gate、M1a-2 及后续多租户隔离。M1 的核心是
**先抽两层，再换存储**，顺序不要颠倒：

1. **身份抽象（M1a-1 已完成）**：HTTP/WS 请求上下文可取得 `Principal.user_id`；
   桌面端固定为 `local`，云端当前支持静态 token 表，未来替换为 JWT。
2. **按用户隔离 Career 数据（M1a-2）**：先用独立 SQLite/私有目录证明岗位、简历、
   投递和面试不会跨用户读取。
3. **SessionManager 多实例（M1a-3）**：按 `user_id` 惰性创建有上限的 manager，
   并把用户目录传给 Career MCP 子进程。
4. **部署收敛（M1a-4）**：单后端容器 + 多个 token/子域名，完成旧数据卷迁移和回滚验证。
5. **M1b 再换存储和登录**：抽象 SQLite/文件存储，云端接 Postgres + 对象存储，
   最后用 JWT 和 RLS 替换静态 token；顺序不能提前。

改动请**小步提交**，每步都保证桌面版仍能启动、云端 alpha 仍能通过
`curl localhost:18080/_openworker/v1/health`。

## 4. 验证清单（改完至少跑这些）

```bash
# 后端能起来（本地）
python -m coworker.server.run --help

# 前端类型检查 + alpha 构建
cd surfaces/gui && npx tsc && cd - && bash deploy/build-frontend.sh

# 抓取 CLI 不联网自检
python -m extensions.career_mcp.crawl_cli --list

# 部署编排语法（不需要 Docker 守护进程）
docker compose -f deploy/docker-compose.ip.yml config >/dev/null
docker compose -f deploy/docker-compose.yml config >/dev/null
```

## 5. 交流约定

- 用中文回答。
- 涉及部署/安全/密钥的改动，先说清「会不会影响正在线上跑的 alpha」，再动手。
- 不要为了让测试通过而放宽 Origin 校验、token 校验或 alpha 模式的能力限制。
