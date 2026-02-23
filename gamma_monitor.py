#!/usr/bin/env python3
"""
Dealer Gamma Monitor - Track S&P gamma levels for volatility signals
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

# Gamma thresholds for alerts
GAMMA_THRESHOLDS = {
    "extreme_low": 500,      # $500M - shock absorbers gone
    "low": 2000,             # $2B - below average, elevated vol
    "normal_low": 4000,      # $4B - lower end of normal
    "normal": 5200,          # $5.2B historical average
    "high": 8000,            # $8B - suppressed volatility
    "extreme_high": 12000    # $12B - max suppression
}

def init_gamma_tracking():
    """Create gamma tracking table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dealer_gamma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            spx_gamma REAL,  -- in millions
            gamma_level TEXT,  -- extreme_low, low, normal, high, extreme_high
            historical_avg REAL,
            percentile REAL,
            sources TEXT,  -- JSON array
            signal TEXT,  -- VOLATILITY_EXPANSION, VOLATILITY_SUPPRESSION, NORMAL
            alert_triggered BOOLEAN,
            notes TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def log_gamma_reading(gamma_millions, sources, notes=""):
    """Log a gamma reading and generate signal"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    avg = GAMMA_THRESHOLDS["normal"]
    percentile = (gamma_millions / avg) * 100
    
    # Determine level
    if gamma_millions < GAMMA_THRESHOLDS["extreme_low"]:
        level = "EXTREME_LOW"
        signal = "VOLATILITY_EXPANSION"
        alert = True
    elif gamma_millions < GAMMA_THRESHOLDS["low"]:
        level = "LOW"
        signal = "ELEVATED_VOLATILITY"
        alert = True
    elif gamma_millions > GAMMA_THRESHOLDS["extreme_high"]:
        level = "EXTREME_HIGH"
        signal = "MAX_SUPPRESSION"
        alert = True
    elif gamma_millions > GAMMA_THRESHOLDS["high"]:
        level = "HIGH"
        signal = "VOLATILITY_SUPPRESSION"
        alert = False
    else:
        level = "NORMAL"
        signal = "NORMAL"
        alert = False
    
    cursor.execute('''
        INSERT INTO dealer_gamma 
        (timestamp, spx_gamma, gamma_level, historical_avg, percentile, sources, signal, alert_triggered, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().isoformat(),
        gamma_millions,
        level,
        avg,
        percentile,
        json.dumps(sources),
        signal,
        alert,
        notes
    ))
    
    conn.commit()
    conn.close()
    
    if alert:
        return f"🚨 GAMMA ALERT: {level} (${gamma_millions}M) - {signal}"
    return f"Gamma logged: {level} (${gamma_millions}M)"

if __name__ == '__main__':
    init_gamma_tracking()
    # Log today's extreme reading
    result = log_gamma_reading(
        200,  # $200M
        ["@zerohedge", "@TheBronxViking"],
        "Post-OpEx dealer gamma collapse. Historical average $5.2B. Expect violent moves."
    )
    print(result)
    print("\n📊 Dealer Gamma Monitor Initialized")
    print(f"Current: $200M | Average: $5.2B | Percentile: 3.8%")
    print("\n🚨 ALERT: EXTREME LOW GAMMA")
    print("   Dealers not hedging. Shock absorbers removed.")
    print("   Historical pattern: Near-zero gamma = violent moves")
    print("   Action: Tighten stops, reduce size, expect outsized moves")
