ATTACH TABLE _ UUID '5f6ec636-8119-4a1e-bf4f-979ae5bce9f6'
(
    `timestamp` DateTime,
    `platform` String,
    `author` String,
    `content` String,
    `tickers` Array(String),
    `sentiment` Int8,
    `engagement` UInt32,
    `price_impact_1h` Float64
)
ENGINE = MergeTree
ORDER BY (timestamp, platform)
SETTINGS index_granularity = 8192
