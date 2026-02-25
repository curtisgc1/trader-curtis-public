#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"
PY_BIN="$(command -v python3.11 || command -v python3)"
KAGGLE_BIN="$HOME/Library/Python/3.11/bin/kaggle"
KAGGLE_JSON="${KAGGLE_CONFIG_DIR:-$HOME/.kaggle}/kaggle.json"

echo "== Local GRPO Stack Check =="
echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "host=$(hostname)"
echo "chip=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)"
echo "ram_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo unknown)"
echo "python=$PY_BIN"

echo ""
echo "-- Python libs --"
"$PY_BIN" - <<'PY'
import importlib
for name in ["mlx", "mlx.core", "mlx_lm", "transformers", "torch"]:
    try:
        mod = importlib.import_module(name)
        ver = getattr(mod, "__version__", "n/a")
        print(f"{name}=ok version={ver}")
    except Exception as e:
        print(f"{name}=missing error={e.__class__.__name__}:{e}")
PY

echo ""
echo "-- Ollama --"
if command -v ollama >/dev/null 2>&1; then
  echo "ollama_bin=$(command -v ollama)"
  echo "ollama_version=$(ollama --version 2>/dev/null || echo unknown)"
  echo "ollama_models:"
  ollama list 2>/dev/null || true
  echo "ollama_running:"
  ollama ps 2>/dev/null || true
else
  echo "ollama_bin=missing"
fi

echo ""
echo "-- Kaggle --"
if [ -x "$KAGGLE_BIN" ]; then
  echo "kaggle_bin=$KAGGLE_BIN"
  echo "kaggle_version=$("$KAGGLE_BIN" --version 2>/dev/null || echo unknown)"
else
  echo "kaggle_bin=missing"
fi
if [ -f "$KAGGLE_JSON" ]; then
  echo "kaggle_credentials=present file=$KAGGLE_JSON"
else
  echo "kaggle_credentials=missing file=$KAGGLE_JSON"
fi

echo ""
echo "-- Controls --"
if [ -f "$DB" ]; then
  sqlite3 "$DB" "SELECT key||'='||value FROM execution_controls WHERE key IN (
    'grpo_alignment_enabled','grpo_apply_weight_updates','grpo_llm_reasoner_enabled','grpo_local_model',
    'kaggle_auto_pull_enabled','kaggle_poly_dataset_slug','kaggle_daily_download_limit',
    'kaggle_min_hours_between_runs','kaggle_max_files_per_run','kaggle_max_rows_per_file',
    'runtime:kaggle_last_success_utc'
  ) ORDER BY key;" || true
else
  echo "db_missing=$DB"
fi

echo ""
echo "-- Alignment Dry Run --"
"$ROOT/scripts/run_grpo_alignment.sh" || true
