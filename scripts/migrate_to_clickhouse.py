#!/usr/bin/env python3
"""Migrate SQLite data to ClickHouse"""
import sqlite3
from clickhouse_driver import Client
from datetime import datetime

DB_PATH = "/Users/Shared/curtis/trader-curtis/data/trades.db"

def parse_datetime(dt_str):
    if not dt_str:
        return datetime(1970, 1, 1)
    dt_str = str(dt_str).replace('Z', '+00:00')
    if 'T' in dt_str:
        try:
            dt = datetime.fromisoformat(dt_str)
            return dt.replace(tzinfo=None)
        except:
            pass
    for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S']:
        try:
            return datetime.strptime(dt_str.split('+')[0][:26], fmt)
        except:
            continue
    return datetime(1970, 1, 1)

def migrate_trades(client, sqlite_conn):
    cursor = sqlite_conn.cursor()
    cursor.execute("""SELECT trade_id, ticker, entry_date, exit_date, entry_price, exit_price, 
               shares, pnl, pnl_percent, status, source_accuracy_score, 
               decision_grade, created_at, COALESCE(route_id, 0), entry_side 
        FROM trades WHERE entry_date IS NOT NULL""")
    rows = cursor.fetchall()
    data = []
    for row in rows:
        entry_date = parse_datetime(row[2])
        exit_date = parse_datetime(row[3])
        created_at = parse_datetime(row[12])
        data.append([
            str(row[0]), str(row[1]), entry_date, exit_date, float(row[4] or 0), 
            float(row[5]) if row[5] else None, int(row[6] or 0), float(row[7]) if row[7] else None,
            float(row[8]) if row[8] else None, str(row[9] or 'unknown'), 
            float(row[10]) if row[10] else None, str(row[11]) if row[11] else None,
            created_at, int(row[13] or 0), str(row[14]) if row[14] else None
        ])
    if data:
        client.execute('INSERT INTO trader_curtis.trades (trade_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, pnl, pnl_percent, status, source_accuracy_score, decision_grade, created_at, route_id, entry_side) VALUES', data)
    return len(data)

def migrate_route_outcomes(client, sqlite_conn):
    cursor = sqlite_conn.cursor()
    cursor.execute("""SELECT route_id, ticker, source_tag, resolution, pnl, pnl_percent, 
               resolved_at, outcome_type, notes FROM route_outcomes WHERE resolved_at IS NOT NULL""")
    rows = cursor.fetchall()
    data = []
    for row in rows:
        resolved_at = parse_datetime(row[6])
        data.append([
            int(row[0]), str(row[1]), str(row[2]), str(row[3]), float(row[4] or 0), 
            float(row[5] or 0), resolved_at, str(row[7] or 'realized'), str(row[8] or '')
        ])
    if data:
        client.execute('INSERT INTO trader_curtis.route_outcomes (route_id, ticker, source_tag, resolution, pnl, pnl_percent, resolved_at, outcome_type, notes) VALUES', data)
    return len(data)

def migrate_source_learning(client, sqlite_conn):
    cursor = sqlite_conn.cursor()
    cursor.execute("""SELECT id, computed_at, source_tag, sample_size, wins, losses, pushes, 
               win_rate, avg_pnl, avg_pnl_percent, sharpe_ratio FROM source_learning_stats WHERE computed_at IS NOT NULL""")
    rows = cursor.fetchall()
    data = []
    for row in rows:
        computed_at = parse_datetime(row[1])
        data.append([
            str(row[2]), int(row[3] or 0), int(row[4] or 0), int(row[5] or 0), int(row[6] or 0), 
            float(row[7] or 0), float(row[8] or 0), float(row[9] or 0), computed_at
        ])
    if data:
        client.execute('INSERT INTO trader_curtis.source_learning_stats (source_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent, computed_at) VALUES', data)
    return len(data)

def migrate_execution_learning(client, sqlite_conn):
    cursor = sqlite_conn.cursor()
    cursor.execute("""SELECT id, created_at, route_id, ticker, source_tag, mode, venue, 
               decision, order_status, reason FROM execution_learning WHERE created_at IS NOT NULL""")
    rows = cursor.fetchall()
    data = []
    for row in rows:
        created_at = parse_datetime(row[1])
        data.append([
            int(row[0]), created_at, int(row[2]), str(row[3] or ''), str(row[4] or ''), 
            str(row[5] or ''), str(row[6] or ''), str(row[7] or ''), str(row[8] or ''), str(row[9] or '')
        ])
    if data:
        client.execute('INSERT INTO trader_curtis.execution_learning (id, created_at, route_id, ticker, source_tag, mode, venue, decision, order_status, reason) VALUES', data)
    return len(data)

def main():
    client = Client(host='localhost')
    sqlite_conn = sqlite3.connect(DB_PATH)
    t = migrate_trades(client, sqlite_conn)
    r = migrate_route_outcomes(client, sqlite_conn)
    s = migrate_source_learning(client, sqlite_conn)
    e = migrate_execution_learning(client, sqlite_conn)
    print(f"Migrated: {t} trades, {r} outcomes, {s} source stats, {e} executions")
    sqlite_conn.close()

if __name__ == '__main__':
    main()
