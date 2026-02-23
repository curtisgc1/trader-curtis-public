ATTACH TABLE _ UUID 'edab9f71-a0b6-4744-9408-4ee87f65511c'
(
    `date` Date,
    `total_trades` UInt32,
    `wins` UInt32,
    `losses` UInt32,
    `total_pnl` Float64,
    `win_rate` Float64,
    `best_source` String,
    `worst_source` String
)
ENGINE = MergeTree
ORDER BY date
SETTINGS index_granularity = 8192
