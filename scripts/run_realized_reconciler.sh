#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/realized-reconciler.log"
LOCK_DIR="/tmp/trader-curtis-realized-reconciler.lock"
LOCK_PID_FILE="$LOCK_DIR/pid"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

mkdir -p "$LOG_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

sql() { sqlite3 "$DB" "$1" 2>/dev/null || true; }
set_control() {
  local key="$1"
  local value="$2"
  local esc
  esc="$(printf "%s" "$value" | sed "s/'/''/g")"
  sql "
    CREATE TABLE IF NOT EXISTS execution_controls (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    INSERT INTO execution_controls (key, value, updated_at)
    VALUES ('${key}', '${esc}', datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
  " >/dev/null
}

if [ -d "$LOCK_DIR" ]; then
  if [ -f "$LOCK_PID_FILE" ]; then
    old_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
      echo "realized_reconciler=skipped reason=lock_active pid=$old_pid" | tee -a "$LOG_FILE"
      exit 0
    fi
  fi
  rm -f "$LOCK_PID_FILE" >/dev/null 2>&1 || true
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "realized_reconciler=skipped reason=lock_create_failed" | tee -a "$LOG_FILE"
  exit 0
fi
echo "$$" > "$LOCK_PID_FILE"

stage="init"
cleanup() {
  local rc=$?
  rm -f "$LOCK_PID_FILE" >/dev/null 2>&1 || true
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
  if [ -f "$DB" ]; then
    if [ $rc -eq 0 ]; then
      set_control "runtime:realized_reconciler_last_status" "ok"
      set_control "runtime:realized_reconciler_last_success_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    else
      set_control "runtime:realized_reconciler_last_status" "error:${stage}"
    fi
    set_control "runtime:realized_reconciler_last_attempt_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi
  exit $rc
}
trap cleanup EXIT

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] realized_reconciler=start python=$PYTHON_BIN" | tee -a "$LOG_FILE"

stage="alpaca_sync"
alpaca_out="$($PYTHON_BIN "$ROOT/sync_alpaca_order_status.py" 2>&1)"
echo "$alpaca_out" | tee -a "$LOG_FILE"

stage="polymarket_settle"
poly_out="$($PYTHON_BIN "$ROOT/reconcile_realized_outcomes.py" 2>&1)"
echo "$poly_out" | tee -a "$LOG_FILE"

stage="learning_feedback"
learn_out="$(SKIP_HEAVY_RESOLVERS=1 $PYTHON_BIN "$ROOT/update_learning_feedback.py" 2>&1)"
echo "$learn_out" | tee -a "$LOG_FILE"

stage="readiness_gate"
"$ROOT/scripts/grpo_readiness_gate.sh" >>"$LOG_FILE" 2>&1 || true

summary="$(printf "alpaca=%s | poly=%s | learn=%s" "$alpaca_out" "$poly_out" "$learn_out" | cut -c1-900)"
set_control "runtime:realized_reconciler_last_summary" "$summary"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] realized_reconciler=ok" | tee -a "$LOG_FILE"
