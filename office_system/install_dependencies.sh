#!/bin/sh
set -eu
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_EXE=${PYTHON_EXE:-python3}
if ! uname -m | grep -Eq '^(aarch64|arm64)$'; then
    echo "[ERROR] Dependencies must be installed on an ARM64 machine."
    exit 1
fi
"$PYTHON_EXE" -m venv "$BASE_DIR/python"
if [ -d "$BASE_DIR/wheels" ]; then
    "$BASE_DIR/python/bin/python3" -m pip install --no-index --find-links "$BASE_DIR/wheels" -r "$BASE_DIR/requirements-kylin-arm64.txt"
else
    echo "[ERROR] Offline wheels directory not found: $BASE_DIR/wheels"
    exit 1
fi
