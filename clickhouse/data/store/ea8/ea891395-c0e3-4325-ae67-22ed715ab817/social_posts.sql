ATTACH TABLE _ UUID '24cf7e29-a35d-4ac5-a373-69058ef1d710'
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
