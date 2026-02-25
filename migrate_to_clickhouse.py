#!/usr/bin/env python3
"""Migrate SQLite data to ClickHouse"""
import sqlite3
import requests
import re
from datetime import datetime

DB_PATH = '/Users/Shared/curtis/trader-curtis/data/trades.db'
CH_URL = 'http://localhost:8123/'

def parse_datetime(dt_str):
    """Parse various datetime formats to ClickHouse format"""
    if not dt_str:
        return None
    # Handle ISO format with timezone
    dt_str = dt_str.replace('T', ' ').replace('Z', '')
    # Remove fractional seconds and timezone offset
    dt_str = re.sub(r'\.[0-9]+(\+[0-9:]+)?$', '', dt_str)
    dt_str = re.sub(r'\+[0-9:]+$', '', dt_str)
    return dt_str.strip()

def parse_date(dt_str):
    """Extract date part only"""
    if not dt_str:
        return None
    dt_str = dt_str.replace('T', ' ').replace('Z', '')
    dt_str = re.sub(r'\.[0-9]+.*$', '', dt_str)
    return dt_str[:10]  # YYYY-MM-DD

def escape_str(s):
    """Escape string for SQL"""
    if s is None:
        return 'NULL'
    s = str(s).replace("'", "\\'")
    return f"'{s}'"

def migrate_trades():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades")
    rows = cursor.fetchall()
    
    count = 0
    for row in rows:
        # Map columns
        trade_id = escape_str(row[0])
        ticker = escape_str(row[1])
        entry_date = escape_str(parse_date(row[2]))
        exit_date = escape_str(parse_date(row[3])) if row[3] else 'NULL'
        entry_price = row[4] if row[4] is not None else 0
        exit_price = row[5] if row[5] is not None else 'NULL'
        shares = row[6] if row[6] is not None else 0
        pnl = row[7] if row[7] is not None else 'NULL'
        pnl_percent = row[8] if row[8] is not None else 'NULL'
        status = escape_str(row[9])
        sentiment_reddit = row[10] if row[10] is not None else 0
        sentiment_twitter = row[11] if row[11] is not None else 0
        sentiment_trump = row[12] if row[12] is not None else 0
        source_reddit_wsb = escape_str(row[13])
        source_reddit_stocks = escape_str(row[14])
        source_reddit_investing = escape_str(row[15])
        source_twitter_general = escape_str(row[16])
        source_twitter_analysts = escape_str(row[17])
        source_trump_posts = escape_str(row[18])
        source_news = escape_str(row[19])
        source_accuracy_score = row[20] if row[20] is not None else 0
        thesis = escape_str(row[21])
        outcome_analysis = escape_str(row[22])
        lesson_learned = escape_str(row[23])
        decision_grade = escape_str(row[24])
        created_at = escape_str(parse_datetime(row[25]))
        route_id = row[26] if row[26] is not None else 'NULL'
        broker_order_id = escape_str(row[27])
        last_sync = escape_str(parse_datetime(row[28])) if row[28] else 'NULL'
        
        sql = f"""INSERT INTO trader_curtis.trades VALUES (
            {trade_id}, {ticker}, {entry_date}, {exit_date}, {entry_price}, {exit_price},
            {shares}, {pnl}, {pnl_percent}, {status}, {sentiment_reddit}, {sentiment_twitter},
            {sentiment_trump}, {source_reddit_wsb}, {source_reddit_stocks}, {source_reddit_investing},
            {source_twitter_general}, {source_twitter_analysts}, {source_trump_posts}, {source_news},
            {source_accuracy_score}, {thesis}, {outcome_analysis}, {lesson_learned}, {decision_grade},
            {created_at}, {route_id}, {broker_order_id}, {last_sync}
        )"""
        
        try:
            requests.post(CH_URL, data=sql, timeout=30)
            count += 1
        except Exception as e:
            print(f"Error inserting trade {row[0]}: {e}")
    
    conn.close()
    return count

def migrate_route_outcomes():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM route_outcomes")
    rows = cursor.fetchall()
    
    count = 0
    for row in rows:
        route_id = row[0]
        ticker = escape_str(row[1])
        source_tag = escape_str(row[2])
        resolution = escape_str(row[3])
        pnl = row[4] if row[4] is not None else 0
        pnl_percent = row[5] if row[5] is not None else 0
        resolved_at = escape_str(parse_datetime(row[6]))
        notes = escape_str(row[7])
        outcome_type = escape_str(row[8])
        
        sql = f"""INSERT INTO trader_curtis.route_outcomes VALUES (
            {route_id}, {ticker}, {source_tag}, {resolution}, {pnl}, {pnl_percent},
            {resolved_at}, {notes}, {outcome_type}
        )"""
        
        try:
            requests.post(CH_URL, data=sql, timeout=30)
            count += 1
        except Exception as e:
            print(f"Error inserting route_outcome {row[0]}: {e}")
    
    conn.close()
    return count

def migrate_source_learning_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM source_learning_stats")
    rows = cursor.fetchall()
    
    count = 0
    for row in rows:
        id = row[0]
        computed_at = escape_str(parse_datetime(row[1]))
        source_tag = escape_str(row[2])
        sample_size = row[3] if row[3] is not None else 0
        wins = row[4] if row[4] is not None else 0
        losses = row[5] if row[5] is not None else 0
        pushes = row[6] if row[6] is not None else 0
        win_rate = row[7] if row[7] is not None else 0
        avg_pnl = row[8] if row[8] is not None else 0
        avg_pnl_percent = row[9] if row[9] is not None else 0
        
        sql = f"""INSERT INTO trader_curtis.source_learning_stats VALUES (
            {id}, {computed_at}, {source_tag}, {sample_size}, {wins}, {losses},
            {pushes}, {win_rate}, {avg_pnl}, {avg_pnl_percent}
        )"""
        
        try:
            requests.post(CH_URL, data=sql, timeout=30)
            count += 1
        except Exception as e:
            print(f"Error inserting source_stats {row[0]}: {e}")
    
    conn.close()
    return count

def migrate_strategy_learning_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM strategy_learning_stats")
    rows = cursor.fetchall()
    
    count = 0
    for row in rows:
        id = row[0]
        computed_at = escape_str(parse_datetime(row[1]))
        strategy_tag = escape_str(row[2])
        sample_size = row[3] if row[3] is not None else 0
        wins = row[4] if row[4] is not None else 0
        losses = row[5] if row[5] is not None else 0
        pushes = row[6] if row[6] is not None else 0
        win_rate = row[7] if row[7] is not None else 0
        avg_pnl = row[8] if row[8] is not None else 0
        avg_pnl_percent = row[9] if row[9] is not None else 0
        
        sql = f"""INSERT INTO trader_curtis.strategy_learning_stats VALUES (
            {id}, {computed_at}, {strategy_tag}, {sample_size}, {wins}, {losses},
            {pushes}, {win_rate}, {avg_pnl}, {avg_pnl_percent}
        )"""
        
        try:
            requests.post(CH_URL, data=sql, timeout=30)
            count += 1
        except Exception as e:
            print(f"Error inserting strategy_stats {row[0]}: {e}")
    
    conn.close()
    return count

if __name__ == '__main__':
    print("Migrating trades...")
    trades_count = migrate_trades()
    print(f"  Migrated {trades_count} trades")
    
    print("Migrating route_outcomes...")
    outcomes_count = migrate_route_outcomes()
    print(f"  Migrated {outcomes_count} route_outcomes")
    
    print("Migrating source_learning_stats...")
    source_count = migrate_source_learning_stats()
    print(f"  Migrated {source_count} source_learning_stats")
    
    print("Migrating strategy_learning_stats...")
    strategy_count = migrate_strategy_learning_stats()
    print(f"  Migrated {strategy_count} strategy_learning_stats")
    
    print(f"\n✅ Migration complete: {trades_count + outcomes_count + source_count + strategy_count} total rows")
