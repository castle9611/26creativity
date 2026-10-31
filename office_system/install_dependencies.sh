#!/bin/sh
set -eu
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_EXE=${PYTHON_EXE:-python3}
. "$BASE_DIR/runtime_env.sh"
if ! uname -m | grep -Eq '^(aarch64|arm64)$'; then
    echo "[ERROR] Dependencies must be installed on an ARM64 machine."
    exit 1
fi
if [ -d "$BASE_DIR/runtime_packages" ]; then
    "$PYTHON_EXE" -I "$BASE_DIR/setup_runtime.py"
    RUNTIME_PYTHON="$BASE_DIR/python-linux/bin/python3.8"
else
    echo "[ERROR] Bundled runtime_packages directory is missing."
    exit 1
fi
if [ -d "$BASE_DIR/wheels" ]; then
    "$RUNTIME_PYTHON" -I -m pip --isolated install --no-index --no-cache-dir --no-user --prefix "$BASE_DIR/python-linux" --find-links "$BASE_DIR/wheels" -r "$BASE_DIR/requirements-kylin-arm64.txt"
    "$RUNTIME_PYTHON" -I -m pip --isolated check
    "$RUNTIME_PYTHON" -I "$BASE_DIR/check_portable.py"
    touch "$BASE_DIR/python-linux/.oa-dependencies-ready"
else
    echo "[ERROR] Offline wheels directory not found: $BASE_DIR/wheels"
    exit 1
fi
