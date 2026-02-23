ATTACH TABLE _ UUID '7df90b2d-4ff3-40b8-aef4-f1450563d3d0'
(
    `source` String,
    `total_trades` Int32 DEFAULT 0,
    `wins_when_bullish` Int32 DEFAULT 0,
    `losses_when_bullish` Int32 DEFAULT 0,
    `wins_when_bearish` Int32 DEFAULT 0,
    `losses_when_bearish` Int32 DEFAULT 0,
    `neutral_calls` Int32 DEFAULT 0,
    `accuracy_rate` Float64 DEFAULT 0.,
    `avg_pnl_when_followed` Float64 DEFAULT 0.,
    `combo_performance` Nullable(String),
    `last_updated` DateTime
)
ENGINE = ReplacingMergeTree
ORDER BY source
SETTINGS index_granularity = 8192
