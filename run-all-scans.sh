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

echo "📰 RUNNING PIPELINE F (FINVIZ FREE RSS)..."
/Users/Shared/curtis/trader-curtis/pipeline_f_finviz.py 2>/dev/null || true
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

echo "👀 INGESTING TRACKED POLYMARKET WALLET ACTIVITY..."
/Users/Shared/curtis/trader-curtis/ingest_polymarket_wallet_activity.py 2>/dev/null || true
echo ""

echo "🗳️ RUNNING POLYMARKET PIPELINE..."
/Users/Shared/curtis/trader-curtis/pipeline_polymarket.py || true
echo ""

echo "🌤️ RUNNING PIPELINE G (WEATHER PROBS)..."
/Users/Shared/curtis/trader-curtis/pipeline_g_weather.py 2>/dev/null || true
echo ""

echo "🧬 RUNNING PIPELINE B (LONG-TERM INNOVATION)..."
/Users/Shared/curtis/trader-curtis/pipeline_b_innovation.py 2>/dev/null || true
echo ""

echo "🚀 RUNNING PIPELINE E (BREAKTHROUGHS)..."
/Users/Shared/curtis/trader-curtis/pipeline_e_breakthroughs.py 2>/dev/null || true
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

echo "🎯 ALIGNING HIGH-SIGNAL PLAYS TO POLYMARKET..."
/Users/Shared/curtis/trader-curtis/align_high_signal_polymarket.py 2>/dev/null || true
echo ""

echo "🧮 BUILDING POLYMARKET MM SNAPSHOTS..."
/Users/Shared/curtis/trader-curtis/polymarket_mm_engine.py 2>/dev/null || true
echo ""

ROUTE_LIMIT=$(sqlite3 /Users/Shared/curtis/trader-curtis/data/trades.db "SELECT value FROM execution_controls WHERE key='auto_route_limit' LIMIT 1;" 2>/dev/null)
ROUTE_NOTIONAL=$(sqlite3 /Users/Shared/curtis/trader-curtis/data/trades.db "SELECT value FROM execution_controls WHERE key='auto_route_notional' LIMIT 1;" 2>/dev/null)
if [ -z "$ROUTE_LIMIT" ]; then ROUTE_LIMIT=24; fi
if [ -z "$ROUTE_NOTIONAL" ]; then ROUTE_NOTIONAL=75; fi

echo "🛡️ APPLYING EXECUTION GUARDS + ROUTING..."
/Users/Shared/curtis/trader-curtis/signal_router.py --mode paper --limit "$ROUTE_LIMIT" --notional "$ROUTE_NOTIONAL" 2>/dev/null || true
echo ""

echo "📤 EXECUTING APPROVED ROUTES (PAPER WORKER)..."
/Users/Shared/curtis/trader-curtis/execution_worker.py 2>/dev/null || true
echo ""

echo "🗳️ POLYMARKET EXECUTION..."
/Users/Shared/curtis/trader-curtis/scripts/with_polymarket_keychain.sh python3.11 /Users/Shared/curtis/trader-curtis/execution_polymarket.py || true
echo ""

echo "🔄 SYNCING ALPACA ORDER STATUS..."
/Users/Shared/curtis/trader-curtis/sync_alpaca_order_status.py 2>/dev/null || true
echo ""

echo "📊 RANKING SOURCES..."
/Users/Shared/curtis/trader-curtis/source_ranker.py 2>/dev/null || true
/Users/Shared/curtis/trader-curtis/score_polymarket_wallets.py 2>/dev/null || true
echo ""

echo "🧹 APPLYING TABLE RETENTION..."
/Users/Shared/curtis/trader-curtis/maintain_tables.py 2>/dev/null || true
echo ""

echo "🔐 SYNCING WALLET CONFIG..."
/Users/Shared/curtis/trader-curtis/sync_wallet_config.py 2>/dev/null || true
echo ""

echo "📚 UPDATING LEARNING FEEDBACK..."
/Users/Shared/curtis/trader-curtis/update_learning_feedback.py 2>/dev/null || true
echo ""

echo "═══════════════════════════════════════════════════"
echo "  ANALYSIS COMPLETE"
echo "═══════════════════════════════════════════════════"
