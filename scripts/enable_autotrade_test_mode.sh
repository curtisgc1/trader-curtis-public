#!/bin/bash
set -euo pipefail

DB="/Users/Shared/curtis/trader-curtis/data/trades.db"

sqlite3 "$DB" <<'SQL'
CREATE TABLE IF NOT EXISTS execution_controls (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
INSERT OR REPLACE INTO execution_controls (key, value, updated_at) VALUES
('allow_live_trading', '0', datetime('now')),
('allow_hyperliquid_live', '1', datetime('now')),
('enable_alpaca_paper_auto', '1', datetime('now')),
('enable_hyperliquid_test_auto', '1', datetime('now')),
('hyperliquid_test_notional_usd', '10', datetime('now')),
('min_candidate_score', '60', datetime('now')),
('max_open_positions', '5', datetime('now')),
('max_daily_new_notional_usd', '1000', datetime('now')),
('max_signal_notional_usd', '150', datetime('now'));
SQL

echo "execution_controls updated for auto-trade test mode"
sqlite3 -header -column "$DB" "SELECT key, value, updated_at FROM execution_controls ORDER BY key;"
