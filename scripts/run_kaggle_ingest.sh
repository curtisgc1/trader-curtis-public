#!/bin/bash
set -euo pipefail
ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
PY_BIN="$(command -v python3.11 || command -v python3)"
if [ -z "${PY_BIN}" ]; then
  echo "No Python interpreter found"
  exit 1
fi

KAGGLE_JSON="${KAGGLE_CONFIG_DIR:-$HOME/.kaggle}/kaggle.json"

get_control() {
  local key="$1"
  local fallback="$2"
  local v=""
  if [ -f "$DB" ]; then
    v="$(sqlite3 -cmd ".timeout 15000" "$DB" "SELECT value FROM execution_controls WHERE key='${key}' LIMIT 1;" 2>/dev/null || true)"
  fi
  if [ -z "${v}" ]; then
    echo "$fallback"
  else
    echo "$v"
  fi
}

get_runtime_state() {
  local key="$1"
  get_control "runtime:${key}" ""
}

set_runtime_state() {
  local key="$1"
  local value="$2"
  if [ -f "$DB" ]; then
    sqlite3 "$DB" "
      PRAGMA busy_timeout=15000;
      CREATE TABLE IF NOT EXISTS execution_controls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      INSERT INTO execution_controls (key, value, updated_at)
      VALUES ('runtime:${key}', '${value}', datetime('now'))
      ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
    " >/dev/null 2>&1
  fi
}

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

FORCE_KAGGLE_INGEST="${FORCE_KAGGLE_INGEST:-0}"
MIN_HOURS_BETWEEN_RUNS="${KAGGLE_MIN_HOURS_BETWEEN_RUNS:-$(get_control "kaggle_min_hours_between_runs" "24")}"
MAX_FILES_PER_RUN="${KAGGLE_MAX_FILES_PER_RUN:-$(get_control "kaggle_max_files_per_run" "10")}"
MAX_ROWS_PER_FILE="${KAGGLE_MAX_ROWS_PER_FILE:-$(get_control "kaggle_max_rows_per_file" "50000")}"
LAST_SUCCESS_UTC="$(get_runtime_state "kaggle_last_success_utc")"
if [ "${FORCE_KAGGLE_INGEST}" != "1" ] && [ -n "${LAST_SUCCESS_UTC}" ]; then
  HOURS_SINCE_LAST="$(sqlite3 "$DB" "SELECT ROUND((julianday('now') - julianday('${LAST_SUCCESS_UTC}')) * 24.0, 2);" 2>/dev/null || true)"
  if [ -z "${HOURS_SINCE_LAST}" ]; then HOURS_SINCE_LAST=99999; fi
  if awk "BEGIN {exit !(${HOURS_SINCE_LAST} < ${MIN_HOURS_BETWEEN_RUNS})}"; then
    echo "kaggle_ingest=skipped reason=min_hours_gate hours_since_last=${HOURS_SINCE_LAST} min_hours=${MIN_HOURS_BETWEEN_RUNS}"
    exit 0
  fi
fi

if [ -n "$SLUG" ]; then
  if [ ! -f "$KAGGLE_JSON" ]; then
    echo "kaggle_ingest=blocked reason=missing_credentials file=$KAGGLE_JSON"
    exit 1
  fi
  DAILY_DOWNLOAD_LIMIT="${KAGGLE_DAILY_DOWNLOAD_LIMIT:-$(get_control "kaggle_daily_download_limit" "1")}"
  TODAY_UTC="$(date -u +%F)"
  LAST_DAY="$(get_runtime_state "kaggle_last_download_day")"
  DOWNLOADS_TODAY="$(get_runtime_state "kaggle_downloads_today")"

  if [ -z "${DOWNLOADS_TODAY}" ]; then DOWNLOADS_TODAY=0; fi
  if [ -z "${LAST_DAY}" ] || [ "${LAST_DAY}" != "${TODAY_UTC}" ]; then
    DOWNLOADS_TODAY=0
  fi

  if [ "${DOWNLOADS_TODAY}" -ge "${DAILY_DOWNLOAD_LIMIT}" ]; then
    echo "kaggle_ingest=skipped reason=daily_limit_reached downloads_today=${DOWNLOADS_TODAY} limit=${DAILY_DOWNLOAD_LIMIT}"
    exit 0
  fi

  PIPELINE_OUTPUT="$("${PY_BIN}" "$ROOT/pipeline_j_kaggle_polymarket.py" \
    --kaggle-dataset "$SLUG" \
    --max-files "${MAX_FILES_PER_RUN}" \
    --max-rows-per-file "${MAX_ROWS_PER_FILE}" 2>&1)" || {
      echo "$PIPELINE_OUTPUT"
      echo "kaggle_ingest=failed reason=pipeline_error"
      exit 1
    }
  echo "$PIPELINE_OUTPUT"
  if printf "%s\n" "$PIPELINE_OUTPUT" | grep -q "^kaggle_download=error:"; then
    echo "kaggle_ingest=failed reason=download_error"
    exit 1
  fi

  DOWNLOADS_TODAY=$((DOWNLOADS_TODAY + 1))
  set_runtime_state "kaggle_last_success_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set_runtime_state "kaggle_last_download_day" "${TODAY_UTC}"
  set_runtime_state "kaggle_downloads_today" "${DOWNLOADS_TODAY}"
  echo "kaggle_ingest=ok downloads_today=${DOWNLOADS_TODAY} limit=${DAILY_DOWNLOAD_LIMIT} max_files=${MAX_FILES_PER_RUN} max_rows_per_file=${MAX_ROWS_PER_FILE}"
else
  PIPELINE_OUTPUT="$("${PY_BIN}" "$ROOT/pipeline_j_kaggle_polymarket.py" --max-files "${MAX_FILES_PER_RUN}" --max-rows-per-file "${MAX_ROWS_PER_FILE}" 2>&1)" || {
    echo "$PIPELINE_OUTPUT"
    echo "kaggle_ingest=failed reason=pipeline_error"
    exit 1
  }
  echo "$PIPELINE_OUTPUT"
  set_runtime_state "kaggle_last_success_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "kaggle_ingest=ok source=local_files max_files=${MAX_FILES_PER_RUN} max_rows_per_file=${MAX_ROWS_PER_FILE}"
fi
