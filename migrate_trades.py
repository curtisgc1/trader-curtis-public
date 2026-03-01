#!/usr/bin/env python3
"""Migrate trades table specifically"""
import sqlite3

def to_float(val):
    try:
        return float(val) if val else 0.0
    except:
        return 0.0

def to_int(val):
    try:
        return int(float(val)) if val else 0
    except:
        return 0

def escape(val):
    if val is None:
        return ''
    val = str(val)
    return val.replace('\\', '\\\\').replace('\t', ' ').replace('\n', ' ').replace('\r', '')

def parse_dt(val):
    if not val:
        return '1970-01-01 00:00:00'
    val = str(val).replace('Z', '').replace('T', ' ')
    if '.' in val:
        val = val.split('.')[0]
    return val[:19] if len(val) > 19 else val

conn = sqlite3.connect('data/trades.db')
cursor = conn.cursor()

cursor.execute("""SELECT trade_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, 
                  pnl, pnl_percent, status, sentiment_reddit, sentiment_twitter, sentiment_trump,
                  source_reddit_wsb, source_reddit_stocks, source_reddit_investing, 
                  source_twitter_general, source_twitter_analysts, source_trump_posts, source_news,
                  source_accuracy_score, thesis, outcome_analysis, lesson_learned, decision_grade,
                  created_at, route_id, broker_order_id, last_sync, entry_side FROM trades""")

lines = []
for row in cursor.fetchall():
    trade_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, pnl, pnl_percent, status = row[:10]
    sentiment_reddit, sentiment_twitter, sentiment_trump = row[10:13]
    source_reddit_wsb, source_reddit_stocks, source_reddit_investing = row[13:16]
    source_twitter_general, source_twitter_analysts, source_trump_posts, source_news = row[16:20]
    source_accuracy_score, thesis, outcome_analysis, lesson_learned, decision_grade = row[20:25]
    created_at, route_id, broker_order_id, last_sync, entry_side = row[25:30]
    
    line = '\t'.join([
        escape(trade_id),
        escape(ticker),
        parse_dt(entry_date),
        parse_dt(exit_date),
        str(to_float(entry_price)),
        str(to_float(exit_price)),
        str(to_int(shares)),
        str(to_float(pnl)),
        str(to_float(pnl_percent)),
        escape(status),
        str(to_int(sentiment_reddit)),
        str(to_int(sentiment_twitter)),
        str(to_int(sentiment_trump)),
        escape(source_reddit_wsb),
        escape(source_reddit_stocks),
        escape(source_reddit_investing),
        escape(source_twitter_general),
        escape(source_twitter_analysts),
        escape(source_trump_posts),
        escape(source_news),
        str(to_float(source_accuracy_score)),
        escape(thesis),
        escape(outcome_analysis),
        escape(lesson_learned),
        escape(decision_grade),
        parse_dt(created_at),
        str(to_int(route_id)),
        escape(broker_order_id),
        parse_dt(last_sync),
        escape(entry_side)
    ])
    lines.append(line)

conn.close()

with open('/tmp/ch_migrate/trades_fixed.tsv', 'w') as f:
    f.write('\n'.join(lines))

print(f"Exported {len(lines)} trades")

# Import
import subprocess
result = subprocess.run(
    "clickhouse client --query 'INSERT INTO trades FORMAT TSV' < /tmp/ch_migrate/trades_fixed.tsv",
    shell=True, capture_output=True, text=True
)

if result.returncode != 0:
    print(f"ERROR: {result.stderr[:300]}")
else:
    print(f"SUCCESS: Imported {len(lines)} rows")
