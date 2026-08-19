#!/bin/sh
if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ':5000 '; then
    echo "[RUNNING] Port 5000 is listening."
else
    echo "[STOPPED] Port 5000 is not listening."
fi
