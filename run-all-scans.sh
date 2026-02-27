#!/bin/bash
# Complete Trader Curtis Sentiment Suite
# Runs all scanners and generates report
# Errors are captured — no silent failures

set -o pipefail

DB="/Users/Shared/curtis/trader-curtis/data/trades.db"
LOG_DIR="/Users/Shared/curtis/trader-curtis/logs"
RUN_LOG="$LOG_DIR/last-scan-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$LOG_DIR"

FAILURES=()
PASS=0
FAIL=0

# Record pipeline run status to pipeline_runtime_state table
record_run() {
    local key="$1" status="$2" detail="$3"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    sqlite3 "$DB" \
        "INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('run:${key}:status','${status}','${ts}')
         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
         INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('run:${key}:last_run','${ts}','${ts}')
         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
         INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('run:${key}:detail','${detail}','${ts}')
         ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;" 2>/dev/null || true
}

# Run a pipeline script, capture errors, log health
run_step() {
    local label="$1" key="$2"
    shift 2
    local cmd=("$@")

    echo "  → ${label}..."
    local err_output
    err_output=$("${cmd[@]}" 2>&1)
    local rc=$?

    if [ $rc -eq 0 ]; then
        echo "    ✅ OK"
        record_run "$key" "ok" ""
        PASS=$((PASS + 1))
    else
        echo "    ❌ FAILED (exit $rc)"
        # Show last 3 lines of error for diagnosis
        echo "$err_output" | tail -3 | sed 's/^/       /'
        record_run "$key" "error:$rc" "$(echo "$err_output" | tail -1 | tr '\n' ' ' | cut -c1-200)"
        FAILURES+=("$label")
        FAIL=$((FAIL + 1))
    fi
    echo "$err_output" >> "$RUN_LOG" 2>&1
    echo ""
}

echo "═══════════════════════════════════════════════════"
echo "  TRADER CURTIS — SCAN $(date '+%Y-%m-%d %H:%M')"
echo "═══════════════════════════════════════════════════"
echo ""

# ── SOCIAL / SENTIMENT ────────────────────────────────
echo "── SOCIAL FEEDS ─────────────────────────────────"
run_step "StockTwits scanner"  "stocktwits"  node /Users/Shared/curtis/trader-curtis/integrated-scanner.js
run_step "Reddit scanner"      "reddit"      node /Users/Shared/curtis/trader-curtis/reddit-scanner.js
run_step "Pipeline F (Finviz)" "pipeline_f"  /Users/Shared/curtis/trader-curtis/pipeline_f_finviz.py

if command -v bird &> /dev/null; then
    run_step "X/Twitter (bird)"   "x_bird"  bird search "trading OR stock OR market" -n 5
fi

# ── SIGNAL PIPELINES ──────────────────────────────────
echo "── SIGNAL PIPELINES ─────────────────────────────"
run_step "Pipeline D (Bookmarks)"  "pipeline_d"  /Users/Shared/curtis/trader-curtis/pipeline_d_bookmarks.py
run_step "Pipeline X (X handles)"  "pipeline_x"  /Users/Shared/curtis/trader-curtis/pipeline_x_handle_bridge.py
run_step "Pipeline A (Liquidity)"  "pipeline_a"  /Users/Shared/curtis/trader-curtis/pipeline_a_liquidity.py
run_step "Chart Liquidity"         "pipeline_chart" /Users/Shared/curtis/trader-curtis/pipeline_chart_liquidity.py
run_step "Pipeline H (Kyle W)"     "pipeline_h"  /Users/Shared/curtis/trader-curtis/pipeline_h_kyle_williams.py
run_step "Pipeline G (Weather)"    "pipeline_g"  /Users/Shared/curtis/trader-curtis/pipeline_g_weather.py
run_step "Pipeline B (Innovation)" "pipeline_b"  /Users/Shared/curtis/trader-curtis/pipeline_b_innovation.py
run_step "Pipeline E (Breakthroughs)" "pipeline_e" /Users/Shared/curtis/trader-curtis/pipeline_e_breakthroughs.py
run_step "Pipeline C (Events)"     "pipeline_c"  /Users/Shared/curtis/trader-curtis/pipeline_c_event.py
run_step "Pipeline K (VIX Regime)" "pipeline_k"  /Users/Shared/curtis/trader-curtis/pipeline_k_vix_regime.py
run_step "Event alert engine"      "event_alerts" /Users/Shared/curtis/trader-curtis/event_alert_engine.py

# ── POLYMARKET ────────────────────────────────────────
echo "── POLYMARKET ───────────────────────────────────"
run_step "Polymarket pipeline"     "polymarket"  /Users/Shared/curtis/trader-curtis/pipeline_polymarket.py
run_step "Momentum scanner"        "pm_momentum" /Users/Shared/curtis/trader-curtis/polymarket_momentum_scanner.py
run_step "Options bridge"          "pm_options"  /Users/Shared/curtis/trader-curtis/polymarket_options_bridge.py
run_step "Wallet activity ingest"  "pm_wallets"  /Users/Shared/curtis/trader-curtis/ingest_polymarket_wallet_activity.py
run_step "Wallet scorer"           "pm_scores"   /Users/Shared/curtis/trader-curtis/score_polymarket_wallets.py
run_step "MM snapshots"            "pm_mm"       /Users/Shared/curtis/trader-curtis/polymarket_mm_engine.py

# ── CANDIDATE GENERATION ──────────────────────────────
echo "── CANDIDATE GENERATION ─────────────────────────"
run_step "Reweight input sources"  "reweight"    /Users/Shared/curtis/trader-curtis/reweight_input_sources.py
run_step "Generate trade candidates" "candidates" /Users/Shared/curtis/trader-curtis/generate_trade_candidates.py
run_step "Kelly signal"            "kelly"       /Users/Shared/curtis/trader-curtis/kelly_signal.py
run_step "Align to Polymarket"     "pm_align"    /Users/Shared/curtis/trader-curtis/align_high_signal_polymarket.py

CANDIDATE_COUNT=$(sqlite3 "$DB" "SELECT count(*) FROM trade_candidates;" 2>/dev/null)
echo "  → Candidates in DB: ${CANDIDATE_COUNT:-0}"
record_run "candidates" "ok" "count=${CANDIDATE_COUNT:-0}"
echo ""

# ── ROUTING & EXECUTION ───────────────────────────────
echo "── ROUTING & EXECUTION ──────────────────────────"
ROUTE_LIMIT=$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='auto_route_limit' LIMIT 1;" 2>/dev/null)
ROUTE_NOTIONAL=$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='auto_route_notional' LIMIT 1;" 2>/dev/null)
[ -z "$ROUTE_LIMIT" ] && ROUTE_LIMIT=24
[ -z "$ROUTE_NOTIONAL" ] && ROUTE_NOTIONAL=75

run_step "Signal router (paper)"   "router"  /Users/Shared/curtis/trader-curtis/signal_router.py --mode paper --limit "$ROUTE_LIMIT" --notional "$ROUTE_NOTIONAL"
run_step "Execution worker (paper)" "exec_worker" /Users/Shared/curtis/trader-curtis/execution_worker.py
run_step "Polymarket execution"    "pm_exec" /Users/Shared/curtis/trader-curtis/scripts/run_polymarket_exec.sh

# ── POSITION MANAGEMENT ───────────────────────────────
echo "── POSITION MANAGEMENT ──────────────────────────"
if command -v python3.11 >/dev/null 2>&1; then PY=python3.11; else PY=python3; fi
run_step "Alpaca order sync"       "alpaca_sync"  $PY /Users/Shared/curtis/trader-curtis/sync_alpaca_order_status.py
run_step "Open position mgmt"      "pos_mgmt"     $PY /Users/Shared/curtis/trader-curtis/manage_open_positions.py
run_step "Execute position intents" "pos_intents"  $PY /Users/Shared/curtis/trader-curtis/execute_position_intents.py

# ── RECONCILIATION ───────────────────────────────────
echo "── RECONCILIATION ─────────────────────────────"
run_step "Reconcile realized (equity+HL)" "reconcile_equity" $PY /Users/Shared/curtis/trader-curtis/reconcile_realized_outcomes_equity.py

# ── LEARNING & SCORING ────────────────────────────────
echo "── LEARNING & SCORING ───────────────────────────"
run_step "Source ranker"           "source_rank"   /Users/Shared/curtis/trader-curtis/source_ranker.py

# Heavy resolvers (Alpaca price lookups for counterfactual + horizon scoring) run once per day.
# Every 4h scan: fast feedback only. Once per day (age >= 20h): full resolve with price lookups.
LAST_HEAVY=$(sqlite3 "$DB" "SELECT value FROM pipeline_runtime_state WHERE key='run:heavy_resolvers:last_run';" 2>/dev/null)
NOW_EPOCH=$(date +%s)
LAST_EPOCH=0
if [ -n "$LAST_HEAVY" ]; then
  LAST_EPOCH=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$LAST_HEAVY" +%s 2>/dev/null || echo 0)
fi
AGE_HOURS=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))

if [ "$AGE_HOURS" -ge 20 ]; then
  echo "  → Full resolve pass (heavy resolvers, last ran ${AGE_HOURS}h ago)"
  run_step "Learning feedback (full)" "learning" /Users/Shared/curtis/trader-curtis/update_learning_feedback.py
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  sqlite3 "$DB" "INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('run:heavy_resolvers:last_run','${TS}','${TS}') ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;" 2>/dev/null || true

  # Candidate scoring (truth layer) — runs during heavy pass only (needs price lookups)
  SCORING_ENABLED=$(sqlite3 "$DB" "SELECT value FROM execution_controls WHERE key='candidate_scoring_enabled' LIMIT 1;" 2>/dev/null)
  [ -z "$SCORING_ENABLED" ] && SCORING_ENABLED=1
  if [ "$SCORING_ENABLED" = "1" ]; then
    run_step "Score all candidates" "candidate_scoring" $PY /Users/Shared/curtis/trader-curtis/score_all_candidates.py
  fi
else
  echo "  → Fast feedback only (heavy resolvers ran ${AGE_HOURS}h ago, skipping price lookups)"
  run_step "Learning feedback (fast)" "learning" env SKIP_HEAVY_RESOLVERS=1 /Users/Shared/curtis/trader-curtis/update_learning_feedback.py
fi

run_step "Auto-tuner"              "auto_tune"     /Users/Shared/curtis/trader-curtis/auto_tune_controls.py

# ── MAINTENANCE ───────────────────────────────────────
echo "── MAINTENANCE ──────────────────────────────────"
run_step "Table retention"         "maintain"  /Users/Shared/curtis/trader-curtis/maintain_tables.py
run_step "Wallet config sync"      "wallet_sync" /Users/Shared/curtis/trader-curtis/sync_wallet_config.py

# ── VERIFICATION ──────────────────────────────────────
echo "── VERIFICATION ─────────────────────────────────"
/Users/Shared/curtis/trader-curtis/scripts/trade_claim_guard.sh 2>/dev/null || true
/Users/Shared/curtis/trader-curtis/scripts/pipeline_digest_check.sh 2>/dev/null || true
echo ""

# ── SUMMARY ───────────────────────────────────────────
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "═══════════════════════════════════════════════════"
echo "  SCAN COMPLETE — $TS"
echo "  ✅ Passed: $PASS  ❌ Failed: $FAIL"
if [ ${#FAILURES[@]} -gt 0 ]; then
    echo ""
    echo "  FAILED STEPS:"
    for f in "${FAILURES[@]}"; do
        echo "    • $f"
    done
    echo ""
    echo "  Full log: $RUN_LOG"
fi
echo "═══════════════════════════════════════════════════"

# Write scan summary to DB
sqlite3 "$DB" \
    "INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('scan:last_run','${TS}','${TS}')
     ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
     INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('scan:last_pass_count','${PASS}','${TS}')
     ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
     INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('scan:last_fail_count','${FAIL}','${TS}')
     ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
     INSERT INTO pipeline_runtime_state(key,value,updated_at) VALUES('scan:last_fail_steps','$(IFS=,; echo "${FAILURES[*]}")','${TS}')
     ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;" 2>/dev/null || true

exit $FAIL
