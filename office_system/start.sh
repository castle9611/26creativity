#!/bin/sh
set -eu
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$BASE_DIR"

if [ "$(uname -s)" != "Linux" ] || ! uname -m | grep -Eq '^(aarch64|arm64)$'; then
    echo "[ERROR] This package requires a Linux ARM64 (aarch64) system."
    exit 1
fi

PYTHON_EXE="$BASE_DIR/python/bin/python3"
if [ ! -x "$PYTHON_EXE" ]; then
    PYTHON_EXE=$(command -v python3 || true)
fi
if [ -z "$PYTHON_EXE" ]; then
    echo "[ERROR] Python 3 was not found. See KYLIN_ARM64_DEPLOY.md."
    exit 1
fi

mkdir -p "$BASE_DIR/data/uploads" "$BASE_DIR/logs"
"$PYTHON_EXE" "$BASE_DIR/health_check.py"
if [ -f "$BASE_DIR/logs/server.pid" ]; then
    OLD_PID=$(cat "$BASE_DIR/logs/server.pid")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[INFO] Service is already running, PID $OLD_PID."
        exit 0
    fi
fi
nohup "$PYTHON_EXE" "$BASE_DIR/run.py" >>"$BASE_DIR/logs/server.log" 2>>"$BASE_DIR/logs/server-error.log" &
echo $! > "$BASE_DIR/logs/server.pid"
echo "[OK] OA system started, PID $!."
echo "[INFO] Open http://127.0.0.1:5000"
