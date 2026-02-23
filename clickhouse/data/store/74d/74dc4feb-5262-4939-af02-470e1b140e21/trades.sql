ATTACH TABLE _ UUID '57b2b9a9-381f-402c-8033-7316dcd48c56'
(
    `trade_id` String,
    `ticker` String,
    `entry_date` DateTime,
    `exit_date` Nullable(DateTime),
    `entry_price` Float64,
    `exit_price` Nullable(Float64),
    `shares` Int32,
    `pnl` Nullable(Float64),
    `pnl_percent` Nullable(Float64),
    `status` String,
    `sentiment_reddit` Nullable(Int32),
    `sentiment_twitter` Nullable(Int32),
    `sentiment_trump` Nullable(Int32),
    `source_reddit_wsb` Nullable(String),
    `source_reddit_stocks` Nullable(String),
    `source_reddit_investing` Nullable(String),
    `source_twitter_general` Nullable(String),
    `source_twitter_analysts` Nullable(String),
    `source_trump_posts` Nullable(String),
    `source_news` Nullable(String),
    `source_accuracy_score` Nullable(Float64),
    `thesis` Nullable(String),
    `outcome_analysis` Nullable(String),
    `lesson_learned` Nullable(String),
    `decision_grade` Nullable(String),
    `created_at` DateTime
)
ENGINE = MergeTree
ORDER BY (ticker, entry_date)
SETTINGS index_granularity = 8192
