#!/usr/bin/env python3
"""
Quick trade executor for paper trading - v2
Generates data for sentiment learning system
"""
import requests
import os
from datetime import datetime

api_key = os.environ.get('ALPACA_API_KEY', '')
secret = os.environ.get('ALPACA_SECRET_KEY', '')
base_url = 'https://paper-api.alpaca.markets'

def place_order(symbol, qty, side, order_type='market'):
    """Place an order"""
    headers = {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': secret
    }
    
    order_data = {
        'symbol': symbol,
        'qty': qty,
        'side': side,
        'type': order_type,
        'time_in_force': 'day'
    }
    
    try:
        r = requests.post(f'{base_url}/v2/orders', json=order_data, headers=headers, timeout=10)
        return r.status_code == 200, r.json() if r.status_code == 200 else r.text
    except Exception as e:
        return False, str(e)

def log_trade(symbol, qty, side, reason, political_score=None):
    """Log trade for learning system"""
    timestamp = datetime.now().isoformat()
    log_entry = f"{timestamp}|{symbol}|{side}|{qty}|market|{reason}|{political_score}\n"
    with open('trades_log.csv', 'a') as f:
        f.write(log_entry)
    print(f"📝 Logged: {side.upper()} {qty} {symbol}")

print('🚀 PAPER TRADE EXECUTOR v2')
print('=' * 60)
print('Based on political alpha alerts (Trump 84/50, Bessent 41/50):')
print('- Gold mentions: Adding to NEM, AEM positions')
print('- Bitcoin mentions: Opening MARA position')  
print('- Tech tariff risk: Small PLTR position')
print('=' * 60)

# Trade Plan
# Deploy ~$25k of the $87k available to generate data
trades = [
    ('NEM', 50, 'Gold mentions in Trump/Bessent posts'),
    ('AEM', 30, 'Gold miner play on political mentions'),
    ('MARA', 100, 'Bitcoin mentioned in Trump post'),
    ('PLTR', 50, 'Tech exposure to tariff discussion'),
    ('GLD', 30, 'Direct gold ETF play'),
]

print('\n📈 Executing Trades:')
for symbol, qty, reason in trades:
    success, result = place_order(symbol, qty, 'buy')
    if success:
        print(f"✅ BOUGHT {qty} {symbol} - {reason}")
        log_trade(symbol, qty, 'buy', reason, 84)
    else:
        print(f"❌ {symbol} failed: {result}")

print('\n' + '=' * 60)
print('✅ Trade execution complete!')
print('📊 Data logged to: trades_log.csv')
print('🧠 Learning engine will track outcomes')
print('=' * 60)
