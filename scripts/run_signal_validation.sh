#!/bin/bash
# Signal-only validation run (no execution submission)
set -euo pipefail

BASE="/Users/Shared/curtis/trader-curtis"

echo "═══════════════════════════════════════════════════"
echo "  TRADER CURTIS - SIGNAL VALIDATION (NO EXECUTION)"
echo "═══════════════════════════════════════════════════"

echo "🔍 SCANNING STOCKTWITS..."
node "$BASE/integrated-scanner.js" 2>/dev/null || true

echo "🔍 SCANNING REDDIT..."
node "$BASE/reddit-scanner.js" 2>/dev/null || true

echo "🔗 PIPELINE D (BOOKMARKS)..."
"$BASE/pipeline_d_bookmarks.py" 2>/dev/null || true

echo "⚡ PIPELINE A (LIQUIDITY)..."
"$BASE/pipeline_a_liquidity.py" 2>/dev/null || true

echo "📈 CHART LIQUIDITY..."
"$BASE/pipeline_chart_liquidity.py" 2>/dev/null || true

echo "🗳️ POLYMARKET PIPELINE..."
"$BASE/pipeline_polymarket.py" 2>/dev/null || true

echo "🧬 PIPELINE B (INNOVATION)..."
"$BASE/pipeline_b_innovation.py" 2>/dev/null || true

echo "🚨 EVENT ALERT ENGINE..."
"$BASE/event_alert_engine.py" 2>/dev/null || true

echo "🌍 PIPELINE C (EVENT ALPHA)..."
"$BASE/pipeline_c_event.py" 2>/dev/null || true

echo "🧠 GENERATE CANDIDATES..."
"$BASE/generate_trade_candidates.py" 2>/dev/null || true

echo "🛡️ ROUTE ONLY (PAPER MODE)..."
"$BASE/signal_router.py" --mode paper --limit 12 --notional 100 2>/dev/null || true

echo "📚 REFRESH LEARNING + SCORES..."
"$BASE/update_learning_feedback.py" 2>/dev/null || true
"$BASE/source_ranker.py" 2>/dev/null || true

echo "✅ SIGNAL VALIDATION COMPLETE (NO EXECUTION CALLED)"
