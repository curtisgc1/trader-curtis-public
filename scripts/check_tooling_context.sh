#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
cd "$ROOT"

status=0
echo "== Tooling Context Check =="
echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

must_files=(
  "./docs/TOOLING-RUNTIME-PLAYBOOK.md"
  "./docs/AGENT-ROLE-CONTEXT.md"
  "./docs/AGENT-SIGNAL-COMMANDS.md"
)

must_exec=(
  "./run-all-scans.sh"
  "./scripts/check_agent_awareness.sh"
  "./scripts/trade_claim_guard.sh"
  "./scripts/polymarket_control.sh"
  "./scripts/full_pipeline_audit.sh"
)

must_py=(
  "./signal_router.py"
  "./quant_gate.py"
  "./execution_worker.py"
  "./execution_adapters.py"
  "./execution_polymarket.py"
  "./update_learning_feedback.py"
)

for f in "${must_files[@]}"; do
  if [ -s "$f" ]; then
    echo "doc.$(basename "$f")=ok"
  else
    echo "doc.$(basename "$f")=missing_or_empty"
    status=1
  fi
done

for f in "${must_exec[@]}"; do
  if [ -x "$f" ]; then
    echo "exec.$(basename "$f")=ok"
  else
    echo "exec.$(basename "$f")=missing_or_not_executable"
    status=1
  fi
done

for f in "${must_py[@]}"; do
  if [ -f "$f" ]; then
    echo "py.$(basename "$f")=ok"
  else
    echo "py.$(basename "$f")=missing"
    status=1
  fi
done

if [ ! -f "$DB" ]; then
  echo "db=missing"
  status=2
else
  required_tables=(
    pipeline_signals
    signal_routes
    quant_validations
    execution_orders
    polymarket_orders
    trade_intents
    route_trade_links
    route_outcomes
    route_feedback_features
    input_feature_stats
    source_learning_stats
    strategy_learning_stats
    execution_learning
    execution_controls
  )
  for t in "${required_tables[@]}"; do
    if sqlite3 "$DB" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='$t' LIMIT 1;" | grep -q 1; then
      echo "table.$t=ok"
    else
      echo "table.$t=missing"
      status=1
    fi
  done
fi

if [ "$status" -eq 0 ]; then
  echo "tooling_context=good"
elif [ "$status" -eq 1 ]; then
  echo "tooling_context=warn"
else
  echo "tooling_context=bad"
fi

exit "$status"
