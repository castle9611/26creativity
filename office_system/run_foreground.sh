#!/bin/sh
set -eu
BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$BASE_DIR"
. "$BASE_DIR/runtime_env.sh"
"$RUNTIME_PYTHON" -I "$BASE_DIR/check_portable.py"
exec "$RUNTIME_PYTHON" -I "$BASE_DIR/run.py"
