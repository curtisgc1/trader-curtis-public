#!/bin/bash
# Political Alpha Monitor - Heartbeat Wrapper
# Called by OpenClaw heartbeat every 15 minutes during market hours

VAULT_PATH="/Users/Shared/curtis/trader-curtis"
SCRIPT="$VAULT_PATH/scripts/political_alpha_monitor.py"
LOG_FILE="$VAULT_PATH/logs/policy-monitor-cron.log"

# Log start
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Political Alpha scan starting..." >> "$LOG_FILE"

# Run monitor
python3 "$SCRIPT" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

# Log completion
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scan completed successfully" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Scan failed with code $EXIT_CODE" >> "$LOG_FILE"
fi

# Check for critical alerts and notify if found
CRITICAL_ALERTS=$(find "$VAULT_PATH/alerts" -name "policy-alert-CRITICAL-*" -mmin -15 2>/dev/null)
if [ -n "$CRITICAL_ALERTS" ]; then
    echo "🚨 CRITICAL POLICY ALERTS DETECTED"
    for alert in $CRITICAL_ALERTS; do
        echo "Found: $alert"
        # Would send notification here
    done
fi

exit $EXIT_CODE
