#!/usr/bin/env bash
# OpenCareer 云端 alpha —— 阿里云（中国内地）一键上线脚本，**在服务器上**执行。
#
# 它做的事情，按顺序：
#   1. 体检：系统、内存、磁盘、Docker / Docker Compose 是否可用
#   2. 加 swap（2C2G 机器构建镜像时内存会不够，没有 swap 容易在 pip 那一步被 OOM kill）
#   3. 配 Docker 镜像加速器（国内直连 Docker Hub 基本拉不动）
#   4. 生成 deploy/.env：自动填公网 IP、随机邀请码；模型 API Key 留给你手填
#   5. 构建并启动 caddy + backend-a（抓取容器默认不启动，见文末提示）
#   6. 自检：容器状态 + /v1/health + 首页 HTML，最后打印你要在浏览器里输入的地址
#
# 用法：
#   cd /opt/opencareer/deploy
#   sudo bash aliyun-bootstrap.sh                      # 交互最少的默认流程
#   sudo DOCKER_MIRROR=https://xxxx.mirror.aliyuncs.com bash aliyun-bootstrap.sh
#   sudo IP_PORT=18080 bash aliyun-bootstrap.sh
#
# 幂等：可以反复执行。已存在的 .env 不会被覆盖（只补缺失项），swap 和加速器配置存在就跳过。
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEPLOY_DIR"

COMPOSE_FILE="docker-compose.ip.yml"
ENV_FILE=".env"
SWAP_FILE="/swapfile"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-2048}"
DOCKER_MIRROR="${DOCKER_MIRROR:-}"

c_ok()   { printf '\033[32m✔\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m✘\033[0m %s\n' "$*" >&2; }
step()   { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

[ "$(id -u)" = "0" ] || { c_err "请用 root 执行：sudo bash aliyun-bootstrap.sh"; exit 1; }

# ---------------------------------------------------------------------------------------
step "1/6 体检"

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  c_ok "系统：${PRETTY_NAME:-unknown}"
fi

MEM_MB="$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)"
DISK_AVAIL_G="$(df -BG --output=avail / | tail -1 | tr -dc '0-9')"
c_ok "内存：${MEM_MB} MB；根分区可用：${DISK_AVAIL_G} GB"
[ "$DISK_AVAIL_G" -ge 12 ] || c_warn "磁盘可用不足 12G，构建镜像可能失败（后端镜像 ~600MB，抓取镜像 ~1.5GB）"

if ! command -v docker >/dev/null 2>&1; then
  c_err "没有 docker。你买的是 Docker 应用镜像的话它应该自带；请先执行：
  curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun && systemctl enable --now docker
装好后重新跑本脚本。"
  exit 1
fi
systemctl is-active --quiet docker || systemctl start docker
c_ok "docker：$(docker --version)"

if docker compose version >/dev/null 2>&1; then
  c_ok "compose 插件：$(docker compose version --short 2>/dev/null || echo ok)"
else
  c_err "docker compose 插件不可用（老的 docker-compose 独立命令不支持本文件里的 profiles 写法）。
安装：apt-get update && apt-get install -y docker-compose-plugin"
  exit 1
fi

[ -f "$COMPOSE_FILE" ] || { c_err "当前目录找不到 $COMPOSE_FILE，请确认你在仓库的 deploy/ 目录下"; exit 1; }
if [ -f web/index.html ]; then
  c_ok "前端产物已就位：deploy/web/index.html"
else
  c_err "缺少 deploy/web/index.html —— Caddy 没东西可托管。
前端产物应该在你本地打好一起传上来（bash deploy/build-frontend.sh），
或者在这台机器上装 Node 18+ 后执行 bash build-frontend.sh（2G 内存跑 npm ci 会比较吃力）。"
  exit 1
fi

# ---------------------------------------------------------------------------------------
step "2/6 swap（构建期防 OOM）"

if [ "$(swapon --show --noheadings | wc -l)" -gt 0 ]; then
  c_ok "已有 swap：$(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
elif [ "$MEM_MB" -ge 3500 ]; then
  c_ok "内存 ${MEM_MB}MB，够用，跳过 swap"
else
  if [ ! -f "$SWAP_FILE" ]; then
    fallocate -l "${SWAP_SIZE_MB}M" "$SWAP_FILE" 2>/dev/null || dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_SIZE_MB" status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
  fi
  swapon "$SWAP_FILE"
  grep -q "^$SWAP_FILE" /etc/fstab || echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
  # 小内存机器上把 swappiness 调低一点：让内核尽量还是用内存，swap 只当保险。
  sysctl -q -w vm.swappiness=20
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=20' >> /etc/sysctl.conf
  c_ok "已启用 ${SWAP_SIZE_MB}MB swap（写入 /etc/fstab，重启后仍生效）"
fi

# ---------------------------------------------------------------------------------------
step "3/6 Docker 镜像加速器"

DAEMON_JSON=/etc/docker/daemon.json
if [ -n "$DOCKER_MIRROR" ]; then
  mkdir -p /etc/docker
  if [ -s "$DAEMON_JSON" ] && grep -q registry-mirrors "$DAEMON_JSON"; then
    c_warn "$DAEMON_JSON 里已有 registry-mirrors，保持原样（要改请自己编辑）"
  else
    [ -s "$DAEMON_JSON" ] && cp "$DAEMON_JSON" "$DAEMON_JSON.bak.$(date +%s)"
    cat > "$DAEMON_JSON" <<EOF
{
  "registry-mirrors": ["$DOCKER_MIRROR"]
}
EOF
    systemctl daemon-reload
    systemctl restart docker
    c_ok "已写入加速器 $DOCKER_MIRROR 并重启 docker"
  fi
elif [ -s "$DAEMON_JSON" ] && grep -q registry-mirrors "$DAEMON_JSON"; then
  c_ok "已配置过镜像加速器（$DAEMON_JSON）"
else
  c_warn "没配镜像加速器。国内直连 Docker Hub 大概率拉不下 python:3.11-slim / caddy:2.8-alpine。
获取你自己的加速地址：阿里云控制台 → 容器镜像服务 ACR → 镜像工具 → 镜像加速器，
形如 https://xxxxxxxx.mirror.aliyuncs.com，然后：
  sudo DOCKER_MIRROR=https://xxxxxxxx.mirror.aliyuncs.com bash aliyun-bootstrap.sh"
fi

step "3.5/6 试拉基础镜像（这一步失败就是网络/加速器问题，不是你的代码问题）"
for img in python:3.11-slim caddy:2.8-alpine; do
  if docker image inspect "$img" >/dev/null 2>&1; then
    c_ok "$img 已在本地"
  elif timeout 420 docker pull "$img" >/dev/null 2>&1; then
    c_ok "拉取成功：$img"
  else
    c_err "拉不下来：$img。先解决镜像加速器（见上一步提示），再重跑本脚本。"
    exit 1
  fi
done

# ---------------------------------------------------------------------------------------
step "4/6 生成 / 补全 deploy/.env"

# 公网 IP：优先问阿里云元数据服务（100.100.100.200 是内网地址，不走公网，很快）
detect_ip() {
  local ip
  ip="$(timeout 5 curl -fsS http://100.100.100.200/latest/meta-data/eipv4 2>/dev/null || true)"
  [ -z "$ip" ] && ip="$(timeout 5 curl -fsS http://100.100.100.200/latest/meta-data/public-ipv4 2>/dev/null || true)"
  printf '%s' "$ip"
}

set_kv() {  # set_kv KEY VALUE：有该键就替换，没有就追加；已有非空值则不动
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    local cur
    cur="$(grep "^${key}=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
    if [ -z "$cur" ]; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
      c_ok "$key 已填入"
    else
      c_ok "$key 已有值，保持不变"
    fi
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
    c_ok "$key 已追加"
  fi
}

force_kv() {  # 你在命令行上显式指定的值，优先级高于 .env 里的旧值
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
  c_ok "$key=${val}（按你命令行传入的值写入）"
}

if [ ! -f "$ENV_FILE" ]; then
  cp .env.example "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  c_ok "已从 .env.example 生成 .env（权限 600）"
else
  c_ok ".env 已存在，只补空缺项"
fi

PUBLIC_IP="$(detect_ip)"
if [ -n "$PUBLIC_IP" ]; then
  set_kv SERVER_IP "$PUBLIC_IP"
else
  c_warn "自动识别公网 IP 失败，请手动编辑 .env 里的 SERVER_IP"
fi
# .env.example 里已经预置了 IP_PORT=18080，所以只有你在命令行显式传 IP_PORT 时才覆盖它。
if [ -n "${IP_PORT:-}" ]; then force_kv IP_PORT "$IP_PORT"; else set_kv IP_PORT 18080; fi
set_kv TOKEN_A "$(openssl rand -hex 24)"
set_kv APT_MIRROR "mirrors.aliyun.com"
set_kv PIP_INDEX_URL "https://mirrors.aliyun.com/pypi/simple/"
set_kv PIP_TRUSTED_HOST "mirrors.aliyun.com"
set_kv REQUIREMENTS "deploy/requirements-server.cn.txt"
set_kv PLAYWRIGHT_DOWNLOAD_HOST "https://cdn.npmmirror.com/binaries/playwright"

# 模型 Key 不能猜，必须你自己填；没填也能起服务，但对话/解析简历会报错。
MODEL_KEY_SET=0
for k in OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY DEEPSEEK_API_KEY MOONSHOT_API_KEY; do
  v="$(grep "^${k}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  [ -n "$v" ] && MODEL_KEY_SET=1
done
if [ "$MODEL_KEY_SET" = "0" ]; then
  c_warn "还没填任何模型 API Key。服务能起来，但一对话就会报鉴权错误。
现在填：nano $DEPLOY_DIR/.env  → 找到 OPENAI_API_KEY= 那行写上你的 key（并确认 OPENCAR_MODEL 与之匹配），
改完执行：docker compose -f $COMPOSE_FILE up -d"
fi

# ---------------------------------------------------------------------------------------
step "5/6 构建并启动（第一次构建约 5~15 分钟，取决于网络）"

docker compose -f "$COMPOSE_FILE" up -d --build

# ---------------------------------------------------------------------------------------
step "6/6 自检"

PORT="$(grep '^IP_PORT=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
PORT="${PORT:-18080}"
IP="$(grep '^SERVER_IP=' "$ENV_FILE" | head -1 | cut -d= -f2-)"

docker compose -f "$COMPOSE_FILE" ps

ok_health=0
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/_openworker/v1/health" >/dev/null 2>&1; then
    ok_health=1; break
  fi
  sleep 4
done
if [ "$ok_health" = "1" ]; then
  c_ok "后端健康检查通过：/_openworker/v1/health"
else
  c_err "后端健康检查没通过。看日志定位：
  docker compose -f $COMPOSE_FILE logs --tail=80 backend-a
  docker compose -f $COMPOSE_FILE logs --tail=40 caddy"
fi

if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/" | grep -qi '<div id="root"\|<title'; then
  c_ok "前端首页可访问（Caddy 托管正常）"
else
  c_warn "首页返回内容不对，检查 deploy/web/ 是否是 alpha 模式构建的产物"
fi

cat <<EOF

────────────────────────────────────────────────────────────────────────
本机自检完成。还差最后一步：**去阿里云控制台放行端口**。

  轻量应用服务器控制台 → 你的实例 → 安全 / 防火墙 → 添加规则
    协议 TCP，端口 ${PORT}，备注 opencareer-alpha

然后在浏览器打开：   http://${IP:-<你的公网IP>}:${PORT}

⚠️ 三件必须知道的事：
 1) 这个地址**没有登录**，谁知道就能用（还会花你的模型额度）。自测完请回控制台
    把那条 ${PORT} 端口规则**删掉**，等于对外关门。
 2) 这是明文 HTTP，不是 HTTPS。自测阶段不要上传真实简历，用脱敏的假简历。
 3) 要让其他人正式使用，请先完成 ICP 备案，再按下面的手册配置 Authing 与单域名 HTTPS：
    docs/19_DOMAIN_AUTHING_LAUNCH_RUNBOOK.md
    当前 18080 会按你的决定暂时保留，不要公开这个地址。

可选：验证每日岗位抓取（会额外拉 ~1.5GB 的 chromium 镜像，2G 内存机器建议先停掉再单独跑）
  docker compose -f $COMPOSE_FILE --profile crawl up -d --build crawler
  docker compose -f $COMPOSE_FILE --profile crawl run --rm crawler list
────────────────────────────────────────────────────────────────────────
EOF
