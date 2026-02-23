#!/usr/bin/env python3
"""
Simplified source outcome logger - just track the essentials
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

def log_simple_outcome(symbol, entry, exit_price, pnl, pnl_pct, grade, sources):
    """Simplified logging that captures source performance"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create simple table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS simple_source_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            trade_grade TEXT,
            outcome TEXT,
            sources TEXT,  -- JSON of all source scores
            bullish_count INTEGER,
            bearish_count INTEGER,
            neutral_count INTEGER,
            combo_used TEXT,
            created_at TEXT
        )
    ''')
    
    # Count predictions
    bullish = sum(1 for s in sources.values() if s.get('score', 50) > 60)
    bearish = sum(1 for s in sources.values() if s.get('score', 50) < 40)
    neutral = sum(1 for s in sources.values() if 40 <= s.get('score', 50) <= 60)
    
    outcome = 'win' if pnl > 0 else 'loss'
    
    # Find combo (sources that agreed)
    if bullish >= 2:
        combo = '+'.join([k for k, v in sources.items() if v.get('score', 50) > 60])
    elif bearish >= 2:
        combo = '+'.join([k for k, v in sources.items() if v.get('score', 50) < 40])
    else:
        combo = 'no_consensus'
    
    cursor.execute('''
        INSERT INTO simple_source_outcomes 
        (ticker, entry_price, exit_price, pnl, pnl_pct, trade_grade, outcome,
         sources, bullish_count, bearish_count, neutral_count, combo_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        symbol, entry, exit_price, pnl, pnl_pct, grade, outcome,
        json.dumps(sources), bullish, bearish, neutral, combo,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()
    print(f"✅ Logged {symbol}: {grade} | Bulls:{bullish} Bears:{bearish} Neut:{neutral} | Combo:{combo}")

def analyze_sources():
    """Analyze which sources perform best"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM simple_source_outcomes')
        rows = cursor.fetchall()
    except:
        print("⚠️ No data yet")
        return
    
    print(f"\n📊 Analyzed {len(rows)} trades:\n")
    
    for row in rows:
        ticker = row[1]
        pnl_pct = row[5]
        grade = row[6]
        outcome = row[7]
        sources = json.loads(row[8])
        bullish = row[9]
        bearish = row[10]
        neutral = row[11]
        combo = row[12]
        
        print(f"  {ticker}: {pnl_pct:+.1f}% ({grade}) - Bulls:{bullish} Bears:{bearish} Neut:{neutral}")
        if combo != 'no_consensus':
            print(f"    → Combo used: {combo}")
    
    conn.close()

if __name__ == '__main__':
    # Test with sample data
    test_sources = {
        'reddit_wsb': {'score': 50, 'prediction': 'neutral'},
        'twitter': {'score': 50, 'prediction': 'neutral'},
        'grok_ai': {'score': 50, 'prediction': 'neutral'}
    }
    
    print("🧪 Testing source outcome logging...")
    log_simple_outcome('TEST', 100.0, 90.0, -100.0, -10.0, 'D', test_sources)
    analyze_sources()
