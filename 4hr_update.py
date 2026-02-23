#!/usr/bin/env python3
"""
Trader Curtis - 4 Hour Status Update
Run this every 4 hours to show trading activity
"""

import json
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

def show_4hr_update():
    print("📊 4HR TRADING UPDATE")
    print("=" * 50)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}\n")
    
    # Load positions
    positions_file = SCRIPT_DIR / "data" / "open_positions.json"
    if positions_file.exists():
        with open(positions_file) as f:
            positions = json.load(f)
        
        print(f"Positions ({len(positions)} open):")
        for p in positions:
            print(f"  {p['symbol']}: {p['shares']} @ ${p['entry_price']}")
            print(f"    Stop: ${p['stop_loss']} | Target: ${p['take_profit']}")
            print(f"    Sentiment: {p['sentiment_score']}/100")
            print()
    else:
        print("No open positions")
    
    # Load recent trades
    trades_file = SCRIPT_DIR / "memory" / f"TRADES-{datetime.now().strftime('%Y-%m-%d')}.json"
    if trades_file.exists():
        with open(trades_file) as f:
            trades = json.load(f)
        print(f"New today: {len(trades)} trades entered")
    
    print("\nNext update in 4 hours.")
    print("=" * 50)

if __name__ == '__main__':
    show_4hr_update()
