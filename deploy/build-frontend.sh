#!/usr/bin/env bash
# 构建云端 alpha 的前端静态产物到 deploy/web/（Caddy 直接托管这个目录）。
#
# 用法（在仓库任意目录下都能跑）：
#   bash deploy/build-frontend.sh
#
# 需要 Node 18+ 和 npm。在 2 核 4G 的小机器上首次 npm ci 可能要几分钟；
# 也可以在自己电脑上跑完，再把 deploy/web/ 整个目录 scp 到服务器。
#
# 为什么是 --mode alpha：这个模式产出的是「同源」版本——API 前缀固定为 /_openworker、
# 且**不把 token 内联进 JS**（surfaces/gui/src/api.ts:8-31）。默认 `npm run build` 会把
# http://127.0.0.1:8765 打进包里，浏览器版必坏。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="$ROOT/surfaces/gui"
OUT="$ROOT/deploy/web"

command -v npm >/dev/null || { echo "缺少 npm，请先装 Node.js 18+"; exit 1; }

cd "$GUI"
if [ "${SKIP_NPM_CI:-0}" != "1" ]; then
  echo "==> npm ci（安装前端依赖）"
  npm ci
fi

echo "==> tsc 类型检查"
npx tsc

echo "==> vite build --mode alpha → $OUT"
export VITE_OPENCAR_RELEASE="${VITE_OPENCAR_RELEASE:-${OPENCAR_RELEASE:-unknown}}"
npx vite build --mode alpha --outDir "$OUT" --emptyOutDir

test -f "$OUT/index.html" || { echo "构建失败：$OUT/index.html 不存在"; exit 1; }
# 这两条是护栏：alpha 产物里既不该出现 127.0.0.1:8765，也不该出现任何 token。
if grep -rqs "127\.0\.0\.1:8765" "$OUT"; then
  echo "警告：产物里出现了 127.0.0.1:8765，说明不是 alpha 模式构建，浏览器里会连不上后端" >&2
  exit 1
fi

echo "==> 完成。产物大小："
du -sh "$OUT"
echo "接下来：cd deploy && docker compose up -d --build"
