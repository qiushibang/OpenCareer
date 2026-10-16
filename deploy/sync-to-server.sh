#!/usr/bin/env bash
# 把本地改动同步到服务器并重启云端 alpha —— 「在 Trae 里改完代码，一条命令上线」。
#
# 在**你自己的电脑**上执行（不是服务器上），需要本机装了 rsync（macOS 自带）和 ssh 免密或输密码。
#
# 用法：
#   bash deploy/sync-to-server.sh root@203.0.113.10
#   SKIP_FRONTEND=1 bash deploy/sync-to-server.sh root@203.0.113.10      # 只改了后端 Python，跳过前端构建
#   NO_BUILD=1 bash deploy/sync-to-server.sh root@203.0.113.10           # 只改了前端/Caddyfile，不重建镜像
#   REMOTE_DIR=/opt/opencareer bash deploy/sync-to-server.sh root@203.0.113.10
#
# 它做四件事：
#   1) 本地用 alpha 模式构建前端（产物在 deploy/web/）
#   2) rsync 代码 + 产物到服务器（排除 node_modules / .git / .env 等）
#   3) 服务器上 docker compose up -d --build（默认会重建后端镜像）
#   4) 远端自检 /v1/health，并把最近日志打回来
#
# ⚠️ 故意**不同步** deploy/.env：服务器上的密钥和邀请码只存在服务器上，别被本地文件覆盖。
set -eEuo pipefail

TARGET="${1:-}"
[ -n "$TARGET" ] || { echo "用法：bash deploy/sync-to-server.sh root@<公网IP>"; exit 1; }

# Production uses a dedicated deployment key.  Reuse it for rsync and every
# subsequent ssh call so a successful upload cannot be followed by a command
# that silently falls back to an unrelated default identity.
SSH_ARGS=()
if [ -n "${OPENCAR_SSH_KEY:-}" ]; then
  SSH_ARGS=(-i "$OPENCAR_SSH_KEY")
fi
remote() { ssh "${SSH_ARGS[@]}" "$TARGET" "$@"; }
RSYNC_RSH_COMMAND="ssh"
if [ -n "${OPENCAR_SSH_KEY:-}" ]; then
  RSYNC_RSH_COMMAND="ssh -i $OPENCAR_SSH_KEY"
fi

REMOTE_DIR="${REMOTE_DIR:-/opt/opencareer}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Production synchronization is allowed only after a complete, checksum-verified
# recovery point exists.  This keeps the convenient script from bypassing the
# mandatory PostgreSQL restore gate in docs/18_BACKUP_AND_ROLLBACK_RUNBOOK.md.
BACKUP_ID="${OPENCAR_BACKUP_ID:-}"
[[ "$BACKUP_ID" =~ ^[A-Za-z0-9._-]{1,96}$ ]] || {
  echo "缺少有效 OPENCAR_BACKUP_ID；请先按文档 18 创建并验证恢复点" >&2
  exit 1
}
remote "set -e; backup=/opt/opencareer-backups/$BACKUP_ID; \
  test -f \"\$backup/SHA256SUMS\"; \
  test -f \"\$backup/postgres-final.dump\"; \
  test -f \"\$backup/frontend.tgz\"; \
  test -f \"\$backup/meta/backend-image-id.txt\"; \
  test -f \"\$backup/config/Caddyfile\"; \
  test -f \"\$backup/config/docker-compose.yml\"; \
  test -f \"\$backup/meta/final-restore-table-counts.tsv\"; \
  test -f \"\$backup/meta/final-restore-blob-manifest.tsv\"; \
  cd \"\$backup\"; sha256sum -c SHA256SUMS >/dev/null; \
  test \"\$(cat meta/backend-image-id.txt)\" = \"\$(docker inspect opencareer-alpha-backend-a-1 --format '{{.Image}}')\"; \
  cmp -s config/Caddyfile $REMOTE_DIR/deploy/Caddyfile; \
  cmp -s config/docker-compose.yml $REMOTE_DIR/deploy/$COMPOSE_FILE; \
  test \"\$(tar -xOf frontend.tgz ./index.html | sha256sum | cut -d' ' -f1)\" = \
       \"\$(sha256sum $REMOTE_DIR/deploy/web/index.html | cut -d' ' -f1)\""

# The convenience path never applies a new schema.  Database releases require
# the maintenance-window candidate/restore workflow because an automatic image
# rollback cannot safely undo a forward migration.
REMOTE_SCHEMA_VERSION="$(remote "sudo -u postgres psql -d opencareer_prod -Atc 'select coalesce(max(version),0) from opencareer_meta.schema_migrations'")"
LOCAL_SCHEMA_VERSION="$(find coworker/storage/postgres/sql -maxdepth 1 -type f -name '[0-9][0-9][0-9][0-9]_*.sql' -exec basename '{}' \; | cut -c1-4 | sort -n | tail -1 | sed 's/^0*//')"
LOCAL_SCHEMA_VERSION="${LOCAL_SCHEMA_VERSION:-0}"
[[ "$REMOTE_SCHEMA_VERSION" =~ ^[0-9]+$ && "$LOCAL_SCHEMA_VERSION" =~ ^[0-9]+$ ]] || {
  echo "无法确认数据库迁移版本，停止发布" >&2
  exit 1
}
if [ "$LOCAL_SCHEMA_VERSION" -gt "$REMOTE_SCHEMA_VERSION" ]; then
  echo "检测到新数据库迁移；请按文档 18 的候选库和维护窗口流程发布" >&2
  exit 1
fi

# The browser submits its compiled release identifier to the backend.  Read the
# non-secret identifier from the server and fail closed if a caller tries to
# publish a frontend built for a different backend release.
REMOTE_RELEASE="$(remote "sed -n 's/^OPENCAR_RELEASE=//p' $REMOTE_DIR/deploy/.env | tail -1")"
LOCAL_RELEASE="${OPENCAR_RELEASE:-${REMOTE_RELEASE:-unknown}}"
[[ "$LOCAL_RELEASE" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || {
  echo "OPENCAR_RELEASE 格式无效" >&2
  exit 1
}
if [ -n "$REMOTE_RELEASE" ] && [ "$LOCAL_RELEASE" != "$REMOTE_RELEASE" ]; then
  echo "本地 OPENCAR_RELEASE 与服务器不一致；请先安全更新服务器配置再发布" >&2
  exit 1
fi
export OPENCAR_RELEASE="$LOCAL_RELEASE"

# Keep the candidate outside REMOTE_DIR.  The source rsync below uses
# --delete on REMOTE_DIR and would otherwise remove the candidate before the
# atomic index switch.
WEB_STAGE="${REMOTE_DIR}.releases/web-$BACKUP_ID"
ROLLBACK_ARMED=0
rollback_release() {
  local status="$1"
  trap - ERR
  if [ "$ROLLBACK_ARMED" = "1" ]; then
    echo "发布未完成，正在从已验证恢复点回滚运行版本" >&2
    remote "set -e; \
      backup=/opt/opencareer-backups/$BACKUP_ID; \
      image_id=\$(cat \"\$backup/meta/backend-image-id.txt\"); \
      docker image inspect \"\$image_id\" >/dev/null; \
      docker tag \"\$image_id\" opencareer-backend:domain; \
      cp \"\$backup/config/Caddyfile\" $REMOTE_DIR/deploy/Caddyfile; \
      cp \"\$backup/config/docker-compose.yml\" $REMOTE_DIR/deploy/$COMPOSE_FILE; \
      restore=$REMOTE_DIR/deploy/web.rollback-$BACKUP_ID; \
      mkdir -p \"\$restore\" $REMOTE_DIR/deploy/web/assets; \
      tar -xzf \"\$backup/frontend.tgz\" -C \"\$restore\"; \
      cp -a \"\$restore/assets/.\" $REMOTE_DIR/deploy/web/assets/; \
      cp \"\$restore/index.html\" $REMOTE_DIR/deploy/web/index.html.rollback; \
      mv $REMOTE_DIR/deploy/web/index.html.rollback $REMOTE_DIR/deploy/web/index.html; \
      cd $REMOTE_DIR/deploy; \
      docker compose -f $COMPOSE_FILE up -d --no-build backend-a caddy; \
      docker compose -f $COMPOSE_FILE --profile crawl up -d --no-build crawler"
  fi
  exit "$status"
}
trap 'rollback_release $?' ERR

if [ "${SKIP_FRONTEND:-0}" != "1" ]; then
  echo "==> 1/4 本地构建前端（alpha 模式）"
  bash deploy/build-frontend.sh
else
  echo "==> 1/4 跳过前端构建（SKIP_FRONTEND=1）"
  [ -f deploy/web/index.html ] || { echo "但 deploy/web/index.html 不存在，第一次同步必须构建"; exit 1; }
fi
grep -rFqs -- "$OPENCAR_RELEASE" deploy/web || {
  echo "前端产物与 OPENCAR_RELEASE 不匹配，请重新构建" >&2
  exit 1
}

echo "==> 2/4 同步到 $TARGET:$REMOTE_DIR"
# --delete 只在同步的目录范围内生效；deploy/.env 用 --exclude 保护，不会被删。
# 静态前端单独进入候选目录，最后只原子替换 index.html；运行中的 Caddy 不会看见
# rsync 到一半的资源集合，旧哈希资源继续保留用于回滚。
remote "mkdir -p ${REMOTE_DIR}.releases"
RSYNC_RSH="$RSYNC_RSH_COMMAND" rsync -az --delete deploy/web/ "$TARGET:$WEB_STAGE/"
ROLLBACK_ARMED=1
RSYNC_RSH="$RSYNC_RSH_COMMAND" rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.venv' \
  --exclude '.local-state' \
  --exclude '.zcode' \
  --exclude '.env' \
  --exclude 'surfaces/gui/src-tauri/target' \
  --exclude 'surfaces/gui/dist' \
  --exclude 'artifacts' \
  --exclude 'deploy/.env' \
  --exclude 'deploy/web' \
  ./ "$TARGET:$REMOTE_DIR/"

if [ "${NO_BUILD:-0}" = "1" ]; then
  echo "==> 3/4 只重启容器（NO_BUILD=1，不重建镜像）"
  # 前端是挂载进 Caddy 的，改前端只要重启 caddy 就生效；改了 Caddyfile 也是这条。
  remote "cd $REMOTE_DIR/deploy && docker compose -f $COMPOSE_FILE up -d"
else
  echo "==> 3/4 服务器上重建并启动（改了 Python 依赖/后端代码走这条）"
  remote "cd $REMOTE_DIR/deploy && docker compose -f $COMPOSE_FILE up -d --build"
fi
remote "set -e; \
  test -f $WEB_STAGE/index.html; \
  mkdir -p $REMOTE_DIR/deploy/web/assets; \
  cp -a $WEB_STAGE/assets/. $REMOTE_DIR/deploy/web/assets/; \
  find $WEB_STAGE -maxdepth 1 -type f ! -name index.html -exec cp '{}' $REMOTE_DIR/deploy/web/ ';'; \
  cp $WEB_STAGE/index.html $REMOTE_DIR/deploy/web/index.html.next; \
  mv $REMOTE_DIR/deploy/web/index.html.next $REMOTE_DIR/deploy/web/index.html"
remote "cd $REMOTE_DIR/deploy && docker compose -f $COMPOSE_FILE exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile"

echo "==> 4/4 远端自检"
DOMAIN="$(remote "grep '^BASE_DOMAIN=' $REMOTE_DIR/deploy/.env | head -1 | cut -d= -f2-")"
[ -n "$DOMAIN" ] || { echo '未配置正式域名，停止健康检查'; exit 1; }
remote "cd $REMOTE_DIR/deploy \
  && docker compose -f $COMPOSE_FILE ps \
  && (curl -fsS --max-time 8 https://app.${DOMAIN}/_openworker/v1/health && echo ' <- health OK' \
      || (echo '健康检查失败，将执行自动回滚' && exit 1))"

ROLLBACK_ARMED=0
trap - ERR

echo "完成。浏览器刷新看效果（前端有强缓存的话按 Shift+刷新）。"
