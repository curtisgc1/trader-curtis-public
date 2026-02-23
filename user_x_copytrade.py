#!/usr/bin/env python3
"""
User X Account Copy-Trade Integration
Monitors user's X posts for trading signals and executes immediately
"""

import os
import sqlite3
import re
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"
USER_X_HANDLE = "@curtistrader"  # UPDATE THIS WITH YOUR ACTUAL HANDLE

def parse_user_trade_signal(text):
    """
    Parse user's X post for trade signals
    Expected format examples:
    - "Long $AAPL @ 180 stop 175"
    - "Buy TSLA 250 target 300"
    - "Short SPY entry 450"
    """
    
    # Extract ticker
    ticker_match = re.search(r'\$?([A-Z]{1,5})', text.upper())
    ticker = ticker_match.group(1) if ticker_match else None
    
    # Extract action
    action = None
    if any(word in text.lower() for word in ['long', 'buy', 'bullish', 'calls']):
        action = 'LONG'
    elif any(word in text.lower() for word in ['short', 'sell', 'bearish', 'puts']):
        action = 'SHORT'
    
    # Extract prices
    prices = re.findall(r'\d+\.?\d*', text)
    entry = float(prices[0]) if prices else None
    
    # Look for stop/target
    stop_match = re.search(r'stop[@\s]*(\d+\.?\d*)', text.lower())
    target_match = re.search(r'target[@\s]*(\d+\.?\d*)', text.lower())
    
    stop = float(stop_match.group(1)) if stop_match else (entry * 0.88 if entry else None)
    target = float(target_match.group(1)) if target_match else (entry * 1.15 if entry else None)
    
    return {
        'ticker': ticker,
        'action': action,
        'entry': entry,
        'stop': stop,
        'target': target,
        'raw_text': text,
        'timestamp': datetime.now().isoformat()
    }

def execute_user_signal(signal):
    """Execute the trade signal immediately"""
    import alpaca_trade_api as tradeapi
    
    if not signal['ticker'] or not signal['action']:
        return None, "Invalid signal format"
    
    api = tradeapi.REST(
        os.environ.get('ALPACA_API_KEY'),
        os.environ.get('ALPACA_SECRET_KEY'),
        'https://paper-api.alpaca.markets'
    )
    
    account = api.get_account()
    portfolio_value = float(account.portfolio_value)
    
    # 2% position size
    position_value = portfolio_value * 0.02
    
    # Get current price if no entry specified
    if not signal['entry']:
        bar = api.get_latest_bar(signal['ticker'])
        signal['entry'] = float(bar.c)
    
    shares = int(position_value / signal['entry'])
    
    if shares < 1:
        return None, f"Position too small"
    
    # Execute
    order = api.submit_order(
        symbol=signal['ticker'],
        qty=shares,
        side='buy' if signal['action'] == 'LONG' else 'sell',
        type='market',
        time_in_force='day'
    )
    
    # Log to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO copy_trades 
        (source_handle, ticker, call_type, entry_price, copied_entry, shares, copied_timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        USER_X_HANDLE,
        signal['ticker'],
        signal['action'],
        signal['entry'],
        signal['entry'],
        shares,
        datetime.now().isoformat(),
        'OPEN'
    ))
    conn.commit()
    conn.close()
    
    return {
        'ticker': signal['ticker'],
        'action': signal['action'],
        'shares': shares,
        'entry': signal['entry'],
        'stop': signal['stop'],
        'target': signal['target'],
        'order_id': order.id
    }, "SUCCESS"

if __name__ == '__main__':
    print("=" * 60)
    print("👤 USER X ACCOUNT COPY-TRADE")
    print("=" * 60)
    print(f"\nMonitoring: {USER_X_HANDLE}")
    print("Status: TRUSTED - Execute immediately")
    print("\nSignal Format Examples:")
    print('  "Long $AAPL @ 180 stop 175 target 200"')
    print('  "Buy TSLA 250"')
    print('  "Short SPY entry 450 stop 460"')
    print("\nWhen you post a signal on X, paste it here to execute.")
