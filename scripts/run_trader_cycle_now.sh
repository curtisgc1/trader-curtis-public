#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
"$ROOT/scripts/trader_cycle_locked.sh" manual
tail -n 80 "$ROOT/logs/trader-cycle.log"

