ATTACH TABLE _ UUID '530c51f3-ff59-4046-806d-060de0ae9d96'
(
    `id` UInt32,
    `ticker` String,
    `date` DateTime,
    `source` String,
    `predicted_direction` String,
    `actual_direction` Nullable(String),
    `accuracy_score` Nullable(Float64),
    `sentiment_score` Int32,
    `trade_grade` Nullable(String),
    `pnl_pct` Nullable(Float64),
    `created_at` DateTime
)
ENGINE = MergeTree
ORDER BY (ticker, date, source)
SETTINGS index_granularity = 8192
