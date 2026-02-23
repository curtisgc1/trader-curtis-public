#!/usr/bin/env python3
"""
Trader Curtis - SENTIMENT ACCURACY TRACKER
Tracks which sources predict correctly over time
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

def init_sentiment_db():
    """Initialize sentiment tracking tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if table exists with old schema
    cursor.execute("PRAGMA table_info(sentiment_accuracy)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    if existing_columns and 'pnl_pct' not in existing_columns:
        # Table exists but needs migration
        print("🔄 Migrating sentiment_accuracy table...")
        cursor.execute('ALTER TABLE sentiment_accuracy RENAME TO sentiment_accuracy_old')
        
        # Create new table with full schema
        cursor.execute('''
            CREATE TABLE sentiment_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT,
                source TEXT,
                predicted_direction TEXT,
                actual_direction TEXT,
                accuracy_score REAL,
                sentiment_score INTEGER,
                trade_grade TEXT,
                pnl_pct REAL,
                created_at TEXT
            )
        ''')
        
        # Migrate old data
        cursor.execute('''
            INSERT INTO sentiment_accuracy 
            (id, ticker, date, source, predicted_direction, actual_direction, accuracy_score)
            SELECT id, ticker, prediction_date, source, predicted_direction, actual_direction, accuracy_score
            FROM sentiment_accuracy_old
        ''')
        
        cursor.execute('DROP TABLE sentiment_accuracy_old')
        print("✅ Migration complete")
    elif not existing_columns:
        # Create new table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sentiment_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT,
                source TEXT,
                predicted_direction TEXT,
                actual_direction TEXT,
                accuracy_score REAL,
                sentiment_score INTEGER,
                trade_grade TEXT,
                pnl_pct REAL,
                created_at TEXT
            )
        ''')
    
    # Source performance summary (matches existing schema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_performance (
            source TEXT PRIMARY KEY,
            total_signals INTEGER DEFAULT 0,
            bullish_signals INTEGER DEFAULT 0,
            bearish_signals INTEGER DEFAULT 0,
            wins_when_bullish INTEGER DEFAULT 0,
            losses_when_bullish INTEGER DEFAULT 0,
            wins_when_bearish INTEGER DEFAULT 0,
            losses_when_bearish INTEGER DEFAULT 0,
            neutral_signals INTEGER DEFAULT 0,
            win_rate_bullish REAL DEFAULT 0,
            win_rate_bearish REAL DEFAULT 0,
            overall_accuracy REAL DEFAULT 0,
            avg_pnl_when_followed REAL DEFAULT 0,
            grade TEXT DEFAULT 'C',
            last_updated TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Sentiment accuracy tables initialized")

def log_sentiment_result(ticker, source, predicted, actual, score, trade_grade, pnl_pct):
    """Log a sentiment prediction result"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Determine accuracy score
    predicted_bullish = score > 60
    predicted_bearish = score < 40
    actual_gain = pnl_pct > 0
    
    if predicted_bullish and actual_gain:
        accuracy = 1.0
    elif predicted_bearish and not actual_gain:
        accuracy = 1.0
    elif predicted_bullish and not actual_gain:
        accuracy = 0.0
    elif predicted_bearish and actual_gain:
        accuracy = 0.0
    else:
        accuracy = 0.5  # Neutral prediction
    
    cursor.execute('''
        INSERT INTO sentiment_accuracy 
        (ticker, date, source, predicted_direction, actual_direction, accuracy_score, sentiment_score, trade_grade, pnl_pct, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        ticker,
        datetime.now().strftime('%Y-%m-%d'),
        source,
        'bullish' if predicted_bullish else ('bearish' if predicted_bearish else 'neutral'),
        'gain' if actual_gain else 'loss',
        accuracy,
        score,
        trade_grade,
        pnl_pct,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()
    print(f"📝 Logged {source} sentiment accuracy for {ticker}: {accuracy}")

def update_source_performance():
    """Update overall accuracy stats for each source"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all sources from sentiment_accuracy
    cursor.execute('SELECT DISTINCT source FROM sentiment_accuracy')
    sources = cursor.fetchall()
    
    for (source,) in sources:
        # Get predictions for this source
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN accuracy_score = 1.0 THEN 1 ELSE 0 END) as correct,
                AVG(CASE WHEN accuracy_score = 1.0 THEN pnl_pct ELSE NULL END) as avg_pnl,
                SUM(CASE WHEN predicted_direction = 'bullish' THEN 1 ELSE 0 END) as bullish,
                SUM(CASE WHEN predicted_direction = 'bearish' THEN 1 ELSE 0 END) as bearish,
                SUM(CASE WHEN predicted_direction = 'neutral' THEN 1 ELSE 0 END) as neutral
            FROM sentiment_accuracy
            WHERE source = ?
        ''', (source,))
        
        row = cursor.fetchone()
        if row and row[0] > 0:
            total, correct, avg_pnl, bullish, bearish, neutral = row
            accuracy = (correct / total * 100) if total > 0 else 0
            
            # Determine grade
            if accuracy >= 80:
                grade = 'A'
            elif accuracy >= 70:
                grade = 'B'
            elif accuracy >= 50:
                grade = 'C'
            elif accuracy >= 30:
                grade = 'D'
            else:
                grade = 'F'
            
            cursor.execute('''
                INSERT OR REPLACE INTO source_performance 
                (source, total_signals, overall_accuracy, avg_pnl_when_followed, 
                 bullish_signals, bearish_signals, neutral_signals, grade, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                source,
                total,
                accuracy,
                avg_pnl or 0,
                bullish or 0,
                bearish or 0,
                neutral or 0,
                grade,
                datetime.now().isoformat()
            ))
    
    conn.commit()
    conn.close()
    print("✅ Source performance updated")

def get_accuracy_report():
    """Generate sentiment accuracy report"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM source_performance ORDER BY overall_accuracy DESC')
    sources = cursor.fetchall()
    
    cursor.execute('''
        SELECT 
            ticker,
            AVG(accuracy_score) as avg_accuracy,
            COUNT(*) as predictions
        FROM sentiment_accuracy
        GROUP BY ticker
        ORDER BY avg_accuracy DESC
    ''')
    
    by_ticker = cursor.fetchall()
    conn.close()
    
    return {'sources': sources, 'by_ticker': by_ticker}

def generate_sentiment_report():
    """Generate standalone sentiment accuracy report"""
    data = get_accuracy_report()
    
    report = f"""# 📊 SENTIMENT ACCURACY REPORT
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M PST')}

---

## 🎯 SOURCE PERFORMANCE RANKING

| Source | Predictions | Accuracy | Grade | Avg PnL | Bullish | Bearish |
|--------|-------------|----------|-------|---------|---------|---------|
"""
    
    for src in data['sources']:
        # schema: source, total_signals, bullish_signals, bearish_signals, wins_when_bullish, 
        # losses_when_bullish, wins_when_bearish, losses_when_bearish, neutral_signals, 
        # win_rate_bullish, win_rate_bearish, overall_accuracy, avg_pnl_when_followed, grade, last_updated
        source, total_signals, bullish, bearish, _, _, _, _, neutral, _, _, accuracy, avg_pnl, grade, _ = src
        emoji = '🟢' if accuracy >= 70 else ('🟡' if accuracy >= 50 else '🔴')
        report += f"| {emoji} {source} | {total_signals} | {accuracy:.1f}% | {grade} | {avg_pnl:+.1f}% | {bullish} | {bearish} |\n"
    
    report += f"""
---

## 📈 ACCURACY BY TICKER

| Ticker | Avg Accuracy | Predictions |
|--------|--------------|-------------|
"""
    
    for tck in data['by_ticker']:
        ticker, avg_acc, preds = tck
        pct = avg_acc * 100
        emoji = '🟢' if pct > 60 else ('🟡' if pct > 40 else '🔴')
        report += f"| {emoji} {ticker} | {pct:.1f}% | {preds} |\n"
    
    report += f"""
---

## 🧠 KEY INSIGHTS

### High Confidence Signals (Score >70 or <30)
These should be weighted heavily in future decisions.

### Neutral Signals (Score 40-60)
These had no predictive value - consider not trading on neutral sentiment.

### Best Performing Source
The source with highest accuracy_rate should be trusted most.

### Worst Performing Source
The source with lowest accuracy_rate should be ignored or inverted.

---
*Generated by Sentiment Accuracy Tracker*
"""
    
    # Save report
    report_file = SCRIPT_DIR / "memory" / f"SENTIMENT-ACCURACY-{datetime.now().strftime('%Y-%m-%d')}.md"
    report_file.parent.mkdir(exist_ok=True)
    
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"📄 Sentiment accuracy report saved: {report_file}")
    return report

if __name__ == '__main__':
    print("=" * 70)
    print("📊 SENTIMENT ACCURACY TRACKER")
    print("=" * 70)
    
    init_sentiment_db()
    update_source_performance()
    generate_sentiment_report()
    
    print("\n✅ Complete!")
