#!/usr/bin/env python3
"""
Pattern Recognition Loop — Run before EVERY trade
Validates institutional pattern + sentiment alignment
"""

import json
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

def pattern_recognition_loop(ticker, chart_image_path=None):
    """
    Pre-trade pattern recognition loop
    Returns: APPROVED (with details) or REJECTED (with reason)
    """
    
    print("=" * 60)
    print(f"🔍 PATTERN RECOGNITION LOOP — {ticker}")
    print("=" * 60)
    
    # Step 1: Identify Pattern
    print("\n📊 Step 1: Identify Pattern")
    print("-" * 40)
    print("Analyze chart for:")
    print("  [ ] QML (Quasimodo Level) — Failed high/low, order block")
    print("  [ ] Supply/Demand Flip — Old resistance → support")
    print("  [ ] Liquidity Grab — Sweep of equal highs/lows")
    print("  [ ] Fakeout — Break + immediate rejection")
    print("  [ ] Compression → Expansion — Coil building energy")
    print("  [ ] Stop Hunt — Brief violation, immediate reversal")
    print("  [ ] Flag Limit — Return to order block")
    print("  [ ] Institutional Reversal — Double top, H&S, etc.")
    
    pattern = input("\nPattern identified? (qml/flip/grab/fakeout/compression/stophunt/flag/reversal/none): ").strip().lower()
    
    if pattern == "none" or not pattern:
        return "REJECTED", "No institutional pattern identified"
    
    # Pattern reliability
    reliability = {
        "qml": 75, "institutional_reversal": 74, "flag": 73,
        "liquidity_grab": 72, "flip": 70, "stophunt": 70,
        "fakeout": 68, "compression": 65
    }.get(pattern, 0)
    
    print(f"  → Pattern: {pattern.upper()} | Reliability: {reliability}%")
    
    # Step 2: Map Liquidity
    print("\n🎯 Step 2: Map Liquidity Zone")
    print("-" * 40)
    print("Where are the stops sitting?")
    print("  - Equal highs/lows above/below?")
    print("  - Previous swing points?")
    print("  - Retail stop clusters?")
    liquidity_zone = input("Liquidity zone identified? (price level): ").strip()
    
    if not liquidity_zone:
        return "REJECTED", "Liquidity zone not mapped"
    
    print(f"  → Liquidity at: ${liquidity_zone}")
    
    # Step 3: Check Sentiment
    print("\n📈 Step 3: Sentiment Confirmation")
    print("-" * 40)
    sentiment = input("Current sentiment score (0-100): ").strip()
    
    try:
        sentiment = int(sentiment)
    except:
        sentiment = 50
    
    direction = input("Pattern direction (bullish/bearish): ").strip().lower()
    
    if direction == "bullish" and sentiment < 60:
        print(f"  ⚠️ Sentiment {sentiment} below bullish threshold (60)")
        confirm = input("  Override? (y/n): ").strip().lower()
        if confirm != 'y':
            return "REJECTED", f"Insufficient sentiment ({sentiment}/100) for bullish pattern"
    
    if direction == "bearish" and sentiment > 40:
        print(f"  ⚠️ Sentiment {sentiment} above bearish threshold (40)")
        confirm = input("  Override? (y/n): ").strip().lower()
        if confirm != 'y':
            return "REJECTED", f"Insufficient sentiment ({sentiment}/100) for bearish pattern"
    
    print(f"  → Sentiment: {sentiment}/100 | Direction: {direction} ✅")
    
    # Step 4: Gamma/Political Context
    print("\n⚡ Step 4: Macro Filters")
    print("-" * 40)
    gamma = input("Gamma context (extreme_low/low/normal/high/extreme_high): ").strip().lower()
    political = input("Political alerts active? (y/n): ").strip().lower()
    
    adjustments = []
    if gamma == "extreme_low":
        adjustments.append("TIGHTEN_STOPS_TO_8_PERCENT")
        adjustments.append("REDUCE_SIZE_50_PERCENT")
        print("  ⚠️ EXTREME LOW GAMMA — Expect violent moves")
    
    if political == 'y':
        adjustments.append("POLITICAL_ALERT_ACTIVE")
        print("  ⚠️ Political alert — Confirm catalyst direction")
    
    # Step 5: Calculate Trade Parameters
    print("\n🎯 Step 5: Trade Parameters")
    print("-" * 40)
    
    entry = input("Entry price: ").strip()
    stop = input("Stop loss: ").strip()
    target = input("Target: ").strip()
    
    try:
        entry_f = float(entry)
        stop_f = float(stop)
        target_f = float(target)
        
        risk = abs(entry_f - stop_f)
        reward = abs(target_f - entry_f)
        rr = reward / risk if risk > 0 else 0
        
        print(f"  → Risk/Reward: 1:{rr:.1f}")
        
        if rr < 2.0:
            confirm = input("  ⚠️ R:R below 2.0 — Proceed? (y/n): ").strip().lower()
            if confirm != 'y':
                return "REJECTED", "Risk/Reward below minimum 2:1"
    except:
        return "REJECTED", "Invalid price inputs"
    
    # Step 6: Final Confirmation
    print("\n✅ Step 6: Final Confirmation")
    print("-" * 40)
    print(f"Pattern: {pattern.upper()} ({reliability}% reliability)")
    print(f"Direction: {direction.upper()}")
    print(f"Sentiment: {sentiment}/100")
    print(f"Entry: ${entry} | Stop: ${stop} | Target: ${target}")
    print(f"R:R: 1:{rr:.1f}")
    
    if adjustments:
        print("\nAdjustments:")
        for adj in adjustments:
            print(f"  • {adj}")
    
    final = input("\nExecute trade via Alpaca? (y/n): ").strip().lower()
    
    if final == 'y':
        return "APPROVED", {
            "ticker": ticker,
            "pattern": pattern,
            "reliability": reliability,
            "direction": direction,
            "sentiment": sentiment,
            "entry": entry_f,
            "stop": stop_f,
            "target": target_f,
            "rr": rr,
            "liquidity_zone": liquidity_zone,
            "adjustments": adjustments,
            "timestamp": datetime.now().isoformat()
        }
    else:
        return "REJECTED", "User cancelled"

if __name__ == '__main__':
    print("=" * 60)
    print("INSTITUTIONAL PATTERN RECOGNITION LOOP")
    print("Run this BEFORE every trade")
    print("=" * 60)
    print()
    print("This validates:")
    print("  ✓ Pattern identified on chart")
    print("  ✓ Liquidity zone mapped")
    print("  ✓ Sentiment confirms direction")
    print("  ✓ Gamma/political filters applied")
    print("  ✓ Risk/Reward acceptable")
    print()
    
    ticker = input("Enter ticker: ").strip().upper()
    result, details = pattern_recognition_loop(ticker)
    
    print("\n" + "=" * 60)
    print(f"RESULT: {result}")
    print("=" * 60)
    
    if result == "APPROVED":
        print("\n✅ TRADE APPROVED — Ready for Alpaca execution")
        print(f"\nDetails:")
        for key, val in details.items():
            print(f"  {key}: {val}")
    else:
        print(f"\n❌ TRADE REJECTED — {details}")
