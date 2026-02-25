#!/bin/bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
PY_BIN="$(command -v python3.11 || command -v python3 || true)"

backend="pyclob"
if [ -f "$DB" ]; then
  b="$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='polymarket_exec_backend' LIMIT 1;" 2>/dev/null || true)"
  if [ -n "${b:-}" ]; then backend="$b"; fi
fi

if [ "$backend" = "cli" ]; then
  if command -v polymarket >/dev/null 2>&1; then
    echo "POLY_EXEC_BACKEND=cli detected; running health check then python executor fallback"
    polymarket --help >/dev/null 2>&1 || true
  elif command -v polymarket-cli >/dev/null 2>&1; then
    echo "POLY_EXEC_BACKEND=cli detected; running health check then python executor fallback"
    polymarket-cli --help >/dev/null 2>&1 || true
  else
    echo "POLY_EXEC_BACKEND=cli but cli binary missing; falling back to pyclob executor"
  fi
fi

if [ -z "$PY_BIN" ]; then
  echo "WARN: no python interpreter available for execution_polymarket.py"
  exit 0
fi

"$ROOT/scripts/with_polymarket_keychain.sh" "$PY_BIN" "$ROOT/execution_polymarket.py"
