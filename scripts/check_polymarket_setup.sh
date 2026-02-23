#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
ENV_FILE="$ROOT/.env"
ACCT="curtiscorum"

state="good"

warn() {
  echo "WARN: $1"
  if [ "$state" = "good" ]; then state="warn"; fi
}

bad() {
  echo "BAD: $1"
  state="bad"
}

keychain_has() {
  local service="$1"
  security find-generic-password -a "$ACCT" -s "$service" -w >/dev/null 2>&1
}

env_has() {
  local key="$1"
  [ -f "$ENV_FILE" ] && grep -qE "^${key}=.+$" "$ENV_FILE"
}

echo "== Polymarket Awareness Check =="

if [ ! -f "$DB" ]; then
  bad "trades.db missing at $DB"
  echo "overall=$state"
  exit 2
fi

poly_auto="$(sqlite3 "$DB" "select value from execution_controls where key='enable_polymarket_auto' limit 1;" 2>/dev/null || true)"
poly_live="$(sqlite3 "$DB" "select value from execution_controls where key='allow_polymarket_live' limit 1;" 2>/dev/null || true)"
poly_wallet="$(sqlite3 "$DB" "select value from wallet_config where key='poly_wallet_address' limit 1;" 2>/dev/null || true)"

echo "control.enable_polymarket_auto=${poly_auto:-0}"
echo "control.allow_polymarket_live=${poly_live:-0}"
echo "wallet.poly_wallet_address=${poly_wallet:-<unset>}"

api_env_ok=0
if env_has "POLY_API_KEY" && env_has "POLY_API_SECRET" && env_has "POLY_API_PASSPHRASE"; then
  api_env_ok=1
fi
api_keychain_ok=0
if keychain_has "trader-curtis-POLY_API_KEY" && keychain_has "trader-curtis-POLY_API_SECRET" && keychain_has "trader-curtis-POLY_API_PASSPHRASE"; then
  api_keychain_ok=1
fi

sign_env_ok=0
if env_has "POLY_PRIVATE_KEY"; then
  sign_env_ok=1
fi
sign_keychain_ok=0
if keychain_has "trader-curtis-POLY_PRIVATE_KEY"; then
  sign_keychain_ok=1
fi

if [ "$api_env_ok" -eq 1 ] || [ "$api_keychain_ok" -eq 1 ]; then
  echo "api_credentials=ok"
else
  bad "Polymarket API credentials missing (env/keychain)"
fi

if [ "$sign_env_ok" -eq 1 ] || [ "$sign_keychain_ok" -eq 1 ]; then
  echo "signing_key=ok"
else
  if [ "${poly_live:-0}" = "1" ]; then
    bad "allow_polymarket_live=1 but POLY_PRIVATE_KEY missing; runtime will fall back to paper"
  else
    warn "POLY_PRIVATE_KEY not set (live disabled, paper-only is fine)"
  fi
fi

m_age="$(sqlite3 "$DB" "select round((julianday('now') - julianday(max(fetched_at))) * 1440, 2) from polymarket_markets;" 2>/dev/null || true)"
c_age="$(sqlite3 "$DB" "select round((julianday('now') - julianday(max(created_at))) * 1440, 2) from polymarket_candidates;" 2>/dev/null || true)"
o_age="$(sqlite3 "$DB" "select round((julianday('now') - julianday(max(created_at))) * 1440, 2) from polymarket_orders;" 2>/dev/null || true)"

echo "markets_age_min=${m_age:-na}"
echo "candidates_age_min=${c_age:-na}"
echo "orders_age_min=${o_age:-na}"

if [ -z "${m_age:-}" ]; then warn "no polymarket_markets freshness data"; fi
if [ -z "${c_age:-}" ]; then warn "no polymarket_candidates freshness data"; fi
if [ -z "${o_age:-}" ]; then warn "no polymarket_orders yet"; fi

echo "overall=$state"
if [ "$state" = "bad" ]; then exit 2; fi
if [ "$state" = "warn" ]; then exit 1; fi
exit 0
