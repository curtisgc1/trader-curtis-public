#!/usr/bin/env python3
"""
Process closed orders from Alpaca and log outcomes
Called by run_analysis.sh or manually
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from trade_analyzer import log_trade_outcome, init_db

def process_orders(orders_json):
    """Process closed orders and log to database"""
    orders = json.loads(orders_json)
    
    for order in orders:
        if order.get('status') != 'filled':
            continue
            
        # Build trade record
        trade_data = {
            'trade_id': order.get('id'),
            'ticker': order.get('symbol'),
            'entry_date': order.get('filled_at', '').split('T')[0],
            'exit_date': None,  # Will be updated on close
            'entry_price': float(order.get('filled_avg_price', 0)),
            'exit_price': None,
            'shares': int(order.get('filled_qty', 0)),
            'pnl': None,
            'pnl_percent': None,
            'status': 'open',
            'sentiment_reddit': None,  # Fill from scan data
            'sentiment_twitter': None,
            'thesis': '',
            'outcome_analysis': '',
            'lesson_learned': '',
            'decision_grade': None
        }
        
        log_trade_outcome(trade_data)
        print(f"Processed: {trade_data['ticker']} @ {trade_data['entry_price']}")

if __name__ == '__main__':
    init_db()
    if not sys.stdin.isatty():
        orders_json = sys.stdin.read()
        process_orders(orders_json)
    else:
        print("Usage: cat orders.json | python3 process_closed_orders.py")
