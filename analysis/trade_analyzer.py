#!/usr/bin/env python3
"""
Trader Curtis - Trade Outcome Analyzer
Runs automatically on trade exit to extract learnings
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"

def init_db():
    """Initialize the trade analysis database"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            shares INTEGER,
            pnl REAL,
            pnl_percent REAL,
            status TEXT,
            sentiment_reddit INTEGER,
            sentiment_twitter INTEGER,
            sentiment_trump INTEGER,
            source_reddit_wsb TEXT,
            source_reddit_stocks TEXT,
            source_reddit_investing TEXT,
            source_twitter_general TEXT,
            source_twitter_analysts TEXT,
            source_trump_posts TEXT,
            source_news TEXT,
            source_accuracy_score REAL,
            thesis TEXT,
            outcome_analysis TEXT,
            lesson_learned TEXT,
            decision_grade TEXT,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentiment_accuracy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            prediction_date TEXT,
            predicted_direction TEXT,
            actual_direction TEXT,
            accuracy_score REAL,
            source TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def log_trade_outcome(trade_data):
    """Log a completed trade with full analysis"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO trades VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    ''', (
        trade_data.get('trade_id'),
        trade_data.get('ticker'),
        trade_data.get('entry_date'),
        trade_data.get('exit_date'),
        trade_data.get('entry_price'),
        trade_data.get('exit_price'),
        trade_data.get('shares'),
        trade_data.get('pnl'),
        trade_data.get('pnl_percent'),
        trade_data.get('status'),
        trade_data.get('sentiment_reddit'),
        trade_data.get('sentiment_twitter'),
        trade_data.get('thesis'),
        trade_data.get('outcome_analysis'),
        trade_data.get('lesson_learned'),
        trade_data.get('decision_grade'),
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()
    print(f"✓ Logged trade outcome for {trade_data.get('ticker')}")

def analyze_sentiment_accuracy(ticker, entry_date, predicted, actual):
    """Track whether sentiment predictions were correct"""
    accuracy = 1.0 if (predicted == actual) else 0.0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO sentiment_accuracy 
        (ticker, prediction_date, predicted_direction, actual_direction, accuracy_score, source)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (ticker, entry_date, predicted, actual, accuracy, 'aggregate'))
    
    conn.commit()
    conn.close()
    return accuracy

def get_performance_summary():
    """Generate summary of trading performance"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            SUM(pnl) as total_pnl,
            AVG(pnl_percent) as avg_return,
            AVG(CASE WHEN pnl > 0 THEN pnl_percent END) as avg_win,
            AVG(CASE WHEN pnl < 0 THEN pnl_percent END) as avg_loss
        FROM trades WHERE status = 'closed'
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    return {
        'total_trades': result[0] or 0,
        'wins': result[1] or 0,
        'losses': result[2] or 0,
        'win_rate': (result[1] / result[0] * 100) if result[0] else 0,
        'total_pnl': result[3] or 0,
        'avg_return': result[4] or 0,
        'avg_win': result[5] or 0,
        'avg_loss': result[6] or 0
    }

if __name__ == '__main__':
    init_db()
    print("Trade analysis database initialized")
    
    # If run with JSON arg, log that trade
    if len(sys.argv) > 1:
        try:
            trade_data = json.loads(sys.argv[1])
            log_trade_outcome(trade_data)
        except json.JSONDecodeError:
            print("Error: Invalid JSON")
