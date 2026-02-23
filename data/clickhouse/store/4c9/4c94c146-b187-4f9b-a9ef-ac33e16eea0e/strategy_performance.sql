ATTACH TABLE _ UUID '7cf0ebfa-ac0a-4e4c-bf54-6a7e59eb0ab7'
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
