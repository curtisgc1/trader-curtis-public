# ClickHouse Analytics Report
Generated: 2026-02-19 22:00 PST

## Executive Summary
- **Total Trades Migrated:** 18
- **Total PnL:** -$27,568.35
- **Win Rate:** 0% (0 wins, 18 losses)
- **Avg Return Per Trade:** -14.95%

## Database Status
✅ ClickHouse server running on port 9000
✅ Database `trader_curtis` initialized
✅ Schema created with 6 tables
✅ 18 trades migrated from SQLite

## Trade Performance by Ticker
| Ticker | Trades | Total PnL | Avg Return | Worst Trade | Best Trade |
|--------|--------|-----------|------------|-------------|------------|
| MARA   | 6      | -$2,872.77 | -13.79%    | -$865.79    | -$91.80    |
| ASTS   | 6      | -$4,733.40 | -20.61%    | -$788.90    | -$788.90   |
| PLTR   | 6      | -$19,962.18 | -10.43%    | -$6,556.28  | -$97.78    |

## Daily Performance
| Date       | Trades | Daily PnL      |
|------------|--------|----------------|
| 2026-02-19 | 9      | -$17,400.42    |
| 2026-02-18 | 6      | -$9,189.45     |
| 2026-02-15 | 3      | -$978.48       |

## Grade Analysis
| Grade | Trades | Total PnL      | Avg Return  |
|-------|--------|----------------|-------------|
| C     | 6      | -$22,266.21    | -4.96%      |
| D     | 12     | -$5,302.14     | -19.94%     |

## Strategy Performance
| Strategy    | Trades | Total PnL      | Avg Return  |
|-------------|--------|----------------|-------------|
| no_consensus| 18     | -$27,568.35    | -14.95%     |

## Key Insights
1. **No Winning Trades:** All 18 trades resulted in losses
2. **PLTR Biggest Drag:** Palantir accounts for 72% of total losses
3. **Grade C Worse Than D:** Despite better grades, C-rated trades had larger $ losses
4. **Consistent Strategy:** All trades used "no_consensus" strategy
5. **Recent Deterioration:** Feb 19 had the worst daily performance

## ClickHouse Schema
- `trades` - Main trade records with sentiment scores
- `sentiment_accuracy` - Prediction accuracy tracking
- `social_posts` - Social media monitoring
- `performance_daily` - Daily aggregated metrics
- `strategy_performance` - Monthly strategy stats
- `daily_trades_mv` - Materialized view for performance

## Next Steps
1. Implement winning trades to improve metrics
2. Analyze source accuracy for better signals
3. Review entry/exit timing
4. Consider position sizing adjustments
