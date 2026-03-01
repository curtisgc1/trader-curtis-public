-- ClickHouse tables for trader-curtis analytics

-- Core trades table
CREATE TABLE IF NOT EXISTS trades (
    trade_id String,
    ticker String,
    entry_date DateTime,
    exit_date DateTime,
    entry_price Float64,
    exit_price Float64,
    shares Int32,
    pnl Float64,
    pnl_percent Float64,
    status String,
    sentiment_reddit Int32,
    sentiment_twitter Int32,
    sentiment_trump Int32,
    source_reddit_wsb String,
    source_reddit_stocks String,
    source_reddit_investing String,
    source_twitter_general String,
    source_twitter_analysts String,
    source_trump_posts String,
    source_news String,
    source_accuracy_score Float64,
    thesis String,
    outcome_analysis String,
    lesson_learned String,
    decision_grade String,
    created_at DateTime,
    route_id Int32,
    broker_order_id String,
    last_sync DateTime,
    entry_side String
) ENGINE = MergeTree()
ORDER BY (ticker, entry_date)
SETTINGS index_granularity = 8192;

-- Route outcomes for learning
CREATE TABLE IF NOT EXISTS route_outcomes (
    route_id Int32,
    ticker String,
    source_tag String,
    resolution String,
    pnl Float64,
    pnl_percent Float64,
    resolved_at DateTime,
    notes String,
    outcome_type String
) ENGINE = MergeTree()
ORDER BY (source_tag, resolved_at)
SETTINGS index_granularity = 8192;

-- Source learning stats
CREATE TABLE IF NOT EXISTS source_learning_stats (
    id Int32,
    computed_at DateTime,
    source_tag String,
    sample_size Int32,
    wins Int32,
    losses Int32,
    pushes Int32,
    win_rate Float64,
    avg_pnl Float64,
    avg_pnl_percent Float64
) ENGINE = MergeTree()
ORDER BY (source_tag, computed_at)
SETTINGS index_granularity = 8192;

-- Strategy learning stats  
CREATE TABLE IF NOT EXISTS strategy_learning_stats (
    id Int32,
    computed_at DateTime,
    strategy_tag String,
    sample_size Int32,
    wins Int32,
    losses Int32,
    pushes Int32,
    win_rate Float64,
    avg_pnl Float64,
    avg_pnl_percent Float64
) ENGINE = MergeTree()
ORDER BY (strategy_tag, computed_at)
SETTINGS index_granularity = 8192;

-- Signal routes
CREATE TABLE IF NOT EXISTS signal_routes (
    id Int32,
    routed_at DateTime,
    ticker String,
    direction String,
    score Float64,
    source_tag String,
    proposed_notional Float64,
    mode String,
    decision String,
    reason String,
    status String,
    validation_id Int32,
    allocator_factor Float64,
    allocator_regime String,
    allocator_reason String,
    allocator_blocked Int8,
    venue_scores_json String,
    venue_decisions_json String,
    preferred_venue String
) ENGINE = MergeTree()
ORDER BY (ticker, routed_at)
SETTINGS index_granularity = 8192;

-- Execution orders
CREATE TABLE IF NOT EXISTS execution_orders (
    id Int32,
    created_at DateTime,
    route_id Int32,
    ticker String,
    direction String,
    mode String,
    notional Float64,
    order_status String,
    broker_order_id String,
    notes String,
    leverage_used Float64,
    leverage_capable Int8
) ENGINE = MergeTree()
ORDER BY (ticker, created_at)
SETTINGS index_granularity = 8192;

-- Polymarket orders
CREATE TABLE IF NOT EXISTS polymarket_orders (
    id Int32,
    created_at DateTime,
    strategy_id String,
    candidate_id Int32,
    market_id String,
    outcome String,
    side String,
    price Float64,
    size Float64,
    order_id String,
    status String,
    notes String,
    route_id Int32,
    token_id String,
    mode String,
    notional Float64,
    response_json String
) ENGINE = MergeTree()
ORDER BY (market_id, created_at)
SETTINGS index_granularity = 8192;

-- Execution learning
CREATE TABLE IF NOT EXISTS execution_learning (
    id Int32,
    created_at DateTime,
    route_id Int32,
    ticker String,
    source_tag String,
    pipeline_hint String,
    mode String,
    venue String,
    decision String,
    order_status String,
    reason String
) ENGINE = MergeTree()
ORDER BY (venue, created_at)
SETTINGS index_granularity = 8192;

-- VIX regime state
CREATE TABLE IF NOT EXISTS vix_regime_state (
    id Int32,
    fetched_at DateTime,
    vix_close Float64,
    vix_5d_avg Float64,
    regime String,
    leverage_scale Float64,
    gex_signal String,
    gex_confirmed Int8,
    signal_ticker String,
    signal_direction String,
    confidence Float64,
    notes String
) ENGINE = MergeTree()
ORDER BY fetched_at
SETTINGS index_granularity = 8192;

-- Position awareness
CREATE TABLE IF NOT EXISTS position_awareness_snapshots (
    id Int32,
    created_at DateTime,
    venue String,
    symbol String,
    side String,
    qty Float64,
    entry_price Float64,
    mark_price Float64,
    notional_usd Float64,
    unrealized_pnl_usd Float64,
    unrealized_pnl_pct Float64,
    action String,
    confidence Float64,
    reason String
) ENGINE = MergeTree()
ORDER BY (venue, symbol, created_at)
SETTINGS index_granularity = 8192;

-- Kelly signals
CREATE TABLE IF NOT EXISTS kelly_signals (
    id Int32,
    computed_at DateTime,
    ticker String,
    direction String,
    source_tag String,
    horizon_hours Int32,
    win_prob Float64,
    avg_win_pct Float64,
    avg_loss_pct Float64,
    payout_ratio Float64,
    kelly_fraction Float64,
    frac_kelly Float64,
    convexity_score Float64,
    ev_percent Float64,
    sample_size Int32,
    verdict String,
    verdict_reason String
) ENGINE = MergeTree()
ORDER BY (ticker, computed_at)
SETTINGS index_granularity = 8192;

-- Momentum signals
CREATE TABLE IF NOT EXISTS momentum_signals (
    id Int32,
    created_at DateTime,
    ticker String,
    asset_class String,
    rank Int32,
    rank_of Int32,
    momentum_score Float64,
    pct_30d Float64,
    batch_ts DateTime
) ENGINE = MergeTree()
ORDER BY (ticker, created_at)
SETTINGS index_granularity = 8192;
