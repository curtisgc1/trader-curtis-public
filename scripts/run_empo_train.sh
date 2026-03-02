#!/usr/bin/env bash
# EMPO² Training Gateway — daily-gated MLX LoRA trainer
# Paper: arXiv:2602.23008 (ICLR 2026)
#
# Usage: ./scripts/run_empo_train.sh [--dry-run]
#
# Prerequisites:
#   pip install mlx mlx_lm
#   python3 -m training.empo.build_dataset --mlx

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY_BIN="${PY_BIN:-python3}"
DRY_RUN=""

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
fi

echo "============================================================"
echo "EMPO² Training Gateway"
echo "============================================================"
echo "  Root: $ROOT"
echo "  Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

# Check if EMPO training is enabled
ENABLED=$($PY_BIN -c "
import sqlite3
conn = sqlite3.connect('$ROOT/data/trades.db')
cur = conn.cursor()
cur.execute(\"SELECT value FROM execution_controls WHERE key='empo_mlx_train_enabled' LIMIT 1\")
row = cur.fetchone()
print(str(row[0]) if row else '0')
conn.close()
" 2>/dev/null || echo "0")

if [[ "$ENABLED" != "1" ]]; then
    echo "  EMPO² training disabled (empo_mlx_train_enabled != 1)"
    echo "  Enable: UPDATE execution_controls SET value='1' WHERE key='empo_mlx_train_enabled';"
    exit 0
fi

# Step 1: Build dataset
echo "  Step 1: Building EMPO² dataset..."
$PY_BIN -m training.empo.build_dataset --mlx 2>&1 | sed 's/^/    /'
echo ""

# Step 2: Train
echo "  Step 2: Running EMPO² training..."
$PY_BIN -m training.empo.trainer $DRY_RUN 2>&1 | sed 's/^/    /'

echo ""
echo "============================================================"
echo "  EMPO² training complete"
echo "============================================================"
