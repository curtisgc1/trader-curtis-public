#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
cd "$ROOT"

echo "== Trader Agent Awareness Check =="
echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "policy.execution_model=control_gated_db_truth"

status=0

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

if [ "$status" -eq 0 ]; then
  echo "overall=good"
elif [ "$status" -eq 1 ]; then
  echo "overall=warn"
else
  echo "overall=bad"
fi

exit "$status"
