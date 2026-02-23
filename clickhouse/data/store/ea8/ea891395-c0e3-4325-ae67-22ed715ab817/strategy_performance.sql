ATTACH TABLE _ UUID '4c4c84a1-5f86-4478-8005-897271aa20ec'
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
