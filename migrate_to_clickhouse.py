#!/usr/bin/env python3
"""
Migrate SQLite trading data to ClickHouse
"""
import sqlite3
import subprocess
import json
from datetime import datetime

SQLITE_DB = '/Users/Shared/curtis/trader-curtis/data/trades.db'
CLICKHOUSE_CMD = ['/opt/homebrew/bin/clickhouse', 'client']

def run_clickhouse_query(query):
    """Execute a ClickHouse query"""
    result = subprocess.run(
        CLICKHOUSE_CMD + ['--query', query],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    return result.stdout

def migrate_simple_source_outcomes():
    """Migrate simple source outcomes to ClickHouse trades table"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ticker, entry_price, exit_price, pnl, pnl_pct, 
               trade_grade, outcome, sources, bullish_count, bearish_count, 
               neutral_count, combo_used, created_at 
        FROM simple_source_outcomes
    """)
    
    rows = cursor.fetchall()
    count = 0
    
    for row in rows:
        ticker, entry_price, exit_price, pnl, pnl_pct, trade_grade, outcome, sources, bullish_count, bearish_count, neutral_count, combo_used, created_at = row
        
        # Parse sources JSON
        sources_data = json.loads(sources) if sources else {}
        
        # Calculate side based on PNL direction (simplified)
        side = 'buy' if outcome == 'win' else 'sell'
        status = 'closed'
        
        # Convert timestamp
        timestamp = created_at.replace('T', ' ').split('.')[0] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Generate trade_id
        trade_id = f"{ticker}_{timestamp.replace(' ', '_').replace(':', '')}_{count}"
        
        # Extract sentiment scores (simplified - all neutral 50 -> 0)
        sentiment_reddit = 0
        sentiment_twitter = 0
        sentiment_stocktwits = 0
        sentiment_grok = 0
        
        # Extract source scores
        source_reddit_wsb = sources_data.get('reddit_wsb', {}).get('score', 50)
        source_reddit_stocks = sources_data.get('reddit_stocks', {}).get('score', 50)
        source_twitter = sources_data.get('twitter', {}).get('score', 50)
        source_stocktwits = sources_data.get('stocktwits', {}).get('score', 50) if 'stocktwits' in sources_data else 50
        source_trump = sources_data.get('trump', {}).get('score', 50)
        source_bessent = sources_data.get('bessent', {}).get('score', 50) if 'bessent' in sources_data else 50
        
        # Build INSERT query
        query = f"""
        INSERT INTO trader_curtis.trades (
            timestamp, trade_id, ticker, side, shares, entry_price, exit_price,
            position_size, pnl, pnl_percent, status,
            sentiment_reddit, sentiment_twitter, sentiment_stocktwits, sentiment_grok,
            source_reddit_wsb, source_reddit_stocks, source_twitter, source_stocktwits,
            source_trump, source_bessent,
            decision_grade, lesson_learned, strategy_used
        ) VALUES (
            '{timestamp}', '{trade_id}', '{ticker}', '{side}', 100,
            {entry_price or 0}, {exit_price or 0}, 
            {entry_price * 100 if entry_price else 0}, {pnl or 0}, {pnl_pct or 0}, '{status}',
            {sentiment_reddit}, {sentiment_twitter}, {sentiment_stocktwits}, {sentiment_grok},
            {source_reddit_wsb}, {source_reddit_stocks}, {source_twitter}, {source_stocktwits},
            {source_trump}, {source_bessent},
            '{trade_grade or 'C'}', '{outcome or ''}', '{combo_used or ''}'
        )
        """
        
        result = run_clickhouse_query(query)
        if result is not None:
            count += 1
    
    conn.close()
    return count

def migrate_source_performance():
    """Migrate source performance data"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT source, total_signals, bullish_signals, bearish_signals,
               wins_when_bullish, losses_when_bullish, wins_when_bearish, losses_when_bearish,
               neutral_signals, win_rate_bullish, win_rate_bearish, overall_accuracy,
               avg_pnl_when_followed, grade, last_updated
        FROM source_performance
    """)
    
    rows = cursor.fetchall()
    count = 0
    
    for row in rows:
        source, total_signals, bullish_signals, bearish_signals, wins_when_bullish, losses_when_bullish, wins_when_bearish, losses_when_bearish, neutral_signals, win_rate_bullish, win_rate_bearish, overall_accuracy, avg_pnl_when_followed, grade, last_updated = row
        
        # For now, just print summary - we'll build a proper source analytics table later
        count += 1
    
    conn.close()
    return count

def migrate_sentiment_accuracy():
    """Migrate sentiment accuracy data"""
    conn = sqlite3.connect(SQLITE_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ticker, date, source, predicted_direction, actual_direction,
               accuracy_score, sentiment_score, trade_grade, pnl_pct, created_at
        FROM sentiment_accuracy
    """)
    
    rows = cursor.fetchall()
    count = 0
    
    for row in rows:
        ticker, date, source, predicted_direction, actual_direction, accuracy_score, sentiment_score, trade_grade, pnl_pct, created_at = row
        
        # Parse date
        prediction_date = date if date else (created_at.split('T')[0] if created_at else datetime.now().strftime('%Y-%m-%d'))
        
        query = f"""
        INSERT INTO trader_curtis.sentiment_accuracy (
            prediction_date, ticker, source, predicted_direction, actual_direction,
            accuracy_score, confidence, price_at_prediction, price_3d_later, price_7d_later
        ) VALUES (
            '{prediction_date}', '{ticker}', '{source}', '{predicted_direction or ''}', '{actual_direction or ''}',
            {accuracy_score or 0}, {abs(sentiment_score or 0) / 100.0}, 0, 0, 0
        )
        """
        
        result = run_clickhouse_query(query)
        if result is not None:
            count += 1
    
    conn.close()
    return count

def show_stats():
    """Show migration statistics"""
    print("\n=== CLICKHOUSE MIGRATION STATISTICS ===\n")
    
    # Count trades
    result = run_clickhouse_query("SELECT COUNT(*) FROM trader_curtis.trades")
    print(f"Trades migrated: {result.strip() if result else 'N/A'}")
    
    # Count sentiment accuracy records
    result = run_clickhouse_query("SELECT COUNT(*) FROM trader_curtis.sentiment_accuracy")
    print(f"Sentiment accuracy records: {result.strip() if result else 'N/A'}")
    
    # Show total PnL
    result = run_clickhouse_query("SELECT SUM(pnl) FROM trader_curtis.trades")
    print(f"Total PnL: ${result.strip() if result else 'N/A'}")
    
    # Show win rate
    result = run_clickhouse_query("SELECT COUNTIf(pnl > 0) / COUNT() * 100 FROM trader_curtis.trades")
    print(f"Win Rate: {result.strip() if result else 'N/A'}%")
    
    # Show by ticker
    print("\n--- Trades by Ticker ---")
    result = run_clickhouse_query("""
        SELECT ticker, COUNT(*) as trades, SUM(pnl) as total_pnl 
        FROM trader_curtis.trades 
        GROUP BY ticker 
        ORDER BY total_pnl DESC
    """)
    if result:
        print(result)

if __name__ == "__main__":
    print("Starting ClickHouse migration...")
    
    # Migrate data
    trades_count = migrate_simple_source_outcomes()
    print(f"Migrated {trades_count} trades")
    
    source_count = migrate_source_performance()
    print(f"Migrated {source_count} source performance records")
    
    accuracy_count = migrate_sentiment_accuracy()
    print(f"Migrated {accuracy_count} sentiment accuracy records")
    
    # Show statistics
    show_stats()
    
    print("\nMigration complete!")
