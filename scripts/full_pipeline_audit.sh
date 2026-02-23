#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
cd "$ROOT"

rc=0
warn(){ echo "WARN: $*"; [ $rc -lt 1 ] && rc=1; }
bad(){ echo "BAD: $*"; rc=2; }

printf "== Full Pipeline Audit ==\n"
printf "time_utc=%s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ ! -f "$DB" ]; then
  bad "DB missing: $DB"
  echo "overall=bad"
  exit 2
fi

printf "\n-- 1) Python syntax checks --\n"
if ! python3.11 -m py_compile \
  execution_guard.py signal_router.py generate_trade_candidates.py \
  execution_worker.py execution_polymarket.py pipeline_polymarket.py \
  pipeline_chart_liquidity.py pipeline_g_weather.py polymarket_mm_engine.py \
  dashboard-ui/data.py dashboard-ui/app.py; then
  bad "py_compile failed"
else
  echo "py_compile=ok"
fi

printf "\n-- 2) Agent awareness checks --\n"
if ! ./scripts/check_agent_awareness.sh; then
  warn "agent awareness check returned non-zero"
fi

printf "\n-- 3) Signal validation dry run --\n"
if ! ./scripts/run_signal_validation.sh; then
  warn "signal validation returned non-zero"
fi

printf "\n-- 4) Core table checks --\n"
for t in trade_candidates signal_routes execution_orders polymarket_markets polymarket_candidates polymarket_orders route_outcomes source_learning_stats strategy_learning_stats weather_market_probs polymarket_mm_snapshots; do
  n="$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$t';" 2>/dev/null || echo 0)"
  if [ "${n:-0}" = "0" ]; then
    warn "missing table: $t"
  else
    c="$(sqlite3 "$DB" "SELECT COUNT(*) FROM $t;" 2>/dev/null || echo 0)"
    echo "table.$t.rows=$c"
  fi
done

printf "\n-- 5) Freshness checks (minutes) --\n"
q_age(){
  local table="$1" col="$2"
  sqlite3 "$DB" "SELECT round((julianday('now') - julianday(max($col))) * 1440, 2) FROM $table;" 2>/dev/null || echo ""
}

echo "age.trade_candidates=$(q_age trade_candidates generated_at)"
echo "age.signal_routes=$(q_age signal_routes routed_at)"
echo "age.polymarket_markets=$(q_age polymarket_markets fetched_at)"
echo "age.polymarket_candidates=$(q_age polymarket_candidates created_at)"
echo "age.polymarket_orders=$(q_age polymarket_orders created_at)"
echo "age.weather_market_probs=$(q_age weather_market_probs created_at)"
echo "age.polymarket_mm_snapshots=$(q_age polymarket_mm_snapshots created_at)"

printf "\n-- 6) Risk/control posture --\n"
sqlite3 "$DB" "SELECT key||'='||value FROM execution_controls WHERE key IN (
'agent_master_enabled','consensus_enforce','consensus_min_confirmations','consensus_min_ratio','consensus_min_score',
'high_beta_only','high_beta_min_beta','weather_strict_station_required','mm_enabled','mm_toxicity_threshold') ORDER BY key;" || true

printf "\n-- 7) Recent blocked reasons --\n"
sqlite3 "$DB" "SELECT reason, COUNT(*) AS n FROM signal_routes GROUP BY reason ORDER BY n DESC LIMIT 10;" || true

if [ $rc -eq 0 ]; then
  echo "overall=good"
elif [ $rc -eq 1 ]; then
  echo "overall=warn"
else
  echo "overall=bad"
fi

exit $rc
