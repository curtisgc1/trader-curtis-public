#!/bin/bash
# Complete Trader Curtis Sentiment Suite
# Runs all scanners and generates report

echo "═══════════════════════════════════════════════════"
echo "  TRADER CURTIS - COMPLETE SENTIMENT ANALYSIS"
echo "═══════════════════════════════════════════════════"
echo ""

# StockTwits
echo "🔍 SCANNING STOCKTWITS..."
node /Users/Shared/curtis/trader-curtis/integrated-scanner.js 2>/dev/null
echo ""

# Reddit
echo "🔍 SCANNING REDDIT..."
node /Users/Shared/curtis/trader-curtis/reddit-scanner.js 2>/dev/null
echo ""

# X/Twitter (if bird configured)
if command -v bird &> /dev/null; then
    echo "🔍 CHECKING X/TWITTER..."
    bird search "trading OR stock OR market" -n 5 2>/dev/null | head -20
    echo ""
fi

echo "🔗 INGESTING BOOKMARK THESES (PIPELINE D)..."
/Users/Shared/curtis/trader-curtis/pipeline_d_bookmarks.py 2>/dev/null || true
echo ""

echo "⚡ RUNNING PIPELINE A (LIQUIDITY SCALP)..."
/Users/Shared/curtis/trader-curtis/pipeline_a_liquidity.py 2>/dev/null || true
echo ""

echo "📈 RUNNING CHART LIQUIDITY PIPELINE..."
/Users/Shared/curtis/trader-curtis/pipeline_chart_liquidity.py 2>/dev/null || true
echo ""

echo "🗳️ RUNNING POLYMARKET PIPELINE..."
/Users/Shared/curtis/trader-curtis/pipeline_polymarket.py 2>/dev/null || true
echo ""

echo "🧬 RUNNING PIPELINE B (LONG-TERM INNOVATION)..."
/Users/Shared/curtis/trader-curtis/pipeline_b_innovation.py 2>/dev/null || true
echo ""

echo "🚨 BUILDING EVENT ALERTS..."
/Users/Shared/curtis/trader-curtis/event_alert_engine.py 2>/dev/null || true
echo ""

echo "🌍 RUNNING PIPELINE C (EVENT ALPHA)..."
/Users/Shared/curtis/trader-curtis/pipeline_c_event.py 2>/dev/null || true
echo ""

echo "🧠 BUILDING TRADE CANDIDATES..."
/Users/Shared/curtis/trader-curtis/generate_trade_candidates.py 2>/dev/null || true
echo ""

echo "🛡️ APPLYING EXECUTION GUARDS + ROUTING..."
/Users/Shared/curtis/trader-curtis/signal_router.py --mode paper --limit 12 --notional 100 2>/dev/null || true
echo ""

echo "📤 EXECUTING APPROVED ROUTES (PAPER WORKER)..."
/Users/Shared/curtis/trader-curtis/execution_worker.py 2>/dev/null || true
echo ""

echo "🗳️ POLYMARKET EXECUTION (SCAFFOLD)..."
/Users/Shared/curtis/trader-curtis/execution_polymarket.py 2>/dev/null || true
echo ""

echo "🔄 SYNCING ALPACA ORDER STATUS..."
/Users/Shared/curtis/trader-curtis/sync_alpaca_order_status.py 2>/dev/null || true
echo ""

echo "📊 RANKING SOURCES..."
/Users/Shared/curtis/trader-curtis/source_ranker.py 2>/dev/null || true
echo ""

echo "🧹 APPLYING TABLE RETENTION..."
/Users/Shared/curtis/trader-curtis/maintain_tables.py 2>/dev/null || true
echo ""

echo "📚 UPDATING LEARNING FEEDBACK..."
/Users/Shared/curtis/trader-curtis/update_learning_feedback.py 2>/dev/null || true
echo ""

echo "═══════════════════════════════════════════════════"
echo "  ANALYSIS COMPLETE"
echo "═══════════════════════════════════════════════════"
