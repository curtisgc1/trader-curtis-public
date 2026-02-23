ATTACH TABLE _ UUID '6dd77e24-6b4f-48f0-ae2c-9891d1761a4c'
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
