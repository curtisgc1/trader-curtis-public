ATTACH TABLE _ UUID '43be7934-d07f-4417-b300-8ec01a020c26'
(
    `timestamp` DateTime64(3),
    `trade_id` String,
    `ticker` LowCardinality(String),
    `side` LowCardinality(String),
    `shares` Int32,
    `entry_price` Float64,
    `exit_price` Float64,
    `position_size` Float64,
    `pnl` Float64,
    `pnl_percent` Float64,
    `status` LowCardinality(String),
    `sentiment_reddit` Int8,
    `sentiment_twitter` Int8,
    `sentiment_stocktwits` Int8,
    `sentiment_grok` Int8,
    `source_reddit_wsb` Float64,
    `source_reddit_stocks` Float64,
    `source_twitter` Float64,
    `source_stocktwits` Float64,
    `source_trump` Float64,
    `source_bessent` Float64,
    `decision_grade` LowCardinality(String),
    `lesson_learned` String,
    `strategy_used` LowCardinality(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (ticker, timestamp)
TTL timestamp + toIntervalYear(2)
SETTINGS index_granularity = 8192
