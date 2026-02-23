#!/usr/bin/env python3
"""
Trader Curtis Eval Tests
Validates trading strategy effectiveness
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"

def test_sentiment_accuracy():
    """EVAL: Does WSB sentiment predict 3-day moves?"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ticker, sentiment_reddit, pnl 
        FROM trades 
        WHERE sentiment_reddit IS NOT NULL 
        AND status = 'closed'
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        return {"status": "PENDING", "reason": "No closed trades with sentiment data"}
    
    correct = sum(1 for r in results if (r[1] > 50 and r[2] > 0) or (r[1] < 50 and r[2] < 0))
    accuracy = correct / len(results) * 100
    
    return {
        "test": "sentiment_accuracy",
        "status": "PASS" if accuracy > 60 else "FAIL",
        "accuracy": f"{accuracy:.1f}%",
        "sample_size": len(results),
        "threshold": "60%"
    }

def test_risk_management():
    """EVAL: Are stops preventing large losses?"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT MAX(ABS(pnl_percent)) 
        FROM trades 
        WHERE status = 'closed'
    ''')
    
    max_loss = cursor.fetchone()[0] or 0
    conn.close()
    
    return {
        "test": "risk_management",
        "status": "PASS" if max_loss <= 20 else "FAIL",
        "max_loss": f"{max_loss:.1f}%",
        "threshold": "20%"
    }

def test_position_sizing():
    """EVAL: Are positions within $500 limit?"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) FROM trades 
        WHERE entry_price * shares > 500
    ''')
    
    violations = cursor.fetchone()[0]
    conn.close()
    
    return {
        "test": "position_sizing",
        "status": "PASS" if violations == 0 else "FAIL",
        "violations": violations,
        "threshold": "0"
    }

def run_all_evals():
    """Run complete eval suite"""
    evals = [
        test_sentiment_accuracy(),
        test_risk_management(),
        test_position_sizing()
    ]
    
    report = {
        "timestamp": "now",
        "evals": evals,
        "passed": sum(1 for e in evals if e["status"] == "PASS"),
        "total": len(evals)
    }
    
    print(json.dumps(report, indent=2))
    return report

if __name__ == '__main__':
    run_all_evals()
