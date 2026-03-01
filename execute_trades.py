#!/usr/bin/env python3
"""
Quick trade executor for paper trading
Generates data for sentiment learning system
"""
import requests
import os
from datetime import datetime

api_key = os.environ.get('ALPACA_API_KEY', '')
secret = os.environ.get('ALPACA_SECRET_KEY', '')
base_url = 'https://paper-api.alpaca.markets'

headers = {
    'APCA-API-KEY-ID': api_key,
    'APCA-API-SECRET-KEY': secret
}

def get_last_price(symbol):
    """Get last trade price"""
    try:
        r = requests.get(f'{base_url}/v2/stocks/{symbol}/trades/latest', headers=headers, timeout=5)
        if r.status_code == 200:
            return float(r.json()['trade']['p'])
    except:
        pass
    return None

def place_order(symbol, qty, side, order_type='market', stop_loss=None):
    """Place an order"""
    order_data = {
        'symbol': symbol,
        'qty': qty,
        'side': side,
        'type': order_type,
        'time_in_force': 'day'
    }
    
    if stop_loss:
        order_data['stop_loss'] = {'stop_price': stop_loss}
    
    try:
        r = requests.post(f'{base_url}/v2/orders', json=order_data, headers=headers, timeout=10)
        return r.status_code == 200, r.json() if r.status_code == 200 else r.text
    except Exception as e:
        return False, str(e)

def log_trade(symbol, qty, side, price, reason, political_score=None):
    """Log trade for learning system"""
    timestamp = datetime.now().isoformat()
    log_entry = f"""
{timestamp}|{symbol}|{side}|{qty}|{price:.2f}|{reason}|political_score:{political_score}
"""
    with open('trades_log.csv', 'a') as f:
        f.write(log_entry.strip() + '\n')
    print(f"📝 Logged: {side} {qty} {symbol} @ ${price:.2f}")

print('🚀 PAPER TRADE EXECUTOR - Data Generation Mode')
print('=' * 60)

# Get current prices
tickers = ['NEM', 'AEM', 'MARA', 'PLTR', 'ASTS', 'GLD']
prices = {}

print('\n📊 Current Prices:')
for ticker in tickers:
    price = get_last_price(ticker)
    if price:
        prices[ticker] = price
        print(f"  {ticker}: ${price:.2f}")
    else:
        print(f"  {ticker}: Error fetching")

print('\n' + '=' * 60)
print('Based on political alpha alerts (Trump 84/50, Bessent 41/50):')
print('- Gold mentions: Adding to NEM, AEM positions')
print('- Bitcoin mentions: Opening MARA position')
print('- Tech tariff risk: Small PLTR position')
print('=' * 60)

# Trade 1: Add to NEM (gold bullish from political mentions)
if 'NEM' in prices:
    qty = 50  # ~$6,100 position
    price = prices['NEM']
    success, result = place_order('NEM', qty, 'buy')
    if success:
        print(f"✅ BOUGHT {qty} NEM @ ${price:.2f}")
        log_trade('NEM', qty, 'buy', price, 'Political_alpha_gold_mentions', 84)
    else:
        print(f"❌ NEM order failed: {result}")

# Trade 2: Add to AEM (gold miner)
if 'AEM' in prices:
    qty = 30  # ~$6,300 position
    price = prices['AEM']
    success, result = place_order('AEM', qty, 'buy')
    if success:
        print(f"✅ BOUGHT {qty} AEM @ ${price:.2f}")
        log_trade('AEM', qty, 'buy', price, 'Political_alpha_gold_mentions', 84)
    else:
        print(f"❌ AEM order failed: {result}")

# Trade 3: Open MARA (crypto - Bitcoin mentioned)
if 'MARA' in prices:
    qty = 100  # ~$1,500-2,000 position (volatile)
    price = prices['MARA']
    success, result = place_order('MARA', qty, 'buy')
    if success:
        print(f"✅ BOUGHT {qty} MARA @ ${price:.2f}")
        log_trade('MARA', qty, 'buy', price, 'Political_alpha_bitcoin_mentions', 84)
    else:
        print(f"❌ MARA order failed: {result}")

# Trade 4: Small PLTR position (tech, tariff play)
if 'PLTR' in prices:
    qty = 50  # ~$4,000 position
    price = prices['PLTR']
    success, result = place_order('PLTR', qty, 'buy')
    if success:
        print(f"✅ BOUGHT {qty} PLTR @ ${price:.2f}")
        log_trade('PLTR', qty, 'buy', price, 'Political_alpha_tech_tariff_exposure', 84)
    else:
        print(f"❌ PLTR order failed: {result}")

# Trade 5: GLD ETF (direct gold play)
if 'GLD' in prices:
    qty = 30  # ~$7,000 position
    price = prices['GLD']
    success, result = place_order('GLD', qty, 'buy')
    if success:
        print(f"✅ BOUGHT {qty} GLD @ ${price:.2f}")
        log_trade('GLD', qty, 'buy', price, 'Political_alpha_gold_direct_play', 84)
    else:
        print(f"❌ GLD order failed: {result}")

print('\n' + '=' * 60)
print('✅ Trade execution complete!')
print('📊 Data logged to: trades_log.csv')
print('🧠 Learning engine will analyze outcomes')
print('=' * 60)
