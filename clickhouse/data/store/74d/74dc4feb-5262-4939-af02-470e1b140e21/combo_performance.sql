ATTACH TABLE _ UUID 'c778dcb7-cc7b-40de-baed-0dbabedc4457'
(
    `combo` String,
    `sources` Nullable(String),
    `total_uses` Int32 DEFAULT 0,
    `wins` Int32 DEFAULT 0,
    `losses` Int32 DEFAULT 0,
    `win_rate` Float64 DEFAULT 0.,
    `avg_pnl` Float64 DEFAULT 0.,
    `grade` Nullable(String),
    `last_updated` DateTime
)
ENGINE = ReplacingMergeTree
ORDER BY combo
SETTINGS index_granularity = 8192
