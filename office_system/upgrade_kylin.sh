#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET_DIR=${1:-}
if [ -z "$TARGET_DIR" ]; then
    echo "Usage: ./upgrade_kylin.sh /path/to/existing/office_system"
    exit 1
fi
if [ ! -f "$TARGET_DIR/data/database.db" ]; then
    echo "[ERROR] Existing database not found: $TARGET_DIR/data/database.db"
    exit 1
fi
if [ "$PACKAGE_DIR" = "$TARGET_DIR" ]; then
    echo "[ERROR] Extract the upgrade package to a separate directory."
    exit 1
fi

PYTHON_EXE="$TARGET_DIR/python/bin/python3"
if [ ! -x "$PYTHON_EXE" ]; then PYTHON_EXE=$(command -v python3 || true); fi
if [ -z "$PYTHON_EXE" ]; then echo "[ERROR] Python 3 not found."; exit 1; fi

echo "[1/5] Stopping existing service"
if [ -x "$TARGET_DIR/stop.sh" ]; then "$TARGET_DIR/stop.sh" || true; fi
echo "[2/5] Backing up existing database"
"$PYTHON_EXE" "$TARGET_DIR/backup.py" backup
echo "[3/5] Updating program files"
for name in app run.py wsgi.py migrate.py health_check.py backup.py start.sh stop.sh status.sh install_dependencies.sh convert_video.sh requirements-kylin-arm64.txt KYLIN_ARM64_DEPLOY.md; do
    if [ -e "$PACKAGE_DIR/$name" ]; then cp -R "$PACKAGE_DIR/$name" "$TARGET_DIR/"; fi
done
chmod +x "$TARGET_DIR"/*.sh
echo "[4/5] Migrating database without deleting existing data"
cd "$TARGET_DIR"
"$PYTHON_EXE" migrate.py
echo "[5/5] Starting service"
"$TARGET_DIR/start.sh"
echo "[OK] Upgrade complete. Existing data directory was preserved."
