ATTACH TABLE _ UUID 'd73e6ab3-cdf2-4333-aeee-05e9d0faa579'
(
    `timestamp` DateTime64(3),
    `platform` LowCardinality(String),
    `author` String,
    `content` String,
    `tickers` Array(String),
    `sentiment` Int8,
    `engagement` UInt32,
    `price_impact_1h` Float64,
    `price_impact_1d` Float64,
    `is_viral` UInt8 DEFAULT 0
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (platform, timestamp)
SETTINGS index_granularity = 8192
