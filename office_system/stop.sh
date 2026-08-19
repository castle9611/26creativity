#!/bin/sh
set -eu
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PID_FILE="$BASE_DIR/logs/server.pid"
if [ ! -f "$PID_FILE" ]; then
    echo "[INFO] No PID file; the foreground service is not managed by this script."
    exit 0
fi
PID=$(cat "$PID_FILE")
case "$PID" in *[!0-9]*|'') echo "[ERROR] Invalid PID file."; exit 1;; esac
kill "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "[OK] Service stopped."
