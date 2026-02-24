# ClickHouse Migration Report
Generated: 2026-02-23 22:05 PST

## Summary
✅ ClickHouse server started (v26.1.2.11)
✅ Tables created successfully
✅ Data migrated from SQLite

## Migration Results

### Tables Created
- source_outcomes
- trades
- pipeline_signals
- source_learning_stats
- route_outcomes
- execution_learning
- polymarket_markets
- signal_routes

### Data Migrated
| Table | Records | Status |
|-------|---------|--------|
| trades | 37 | ✅ Complete |
| pipeline_signals | 1,215 | ✅ Complete |
| route_outcomes | 9 | ✅ Complete |
| source_learning_stats | 0 | ℹ️ No data |

## Analytics Results

### Trades Summary
- **Total Trades:** 37
- **Open Positions:** 33
- **Unique Tickers:** 13
- **Avg Entry Price (Open):** $501.73
- **Most Active Ticker:** NVDA (9 trades)

### Top Holdings by Trade Count
1. NVDA - 9 trades @ avg $191.51
2. ASML - 6 trades @ avg $1,472
3. TSM - 5 trades @ avg $366.68
4. ISRG - 5 trades @ avg $498.88
5. CRSP - 3 trades @ avg $52.21

### Pipeline Signals Summary
- **Total Signals:** 1,215
- **Long Signals:** 1,075 (avg confidence: 0.59)
- **Short Signals:** 140 (avg confidence: 0.73)

### Top Signal Tickers
1. ISRG - 70 signals (avg conf: 0.57)
2. ASML - 67 signals (avg conf: 0.61)
3. NVDA - 62 signals (avg conf: 0.67)
4. CRSP - 61 signals (avg conf: 0.54)
5. TSM - 56 signals (avg conf: 0.60)

### Signal Date Range
- First signals: 2026-02-22
- Latest signals: 2026-02-23

## ClickHouse Server Info
- Version: 26.1.2.11
- HTTP Port: 8123
- TCP Port: 9000
- Data Directory: ./clickhouse_data

## Performance Metrics Queries Available
```sql
-- Trade status breakdown
SELECT status, count(), avg(entry_price) FROM trades GROUP BY status;

-- Signal confidence by direction
SELECT direction, avg(confidence), count() FROM pipeline_signals GROUP BY direction;

-- Ticker activity summary
SELECT ticker, count(), min(created_at), max(created_at) 
FROM pipeline_signals GROUP BY ticker ORDER BY count() DESC;
```
