#!/bin/bash
# Auto-run analysis on all completed trades
# Place in crontab or run manually

cd /Users/shared/curtis/trader-curtis

# Check for filled orders and update database
curl -s -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" \
  "$ALPACA_BASE_URL/v2/orders?status=closed" | \
  python3 analysis/process_closed_orders.py

# Generate daily summary
python3 analysis/generate_report.py

echo "Analysis complete: $(date)"
