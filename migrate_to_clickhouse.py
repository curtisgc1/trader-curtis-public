#!/usr/bin/env python3
"""Migrate SQLite data to ClickHouse"""
import sqlite3
import subprocess
import json
from datetime import datetime

def convert_datetime(val):
    """Convert various datetime formats to ClickHouse format"""
    if not val or val == '':
        return '1970-01-01 00:00:00'
    try:
        # Handle ISO format with Z
        if 'T' in val:
            val = val.replace('Z', '').replace('T', ' ')
            if '.' in val:
                val = val.split('.')[0]
        return val
    except:
        return '1970-01-01 00:00:00'

def escape_string(val):
    """Escape strings for ClickHouse TSV"""
    if val is None:
        return ''
    val = str(val)
    # Replace tabs and newlines
    val = val.replace('\\', '\\\\').replace('\t', ' ').replace('\n', ' ').replace('\r', '')
    return val

def migrate_table(table_name, columns, date_columns=None):
    """Migrate a single table"""
    date_columns = date_columns or []
    
    conn = sqlite3.connect('data/trades.db')
    cursor = conn.cursor()
    
    cursor.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
    rows = cursor.fetchall()
    
    if not rows:
        print(f"  {table_name}: no data")
        return
    
    # Create TSV
    lines = []
    for row in rows:
        processed = []
        for i, col in enumerate(columns):
            if col in date_columns:
                processed.append(convert_datetime(row[i]))
            else:
                processed.append(escape_string(row[i]))
        lines.append('\t'.join(processed))
    
    # Write to temp file
    tsv_path = f'/tmp/ch_migrate/{table_name}.tsv'
    with open(tsv_path, 'w') as f:
        f.write('\n'.join(lines))
    
    # Import to ClickHouse
    cmd = f"clickhouse client --query 'INSERT INTO {table_name} FORMAT TSV' < {tsv_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  {table_name}: ERROR - {result.stderr[:200]}")
    else:
        print(f"  {table_name}: imported {len(rows)} rows")
    
    conn.close()

if __name__ == '__main__':
    print("Migrating SQLite to ClickHouse...")
    
    # Define table schemas
    tables = {
        'trades': {
            'columns': ['trade_id', 'ticker', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'shares', 
                       'pnl', 'pnl_percent', 'status', 'sentiment_reddit', 'sentiment_twitter', 'sentiment_trump',
                       'source_reddit_wsb', 'source_reddit_stocks', 'source_reddit_investing', 
                       'source_twitter_general', 'source_twitter_analysts', 'source_trump_posts', 'source_news',
                       'source_accuracy_score', 'thesis', 'outcome_analysis', 'lesson_learned', 'decision_grade',
                       'created_at', 'route_id', 'broker_order_id', 'last_sync', 'entry_side'],
            'dates': ['entry_date', 'exit_date', 'created_at', 'last_sync']
        },
        'route_outcomes': {
            'columns': ['route_id', 'ticker', 'source_tag', 'resolution', 'pnl', 'pnl_percent', 'resolved_at', 'notes', 'outcome_type'],
            'dates': ['resolved_at']
        },
        'source_learning_stats': {
            'columns': ['id', 'computed_at', 'source_tag', 'sample_size', 'wins', 'losses', 'pushes', 
                       'win_rate', 'avg_pnl', 'avg_pnl_percent'],
            'dates': ['computed_at']
        },
        'strategy_learning_stats': {
            'columns': ['id', 'computed_at', 'strategy_tag', 'sample_size', 'wins', 'losses', 'pushes',
                       'win_rate', 'avg_pnl', 'avg_pnl_percent'],
            'dates': ['computed_at']
        },
        'signal_routes': {
            'columns': ['id', 'routed_at', 'ticker', 'direction', 'score', 'source_tag', 'proposed_notional',
                       'mode', 'decision', 'reason', 'status', 'validation_id', 'allocator_factor',
                       'allocator_regime', 'allocator_reason', 'allocator_blocked', 'venue_scores_json',
                       'venue_decisions_json', 'preferred_venue'],
            'dates': ['routed_at']
        },
        'execution_orders': {
            'columns': ['id', 'created_at', 'route_id', 'ticker', 'direction', 'mode', 'notional',
                       'order_status', 'broker_order_id', 'notes', 'leverage_used', 'leverage_capable'],
            'dates': ['created_at']
        },
        'polymarket_orders': {
            'columns': ['id', 'created_at', 'strategy_id', 'candidate_id', 'market_id', 'outcome', 'side',
                       'price', 'size', 'order_id', 'status', 'notes', 'route_id', 'token_id', 'mode',
                       'notional', 'response_json'],
            'dates': ['created_at']
        },
        'execution_learning': {
            'columns': ['id', 'created_at', 'route_id', 'ticker', 'source_tag', 'pipeline_hint', 'mode',
                       'venue', 'decision', 'order_status', 'reason'],
            'dates': ['created_at']
        },
        'vix_regime_state': {
            'columns': ['id', 'fetched_at', 'vix_close', 'vix_5d_avg', 'regime', 'leverage_scale',
                       'gex_signal', 'gex_confirmed', 'signal_ticker', 'signal_direction', 'confidence', 'notes'],
            'dates': ['fetched_at']
        },
        'position_awareness_snapshots': {
            'columns': ['id', 'created_at', 'venue', 'symbol', 'side', 'qty', 'entry_price', 'mark_price',
                       'notional_usd', 'unrealized_pnl_usd', 'unrealized_pnl_pct', 'action', 'confidence', 'reason'],
            'dates': ['created_at']
        },
        'kelly_signals': {
            'columns': ['id', 'computed_at', 'ticker', 'direction', 'source_tag', 'horizon_hours', 'win_prob',
                       'avg_win_pct', 'avg_loss_pct', 'payout_ratio', 'kelly_fraction', 'frac_kelly',
                       'convexity_score', 'ev_percent', 'sample_size', 'verdict', 'verdict_reason'],
            'dates': ['computed_at']
        },
        'momentum_signals': {
            'columns': ['id', 'created_at', 'ticker', 'asset_class', 'rank', 'rank_of', 'momentum_score',
                       'pct_30d', 'batch_ts'],
            'dates': ['created_at', 'batch_ts']
        }
    }
    
    for table, config in tables.items():
        migrate_table(table, config['columns'], config.get('dates', []))
    
    print("\nMigration complete!")
