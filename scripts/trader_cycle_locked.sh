#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
LOG_DIR="$ROOT/logs"
LOCK_DIR="/tmp/trader-curtis-cycle.lock"
MODE="${1:-scheduled}"

mkdir -p "$LOG_DIR"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] trader cycle skipped: lock exists ($LOCK_DIR)"
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

"$ROOT/scripts/openclaw_trader_cycle.sh" "$MODE" >>"$LOG_DIR/trader-cycle.log" 2>&1

