-- Trader Curtis ClickHouse Schema
-- High-performance analytics for trading data

CREATE DATABASE IF NOT EXISTS trader_curtis;

-- Main trades table
CREATE TABLE IF NOT EXISTS trader_curtis.trades (
    timestamp DateTime64(3),
    trade_id String,
    ticker LowCardinality(String),
    side LowCardinality(String),
    shares Int32,
    entry_price Float64,
    exit_price Float64,
    position_size Float64,
    pnl Float64,
    pnl_percent Float64,
    status LowCardinality(String),
    
    -- Sentiment scores at entry
    sentiment_reddit Int8,
    sentiment_twitter Int8,
    sentiment_stocktwits Int8,
    sentiment_grok Int8,
    
    -- Source tracking
    source_reddit_wsb Float64,
    source_reddit_stocks Float64,
    source_twitter Float64,
    source_stocktwits Float64,
    source_trump Float64,
    source_bessent Float64,
    
    -- Analysis
    decision_grade LowCardinality(String),
    lesson_learned String,
    strategy_used LowCardinality(String)
) 
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (ticker, timestamp)
TTL timestamp + INTERVAL 2 YEAR;

-- Sentiment accuracy tracking
CREATE TABLE IF NOT EXISTS trader_curtis.sentiment_accuracy (
    prediction_date Date,
    ticker LowCardinality(String),
    source LowCardinality(String),
    predicted_direction LowCardinality(String),
    actual_direction LowCardinality(String),
    accuracy_score Float64,
    confidence Float64,
    price_at_prediction Float64,
    price_3d_later Float64,
    price_7d_later Float64
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(prediction_date)
ORDER BY (source, prediction_date, ticker);

-- Social posts monitoring
CREATE TABLE IF NOT EXISTS trader_curtis.social_posts (
    timestamp DateTime64(3),
    platform LowCardinality(String),
    author String,
    content String,
    tickers Array(String),
    sentiment Int8,
    engagement UInt32,
    price_impact_1h Float64,
    price_impact_1d Float64,
    is_viral UInt8 DEFAULT 0
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (platform, timestamp);

-- Daily performance summary
CREATE TABLE IF NOT EXISTS trader_curtis.performance_daily (
    date Date,
    total_trades UInt32,
    winning_trades UInt32,
    losing_trades UInt32,
    total_pnl Float64,
    win_rate Float64,
    avg_win Float64,
    avg_loss Float64,
    max_drawdown Float64,
    best_ticker LowCardinality(String),
    worst_ticker LowCardinality(String),
    best_source LowCardinality(String),
    worst_source LowCardinality(String)
)
ENGINE = MergeTree()
ORDER BY date;

-- Strategy performance
CREATE TABLE IF NOT EXISTS trader_curtis.strategy_performance (
    strategy_name LowCardinality(String),
    month Date,
    trades_count UInt32,
    win_rate Float64,
    avg_return Float64,
    sharpe_ratio Float64,
    max_drawdown Float64
)
ENGINE = MergeTree()
ORDER BY (strategy_name, month);

-- Create materialized view for daily aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS trader_curtis.daily_trades_mv
TO trader_curtis.performance_daily
AS
SELECT
    toDate(timestamp) as date,
    count() as total_trades,
    countIf(pnl > 0) as winning_trades,
    countIf(pnl < 0) as losing_trades,
    sum(pnl) as total_pnl,
    countIf(pnl > 0) / count() as win_rate,
    avgIf(pnl_percent, pnl > 0) as avg_win,
    avgIf(pnl_percent, pnl < 0) as avg_loss
FROM trader_curtis.trades
WHERE status = 'closed'
GROUP BY toDate(timestamp);

SELECT 'ClickHouse schema created successfully' as status;
