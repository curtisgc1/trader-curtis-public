# ClickHouse Analytics Migration Report
Generated: 2026-02-24 22:01 PST

## Summary
✅ ClickHouse server started successfully
✅ Database `trader_curtis` created
✅ 4 tables created with MergeTree engine
✅ 107 total rows migrated from SQLite

## Migration Results
| Table | Rows Migrated |
|-------|---------------|
| trades | 44 |
| route_outcomes | 50 |
| source_learning_stats | 10 |
| strategy_learning_stats | 3 |

## Overall Performance Metrics
| Metric | Value |
|--------|-------|
| Total P&L | +$293.49 |
| Avg P&L per Trade | +$5.87 |
| Total Outcomes | 50 |
| Win Rate | 56% |
| Best Trade | +$27.27 |
| Worst Trade | -$4.80 |

## Win/Loss Breakdown
| Resolution | Outcomes | Avg P&L | Total P&L | Avg Return % |
|------------|----------|---------|-----------|--------------|
| Win | 28 | +$11.47 | +$321.16 | +3.15% |
| Loss | 22 | -$1.26 | -$27.67 | -0.37% |

## Top Performing Sources (by Win Rate)
| Source | Sample Size | Wins | Losses | Win Rate | Avg P&L |
|--------|-------------|------|--------|----------|---------|
| TestSource | 3 | 3 | 0 | 100% | +$1.28 |
| manual-test | 1 | 1 | 0 | 100% | +$8.18 |
| B_LONGTERM | 25 | 20 | 5 | 80% | +$10.93 |
| NoLimitGains | 3 | 1 | 2 | 33% | +$0.10 |
| internal | 6 | 2 | 4 | 33% | +$1.84 |
| C_EVENT | 4 | 1 | 3 | 25% | +$0.22 |
| finviz:rss | 5 | 0 | 5 | 0% | -$0.50 |

## Strategy Performance
| Strategy | Sample Size | Wins | Losses | Win Rate | Avg P&L |
|----------|-------------|------|--------|----------|---------|
| B_LONGTERM | 25 | 20 | 5 | 80% | +$10.93 |
| UNSPECIFIED | 21 | 7 | 14 | 33% | +$0.92 |
| C_EVENT | 4 | 1 | 3 | 25% | +$0.22 |

## Recent Daily Performance (Last 7 Days)
| Date | Outcomes | Daily P&L | Avg Return % |
|------|----------|-----------|--------------|
| 2026-02-24 | 41 | +$297.99 | +2.01% |
| 2026-02-23 | 9 | -$4.50 | -0.25% |

## Trade Status Breakdown
| Status | Count |
|--------|-------|
| open | 33 |
| pending | 11 |

## Tables Created
1. **trades** - Main trade records with sentiment data
2. **route_outcomes** - Resolved trade outcomes with P&L
3. **source_learning_stats** - Performance metrics by source
4. **strategy_learning_stats** - Performance metrics by strategy

## Next Steps
- Materialized views can be added for real-time aggregations
- Consider partitioning strategy for larger datasets
- Set up automated ETL pipeline for ongoing sync
