# OpenCareer 域名与 Authing 上线手册

状态：已于 2026-08-31 完成备案后上线；本文继续作为复核与回滚手册。

> 2026-09-17 安全发布变更：以下有关“保留公网 18080”的说明仅为历史记录。
> 正式编排必须仅暴露域名 HTTPS 登录入口；旧共享身份入口不得重新开放。
> `docker-compose.ip.yml` 已限制为 127.0.0.1，仅供 SSH 隧道维护，不可恢复原来的
> 公网免登录代理。回滚应保留该网络收敛和云端身份校验，不回滚为免登录公网服务。

目标入口：`https://app.opencareer.online`

保留入口：`http://203.0.113.10:18080`（仅本人自测，仍是明文 HTTP 与共享 Alpha Token）

## 1. 审批期间规则（历史阶段）

- 不要把 `app.opencareer.online` 解析到中国内地服务器，也不要用该域名提供访问。
- 不改当前服务器编排，不关闭 18080；不要把 18080 地址发给他人，不上传真实简历。
- 可以先创建 Authing 应用和准备密钥，但不在生产服务器启用。

## 2. Authing 控制台配置

在 Authing 控制台创建“自建应用”，应用名建议 `OpenCareer Web`，使用 OpenID Connect（OIDC，开放身份连接）授权码模式：

| 配置项 | 填写值 |
| --- | --- |
| 登录回调地址 | `https://app.opencareer.online/_openworker/auth/callback` |
| 登出回调地址 | `https://app.opencareer.online/` |
| 允许的 Web Origin | `https://app.opencareer.online` |
| 授权模式 | Authorization Code（授权码） |
| PKCE | S256 |
| Scope | `openid profile email` |

从应用配置页复制 OIDC Issuer、Client ID、Client Secret。Issuer 应类似 `https://你的租户.authing.cn/oidc`。Client Secret 只能保存到服务器 `.env`，不要放进前端、聊天或截图。

登录方式建议首期只开放一种或两种容易支持的方式，例如“邮箱验证码”与“手机号验证码”；身份隔离依赖 Authing 返回的稳定 `sub`（Subject，用户唯一标识），不依赖邮箱是否填写。

## 3. 备案通过后的阿里云操作

1. 阿里云云解析 DNS 新增 A 记录：主机记录 `app`，记录值 `203.0.113.10`，初始 TTL 可用控制台默认值。
2. 轻量应用服务器防火墙确认 TCP 80、TCP 443 已放行；UDP 443 可选。按当前决定继续保留 TCP 18080。
3. 等 DNS 生效后验证：`dig +short app.opencareer.online` 应返回 `203.0.113.10`。
4. 取得备案号后，设置 `VITE_ICP_NUMBER` 并重新构建前端；备案号链接会出现在页面底部。
5. 按主管部门要求，在网站开通后 30 日内完成公安联网备案，并补充公安备案标识。

## 4. 服务器配置

先完整备份 PostgreSQL、`data-a`、Caddy 证书卷和现有部署目录。然后更新代码并编辑：

```text
/opt/opencareer/deploy/.env
```

以 `deploy/.env.example` 为模板，必须填写：

- `BASE_DOMAIN=opencareer.online`
- `SERVER_IP=203.0.113.10`
- `TOKEN_A`（保留 18080 使用）
- `DATABASE_URL`（必须复用当前宿主机 PostgreSQL 生产连接串，不得根据旧
  `POSTGRES_PASSWORD` 拼接，也不得启动一套空容器数据库）
- `REDIS_URL=redis://127.0.0.1:6379/0`
- `OPENCAR_AUTH_ISSUER`
- `OPENCAR_AUTH_CLIENT_ID`
- `OPENCAR_AUTH_CLIENT_SECRET`
- `OPENCAR_AUTH_STATE_SECRET`（用 `openssl rand -hex 32` 生成）

审批通过后执行：

```bash
cd /opt/opencareer
VITE_ICP_NUMBER="京ICP备2026055760号-1" SKIP_NPM_CI=1 bash deploy/build-frontend.sh
cd /opt/opencareer/deploy
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

## 5. 上线验收

先验证匿名边界，再用两个独立 Authing 测试账号验数据隔离：

```bash
curl -s https://app.opencareer.online/_openworker/v1/health
curl -s https://app.opencareer.online/_openworker/v1/auth/session
curl -s -o /dev/null -w '%{http_code}\n' https://app.opencareer.online/_openworker/v1/sessions
```

匿名会话应显示 `authenticated: false`，匿名访问 `/v1/sessions` 应返回 401。浏览器点击登录后应回到原页面，HTTPS Cookie 应包含 `HttpOnly`、`Secure`、`SameSite=Lax`。

隔离验收：账号 A 创建一段对话、上传一份纯虚构测试简历并收藏一个岗位；账号 B 登录后不得看到 A 的任何一项。再返回账号 A，三项数据仍应存在。不得用真实简历做上线验收。

## 6. 当前数据与回滚

18080 现有数据属于历史内部用户 `local`；新的 Authing 账号会获得新的内部用户标识，因此不会自动看到这批数据。上线前需要决定“丢弃演示数据”还是在已确认 Authing 账号后执行一次受审计迁移，不能自动把 `local` 数据绑定给第一个访问者。

若域名登录验收失败，停止新的域名编排并用 `docker-compose.ip.yml` 恢复 18080。不要删除 PostgreSQL 或 Docker 数据卷。回滚后域名应临时显示维护页或撤回 DNS 记录，避免把无鉴权页面暴露出去。

## 7. 2026-08-31 上线结果

- `app`、`@`、`www` 均解析到 `203.0.113.10`；Caddy 已为三个域名取得有效证书。
- 正式入口 health 为 `200`，匿名 session 为未登录，匿名读取会话返回 `401`，
  登录入口正确跳转 Authing；根域名与 `www` 永久跳转至 `app`。
- PostgreSQL 继续运行在宿主机并应用 migration 10；现有 `data-a` 与 18080 入口保留。
- 备案号 `京ICP备2026055760号-1` 已显示在登录页和应用页底部。
- 仍待两个独立测试账号完成对话、虚构简历、收藏和申请进度的交叉隔离验收。
