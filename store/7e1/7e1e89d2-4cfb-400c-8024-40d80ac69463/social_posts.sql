ATTACH TABLE _ UUID '73de1c83-dae8-472d-8c2b-25f9dee9c725'
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
