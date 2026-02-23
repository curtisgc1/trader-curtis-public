#!/usr/bin/env bash
set -euo pipefail

BASE="/Users/Shared/curtis/trader-curtis"
ENV_FILE="$BASE/.env"
DB_FILE="$BASE/data/trades.db"

mkdir -p "$BASE/data"
touch "$ENV_FILE"

set_env() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$value" '
    BEGIN { done=0 }
    $0 ~ ("^" k "=") { print k "=" v; done=1; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$ENV_FILE" > "$tmp"
  mv "$tmp" "$ENV_FILE"
}

set_env "HL_USE_TESTNET" "1"
set_env "HL_API_URL" "https://api.hyperliquid-testnet.xyz"
set_env "HL_INFO_URL" "https://api.hyperliquid-testnet.xyz/info"

sqlite3 "$DB_FILE" <<'SQL'
CREATE TABLE IF NOT EXISTS execution_controls (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO execution_controls(key, value, updated_at) VALUES
  ('enable_hyperliquid_test_auto', '1', datetime('now'))
ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
INSERT INTO execution_controls(key, value, updated_at) VALUES
  ('allow_hyperliquid_live', '1', datetime('now'))
ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
INSERT INTO execution_controls(key, value, updated_at) VALUES
  ('hyperliquid_test_notional_usd', '10', datetime('now'))
ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
INSERT INTO execution_controls(key, value, updated_at) VALUES
  ('hyperliquid_test_leverage', '1', datetime('now'))
ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
SQL

echo "Configured HL testnet in .env and execution_controls."