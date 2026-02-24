#!/bin/bash
set -euo pipefail

MODE="${1:-scheduled}"
ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"

printf "[%s] trader cycle start (%s)\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODE"

if [ -x "$ROOT/scripts/check_tooling_context.sh" ]; then
  echo "Running tooling context check..."
  "$ROOT/scripts/check_tooling_context.sh" || true
fi

if [ -x "$ROOT/political_monitor_free.py" ]; then
  echo "Running political monitor..."
  "$ROOT/political_monitor_free.py" >/tmp/trader-political.out 2>/tmp/trader-political.err || true
fi

if [ -x "$ROOT/scripts/check_agent_awareness.sh" ]; then
  echo "Running agent awareness check..."
  "$ROOT/scripts/check_agent_awareness.sh" || true
fi

"$ROOT/run-all-scans.sh"

if [ ! -f "$DB" ]; then
  echo "DB not found at $DB"
  exit 0
fi

echo ""
echo "=== Trader Cycle Summary ==="
sqlite3 -header -column "$DB" "
SELECT pipeline_id AS pipeline, COUNT(*) AS new_rows
FROM pipeline_signals
WHERE generated_at >= datetime('now','-2 hours')
GROUP BY pipeline_id
ORDER BY pipeline_id;
"

echo ""
sqlite3 -header -column "$DB" "
SELECT decision, COUNT(*) AS count
FROM signal_routes
WHERE routed_at >= datetime('now','-2 hours')
GROUP BY decision
ORDER BY decision;
"

echo ""
sqlite3 -header -column "$DB" "
SELECT status, COUNT(*) AS count
FROM signal_routes
WHERE routed_at >= datetime('now','-2 hours')
GROUP BY status
ORDER BY status;
"

echo ""
sqlite3 -header -column "$DB" "
SELECT source_tag, sample_size, reliability_score
FROM source_scores
ORDER BY reliability_score DESC, sample_size DESC
LIMIT 5;
"

echo ""
printf "[%s] trader cycle complete (%s)\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODE"
