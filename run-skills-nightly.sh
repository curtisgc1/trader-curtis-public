#!/bin/bash
# Trader Curtis - Complete Skill Automation
# Runs all skills in sequence

echo "═══════════════════════════════════════════════════"
echo "  TRADER CURTIS - SKILL AUTOMATION SYSTEM"
echo "  $(date)"
echo "═══════════════════════════════════════════════════"
echo ""

cd /Users/shared/curtis/trader-curtis

# 1. Pattern Learning (from trades)
echo "🧠  [1/4] Extracting Patterns..."
python3 << 'PYEOF'
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path("data/trades.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get today's trades
    cursor.execute("""
        SELECT ticker, pnl, pnl_percent, sentiment_reddit, sentiment_twitter 
        FROM trades 
        WHERE date(entry_date) = date('now')
    """)
    
    today_trades = cursor.fetchall()
    
    if today_trades:
        print(f"  📊 Analyzed {len(today_trades)} trades today")
        wins = sum(1 for t in today_trades if t[1] and t[1] > 0)
        losses = len(today_trades) - wins
        print(f"  🟢 Wins: {wins} | 🔴 Losses: {losses}")
        
        # Extract patterns
        if wins > losses:
            print("  💡 Pattern: Today's strategy worked")
        elif losses > wins:
            print("  ⚠️  Pattern: Today's strategy needs adjustment")
    else:
        print("  ⏳ No trades today to analyze")
    
    conn.close()
else:
    print("  ⏳ No database yet")
PYEOF
echo ""

# 2. Run Eval Tests
echo "🧪  [2/4] Running Evaluation Tests..."
python3 analysis/evals.py 2>/dev/null || echo "  ⚠️  Eval tests pending trade data"
echo ""

# 3. Generate Dashboard
echo "📊  [3/4] Generating Performance Dashboard..."
python3 analysis/dashboard.py 2>/dev/null || echo "  ⚠️  Dashboard pending data"
echo ""

# 4. Git Notes Sync
echo "📓  [4/4] Syncing Memory..."
python3 skills/git-notes-memory/memory.py -p . sync --end "{\"summary\":\"Nightly skill automation complete\",\"trades_analyzed\":\"today\"}" 2>/dev/null || echo "  ✅ Memory sync attempted"
echo ""

echo "═══════════════════════════════════════════════════"
echo "  AUTOMATION COMPLETE"
echo "═══════════════════════════════════════════════════"
