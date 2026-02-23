#!/usr/bin/env python3
import requests
import os

api_key = 'PKWOGX25ME3NKR2Y64QKJIMHOZ'
secret = 'CVPEEydxE3nuxGJ99K5iL1mGaZ5ycqneFNJF149mQpgV'
base_url = 'https://paper-api.alpaca.markets'

headers = {
    'APCA-API-KEY-ID': api_key,
    'APCA-API-SECRET-KEY': secret
}

print('📊 ALPACA PAPER ACCOUNT STATUS')
print('=' * 50)

try:
    # Get account
    r = requests.get(f'{base_url}/v2/account', headers=headers, timeout=10)
    if r.status_code == 200:
        data = r.json()
        print(f"Portfolio Value: ${float(data.get('portfolio_value', 0)):,.2f}")
        print(f"Cash: ${float(data.get('cash', 0)):,.2f}")
        print(f"Buying Power: ${float(data.get('buying_power', 0)):,.2f}")
        print(f"Equity: ${float(data.get('equity', 0)):,.2f}")
        print(f"Status: {data.get('status', 'unknown')}")
    else:
        print(f'Account Error: {r.status_code}')
except Exception as e:
    print(f'Error: {e}')

print()
print('📈 POSITIONS')
print('=' * 50)

try:
    r = requests.get(f'{base_url}/v2/positions', headers=headers, timeout=10)
    if r.status_code == 200:
        positions = r.json()
        if positions:
            for pos in positions:
                symbol = pos['symbol']
                qty = int(pos['qty'])
                entry = float(pos['avg_entry_price'])
                current = float(pos['current_price'])
                pnl = float(pos['unrealized_pl'])
                pnl_pct = float(pos['unrealized_plpc']) * 100
                emoji = '🟢' if pnl > 0 else '🔴'
                print(f"{emoji} {symbol}: {qty} shares @ ${entry:.2f} → ${current:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")
        else:
            print("No positions")
    else:
        print(f'Positions Error: {r.status_code}')
except Exception as e:
    print(f'Error: {e}')

print()
print('🛑 OPEN ORDERS')
print('=' * 50)

try:
    r = requests.get(f'{base_url}/v2/orders?status=open', headers=headers, timeout=10)
    if r.status_code == 200:
        orders = r.json()
        if orders:
            for order in orders:
                symbol = order['symbol']
                side = order['side']
                otype = order['type']
                if otype == 'stop':
                    stop_price = order.get('stop_price', 'N/A')
                    print(f"🛑 {symbol}: {side} {otype} @ ${stop_price}")
                else:
                    print(f"⏳ {symbol}: {side} {otype}")
        else:
            print("No open orders")
    else:
        print(f'Orders Error: {r.status_code}')
except Exception as e:
    print(f'Error: {e}')
