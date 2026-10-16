# OpenCareer 部署入口

当前有两套编排，但共用 `opencareer-alpha` 项目名和同一批数据卷：

- `docker-compose.ip.yml`：备案审批期间的 `http://公网IP:18080` 自测入口。Caddy 仍注入原 Alpha Token，不要公开地址，不要上传真实简历。
- `docker-compose.yml`：备案通过后的 `https://app.opencareer.online` 单域名入口。用户通过 Authing 登录，后端使用 PostgreSQL 按内部用户标识隔离数据；18080 暂时同时保留。

正式域名方案不再使用 `friend-a / friend-b / friend-c` 子域名，也不再由 Caddy 给域名请求注入共享 Token。完整控制台配置、上线、验收和回滚步骤见 [域名与 Authing 上线手册](../docs/19_DOMAIN_AUTHING_LAUNCH_RUNBOOK.md)。

备案审批期间继续按 [阿里云 IP 自测手册](README-aliyun.md) 使用现有入口，不要解析或访问备案中的域名。

常用命令：

```bash
# 当前 IP 自测
docker compose -f deploy/docker-compose.ip.yml ps

# 备案通过并完成 Authing / DNS / .env 配置后，先校验再切换
docker compose -f deploy/docker-compose.yml config --quiet
docker compose -f deploy/docker-compose.yml up -d --build
```

真实密钥只写入服务器的 `/opt/opencareer/deploy/.env`，不得提交到仓库。
