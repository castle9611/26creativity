#!/bin/sh
set -eu
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$BASE_DIR"

if [ "$(uname -s)" != "Linux" ] || ! uname -m | grep -Eq '^(aarch64|arm64)$'; then
    echo "[ERROR] This package requires a Linux ARM64 (aarch64) system."
    exit 1
fi

. "$BASE_DIR/runtime_env.sh"
if [ ! -x "$RUNTIME_PYTHON" ] || [ ! -f "$BASE_DIR/python-linux/.oa-dependencies-ready" ]; then
    echo "[INFO] First start: preparing bundled Python and dependencies offline."
    sh "$BASE_DIR/install_dependencies.sh"
fi

mkdir -p "$BASE_DIR/data/uploads" "$BASE_DIR/logs"
"$RUNTIME_PYTHON" -I "$BASE_DIR/check_portable.py"
"$RUNTIME_PYTHON" -I "$BASE_DIR/health_check.py"
if [ -f "$BASE_DIR/logs/server.pid" ]; then
    OLD_PID=$(cat "$BASE_DIR/logs/server.pid")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[INFO] Service is already running, PID $OLD_PID."
        exit 0
    fi
fi
nohup "$RUNTIME_PYTHON" -I "$BASE_DIR/run.py" >>"$BASE_DIR/logs/server.log" 2>>"$BASE_DIR/logs/server-error.log" &
echo $! > "$BASE_DIR/logs/server.pid"
echo "[OK] OA system started, PID $!."
echo "[INFO] Open http://127.0.0.1:5000"
