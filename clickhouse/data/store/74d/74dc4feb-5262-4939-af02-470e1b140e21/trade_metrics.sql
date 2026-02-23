ATTACH TABLE _ UUID 'a0b7d114-d966-4420-9b9c-f26a370bc5b1'
(
    `metric_date` Date,
    `total_trades` UInt32,
    `winning_trades` UInt32,
    `losing_trades` UInt32,
    `win_rate` Float64,
    `total_pnl` Float64,
    `avg_pnl_per_trade` Float64,
    `avg_win` Float64,
    `avg_loss` Float64,
    `profit_factor` Float64,
    `best_trade_ticker` Nullable(String),
    `best_trade_pnl` Nullable(Float64),
    `worst_trade_ticker` Nullable(String),
    `worst_trade_pnl` Nullable(Float64)
)
ENGINE = MergeTree
ORDER BY metric_date
SETTINGS index_granularity = 8192
