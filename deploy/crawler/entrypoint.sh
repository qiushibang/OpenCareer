#!/bin/sh
# 抓取容器的调度循环：每天在 CRAWL_AT 附近跑一次 crawl_cli，然后继续睡。
#
# 为什么不用 cron：容器里跑 cron 要么得用 root、要么得额外把环境变量导给 cron 子进程，
# 日志也不会自然进 docker logs。一个 sh 循环更透明——`docker compose logs -f crawler`
# 直接就能看到每天抓了什么、哪个源挂了。
#
# 为什么不用项目自带的 Scheduler：那个跑在 FastAPI 进程内（coworker/automation/scheduler.py），
# 而抓取要独立于用户后端存活，两者的生命周期不该绑在一起。
set -eu

TARGETS="${CRAWL_TARGETS:-}"
AT="${CRAWL_AT:-04:00}"
JITTER_MINUTES="${CRAWL_JITTER_MINUTES:-25}"
RUN_ON_START="${CRAWL_RUN_ON_START:-0}"
RESUMABLE_BATCHES="${CRAWL_RESUMABLE_BATCHES:-12}"

# 允许直接把参数当命令跑，方便手动介入：
#   docker compose run --rm crawler once --only tencent-wxg-experienced
#   docker compose run --rm crawler list
case "${1:-}" in
  list)  shift; exec python -m extensions.career_mcp.crawl_cli --list "$@" ;;
  once)  shift; MODE=once ;;
  sh|bash) exec "$@" ;;
  "")    MODE=loop ;;
  *)     exec "$@" ;;
esac

build_args() {
  # 把空格分隔的 CRAWL_TARGETS 展开成多个 --data-dir
  set --
  for target in $TARGETS; do
    set -- "$@" --data-dir "$target"
  done
  # CRAWL_ONLY / CRAWL_SKIP 让你不重建镜像就能临时调整源清单：
  # 比如某个站点改版天天报错，先 CRAWL_SKIP=xxx 把它摘掉，别让它每天刷日志。
  if [ -n "${CRAWL_ONLY:-}" ]; then
    set -- "$@" --only "$CRAWL_ONLY"
  fi
  if [ -n "${CRAWL_SKIP:-}" ]; then
    set -- "$@" --skip "$CRAWL_SKIP"
  fi
  echo "$@"
}

run_once() {
  extra="$*"
  # shellcheck disable=SC2046  # 故意让 build_args 的输出按空格分词
  if python -m extensions.career_mcp.crawl_cli $(build_args) --json $extra; then
    echo "[crawler] 本轮抓取完成（全部数据源成功）"
  else
    code=$?
    # 退出码 1 = 部分数据源失败，属于日常噪音（站点改版、风控、超时），不该让容器退出。
    if [ "$code" = "1" ]; then
      echo "[crawler] 本轮抓取部分失败，已写入成功的部分，等下一轮重试" >&2
    else
      echo "[crawler] 本轮抓取异常退出（code=$code）" >&2
    fi
  fi
  if [ -n "${DATABASE_URL:-}" ]; then
    if python -m extensions.career_mcp.crawl_cli \
      --resumable-only \
      --resumable-batches "$RESUMABLE_BATCHES"; then
      echo "[crawler] 字节全量来源本批续跑完成"
    else
      code=$?
      echo "[crawler] 字节全量来源续跑未完成（code=$code），下轮从 checkpoint 继续" >&2
    fi
  fi
}

seconds_until() {
  # 算到下一个 AT 时刻还有多少秒；已过今天的点就顺延到明天。再叠加 0..JITTER 分钟的随机抖动，
  # 避免每天固定同一秒去打招聘站点（也避免多台机器撞在一起）。
  python - "$AT" "$JITTER_MINUTES" <<'PY'
import random, sys
from datetime import datetime, timedelta

at, jitter = sys.argv[1], int(sys.argv[2])
hour, _, minute = at.partition(":")
now = datetime.now()
target = now.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
delay = (target - now).total_seconds() + random.uniform(0, jitter * 60)
print(int(delay))
PY
}

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[crawler] 目标库：共享 PostgreSQL Job Catalog"
elif [ -z "$TARGETS" ]; then
  echo "[crawler] CRAWL_TARGETS 为空，将只写 CAREER_DATA_DIR=${CAREER_DATA_DIR:-<默认>}" >&2
else
  echo "[crawler] 目标库：$TARGETS"
fi

if [ "$MODE" = "once" ]; then
  run_once "$@"
  exit 0
fi

echo "[crawler] 调度已启动：每天 $AT（+0~${JITTER_MINUTES}min 抖动），时区 ${TZ:-UTC}"
if [ "$RUN_ON_START" = "1" ]; then
  echo "[crawler] CRAWL_RUN_ON_START=1，先立即跑一轮"
  run_once
fi

while true; do
  delay="$(seconds_until)"
  echo "[crawler] 下一轮在 $((delay / 60)) 分钟后（约 $(date -d "+${delay} seconds" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '?')）"
  sleep "$delay"
  run_once
done
