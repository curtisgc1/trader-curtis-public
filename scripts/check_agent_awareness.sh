#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
cd "$ROOT"

echo "== Trader Agent Awareness Check =="
echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "policy.execution_model=control_gated_db_truth"

status=0

if [ -x "./scripts/check_tooling_context.sh" ]; then
  rc=0
  ./scripts/check_tooling_context.sh || rc=$?
  if [ "$rc" -gt "$status" ]; then status=$rc; fi
else
  echo "tooling_context_check=missing"
  status=1
fi
echo

if ! ./scripts/check_hl_setup.sh; then
  status=1
fi
echo

rc=0
./scripts/check_polymarket_setup.sh || rc=$?
if [ "$rc" -ne 0 ]; then
  if [ "$rc" -gt "$status" ]; then status=$rc; fi
fi
echo

if [ -f "./self_check.py" ]; then
  echo "self_check=available"
else
  echo "self_check=missing"
  status=1
fi

if [ -x "./scripts/polymarket_control.sh" ]; then
  echo "polymarket_control=available"
else
  echo "polymarket_control=missing"
  status=1
fi

if [ -f "./docs/AGENT-ROLE-CONTEXT.md" ]; then
  echo "role_context=available"
else
  echo "role_context=missing"
  status=1
fi

if [ -x "./scripts/full_pipeline_audit.sh" ]; then
  echo "full_audit_script=available"
else
  echo "full_audit_script=missing"
  status=1
fi

if [ -f "./data/trades.db" ]; then
  approved_routes="$(sqlite3 ./data/trades.db "SELECT COUNT(*) FROM signal_routes WHERE decision='approved';" 2>/dev/null || echo 0)"
  resolved_routes="$(sqlite3 ./data/trades.db "SELECT COUNT(*) FROM route_outcomes;" 2>/dev/null || echo 0)"
  feature_rows="$(sqlite3 ./data/trades.db "SELECT COUNT(*) FROM route_feedback_features;" 2>/dev/null || echo 0)"
  feature_stats_rows="$(sqlite3 ./data/trades.db "SELECT COUNT(*) FROM input_feature_stats;" 2>/dev/null || echo 0)"
  coverage_pct="$(sqlite3 ./data/trades.db "SELECT CASE WHEN $approved_routes>0 THEN ROUND(($resolved_routes*100.0)/$approved_routes,2) ELSE 0 END;" 2>/dev/null || echo 0)"
  echo "learning.approved_routes=$approved_routes"
  echo "learning.resolved_routes=$resolved_routes"
  echo "learning.coverage_pct=$coverage_pct"
  echo "learning.feature_rows=$feature_rows"
  echo "learning.feature_stats_rows=$feature_stats_rows"

  if awk "BEGIN {exit !($coverage_pct < 20)}"; then
    echo "warn=learning coverage below 20% (memory weak for adaptation)"
    if [ "$status" -lt 1 ]; then status=1; fi
  fi
fi

echo
if [ -x "./scripts/trade_claim_guard.sh" ]; then
  rc=0
  ./scripts/trade_claim_guard.sh || rc=$?
  if [ "$rc" -gt "$status" ]; then status=$rc; fi
else
  echo "trade_claim_guard=missing"
  status=1
fi

if [ "$status" -eq 0 ]; then
  echo "overall=good"
elif [ "$status" -eq 1 ]; then
  echo "overall=warn"
else
  echo "overall=bad"
fi

exit "$status"
