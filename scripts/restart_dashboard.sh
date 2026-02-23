#!/bin/bash
set -euo pipefail
BASE="/Users/Shared/curtis/trader-curtis"
APP_DIR="$BASE/dashboard-ui"
LOG_OUT="$APP_DIR/logs/dashboard.out.log"
LOG_ERR="$APP_DIR/logs/dashboard.err.log"
PY="$APP_DIR/.venv/bin/python"

mkdir -p "$APP_DIR/logs"

pid=$(lsof -iTCP:8090 -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR==2 {print $2}')
if [ -n "${pid:-}" ]; then
  kill "$pid" || true
  sleep 1
fi

nohup "$PY" "$APP_DIR/app.py" >> "$LOG_OUT" 2>> "$LOG_ERR" &
sleep 1

curl -sS -o /tmp/dash-health.json http://127.0.0.1:8090/api/system-health
printf "Dashboard restarted with %s\n" "$PY"
