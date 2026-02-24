-- ClickHouse tables for TRADER-CURTIS
-- Migration from SQLite to ClickHouse

-- Main trades table
CREATE TABLE IF NOT EXISTS trades (
    trade_id String,
    ticker String,
    entry_date DateTime64(6),
    exit_date Nullable(DateTime64(6)),
    entry_price Float64,
    exit_price Nullable(Float64),
    shares Int32,
    pnl Nullable(Float64),
    pnl_percent Nullable(Float64),
    status String,
    sentiment_reddit Nullable(Int32),
    sentiment_twitter Nullable(Int32),
    sentiment_trump Nullable(Int32),
    source_reddit_wsb Nullable(String),
    source_reddit_stocks Nullable(String),
    source_reddit_investing Nullable(String),
    source_twitter_general Nullable(String),
    source_twitter_analysts Nullable(String),
    source_trump_posts Nullable(String),
    source_news Nullable(String),
    source_accuracy_score Nullable(Float64),
    thesis Nullable(String),
    outcome_analysis Nullable(String),
    lesson_learned Nullable(String),
    decision_grade Nullable(String),
    created_at DateTime,
    route_id Nullable(Int32),
    broker_order_id Nullable(String),
    last_sync Nullable(DateTime)
) ENGINE = MergeTree()
ORDER BY (ticker, entry_date);

-- Pipeline signals
CREATE TABLE IF NOT EXISTS pipeline_signals (
    id UInt32,
    ticker String,
    signal_type String,
    direction String,
    confidence Float64,
    source String,
    created_at DateTime,
    processed UInt8 DEFAULT 0
) ENGINE = MergeTree()
ORDER BY (ticker, created_at);

-- Source learning stats
CREATE TABLE IF NOT EXISTS source_learning_stats (
    source_name String,
    total_signals UInt32,
    wins UInt32,
    losses UInt32,
    win_rate Float64,
    avg_return Float64,
    last_updated DateTime
) ENGINE = MergeTree()
ORDER BY source_name;

-- Route outcomes
CREATE TABLE IF NOT EXISTS route_outcomes (
    route_id UInt32,
    ticker String,
    signal_count UInt32,
    avg_confidence Float64,
    win_rate Float64,
    total_pnl Float64,
    created_at DateTime
) ENGINE = MergeTree()
ORDER BY route_id;

-- Execution learning
CREATE TABLE IF NOT EXISTS execution_learning (
    id UInt32,
    trade_id String,
    execution_quality String,
    slippage_bps Float64,
    timing_score Float64,
    lesson String,
    created_at DateTime
) ENGINE = MergeTree()
ORDER BY trade_id;

-- Polymarket data
CREATE TABLE IF NOT EXISTS polymarket_markets (
    market_id String,
    question String,
    probability Float64,
    volume Float64,
    created_at DateTime,
    resolved UInt8 DEFAULT 0
) ENGINE = MergeTree()
ORDER BY (market_id, created_at);

-- Signal routes
CREATE TABLE IF NOT EXISTS signal_routes (
    id UInt32,
    ticker String,
    route_type String,
    confidence Float64,
    sources Array(String),
    created_at DateTime,
    executed UInt8 DEFAULT 0
) ENGINE = MergeTree()
ORDER BY (ticker, created_at);
