#!/usr/bin/env python3
"""
Trump & Bessent Post Monitor
Tracks Trump and Treasury Secretary Bessent posts for market-moving content
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"

def init_trump_tracking():
    """Add posts table to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT,
            post_date TEXT,
            platform TEXT,
            content TEXT,
            tickers_mentioned TEXT,
            sentiment TEXT,
            market_impact TEXT,
            price_move_1h REAL,
            price_move_1d REAL,
            noted_at TEXT
        )
    '')
    
    conn.commit()
    conn.close()

def log_post(author, date, platform, content, tickers=None):
    """Log a post with ticker mentions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO posts 
        (author, post_date, platform, content, tickers_mentioned, noted_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (author, date, platform, content, json.dumps(tickers or []), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    if tickers:
        emoji = "🔴" if author == "Trump" else "🟡"
        print(f"{emoji} {author.upper()} POST ALERT: Mentioned {', '.join(tickers)}")

def check_recent_impact(author, ticker, hours=24):
    """Check if author mentioned this ticker recently"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    cursor.execute('''
        SELECT post_date, content, sentiment 
        FROM posts 
        WHERE author = ?
        AND tickers_mentioned LIKE ? 
        AND post_date > ?
        ORDER BY post_date DESC
    ''', (author, f'%"{ticker}"%', since))
    
    results = cursor.fetchall()
    conn.close()
    
    return results

# Legacy alias
check_recent_trump_impact = lambda ticker, hours=24: check_recent_impact("Trump", ticker, hours)

if __name__ == '__main__':
    init_trump_tracking()
    print("Trump & Bessent monitoring initialized")
