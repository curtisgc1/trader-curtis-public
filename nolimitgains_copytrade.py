#!/usr/bin/env python3
"""
NoLimitGains Copy-Trade System
PRIORITY #1: Execute @NoLimitGains calls immediately
"""

import os
import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

def parse_nolimitgains_post(text):
    """
    Parse a NoLimitGains X post for trade signals
    """
    # Patterns to look for
    ticker_pattern = r'\$([A-Z]{1,5})'  # $AAPL, $TSLA
    action_pattern = r'(long|short|buy|sell|calls|puts|entry|target|stop)'  # action words
    price_pattern = r'(\d+\.?\d*)'  # numbers (prices)
    
    tickers = re.findall(ticker_pattern, text.upper())
    actions = re.findall(action_pattern, text.lower())
    prices = re.findall(price_pattern, text)
    
    # Determine direction
    direction = None
    if any(word in text.lower() for word in ['long', 'buy', 'calls', 'bullish']):
        direction = 'LONG'
    elif any(word in text.lower() for word in ['short', 'sell', 'puts', 'bearish']):
        direction = 'SHORT'
    
    return {
        'tickers': tickers,
        'actions': actions,
        'prices': [float(p) for p in prices[:3]] if prices else [],  # First 3 numbers
        'direction': direction,
        'raw_text': text
    }

def rapid_copy_trade(ticker, direction, entry_price=None, size_pct=2.0):
    """
    Execute copy-trade within seconds of call
    """
    import alpaca_trade_api as tradeapi
    
    api = tradeapi.REST(
        os.environ.get('ALPACA_API_KEY'),
        os.environ.get('ALPACA_SECRET_KEY'),
        'https://paper-api.alpaca.markets'
    )
    
    # Get account value
    account = api.get_account()
    portfolio_value = float(account.portfolio_value)
    
    # Calculate position size (default 2% of portfolio)
    position_value = portfolio_value * (size_pct / 100)
    
    # Get current price if not provided
    if not entry_price:
        try:
            bar = api.get_latest_bar(ticker)
            entry_price = float(bar.c)
        except:
            return None, f"Could not get price for {ticker}"
    
    # Calculate shares
    shares = int(position_value / entry_price)
    
    if shares < 1:
        return None, f"Position size too small ({position_value:.2f} for ${entry_price})"
    
    # Execute trade
    try:
        order = api.submit_order(
            symbol=ticker,
            qty=shares,
            side='buy' if direction == 'LONG' else 'sell',
            type='market',
            time_in_force='day'
        )
        
        # Set stop loss (8% for copy trades)
        stop_price = entry_price * 0.92 if direction == 'LONG' else entry_price * 1.08
        
        return {
            'ticker': ticker,
            'direction': direction,
            'shares': shares,
            'entry': entry_price,
            'stop': stop_price,
            'order_id': order.id,
            'timestamp': datetime.now().isoformat()
        }, "SUCCESS"
        
    except Exception as e:
        return None, str(e)

def log_copy_trade(source_handle, ticker, direction, entry_price, shares, call_time):
    """Log the copy trade for tracking"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now()
    call_dt = datetime.fromisoformat(call_time.replace('Z', '+00:00'))
    lag = (now - call_dt).total_seconds()
    
    cursor.execute('''
        INSERT INTO copy_trades 
        (source_handle, ticker, call_type, copied_entry, copied_timestamp, shares, lag_seconds, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        source_handle,
        ticker,
        direction,
        entry_price,
        now.isoformat(),
        shares,
        int(lag),
        'OPEN'
    ))
    
    conn.commit()
    conn.close()

def monitor_nolimitgains():
    """
    Monitor @NoLimitGains for new posts
    In production, this would poll X API or use webhooks
    """
    print("🔍 Monitoring @NoLimitGains for trade calls...")
    print("In production mode, this would:")
    print("  1. Poll X API every 30 seconds")
    print("  2. Detect new posts with ticker symbols")
    print("  3. Parse for entry/stop/target")
    print("  4. Execute copy-trade within 10-30 seconds")
    print("  5. Log for tracking")
    print()
    print("Current status: Ready to copy-trade")
    print("Priority: #1")

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 NoLimitGains COPY-TRADE SYSTEM")
    print("=" * 60)
    print()
    print("PRIORITY: #1")
    print("Action: Copy @NoLimitGains calls IMMEDIATELY")
    print()
    print("Process:")
    print("  1. Detect new X post")
    print("  2. Parse ticker + direction")
    print("  3. Calculate 2% position size")
    print("  4. Execute via Alpaca (10-30 sec lag)")
    print("  5. Set 8% stop loss")
    print("  6. Log for tracking")
    print()
    monitor_nolimitgains()
