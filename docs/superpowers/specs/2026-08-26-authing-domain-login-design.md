# OpenCareer Authing 单域名登录设计

- Status: Approved for implementation
- Date: 2026-08-26
- Production domain: `app.opencareer.online`
- Existing IP Alpha: keep `http://203.0.113.10:18080` during the transition

## 1. Goal

在不改写 OpenWorker Agent Loop、Conversation 或 Career 领域模块的前提下，为云端
OpenCareer 增加真正的用户登录。每个已登录用户解析为一个稳定的 `Principal.user_id`，
已有 PostgreSQL Row-Level Security 继续负责对话、简历、收藏、申请进度和面试数据
隔离。

备案通过前只完成代码、配置模板和本地测试，不配置公网 DNS，不开放 80/443，不切换
线上流量。

## 2. Interfaces and seams

### HostedIdentityProvider

这是 Authing 所在的 Seam。Interface 只有两个行为：

1. 生成带 `state`、`nonce` 和 PKCE S256 的授权跳转。
2. 校验回调并返回标准化 `IdentityClaims(issuer, subject, email, email_verified,
   display_name)`。

生产 Adapter 使用 Authlib + Authing OIDC Discovery；测试 Adapter 返回固定身份。Career
和 Agent 模块不得导入 Authing SDK。

### AuthSessionStore

Interface 负责：

1. 将 `(issuer, subject)` 幂等映射为内部 UUID 用户并签发随机会话。
2. 通过原始会话 Token 解析 `Principal`。
3. 撤销当前会话。

生产 Adapter 使用 PostgreSQL；测试 Adapter 使用内存。数据库只保存 Token SHA-256，
不保存原始 Token、用户密码、Authing Access Token 或 Refresh Token。

### Browser interface

- `GET /auth/login`：跳转 Authing 托管登录页。
- `GET /auth/callback`：完成授权码交换，设置应用会话 Cookie，然后回到站内相对路径。
- `POST /auth/logout`：撤销当前会话并清除 Cookie。
- `GET /v1/auth/session`：返回是否已配置、是否已登录以及最小用户展示信息。

Cookie 名为 `opencar_session`，属性为 `HttpOnly; Secure; SameSite=Lax; Path=/`。线上
REST 和 WebSocket 都从该 Cookie 解析同一个 Principal。现有 Sidecar Token 只为桌面端
和过渡期 IP Alpha 保留。

## 3. PostgreSQL model

新增 migration 10：

- `identity.external_identities`：`issuer + subject` 唯一映射到内部用户；保存可选邮箱、
  邮箱验证状态和展示名。
- `identity.auth_sessions`：保存会话 Token 哈希、用户、过期和撤销时间。

这两张表是身份控制数据，不通过浏览器 Data API 暴露。业务私有表继续只依赖内部
`identity.users.id`，避免身份供应商字段扩散。

## 4. Deployment

新增单域名 Compose/Caddy 配置：

- `https://app.opencareer.online` 不再由 Caddy 注入共享 Token，完全依赖应用会话。
- `http://203.0.113.10:18080` 暂时保留并继续注入原 Alpha Token。
- 两个入口指向同一个后端和同一 PostgreSQL；域名入口按真实用户隔离，IP 入口仍属于
  现有 `local` 用户。
- Origin 白名单精确包含上述两个 Origin，不使用通配符。

## 5. Failure and security behavior

- Authing 配置缺失：`/v1/auth/session` 返回 `configured=false`；现有桌面/IP Token 路径
  不受影响。
- Domain 请求无有效 Cookie：除 health、登录、回调和会话查询外一律 `401`。
- `state`、`nonce`、PKCE、Issuer、Audience 或签名校验失败：不创建用户和会话。
- 回跳地址只接受以单个 `/` 开头的站内路径，拒绝 `//host` 和绝对 URL。
- 会话撤销、过期或 Token 哈希不匹配：REST 返回未登录，WebSocket 使用 `1008` 关闭。
- 日志不得记录授权码、Cookie、Access Token、ID Token、Client Secret 或完整邮箱。

## 6. Acceptance

1. 未配置 Authing 时，当前 Token 测试和 IP Alpha 行为保持兼容。
2. 已配置时，未登录浏览器只看到登录页，不会提前请求私有接口。
3. 登录成功后 REST 与 WebSocket 使用同一个 `Principal.user_id`。
4. Alice/Bob 登录后对话、简历和收藏互不可见。
5. 数据库中找不到任何原始会话 Token。
6. 退出后旧 Cookie 立即失效。
7. 单域名 Caddy 配置通过校验；备案通过前不部署。
