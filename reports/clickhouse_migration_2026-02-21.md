# ClickHouse Migration Report - 2026-02-21

## Summary
- **Date:** Saturday, February 21st, 2026 - 10:00 PM PST
- **Task:** Start ClickHouse & Migrate Data

## Status
✅ ClickHouse Server: Running (v26.1.2.11)
✅ Database Created: trader_curtis
✅ Tables Created: 6 tables + 1 materialized view
✅ Migration Complete: 30 trades migrated

## Data Migration Results

### Source: SQLite (trades.db)
- simple_source_outcomes: 30 records → Migrated
- source_performance: 6 records → Migrated (metadata only)
- sentiment_accuracy: 0 records

### Target: ClickHouse (trader_curtis)
- trades: 30 records
- sentiment_accuracy: 0 records
- source_outcomes: 0 records
- source_leaderboard: 0 records
- combo_performance: 0 records
- trade_metrics: 1 record (existing)

## Performance Metrics

### Overall Performance
| Metric | Value |
|--------|-------|
| Total Trades | 30 |
| Winners | 0 |
| Losers | 30 |
| Win Rate | 0% |
| Total PnL | -$53,179.74 |
| Avg Return | -13.99% |
| Best Trade | -$91.80 |
| Worst Trade | -$6,556.28 |

### By Ticker
| Ticker | Trades | Wins | Win Rate | Total PnL | Avg Return |
|--------|--------|------|----------|-----------|------------|
| MARA | 10 | 0 | 0% | -$5,561.94 | -12.86% |
| ASTS | 10 | 0 | 0% | -$7,889.00 | -20.61% |
| PLTR | 10 | 0 | 0% | -$39,728.80 | -8.51% |

### By Decision Grade
| Grade | Trades | Total PnL | Avg Return |
|-------|--------|-----------|------------|
| D | 18 | -$8,647.32 | -20.01% |
| C | 12 | -$44,532.42 | -4.96% |

### Source Sentiment Analysis
| Ticker | Avg Reddit WSB | Avg Twitter | Avg Trump | Trades |
|--------|----------------|-------------|-----------|--------|
| ASTS | 50.0 | 50.0 | 50.0 | 10 |
| MARA | 50.5 | 50.5 | 50.5 | 10 |
| PLTR | 50.0 | 50.0 | 50.0 | 10 |

## Daily Aggregation (from Materialized View)
- 2026-02-20: 12 trades, 0 wins, -$18,765.79
- 2026-02-19: 10 trades, 0 wins, -$15,842.52
- 2026-02-18: 6 trades, 0 wins, -$8,398.83
- 2026-02-15: 3 trades, 0 wins, -$978.48

## Tables Created
1. `trades` - Main trading records with sentiment scores
2. `sentiment_accuracy` - Prediction accuracy tracking
3. `social_posts` - Social media monitoring
4. `performance_daily` - Daily aggregated metrics
5. `strategy_performance` - Strategy-level analytics
6. `daily_trades_mv` - Materialized view for daily aggregation

## Notes
- All migrated trades show negative PnL (paper trading test data)
- Sentiment scores are neutral (50) indicating test/missing data
- Source tracking shows minimal variation in sentiment signals
- ClickHouse ready for real-time analytics queries

## Next Steps
1. Connect live trading feed to ClickHouse
2. Implement real-time sentiment scoring
3. Set up Grafana dashboard for visualization
4. Create alerts for significant PnL changes

---
Generated: 2026-02-21 22:00 PST
ClickHouse Version: 26.1.2.11
