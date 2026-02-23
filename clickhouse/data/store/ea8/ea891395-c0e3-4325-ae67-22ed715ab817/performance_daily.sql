ATTACH TABLE _ UUID '6d4809f1-c661-4996-8fea-354777a441ec'
(
    `date` Date,
    `total_trades` UInt32,
    `winning_trades` UInt32,
    `losing_trades` UInt32,
    `total_pnl` Float64,
    `win_rate` Float64,
    `avg_win` Float64,
    `avg_loss` Float64,
    `max_drawdown` Float64,
    `best_ticker` LowCardinality(String),
    `worst_ticker` LowCardinality(String),
    `best_source` LowCardinality(String),
    `worst_source` LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY date
SETTINGS index_granularity = 8192
