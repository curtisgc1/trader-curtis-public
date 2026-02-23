CREATE DATABASE IF NOT EXISTS trader_curtis;

USE trader_curtis;

CREATE TABLE IF NOT EXISTS trades (
    timestamp DateTime64(3),
    trade_id String,
    ticker String,
    side String,
    shares Int32,
    entry_price Float64,
    exit_price Float64,
    position_size Float64,
    pnl Float64,
    pnl_percent Float64,
    sentiment_reddit Int8,
    sentiment_twitter Int8,
    sentiment_stocktwits Int8,
    source_reddit_wsb String,
    source_reddit_stocks String,
    source_twitter String,
    source_stocktwits String,
    source_trump String,
    source_bessent String,
    decision_grade String,
    lesson_learned String,
    status String
) ENGINE = MergeTree()
ORDER BY (timestamp, ticker);

CREATE TABLE IF NOT EXISTS sentiment_accuracy (
    id UInt64,
    ticker String,
    prediction_date DateTime,
    predicted_direction String,
    actual_direction String,
    accuracy_score Float64,
    source String
) ENGINE = MergeTree()
ORDER BY (prediction_date, ticker);

CREATE TABLE IF NOT EXISTS social_posts (
    timestamp DateTime,
    platform String,
    author String,
    content String,
    tickers Array(String),
    sentiment Int8,
    engagement UInt32,
    price_impact_1h Float64
) ENGINE = MergeTree()
ORDER BY (timestamp, platform);

CREATE TABLE IF NOT EXISTS performance_daily (
    date Date,
    total_trades UInt32,
    wins UInt32,
    losses UInt32,
    total_pnl Float64,
    win_rate Float64,
    best_source String,
    worst_source String
) ENGINE = MergeTree()
ORDER BY date;

SELECT 'ClickHouse tables created successfully' as result;
