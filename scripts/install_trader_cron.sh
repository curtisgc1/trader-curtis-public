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
$CRON_END
EOF

crontab "$TMP"
rm -f "$TMP" "$EXISTING"

echo "Installed Trader Curtis cron schedule (ET market sessions)."
crontab -l | sed -n "/$CRON_BEGIN/,/$CRON_END/p"

