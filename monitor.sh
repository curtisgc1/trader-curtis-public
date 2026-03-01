#!/bin/bash
# Brain monitor — runs every 30 min, writes to monitor.log
DB="/Users/Shared/curtis/trader-curtis/data/trades.db"
LOG="/Users/Shared/curtis/trader-curtis/monitor.log"

while true; do
  echo "========== $(date '+%Y-%m-%d %H:%M:%S') ==========" >> "$LOG"

  # Heartbeat
  HB=$(sqlite3 "$DB" "SELECT value FROM brain_config WHERE key='heartbeat'" 2>/dev/null)
  if [ -z "$HB" ]; then
    echo "BRAIN: NO HEARTBEAT" >> "$LOG"
  else
    echo "BRAIN: heartbeat $HB" >> "$LOG"
  fi

  # Balance (from most recent arb scan log)
  BAL=$(tmux capture-pane -t trader-brain -p -S -100 2>/dev/null | grep "balances" | tail -1)
  echo "BAL: $BAL" >> "$LOG"

  # Grok alpha bets (last 30 min)
  echo "--- GROK ALPHA (last 30min) ---" >> "$LOG"
  sqlite3 "$DB" "SELECT detected_at, question, grok_confidence, market_price, direction, edge_pct, status, bet_size_usd FROM brain_grok_alpha WHERE detected_at > datetime('now', '-30 minutes') ORDER BY id DESC" 2>/dev/null >> "$LOG"

  # Grok alpha totals
  ALPHA_TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*), SUM(CASE WHEN status='executed' THEN 1 ELSE 0 END), SUM(CASE WHEN status='executed' THEN bet_size_usd ELSE 0 END) FROM brain_grok_alpha" 2>/dev/null)
  echo "ALPHA TOTALS: $ALPHA_TOTAL" >> "$LOG"

  # Arb opportunities (last 30 min)
  echo "--- ARB (last 30min) ---" >> "$LOG"
  sqlite3 "$DB" "SELECT detected_at, title, poly_price, kalshi_price, spread_after_fees, action, notes FROM brain_arb_opportunities WHERE detected_at > datetime('now', '-30 minutes') ORDER BY spread_after_fees DESC LIMIT 10" 2>/dev/null >> "$LOG"

  # Arb totals
  ARB_TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*), SUM(CASE WHEN action='executed' THEN 1 ELSE 0 END), SUM(CASE WHEN action='partial' THEN 1 ELSE 0 END) FROM brain_arb_opportunities" 2>/dev/null)
  echo "ARB TOTALS: $ARB_TOTAL" >> "$LOG"

  # Errors in last 30 min
  echo "--- ERRORS (last 30min) ---" >> "$LOG"
  tmux capture-pane -t trader-brain -p -S -200 2>/dev/null | grep -i "error\|failed\|FAIL" | tail -10 >> "$LOG"

  # Best arb spread seen
  BEST=$(sqlite3 "$DB" "SELECT title, spread_after_fees, action FROM brain_arb_opportunities ORDER BY spread_after_fees DESC LIMIT 3" 2>/dev/null)
  echo "BEST ARBS EVER: $BEST" >> "$LOG"

  echo "" >> "$LOG"
  sleep 1800
done
