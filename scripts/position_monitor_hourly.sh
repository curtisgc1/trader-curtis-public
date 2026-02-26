#!/usr/bin/env bash
# position_monitor_hourly.sh
# Runs every hour during trading hours to:
#   1. Refresh Kelly signals (fast, reads existing candidates)
#   2. Execute pending position intents (stops, take-profit alerts)
#
# Runs independently of the full scan cycle so positions are managed
# between the 5 scheduled full-cycle runs.

set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/position-monitor.log"
LOCK_DIR="/tmp/trader-position-monitor.lock"
PY_BIN="$(command -v python3.11 || command -v python3)"

mkdir -p "$LOG_DIR"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1" | tee -a "$LOG_FILE"
}

# Single-instance lock
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "position_monitor=skipped reason=lock_active"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# Check master enabled flag before doing anything
ENABLED=$(sqlite3 -cmd ".timeout 5000" "$DB" \
  "SELECT value FROM execution_controls WHERE key='agent_master_enabled' LIMIT 1;" \
  2>/dev/null || echo "0")

if [ "$ENABLED" != "1" ]; then
  log "position_monitor=skipped reason=agent_master_disabled"
  exit 0
fi

log "position_monitor=start"

# 1. Refresh Kelly signals against current candidates
if [ -f "$ROOT/kelly_signal.py" ]; then
  log "step=kelly_signal"
  "$PY_BIN" "$ROOT/kelly_signal.py" 2>&1 | tee -a "$LOG_FILE" || log "kelly_signal=failed"
fi

# 2. Reassess open positions using 2-of-3 signal scoring
if [ -f "$ROOT/reassess_open_positions.py" ]; then
  log "step=reassess_open_positions"
  "$PY_BIN" "$ROOT/reassess_open_positions.py" 2>&1 | tee -a "$LOG_FILE" || log "reassess_open_positions=failed"
fi

# 3. Execute pending position intents (stops, take-profit alerts)
if [ -f "$ROOT/execute_position_intents.py" ]; then
  log "step=execute_position_intents"
  "$PY_BIN" "$ROOT/execute_position_intents.py" 2>&1 | tee -a "$LOG_FILE" || log "execute_position_intents=failed"
fi

# Quick summary
PENDING=$(sqlite3 -cmd ".timeout 5000" "$DB" \
  "SELECT COUNT(*) FROM trade_intents WHERE status LIKE 'manage_%';" \
  2>/dev/null || echo "?")
KELLY_PASS=$(sqlite3 -cmd ".timeout 5000" "$DB" \
  "SELECT COUNT(*) FROM kelly_signals WHERE verdict='pass' AND computed_at=(SELECT MAX(computed_at) FROM kelly_signals);" \
  2>/dev/null || echo "?")

log "position_monitor=done pending_intents=${PENDING} kelly_pass=${KELLY_PASS}"
