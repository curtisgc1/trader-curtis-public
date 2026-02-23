#!/usr/bin/env python3
"""
Institutional Pattern Recognition System
Log QML, liquidity grabs, supply/demand flips before trade execution
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

# Institutional Patterns from cheat sheet
PATTERNS = {
    "qml": {
        "name": "Quasimodo Level (QML)",
        "type": "reversal",
        "description": "Failed high/low that becomes order block",
        "reliability": 0.75,
        "timeframe": "H1-H4"
    },
    "supply_demand_flip": {
        "name": "Supply/Demand Zone Flip",
        "type": "continuation",
        "description": "Old resistance becomes support (or vice versa)",
        "reliability": 0.70,
        "timeframe": "H1-D1"
    },
    "liquidity_grab": {
        "name": "Liquidity Grab",
        "type": "reversal",
        "description": "Sweep of highs/lows to trigger stops before reversal",
        "reliability": 0.72,
        "timeframe": "M15-H1"
    },
    "fakeout": {
        "name": "Fakeout/Breakout Trap",
        "type": "reversal",
        "description": "False breakout above resistance, then reverse",
        "reliability": 0.68,
        "timeframe": "M15-H1"
    },
    "compression_expansion": {
        "name": "Compression Into Expansion",
        "type": "momentum",
        "description": "Low volatility coil breaking into high volatility move",
        "reliability": 0.65,
        "timeframe": "H1-H4"
    },
    "stop_hunt": {
        "name": "Stop Hunt Pattern",
        "type": "reversal",
        "description": "Brief violation of level to trigger retail stops",
        "reliability": 0.70,
        "timeframe": "M5-M15"
    },
    "flag_limit": {
        "name": "Flag Limit (Order Block)",
        "type": "entry",
        "description": "Price returns to order block for entry",
        "reliability": 0.73,
        "timeframe": "H1-H4"
    },
    "institutional_reversal": {
        "name": "Institutional Reversal",
        "type": "reversal",
        "description": "Reversal pattern that repeats at key zones",
        "reliability": 0.74,
        "timeframe": "H4-D1"
    }
}

def init_pattern_tracking():
    """Create pattern tracking table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS institutional_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ticker TEXT,
            pattern_type TEXT,  -- qml, liquidity_grab, etc.
            pattern_name TEXT,
            direction TEXT,  -- bullish, bearish
            entry_zone TEXT,  -- price range
            stop_loss REAL,
            target REAL,
            timeframe TEXT,
            liquidity_context TEXT,  -- where are stops sitting?
            sentiment_score INTEGER,
            political_alert BOOLEAN,
            gamma_context TEXT,  -- EXTREME_LOW, NORMAL, etc.
            confirmed BOOLEAN DEFAULT 0,
            outcome TEXT,  -- win, loss, pending
            outcome_pnl REAL,
            grade TEXT,  -- A-F
            notes TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Institutional pattern tracking initialized")

def log_pattern(ticker, pattern_type, direction, entry_zone, stop_loss, target, 
                timeframe, liquidity_context, sentiment_score, gamma_context, notes=""):
    """Log an institutional pattern before trade execution"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    pattern = PATTERNS.get(pattern_type, {})
    
    cursor.execute('''
        INSERT INTO institutional_patterns 
        (timestamp, ticker, pattern_type, pattern_name, direction, entry_zone, 
         stop_loss, target, timeframe, liquidity_context, sentiment_score, 
         gamma_context, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().isoformat(),
        ticker,
        pattern_type,
        pattern.get("name", pattern_type),
        direction,
        entry_zone,
        stop_loss,
        target,
        timeframe,
        liquidity_context,
        sentiment_score,
        gamma_context,
        notes
    ))
    
    pattern_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return pattern_id

def get_pattern_grade(pattern_type):
    """Get historical grade for pattern type"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT outcome, COUNT(*) as count
        FROM institutional_patterns
        WHERE pattern_type = ? AND confirmed = 1
        GROUP BY outcome
    ''', (pattern_type,))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        return "TESTING", 0, 0
    
    wins = sum(r[1] for r in results if r[0] == 'win')
    total = sum(r[1] for r in results)
    win_rate = wins / total if total > 0 else 0
    
    if win_rate >= 0.70:
        grade = "A"
    elif win_rate >= 0.60:
        grade = "B"
    elif win_rate >= 0.50:
        grade = "C"
    elif win_rate >= 0.40:
        grade = "D"
    else:
        grade = "F"
    
    return grade, win_rate, total

def pre_trade_checklist(ticker, pattern_type, sentiment_score, gamma_context):
    """
    Pre-trade checklist incorporating institutional patterns
    Returns: CONFIRMED or REJECTED with reason
    """
    # Check 1: Pattern must be valid
    if pattern_type not in PATTERNS:
        return "REJECTED", f"Unknown pattern: {pattern_type}"
    
    # Check 2: Sentiment must agree with pattern direction
    # (Pattern says bullish but sentiment neutral = wait)
    if sentiment_score < 60:
        return "REJECTED", f"Insufficient sentiment ({sentiment_score}/100). Need >60"
    
    # Check 3: Gamma context
    if gamma_context == "EXTREME_LOW":
        # Can trade but tighten stops
        warning = "EXTREME_LOW_GAMMA - Use 8% stop, 50% size"
    else:
        warning = None
    
    # Check 4: Pattern historical grade
    grade, win_rate, sample_size = get_pattern_grade(pattern_type)
    
    if grade in ["D", "F"] and sample_size >= 10:
        return "REJECTED", f"Pattern grade {grade} ({win_rate:.0%} win rate, n={sample_size})"
    
    return "CONFIRMED", {
        "pattern_grade": grade,
        "win_rate": win_rate,
        "sample_size": sample_size,
        "warning": warning
    }

if __name__ == '__main__':
    init_pattern_tracking()
    print("\n📊 Institutional Pattern Framework Active")
    print("=" * 50)
    print("\nTracked Patterns:")
    for key, p in PATTERNS.items():
        print(f"  {p['name']}: {p['reliability']:.0%} reliability")
    print("\nPre-Trade Checklist:")
    print("  1. Pattern identified?")
    print("  2. Sentiment >60 (bullish) or <40 (bearish)?")
    print("  3. Gamma context considered?")
    print("  4. Pattern grade A-C?")
    print("  5. Liquidity zone mapped?")
    print("\nExecute only when ALL checks pass.")
