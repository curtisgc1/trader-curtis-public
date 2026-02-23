ATTACH TABLE _ UUID '593c6089-3ba2-43b7-9154-a4b581773cc6'
(
    `prediction_date` Date,
    `ticker` LowCardinality(String),
    `source` LowCardinality(String),
    `predicted_direction` LowCardinality(String),
    `actual_direction` LowCardinality(String),
    `accuracy_score` Float64,
    `confidence` Float64,
    `price_at_prediction` Float64,
    `price_3d_later` Float64,
    `price_7d_later` Float64
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(prediction_date)
ORDER BY (source, prediction_date, ticker)
SETTINGS index_granularity = 8192
