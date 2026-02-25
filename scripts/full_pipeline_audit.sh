#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
cd "$ROOT"

rc=0
warn(){
  echo "WARN: $*"
  if [ "$rc" -lt 1 ]; then
    rc=1
  fi
  return 0
}
bad(){
  echo "BAD: $*"
  rc=2
  return 0
}

sql(){ sqlite3 "$DB" "$1" 2>/dev/null || true; }
one(){ local out; out="$(sql "$1")"; echo "${out:-0}"; }
table_exists(){ [ "$(one "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$1';")" != "0" ]; }
column_exists(){ [ "$(one "SELECT COUNT(*) FROM pragma_table_info('$1') WHERE name='$2';")" != "0" ]; }
count_table(){ one "SELECT COUNT(*) FROM $1;"; }
q_age(){
  local table="$1" col="$2"
  if ! table_exists "$table"; then
    echo ""
    return 0
  fi
  if ! column_exists "$table" "$col"; then
    echo ""
    return 0
  fi
  sql "SELECT round((julianday('now') - julianday(max($col))) * 1440, 2) FROM $table WHERE COALESCE($col,'')<>'';"
}

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
  pipeline_x_handle_bridge.py update_learning_feedback.py \
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
for t in \
  trade_candidates signal_routes execution_orders route_outcomes \
  source_learning_stats strategy_learning_stats pipeline_signals \
  tracked_x_sources external_signals copy_trades \
  polymarket_markets polymarket_candidates polymarket_orders \
  polymarket_wallet_activity weather_market_probs polymarket_mm_snapshots; do
  if ! table_exists "$t"; then
    warn "missing table: $t"
  else
    echo "table.$t.rows=$(count_table "$t")"
  fi
done

printf "\n-- 5) Freshness checks (minutes) --\n"
echo "age.trade_candidates=$(q_age trade_candidates generated_at)"
echo "age.signal_routes=$(q_age signal_routes routed_at)"
echo "age.pipeline_signals=$(q_age pipeline_signals generated_at)"
echo "age.external_signals=$(q_age external_signals created_at)"
echo "age.unified_social_sentiment=$(q_age unified_social_sentiment timestamp)"
echo "age.institutional_patterns=$(q_age institutional_patterns timestamp)"
echo "age.polymarket_markets=$(q_age polymarket_markets fetched_at)"
echo "age.polymarket_candidates=$(q_age polymarket_candidates created_at)"
echo "age.polymarket_orders=$(q_age polymarket_orders created_at)"
echo "age.polymarket_wallet_activity=$(q_age polymarket_wallet_activity created_at)"
echo "age.weather_market_probs=$(q_age weather_market_probs created_at)"
echo "age.polymarket_kaggle_markets=$(q_age polymarket_kaggle_markets created_at)"
echo "age.polymarket_mm_snapshots=$(q_age polymarket_mm_snapshots created_at)"

printf "\n-- 6) Risk/control posture --\n"
sql "SELECT key||'='||value FROM execution_controls WHERE key IN (
'agent_master_enabled','consensus_enforce','consensus_min_confirmations','consensus_min_ratio','consensus_min_score',
'high_beta_only','high_beta_min_beta','weather_strict_station_required','mm_enabled','mm_toxicity_threshold',
'x_bridge_enabled','x_bridge_posts_per_handle','x_bridge_max_signals_per_cycle','x_bridge_max_handles',
'kaggle_auto_pull_enabled','kaggle_daily_download_limit','kaggle_min_hours_between_runs','kaggle_poly_dataset_slug'
) ORDER BY key;"

printf "\n-- 7) Recent blocked reasons --\n"
sql "SELECT reason, COUNT(*) AS n FROM signal_routes GROUP BY reason ORDER BY n DESC LIMIT 10;"

printf "\n-- 8) X wiring checks --\n"
tracked_active="$(one "SELECT COUNT(*) FROM tracked_x_sources WHERE COALESCE(active,1)=1;")"
tracked_invalid="$(one "SELECT COUNT(*) FROM tracked_x_sources WHERE COALESCE(active,1)=1 AND trim(COALESCE(handle,''))='';")"
tracked_x_disabled="$(one "SELECT COUNT(*) FROM tracked_x_sources WHERE COALESCE(active,1)=1 AND COALESCE(x_api_enabled,1)=0;")"
external_from_tracked_total="$(one "SELECT COUNT(*) FROM external_signals WHERE replace(lower(trim(COALESCE(source,''))),'@','') IN (SELECT replace(lower(trim(COALESCE(handle,''))),'@','') FROM tracked_x_sources WHERE COALESCE(active,1)=1);")"
external_from_tracked_24h="$(one "SELECT COUNT(*) FROM external_signals WHERE replace(lower(trim(COALESCE(source,''))),'@','') IN (SELECT replace(lower(trim(COALESCE(handle,''))),'@','') FROM tracked_x_sources WHERE COALESCE(active,1)=1) AND julianday(created_at) >= julianday('now') - 1;")"
copy_from_tracked_24h="$(one "SELECT COUNT(*) FROM copy_trades WHERE replace(lower(trim(COALESCE(source_handle,''))),'@','') IN (SELECT replace(lower(trim(COALESCE(handle,''))),'@','') FROM tracked_x_sources WHERE COALESCE(active,1)=1) AND julianday(call_timestamp) >= julianday('now') - 1;")"
x_evidence_candidates="$(one "SELECT COUNT(*) FROM trade_candidates WHERE lower(COALESCE(evidence_json,'')) LIKE '%\"x:%' OR lower(COALESCE(input_breakdown_json,'')) LIKE '%\"x:%';")"
echo "x.tracked_active=$tracked_active"
echo "x.tracked_invalid=$tracked_invalid"
echo "x.tracked_x_api_disabled=$tracked_x_disabled"
echo "x.external_from_tracked.total=$external_from_tracked_total"
echo "x.external_from_tracked.24h=$external_from_tracked_24h"
echo "x.copy_from_tracked.24h=$copy_from_tracked_24h"
echo "x.candidates_with_x_evidence=$x_evidence_candidates"
if [ "$tracked_active" -gt 0 ] && [ "$external_from_tracked_total" -eq 0 ]; then
  warn "tracked handles exist but no external_signals rows are attributed to them"
fi
if [ "$tracked_active" -gt 0 ] && [ "$x_evidence_candidates" -eq 0 ]; then
  warn "tracked handles exist but no trade candidates show x: evidence"
fi
if [ "$tracked_invalid" -gt 0 ]; then
  warn "tracked_x_sources has active rows with empty handle"
fi
echo "x.top_external_sources:"
sql "SELECT source, COUNT(*) AS n FROM external_signals GROUP BY source ORDER BY n DESC LIMIT 10;"

printf "\n-- 9) Learning label quality --\n"
realized_count="$(one "SELECT COUNT(*) FROM route_outcomes WHERE COALESCE(outcome_type,'realized')='realized';")"
operational_count="$(one "SELECT COUNT(*) FROM route_outcomes WHERE COALESCE(outcome_type,'realized')='operational';")"
unknown_count="$(one "SELECT COUNT(*) FROM route_outcomes WHERE COALESCE(outcome_type,'realized') NOT IN ('realized','operational');")"
echo "learning.route_outcomes.realized=$realized_count"
echo "learning.route_outcomes.operational=$operational_count"
echo "learning.route_outcomes.unknown=$unknown_count"
echo "learning.route_outcomes.by_resolution:"
sql "SELECT resolution, COUNT(*) AS n FROM route_outcomes GROUP BY resolution ORDER BY n DESC;"
if [ "$realized_count" -eq 0 ] && [ "$operational_count" -gt 0 ]; then
  warn "learning stats are currently operational-only (no realized outcomes yet)"
fi
if table_exists "trades"; then
  unresolved_realized_links="$(one "SELECT COUNT(*) FROM trades t WHERE COALESCE(t.route_id,0) > 0 AND NOT EXISTS (SELECT 1 FROM route_outcomes o WHERE o.route_id=t.route_id AND COALESCE(o.outcome_type,'realized')='realized');")"
  echo "learning.trades_without_realized_outcome=$unresolved_realized_links"
  if [ "$unresolved_realized_links" -gt 0 ]; then
    warn "some route-linked trades have no realized route_outcomes label"
  fi
fi

printf "\n-- 10) Kaggle ingest posture --\n"
kaggle_enabled="$(one "SELECT COALESCE(value,'0') FROM execution_controls WHERE key='kaggle_auto_pull_enabled' LIMIT 1;")"
kaggle_slug="$(sql "SELECT COALESCE(value,'') FROM execution_controls WHERE key='kaggle_poly_dataset_slug' LIMIT 1;")"
kaggle_rows="0"
if table_exists "polymarket_kaggle_markets"; then
  kaggle_rows="$(count_table polymarket_kaggle_markets)"
fi
echo "kaggle.auto_pull_enabled=${kaggle_enabled:-0}"
echo "kaggle.dataset_slug=${kaggle_slug:-}"
echo "kaggle.polymarket_rows=$kaggle_rows"
if [ "${kaggle_enabled:-0}" = "1" ] && [ -z "${kaggle_slug:-}" ]; then
  warn "kaggle_auto_pull_enabled=1 but kaggle_poly_dataset_slug is empty"
fi
if [ "${kaggle_enabled:-0}" = "1" ] && [ "$kaggle_rows" -eq 0 ]; then
  warn "kaggle auto pull enabled but polymarket_kaggle_markets has no rows"
fi

if [ "$rc" -eq 0 ]; then
  echo "overall=good"
elif [ "$rc" -eq 1 ]; then
  echo "overall=warn"
else
  echo "overall=bad"
fi

exit "$rc"
