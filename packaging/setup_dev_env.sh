#!/usr/bin/env bash
# One-time dev bootstrap for a fresh checkout: creates the Python venv every
# from-source flow expects at .venv — the browser dev flow runs its
# openworker-server directly, and the Tauri desktop shell falls back to it when
# no packaged sidecar binary is present (src-tauri/src/lib.rs, resolution step 3).
#
# Usage: bash packaging/setup_dev_env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"

python3 -m venv "$VENV"
# The coworker package (server, engine, connectors) + inbound-messaging extras.
# aisuite comes in as a regular dependency (git-pinned in pyproject.toml until
# the next PyPI release). The [ocr] extra carries the fixed rapidocr/onnxruntime/
# opencv/numpy stack (it left the core dependencies so the headless cloud image can
# skip ~300 MB of native wheels) — desktop/dev flows must keep installing it.
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$ROOT[messaging,dev,ocr]"

"$VENV/bin/python" -c 'import aisuite, coworker' # fail loudly if the wiring broke
echo "Ready: $VENV"
echo "  server: $VENV/bin/openworker-server --cwd /path/to/your/project --port 8765"
