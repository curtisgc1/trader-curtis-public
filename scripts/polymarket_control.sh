#!/usr/bin/env bash
set -euo pipefail

BASE="/Users/Shared/curtis/trader-curtis"
DB="$BASE/data/trades.db"
EXEC="$BASE/execution_polymarket.py"
WRAP="$BASE/scripts/with_polymarket_keychain.sh"
APPROVE="$BASE/approve_polymarket_candidate.py"

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 is required" >&2
  exit 1
fi

usage() {
  cat <<'EOF'
Usage: scripts/polymarket_control.sh <command> [args]

Commands:
  status
      Show current polymarket control and execution state.

  set-max <max_per_trade_usd> [max_daily_usd]
      Set per-trade and optional daily cap.

  go-live [max_per_trade_usd] [max_daily_usd] [manual_approval:0|1] [min_edge_pct]
      Enable live + auto polymarket execution.

  set-edge <min_edge_pct>
      Set minimum edge threshold used by executor.

  paper-safe [max_per_trade_usd] [max_daily_usd]
      Disable live, keep paper auto on.

  run
      Execute one polymarket execution cycle now.

  approve <candidate_id> [candidate_id...]
      Approve candidate ids for execution.
EOF
}

upsert_ctl() {
  local k="$1"; local v="$2"
  sqlite3 "$DB" "
    INSERT INTO execution_controls(key,value,updated_at)
    VALUES ('$k','$v',datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=datetime('now');
  "
}

show_status() {
  echo "== Controls =="
  sqlite3 -header -column "$DB" "
    SELECT key,value
    FROM execution_controls
    WHERE key IN (
      'enable_polymarket_auto','allow_polymarket_live','polymarket_manual_approval',
      'polymarket_max_notional_usd','polymarket_max_daily_exposure','polymarket_min_edge_pct'
    )
    ORDER BY key;
  "
  echo
  echo "== Candidates =="
  sqlite3 -header -column "$DB" "
    SELECT status, COUNT(*) AS n
    FROM polymarket_candidates
    GROUP BY status
    ORDER BY n DESC;
  " 2>/dev/null || true
  echo
  echo "== Orders (recent) =="
  sqlite3 -header -column "$DB" "
    SELECT id, created_at, candidate_id, mode, status, notional
    FROM polymarket_orders
    ORDER BY id DESC
    LIMIT 10;
  " 2>/dev/null || true
}

cmd="${1:-}"
case "$cmd" in
  status)
    show_status
    ;;

  set-max)
    max_trade="${2:-}"
    max_daily="${3:-}"
    if [ -z "$max_trade" ]; then
      echo "set-max requires <max_per_trade_usd>" >&2
      exit 2
    fi
    upsert_ctl "polymarket_max_notional_usd" "$max_trade"
    if [ -n "$max_daily" ]; then
      upsert_ctl "polymarket_max_daily_exposure" "$max_daily"
    fi
    show_status
    ;;

  go-live)
    max_trade="${2:-5}"
    max_daily="${3:-20}"
    manual="${4:-0}"
    min_edge="${5:-5.0}"
    upsert_ctl "enable_polymarket_auto" "1"
    upsert_ctl "allow_polymarket_live" "1"
    upsert_ctl "polymarket_manual_approval" "$manual"
    upsert_ctl "polymarket_max_notional_usd" "$max_trade"
    upsert_ctl "polymarket_max_daily_exposure" "$max_daily"
    upsert_ctl "polymarket_min_edge_pct" "$min_edge"
    show_status
    ;;

  set-edge)
    edge="${2:-}"
    if [ -z "$edge" ]; then
      echo "set-edge requires <min_edge_pct>" >&2
      exit 2
    fi
    upsert_ctl "polymarket_min_edge_pct" "$edge"
    show_status
    ;;

  paper-safe)
    max_trade="${2:-5}"
    max_daily="${3:-20}"
    upsert_ctl "enable_polymarket_auto" "1"
    upsert_ctl "allow_polymarket_live" "0"
    upsert_ctl "polymarket_manual_approval" "0"
    upsert_ctl "polymarket_max_notional_usd" "$max_trade"
    upsert_ctl "polymarket_max_daily_exposure" "$max_daily"
    show_status
    ;;

  run)
    "$WRAP" python3.11 "$EXEC"
    ;;

  approve)
    shift
    if [ "$#" -lt 1 ]; then
      echo "approve requires at least one candidate id" >&2
      exit 2
    fi
    python3.11 "$APPROVE" "$@"
    ;;

  ""|-h|--help|help)
    usage
    ;;

  *)
    echo "unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac
