#!/usr/bin/env bash
# Launch a disposable, localhost-only Career alpha. Ctrl-C stops both processes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_BIN="$ROOT/.venv/bin/openworker-server"
STATE_DIR="${OPENCAR_ALPHA_STATE_DIR:-$ROOT/.local-state/alpha-test}"
CAREER_DIR="${OPENCAR_ALPHA_CAREER_DIR:-$ROOT/.local-state/alpha-career}"
WORKSPACE="$STATE_DIR/workspace"
PORT="${OPENCAR_ALPHA_PORT:-8766}"
UI_PORT="${OPENCAR_ALPHA_UI_PORT:-1421}"
MODEL="${OPENCAR_ALPHA_MODEL:-deepseek:deepseek-v4-flash}"
RUNTIME_DIR="$(mktemp -d -t opencareer-alpha.XXXXXX)"
SERVER_PID=""
UI_PID=""

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [ -n "$UI_PID" ] && kill "$UI_PID" 2>/dev/null || true
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  wait "$UI_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  rm -rf "$RUNTIME_DIR"
  exit "$status"
}
trap cleanup EXIT INT TERM

for command in "$SERVER_BIN" npm curl; do
  if ! command -v "$command" >/dev/null 2>&1 && [ ! -x "$command" ]; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

if curl --silent --fail "http://127.0.0.1:$PORT/v1/health" >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop the existing OpenWorker server first." >&2
  exit 1
fi
if curl --silent --fail "http://localhost:$UI_PORT/" >/dev/null 2>&1; then
  echo "Port $UI_PORT is already in use. Choose OPENCAR_ALPHA_UI_PORT or stop that server first." >&2
  exit 1
fi

mkdir -p "$WORKSPACE/.coworker" "$STATE_DIR" "$CAREER_DIR"
if [ ! -e "$WORKSPACE/.coworker/skills" ]; then
  ln -s "$ROOT/.coworker/skills" "$WORKSPACE/.coworker/skills"
fi
printf '{\n  "mcpServers": {\n    "career": {\n      "command": "%s",\n      "args": ["-m", "extensions.career_mcp.server"],\n      "enabled": true\n    }\n  }\n}\n' \
  "$ROOT/.venv/bin/python" > "$WORKSPACE/.coworker/mcp.json"

COWORKER_STATE_DIR="$STATE_DIR" CAREER_DATA_DIR="$CAREER_DIR" \
  "$ROOT/.venv/bin/python" "$ROOT/scripts/seed_alpha_demo.py" >"$RUNTIME_DIR/seed.log"

# The alpha UI serves on $UI_PORT (1421), which is outside the default origin
# allowlist (Tauri's 1420) — without this the session WebSocket is rejected 403
# and turns never reach the backend.
OPENCAR_ALPHA_TEST=1 OPENCAR_ALPHA_WORKSPACE="$WORKSPACE" OPENCAR_EXTRA_ORIGINS="http://localhost:$UI_PORT" \
  COWORKER_STATE_DIR="$STATE_DIR" CAREER_DATA_DIR="$CAREER_DIR" \
  "$SERVER_BIN" --cwd "$WORKSPACE" --host 127.0.0.1 --port "$PORT" --model "$MODEL" \
  >"$RUNTIME_DIR/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
  if curl --silent --fail "http://127.0.0.1:$PORT/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if ! curl --silent --fail "http://127.0.0.1:$PORT/v1/health" >/dev/null 2>&1; then
  cat "$RUNTIME_DIR/server.log" >&2
  exit 1
fi

(
  cd "$ROOT/surfaces/gui"
  COWORKER_STATE_DIR="$STATE_DIR" VITE_ALPHA_BACKEND_PORT="$PORT" \
    VITE_ALPHA_UI_PORT="$UI_PORT" npm run alpha
) >"$RUNTIME_DIR/ui.log" 2>&1 &
UI_PID=$!

for _ in $(seq 1 40); do
  if curl --silent --fail "http://localhost:$UI_PORT/" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if ! curl --silent --fail "http://localhost:$UI_PORT/" >/dev/null 2>&1; then
  cat "$RUNTIME_DIR/ui.log" >&2
  exit 1
fi

echo "Career Alpha is available only on this Mac: http://localhost:$UI_PORT"
echo "No public tunnel is created. Press Ctrl-C to stop the isolated test environment."
wait "$UI_PID"
