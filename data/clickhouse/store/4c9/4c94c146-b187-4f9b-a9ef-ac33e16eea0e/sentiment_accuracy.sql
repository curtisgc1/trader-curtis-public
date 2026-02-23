ATTACH TABLE _ UUID '1de271cb-9ab3-44d6-8218-0896bb2a75b7'
(
    `id` UInt64,
    `ticker` String,
    `prediction_date` DateTime,
    `predicted_direction` String,
    `actual_direction` String,
    `accuracy_score` Float64,
    `source` String
)
ENGINE = MergeTree
ORDER BY (prediction_date, ticker)
SETTINGS index_granularity = 8192
