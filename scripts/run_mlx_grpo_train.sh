#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
PY_BIN="$(command -v python3.11 || command -v python3)"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/mlx-grpo-train.log"
LOCK_DIR="/tmp/trader-curtis-mlx-grpo-train.lock"
NO_STATE_WRITE="${GRPO_RUNTIME_NO_STATE_WRITE:-0}"

mkdir -p "$LOG_DIR" "$ROOT/models"

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
  if [ ! -f "$DB" ]; then
    return 0
  fi
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
}

START_EPOCH="$(date +%s)"
START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set_runtime_state "grpo_mlx_last_attempt_utc" "$START_UTC"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  set_runtime_state "grpo_mlx_last_status" "skipped:lock_active"
  log "mlx_grpo_train=skipped reason=lock_active"
  exit 0
fi
cleanup() {
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ -z "${PY_BIN}" ]; then
  set_runtime_state "grpo_mlx_last_status" "failed:no_python"
  set_runtime_state "grpo_mlx_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "mlx_grpo_train=failed reason=no_python"
  exit 1
fi

if [ ! -f "$DB" ]; then
  set_runtime_state "grpo_mlx_last_status" "failed:db_missing"
  set_runtime_state "grpo_mlx_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log "mlx_grpo_train=failed reason=db_missing path=$DB"
  exit 1
fi

ENABLED="${GRPO_MLX_TRAIN_ENABLED:-$(get_control "grpo_mlx_train_enabled" "0")}"
if [ "$ENABLED" != "1" ]; then
  set_runtime_state "grpo_mlx_last_status" "skipped:disabled"
  log "mlx_grpo_train=skipped reason=disabled"
  exit 0
fi

FORCE_TRAIN="${FORCE_MLX_GRPO_TRAIN:-0}"
MIN_HOURS_BETWEEN_RUNS="${GRPO_MLX_MIN_HOURS_BETWEEN_RUNS:-$(get_control "grpo_mlx_min_hours_between_runs" "24")}"
DAILY_LIMIT="${GRPO_MLX_DAILY_LIMIT:-$(get_control "grpo_mlx_daily_train_limit" "1")}"
LAST_SUCCESS_UTC="$(get_runtime_state "grpo_mlx_last_train_utc")"

if [ "$FORCE_TRAIN" != "1" ] && [ -n "$LAST_SUCCESS_UTC" ]; then
  HOURS_SINCE_LAST="$(sqlite3 "$DB" "SELECT ROUND((julianday('now') - julianday('${LAST_SUCCESS_UTC}')) * 24.0, 2);" 2>/dev/null || true)"
  if [ -z "${HOURS_SINCE_LAST}" ]; then
    HOURS_SINCE_LAST=99999
  fi
  if awk "BEGIN {exit !(${HOURS_SINCE_LAST} < ${MIN_HOURS_BETWEEN_RUNS})}"; then
    set_runtime_state "grpo_mlx_last_status" "skipped:min_hours_gate"
    log "mlx_grpo_train=skipped reason=min_hours_gate hours_since_last=${HOURS_SINCE_LAST} min_hours=${MIN_HOURS_BETWEEN_RUNS}"
    exit 0
  fi
fi

TODAY_UTC="$(date -u +%F)"
LAST_DAY="$(get_runtime_state "grpo_mlx_last_train_day")"
TRAINS_TODAY="$(get_runtime_state "grpo_mlx_trains_today")"
if [ -z "${TRAINS_TODAY}" ]; then
  TRAINS_TODAY=0
fi
if [ -z "${LAST_DAY}" ] || [ "${LAST_DAY}" != "${TODAY_UTC}" ]; then
  TRAINS_TODAY=0
fi
if [ "$FORCE_TRAIN" != "1" ] && [ "${TRAINS_TODAY}" -ge "${DAILY_LIMIT}" ]; then
  set_runtime_state "grpo_mlx_last_status" "skipped:daily_limit_reached"
  log "mlx_grpo_train=skipped reason=daily_limit_reached trains_today=${TRAINS_TODAY} limit=${DAILY_LIMIT}"
  exit 0
fi

BASE_MODEL="${GRPO_MLX_BASE_MODEL:-$(get_control "grpo_mlx_base_model" "mlx-community/Qwen2.5-7B-Instruct-4bit")}"
ADAPTER_PATH_RAW="${GRPO_MLX_ADAPTER_PATH:-$(get_control "grpo_mlx_adapter_path" "models/mlx-grpo-adapter")}"
if [[ "$ADAPTER_PATH_RAW" = /* ]]; then
  ADAPTER_PATH="$ADAPTER_PATH_RAW"
else
  ADAPTER_PATH="$ROOT/$ADAPTER_PATH_RAW"
fi

FINE_TUNE_TYPE="${GRPO_MLX_FINE_TUNE_TYPE:-$(get_control "grpo_mlx_fine_tune_type" "lora")}"
ITERS="${GRPO_MLX_ITERS:-$(get_control "grpo_mlx_iters" "120")}"
BATCH_SIZE="${GRPO_MLX_BATCH_SIZE:-$(get_control "grpo_mlx_batch_size" "2")}"
LEARNING_RATE="${GRPO_MLX_LEARNING_RATE:-$(get_control "grpo_mlx_learning_rate" "0.00001")}"
STEPS_PER_REPORT="${GRPO_MLX_STEPS_PER_REPORT:-$(get_control "grpo_mlx_steps_per_report" "10")}"
STEPS_PER_EVAL="${GRPO_MLX_STEPS_PER_EVAL:-$(get_control "grpo_mlx_steps_per_eval" "25")}"
GRAD_ACCUM="${GRPO_MLX_GRAD_ACCUMULATION_STEPS:-$(get_control "grpo_mlx_grad_accum_steps" "4")}"
MAX_SEQ_LENGTH="${GRPO_MLX_MAX_SEQ_LENGTH:-$(get_control "grpo_mlx_max_seq_length" "1024")}"
NUM_LAYERS="${GRPO_MLX_NUM_LAYERS:-$(get_control "grpo_mlx_num_layers" "16")}"
MASK_PROMPT="${GRPO_MLX_MASK_PROMPT:-$(get_control "grpo_mlx_mask_prompt" "0")}"
MIN_TRAIN_ROWS="${GRPO_MLX_MIN_TRAIN_ROWS:-$(get_control "grpo_mlx_min_train_rows" "40")}"
TEST_AFTER_TRAIN="${GRPO_MLX_TEST_AFTER_TRAIN:-$(get_control "grpo_mlx_test_after_train" "1")}"
DRY_RUN="${DRY_RUN_MLX_GRPO_TRAIN:-$(get_control "grpo_mlx_dry_run" "0")}"

DATA_DIR="$ROOT/datasets/mlx_grpo_lora"
mkdir -p "$(dirname "$ADAPTER_PATH")" "$DATA_DIR"

log "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] mlx_grpo_train=prepare"
# Build dataset: wins-only + counterfactual wins from non-taken routes (all horizons)
# --wins-only: only successful calls go into training data — model learns what works
# --include-operational: use operationally-resolved outcomes in addition to realized
# --counterfactual-horizon 24: use 1-day horizon for counterfactual wins
"$PY_BIN" "$ROOT/training/grpo/build_grpo_dataset.py" --include-operational --wins-only --counterfactual-horizon 24 | tee -a "$LOG_FILE"
"$PY_BIN" "$ROOT/training/grpo/build_mlx_lora_dataset.py" --out-dir "$DATA_DIR" | tee -a "$LOG_FILE"

TRAIN_ROWS="0"
if [ -f "$DATA_DIR/train.jsonl" ]; then
  TRAIN_ROWS="$(wc -l < "$DATA_DIR/train.jsonl" | tr -d ' ')"
fi
set_runtime_state "grpo_mlx_last_train_rows" "$TRAIN_ROWS"
if [ "${TRAIN_ROWS}" -lt "${MIN_TRAIN_ROWS}" ]; then
  set_runtime_state "grpo_mlx_last_status" "skipped:insufficient_rows"
  log "mlx_grpo_train=skipped reason=insufficient_rows train_rows=${TRAIN_ROWS} min_rows=${MIN_TRAIN_ROWS}"
  exit 0
fi

CMD=(
  "$PY_BIN" -m mlx_lm lora
  --train
  --model "$BASE_MODEL"
  --data "$DATA_DIR"
  --fine-tune-type "$FINE_TUNE_TYPE"
  --adapter-path "$ADAPTER_PATH"
  --iters "$ITERS"
  --batch-size "$BATCH_SIZE"
  --learning-rate "$LEARNING_RATE"
  --steps-per-report "$STEPS_PER_REPORT"
  --steps-per-eval "$STEPS_PER_EVAL"
  --grad-accumulation-steps "$GRAD_ACCUM"
  --max-seq-length "$MAX_SEQ_LENGTH"
  --num-layers "$NUM_LAYERS"
)

if [ "$MASK_PROMPT" = "1" ]; then
  CMD+=(--mask-prompt)
fi
if [ "$TEST_AFTER_TRAIN" = "1" ]; then
  CMD+=(--test)
fi

if [ "$DRY_RUN" = "1" ]; then
  set_runtime_state "grpo_mlx_last_status" "dry_run"
  set_runtime_state "grpo_mlx_last_model" "$BASE_MODEL"
  set_runtime_state "grpo_mlx_last_adapter_path" "$ADAPTER_PATH"
  log "mlx_grpo_train=dry_run model=${BASE_MODEL} train_rows=${TRAIN_ROWS} adapter_path=${ADAPTER_PATH}"
  printf 'mlx_grpo_train_cmd=' | tee -a "$LOG_FILE"
  printf '%q ' "${CMD[@]}" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  exit 0
fi

RUN_LOG="$(mktemp)"
trap 'rm -f "$RUN_LOG"; cleanup' EXIT

log "mlx_grpo_train=starting model=${BASE_MODEL} train_rows=${TRAIN_ROWS} iters=${ITERS} batch_size=${BATCH_SIZE}"
if ! "${CMD[@]}" 2>&1 | tee -a "$LOG_FILE" "$RUN_LOG"; then
  set_runtime_state "grpo_mlx_last_status" "failed:mlx_lm_lora_error"
  set_runtime_state "grpo_mlx_last_error_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set_runtime_state "grpo_mlx_last_model" "$BASE_MODEL"
  set_runtime_state "grpo_mlx_last_adapter_path" "$ADAPTER_PATH"
  log "mlx_grpo_train=failed reason=mlx_lm_lora_error"
  exit 1
fi

TEST_LOSS="$(sed -n 's/^Test loss \([0-9][0-9.]*\),.*/\1/p' "$RUN_LOG" | tail -n 1)"
if [ -n "$TEST_LOSS" ]; then
  set_runtime_state "grpo_mlx_last_test_loss" "$TEST_LOSS"
fi

TRAINS_TODAY=$((TRAINS_TODAY + 1))
END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DURATION_SEC="$(( $(date +%s) - START_EPOCH ))"
set_runtime_state "grpo_mlx_last_train_utc" "$END_UTC"
set_runtime_state "grpo_mlx_last_train_day" "$TODAY_UTC"
set_runtime_state "grpo_mlx_trains_today" "$TRAINS_TODAY"
set_runtime_state "grpo_mlx_last_status" "ok"
set_runtime_state "grpo_mlx_last_model" "$BASE_MODEL"
set_runtime_state "grpo_mlx_last_adapter_path" "$ADAPTER_PATH"
set_runtime_state "grpo_mlx_last_duration_sec" "$DURATION_SEC"

log "mlx_grpo_train=ok trains_today=${TRAINS_TODAY} limit=${DAILY_LIMIT} duration_sec=${DURATION_SEC} adapter_path=${ADAPTER_PATH}"
