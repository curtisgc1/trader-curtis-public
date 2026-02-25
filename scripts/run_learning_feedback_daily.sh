#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/learning-daily.log"
LOCK_DIR="/tmp/trader-curtis-learning-daily.lock"
LOCK_PID_FILE="$LOCK_DIR/pid"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

mkdir -p "$LOG_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ -d "$LOCK_DIR" ]; then
  if [ -f "$LOCK_PID_FILE" ]; then
    old_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
      echo "learning_daily=skipped reason=lock_active pid=$old_pid" | tee -a "$LOG_FILE"
      exit 0
    fi
  fi
  rm -f "$LOCK_PID_FILE" >/dev/null 2>&1 || true
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "learning_daily=skipped reason=lock_create_failed" | tee -a "$LOG_FILE"
  exit 0
fi
echo "$$" > "$LOCK_PID_FILE"
cleanup() {
  rm -f "$LOCK_PID_FILE" >/dev/null 2>&1 || true
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] learning_daily=start python=$PYTHON_BIN" | tee -a "$LOG_FILE"
MISSED_RESOLVER_FORCE=1 HORIZON_RESOLVER_FORCE=1 "$PYTHON_BIN" "$ROOT/update_learning_feedback.py" | tee -a "$LOG_FILE"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] learning_daily=ok" | tee -a "$LOG_FILE"
