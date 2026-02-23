ATTACH TABLE _ UUID 'f0951935-8c73-4e67-8080-40cf9a105707'
(
    `strategy_name` LowCardinality(String),
    `month` Date,
    `trades_count` UInt32,
    `win_rate` Float64,
    `avg_return` Float64,
    `sharpe_ratio` Float64,
    `max_drawdown` Float64
)
ENGINE = MergeTree
ORDER BY (strategy_name, month)
SETTINGS index_granularity = 8192
