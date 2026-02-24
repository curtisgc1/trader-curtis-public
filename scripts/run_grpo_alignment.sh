#!/bin/bash
set -euo pipefail
ROOT="/Users/Shared/curtis/trader-curtis"
PY_BIN="$(command -v python3.11 || command -v python3)"
if [ -z "${PY_BIN}" ]; then
  echo "No Python interpreter found"
  exit 1
fi

"${PY_BIN}" "$ROOT/grpo_hgrm_weekly.py"
