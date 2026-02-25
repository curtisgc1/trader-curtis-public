#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
CRON_BEGIN="# >>> TRADER_CURTIS_AUTOCYCLE >>>"
CRON_END="# <<< TRADER_CURTIS_AUTOCYCLE <<<"
TMP="$(mktemp)"
EXISTING="$(mktemp)"

crontab -l 2>/dev/null > "$EXISTING" || true

# Keep everything outside the managed trader block.
awk -v begin="$CRON_BEGIN" -v end="$CRON_END" '
  $0==begin {skip=1; next}
  $0==end {skip=0; next}
  !skip {print}
' "$EXISTING" > "$TMP"

cat >> "$TMP" <<EOF

$CRON_BEGIN
CRON_TZ=America/New_York
# Pre-open prep (Mon-Fri)
20 8 * * 1-5 $ROOT/scripts/trader_cycle_locked.sh pre_open
# Post-open confirmation run (Mon-Fri)
40 9 * * 1-5 $ROOT/scripts/trader_cycle_locked.sh post_open
# Midday rebalance run (Mon-Fri)
5 12 * * 1-5 $ROOT/scripts/trader_cycle_locked.sh midday
# Power-hour run (Mon-Fri)
35 15 * * 1-5 $ROOT/scripts/trader_cycle_locked.sh power_hour
# Post-close learning + cleanup (Mon-Fri)
20 16 * * 1-5 $ROOT/scripts/trader_cycle_locked.sh post_close
# Daily Kaggle ingest (all days, gated inside script)
20 18 * * * $ROOT/scripts/run_kaggle_ingest.sh
# Daily MLX training pass (all days, gated inside script)
40 18 * * * $ROOT/scripts/run_mlx_grpo_train.sh
# Daily realized close/settle reconciler (all days, Alpaca + Polymarket settle path)
0 19 * * * $ROOT/scripts/run_realized_reconciler.sh
# Daily GRPO readiness gate (all days)
10 19 * * * $ROOT/scripts/grpo_readiness_gate.sh
# Daily heavy learning resolver pass (all days, counterfactual + horizons)
20 19 * * * $ROOT/scripts/run_learning_feedback_daily.sh
$CRON_END
EOF

crontab "$TMP"
rm -f "$TMP" "$EXISTING"

echo "Installed Trader Curtis cron schedule (ET market sessions)."
crontab -l | sed -n "/$CRON_BEGIN/,/$CRON_END/p"
