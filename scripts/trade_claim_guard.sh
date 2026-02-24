#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
cd "$ROOT"

echo "== Trade Claim Guard =="
echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ ! -f "$DB" ]; then
  echo "state=bad"
  echo "trade_ready=false"
  echo "blocker=trades.db missing"
  exit 2
fi

get_ctl() {
  local key="$1"
  local def="${2:-0}"
  local val
  val="$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='$key' LIMIT 1;" 2>/dev/null || true)"
  if [ -z "$val" ]; then
    echo "$def"
  else
    echo "$val"
  fi
}

agent_master_enabled="$(get_ctl agent_master_enabled 0)"
allow_live_trading="$(get_ctl allow_live_trading 0)"
enable_alpaca_paper_auto="$(get_ctl enable_alpaca_paper_auto 0)"
enable_hyperliquid_test_auto="$(get_ctl enable_hyperliquid_test_auto 0)"
allow_hyperliquid_live="$(get_ctl allow_hyperliquid_live 0)"
enable_polymarket_auto="$(get_ctl enable_polymarket_auto 0)"
allow_polymarket_live="$(get_ctl allow_polymarket_live 0)"

approved_queued="$(sqlite3 "$DB" "SELECT COUNT(*) FROM signal_routes WHERE decision='approved' AND status='queued';" 2>/dev/null || echo 0)"
recent_execution_orders="$(sqlite3 "$DB" "SELECT COUNT(*) FROM execution_orders WHERE datetime(COALESCE(created_at,'1970-01-01')) >= datetime('now','-60 minute');" 2>/dev/null || echo 0)"

echo "control.agent_master_enabled=$agent_master_enabled"
echo "control.allow_live_trading=$allow_live_trading"
echo "control.enable_alpaca_paper_auto=$enable_alpaca_paper_auto"
echo "control.enable_hyperliquid_test_auto=$enable_hyperliquid_test_auto"
echo "control.allow_hyperliquid_live=$allow_hyperliquid_live"
echo "control.enable_polymarket_auto=$enable_polymarket_auto"
echo "control.allow_polymarket_live=$allow_polymarket_live"
echo "routes.approved_queued=$approved_queued"
echo "orders.last_60m=$recent_execution_orders"

status=0

if [ "$agent_master_enabled" != "1" ]; then
  echo "blocker=agent_master_enabled=0 (execution worker paused)"
  status=2
fi

if [ "$enable_alpaca_paper_auto" != "1" ] && [ "$enable_hyperliquid_test_auto" != "1" ] && [ "$enable_polymarket_auto" != "1" ]; then
  echo "blocker=no execution adapters enabled"
  status=2
fi

if [ "$approved_queued" = "0" ]; then
  echo "warn=no approved queued routes"
  if [ "$status" -lt 1 ]; then status=1; fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "blocker=python3 missing"
  status=2
fi

if [ "$allow_polymarket_live" = "1" ]; then
  if ! ./scripts/with_polymarket_keychain.sh env >/tmp/trader_poly_guard_env.txt 2>/dev/null; then
    echo "blocker=polymarket keychain bridge failed"
    status=2
  else
    if ! grep -q '^POLY_PRIVATE_KEY=' /tmp/trader_poly_guard_env.txt; then
      echo "blocker=polymarket live enabled but POLY_PRIVATE_KEY unavailable"
      status=2
    fi
  fi
fi

if [ "$status" -eq 0 ]; then
  echo "state=good"
  echo "trade_ready=true"
  exit 0
elif [ "$status" -eq 1 ]; then
  echo "state=warn"
  echo "trade_ready=false"
  exit 1
else
  echo "state=bad"
  echo "trade_ready=false"
  exit 2
fi
