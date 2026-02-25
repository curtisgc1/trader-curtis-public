#!/bin/bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
PY_BIN="$(command -v python3.11 || command -v python3)"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/kaggle-ingest.log"
LOCK_DIR="/tmp/trader-curtis-kaggle-ingest.lock"
KAGGLE_JSON="${KAGGLE_CONFIG_DIR:-$HOME/.kaggle}/kaggle.json"
NO_STATE_WRITE="${GRPO_RUNTIME_NO_STATE_WRITE:-0}"

mkdir -p "$LOG_DIR"

sql_escape() {
  printf "%s" "$1" | sed "s/'/''/g"
}

log() {
  local msg="$1"
  echo "$msg" | tee -a "$LOG_FILE"
}

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
  if [ "$NO_STATE_WRITE" = "1" ]; then
    return 0
  fi
  if [ -f "$DB" ]; then
    local esc
    esc="$(sql_escape "$value")"
    sqlite3 "$DB" "
      PRAGMA busy_timeout=15000;
      CREATE TABLE IF NOT EXISTS execution_controls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      INSERT INTO execution_controls (key, value, updated_at)
      VALUES ('runtime:${key}', '${esc}', datetime('now'))
      ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
    " >/dev/null 2>&1 || true
  fi
}

env_or_dotenv() {
  local key="$1"
  local val="${!key:-}"
  if [ -n "$val" ]; then
    echo "$val"
    return
  fi
  if [ -f "$ROOT/.env" ]; then
    val="$(sed -n "s/^${key}=//p" "$ROOT/.env" | tail -n 1)"
    echo "$val"
    return
  fi
  echo ""
}

keychain_secret() {
  local service="$1"
  local account="${2:-$USER}"
  local out=""
  out="$(security find-generic-password -s "$service" -a "$account" -w 2>/dev/null || true)"
  if [ -z "$out" ]; then
    out="$(security find-generic-password -s "$service" -w 2>/dev/null || true)"
  fi
  echo "$out"
}

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set_runtime_state "kaggle_last_attempt_utc" "$START_UTC"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  set_runtime_state "kaggle_last_status" "skipped:lock_active"
  log "kaggle_ingest=skipped reason=lock_active"
  exit 0
fi
cleanup() {
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ -z "${PY_BIN}" ]; then
  set_runtime_state "kaggle_last_status" "failed:no_python"
  set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "kaggle_ingest=failed reason=no_python"
  exit 1
fi

if [ ! -f "$DB" ]; then
  set_runtime_state "kaggle_last_status" "failed:db_missing"
  set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "kaggle_ingest=failed reason=db_missing path=$DB"
  exit 1
fi

# Priority:
# 1) env KAGGLE_POLY_DATASET_SLUG
# 2) execution_controls.kaggle_poly_dataset_slug (if kaggle_auto_pull_enabled=1)
DB_AUTO_PULL="$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='kaggle_auto_pull_enabled' LIMIT 1;" 2>/dev/null || true)"
DB_SLUG="$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='kaggle_poly_dataset_slug' LIMIT 1;" 2>/dev/null || true)"

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
    set_runtime_state "kaggle_last_status" "skipped:min_hours_gate"
    log "kaggle_ingest=skipped reason=min_hours_gate hours_since_last=${HOURS_SINCE_LAST} min_hours=${MIN_HOURS_BETWEEN_RUNS}"
    exit 0
  fi
fi

if [ -n "$SLUG" ]; then
  KAGGLE_API_TOKEN_VAL="$(env_or_dotenv KAGGLE_API_TOKEN)"
  if [ -z "$KAGGLE_API_TOKEN_VAL" ]; then
    KAGGLE_API_TOKEN_VAL="$(keychain_secret kaggle_api_token)"
  fi
  if [ -n "$KAGGLE_API_TOKEN_VAL" ]; then
    export KAGGLE_API_TOKEN="$KAGGLE_API_TOKEN_VAL"
  fi

  if [ ! -f "$KAGGLE_JSON" ]; then
    KG_USER="$(env_or_dotenv KAGGLE_USERNAME)"
    KG_KEY="$(env_or_dotenv KAGGLE_KEY)"
    if [ -n "$KG_USER" ] && [ -n "$KG_KEY" ]; then
      mkdir -p "$(dirname "$KAGGLE_JSON")"
      printf '{\"username\":\"%s\",\"key\":\"%s\"}\n' "$KG_USER" "$KG_KEY" > "$KAGGLE_JSON"
      chmod 600 "$KAGGLE_JSON" >/dev/null 2>&1 || true
      log "kaggle_ingest=info credentials_restored_from_env file=$KAGGLE_JSON"
    fi
  fi
  if [ ! -f "$KAGGLE_JSON" ]; then
    if [ -n "$KAGGLE_API_TOKEN_VAL" ]; then
      log "kaggle_ingest=info auth_mode=api_token"
    else
    set_runtime_state "kaggle_last_status" "blocked:missing_credentials"
    set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "kaggle_ingest=blocked reason=missing_credentials file=$KAGGLE_JSON token=missing"
    exit 1
    fi
  fi

  PERM="$(stat -f '%Lp' "$KAGGLE_JSON" 2>/dev/null || echo '')"
  if [ "$PERM" != "600" ]; then
    chmod 600 "$KAGGLE_JSON" >/dev/null 2>&1 || true
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
    set_runtime_state "kaggle_last_status" "skipped:daily_limit_reached"
    log "kaggle_ingest=skipped reason=daily_limit_reached downloads_today=${DOWNLOADS_TODAY} limit=${DAILY_DOWNLOAD_LIMIT}"
    exit 0
  fi

  PIPELINE_OUTPUT="$(${PY_BIN} "$ROOT/pipeline_j_kaggle_polymarket.py" \
    --kaggle-dataset "$SLUG" \
    --max-files "${MAX_FILES_PER_RUN}" \
    --max-rows-per-file "${MAX_ROWS_PER_FILE}" 2>&1)" || {
      log "$PIPELINE_OUTPUT"
      set_runtime_state "kaggle_last_status" "failed:pipeline_error"
      set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      log "kaggle_ingest=failed reason=pipeline_error"
      exit 1
    }
  log "$PIPELINE_OUTPUT"

  if printf "%s\n" "$PIPELINE_OUTPUT" | grep -q "^kaggle_download=error:"; then
    set_runtime_state "kaggle_last_status" "failed:download_error"
    set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "kaggle_ingest=failed reason=download_error"
    exit 1
  fi
  FILE_COUNT="$(printf "%s\n" "$PIPELINE_OUTPUT" | sed -n "s/.*Pipeline J (Kaggle): files=\\([0-9][0-9]*\\).*/\\1/p" | tail -n 1)"
  if [ -n "$FILE_COUNT" ] && [ "$FILE_COUNT" -eq 0 ]; then
    set_runtime_state "kaggle_last_status" "failed:no_supported_files"
    set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "kaggle_ingest=failed reason=no_supported_files"
    exit 1
  fi

  DOWNLOADS_TODAY=$((DOWNLOADS_TODAY + 1))
  ROWS_INSERTED="$(printf "%s\n" "$PIPELINE_OUTPUT" | sed -n "s/.*rows_inserted=\([0-9][0-9]*\).*/\1/p" | tail -n 1)"
  if [ -n "$ROWS_INSERTED" ]; then
    set_runtime_state "kaggle_last_rows_inserted" "$ROWS_INSERTED"
  fi
  set_runtime_state "kaggle_last_success_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set_runtime_state "kaggle_last_download_day" "${TODAY_UTC}"
  set_runtime_state "kaggle_downloads_today" "${DOWNLOADS_TODAY}"
  set_runtime_state "kaggle_last_status" "ok"
  log "kaggle_ingest=ok downloads_today=${DOWNLOADS_TODAY} limit=${DAILY_DOWNLOAD_LIMIT} max_files=${MAX_FILES_PER_RUN} max_rows_per_file=${MAX_ROWS_PER_FILE}"
else
  PIPELINE_OUTPUT="$(${PY_BIN} "$ROOT/pipeline_j_kaggle_polymarket.py" --max-files "${MAX_FILES_PER_RUN}" --max-rows-per-file "${MAX_ROWS_PER_FILE}" 2>&1)" || {
    log "$PIPELINE_OUTPUT"
    set_runtime_state "kaggle_last_status" "failed:pipeline_error"
    set_runtime_state "kaggle_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    log "kaggle_ingest=failed reason=pipeline_error"
    exit 1
  }
  log "$PIPELINE_OUTPUT"

  ROWS_INSERTED="$(printf "%s\n" "$PIPELINE_OUTPUT" | sed -n "s/.*rows_inserted=\([0-9][0-9]*\).*/\1/p" | tail -n 1)"
  if [ -n "$ROWS_INSERTED" ]; then
    set_runtime_state "kaggle_last_rows_inserted" "$ROWS_INSERTED"
  fi
  set_runtime_state "kaggle_last_success_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set_runtime_state "kaggle_last_status" "ok:local_files"
  log "kaggle_ingest=ok source=local_files max_files=${MAX_FILES_PER_RUN} max_rows_per_file=${MAX_ROWS_PER_FILE}"
fi
