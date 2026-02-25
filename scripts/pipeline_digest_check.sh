#!/bin/bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
OUT="$ROOT/reports/pipeline_digest_latest.txt"

if [ ! -f "$DB" ]; then
  echo "pipeline_digest=bad reason=db_missing path=$DB"
  exit 1
fi

q() {
  sqlite3 "$DB" "$1" 2>/dev/null || true
}

control() {
  local key="$1"
  q "SELECT COALESCE(value,'') FROM execution_controls WHERE key='${key}' LIMIT 1;"
}

age_min() {
  local table="$1"
  local ts_col="$2"
  q "SELECT CASE WHEN COUNT(*)=0 THEN '' ELSE ROUND((julianday('now') - julianday(MAX(${ts_col}))) * 24.0 * 60.0, 2) END FROM ${table};"
}

count_24h() {
  local table="$1"
  local ts_col="$2"
  q "SELECT COUNT(*) FROM ${table} WHERE datetime(${ts_col}) >= datetime('now', '-24 hours');"
}

classify_age() {
  local age="$1"
  local warn="$2"
  local bad="$3"
  if [ -z "$age" ]; then
    echo "bad"
    return
  fi
  if awk "BEGIN {exit !($age >= $bad)}"; then
    echo "bad"
    return
  fi
  if awk "BEGIN {exit !($age >= $warn)}"; then
    echo "warn"
    return
  fi
  echo "good"
}

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

sig_age="$(age_min pipeline_signals generated_at)"
cand_age="$(age_min trade_candidates generated_at)"
route_age="$(age_min signal_routes routed_at)"
learn_age="$(age_min route_outcomes resolved_at)"

sig_24h="$(count_24h pipeline_signals generated_at)"
cand_24h="$(count_24h trade_candidates generated_at)"
route_24h="$(count_24h signal_routes routed_at)"
ord_24h="$(count_24h execution_orders created_at)"
poly_24h="$(count_24h polymarket_orders created_at)"
learn_24h="$(count_24h route_outcomes resolved_at)"
kaggle_enabled="$(control kaggle_auto_pull_enabled)"
kaggle_last_status="$(control runtime:kaggle_last_status)"
kaggle_last_success_utc="$(control runtime:kaggle_last_success_utc)"
mlx_enabled="$(control grpo_mlx_train_enabled)"
mlx_last_status="$(control runtime:grpo_mlx_last_status)"
mlx_last_train_utc="$(control runtime:grpo_mlx_last_train_utc)"
mlx_last_test_loss="$(control runtime:grpo_mlx_last_test_loss)"
grpo_readiness_state="$(control runtime:grpo_readiness_state)"
grpo_readiness_reasons="$(control runtime:grpo_readiness_reasons)"
horizon_enabled="$(control horizon_resolver_enabled)"
horizon_rows="$(q "SELECT COUNT(*) FROM route_outcomes_horizons;")"

sig_state="$(classify_age "${sig_age}" 180 720)"
cand_state="$(classify_age "${cand_age}" 180 720)"
route_state="$(classify_age "${route_age}" 180 720)"
learn_state="$(classify_age "${learn_age}" 2880 10080)"

overall="good"
for s in "$sig_state" "$cand_state" "$route_state" "$learn_state"; do
  if [ "$s" = "bad" ]; then overall="bad"; break; fi
  if [ "$s" = "warn" ] && [ "$overall" = "good" ]; then overall="warn"; fi
done
if [ "${kaggle_enabled:-0}" = "1" ] && printf "%s" "${kaggle_last_status:-}" | grep -Eiq '^(blocked|failed)'; then
  if [ "$overall" = "good" ]; then overall="warn"; fi
fi
if [ "${mlx_enabled:-0}" = "1" ] && printf "%s" "${mlx_last_status:-}" | grep -Eiq '^failed'; then
  if [ "$overall" = "good" ]; then overall="warn"; fi
fi
if [ -n "${grpo_readiness_state:-}" ] && [ "${grpo_readiness_state}" != "good" ] && [ "$overall" = "good" ]; then
  overall="warn"
fi

mkdir -p "$(dirname "$OUT")"
cat > "$OUT" <<EOF
pipeline_digest_at_utc=${now_utc}
overall=${overall}
pipeline_signals_age_min=${sig_age}
trade_candidates_age_min=${cand_age}
signal_routes_age_min=${route_age}
route_outcomes_age_min=${learn_age}
pipeline_signals_24h=${sig_24h}
trade_candidates_24h=${cand_24h}
signal_routes_24h=${route_24h}
execution_orders_24h=${ord_24h}
polymarket_orders_24h=${poly_24h}
route_outcomes_24h=${learn_24h}
pipeline_signals_state=${sig_state}
trade_candidates_state=${cand_state}
signal_routes_state=${route_state}
route_outcomes_state=${learn_state}
kaggle_enabled=${kaggle_enabled:-0}
kaggle_last_status=${kaggle_last_status}
kaggle_last_success_utc=${kaggle_last_success_utc}
mlx_enabled=${mlx_enabled:-0}
mlx_last_status=${mlx_last_status}
mlx_last_train_utc=${mlx_last_train_utc}
mlx_last_test_loss=${mlx_last_test_loss}
grpo_readiness_state=${grpo_readiness_state}
grpo_readiness_reasons=${grpo_readiness_reasons}
horizon_enabled=${horizon_enabled:-0}
horizon_rows=${horizon_rows:-0}
EOF

cat "$OUT"
