#!/bin/bash
set -euo pipefail
ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
PY_BIN="$(command -v python3.11 || command -v python3)"
if [ -z "${PY_BIN}" ]; then
  echo "No Python interpreter found"
  exit 1
fi

# Priority:
# 1) env KAGGLE_POLY_DATASET_SLUG
# 2) execution_controls.kaggle_poly_dataset_slug (if kaggle_auto_pull_enabled=1)
DB_AUTO_PULL=""
DB_SLUG=""
if [ -f "$DB" ]; then
  DB_AUTO_PULL="$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='kaggle_auto_pull_enabled' LIMIT 1;" 2>/dev/null || true)"
  DB_SLUG="$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='kaggle_poly_dataset_slug' LIMIT 1;" 2>/dev/null || true)"
fi

SLUG="${KAGGLE_POLY_DATASET_SLUG:-}"
if [ -z "$SLUG" ] && [ "${DB_AUTO_PULL:-0}" = "1" ] && [ -n "${DB_SLUG:-}" ]; then
  SLUG="$DB_SLUG"
fi

if [ -n "$SLUG" ]; then
  "${PY_BIN}" "$ROOT/pipeline_j_kaggle_polymarket.py" --kaggle-dataset "$SLUG"
else
  "${PY_BIN}" "$ROOT/pipeline_j_kaggle_polymarket.py"
fi
