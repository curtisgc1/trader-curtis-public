ATTACH MATERIALIZED VIEW _ UUID 'd4d45b7d-b548-459d-83b7-b9a2ae9c3481' TO trader_curtis.performance_daily
(
    `date` Date,
    `total_trades` UInt64,
    `winning_trades` UInt64,
    `losing_trades` UInt64,
    `total_pnl` Float64,
    `win_rate` Float64,
    `avg_win` Float64,
    `avg_loss` Float64
)
AS SELECT
    toDate(timestamp) AS date,
    count() AS total_trades,
    countIf(pnl > 0) AS winning_trades,
    countIf(pnl < 0) AS losing_trades,
    sum(pnl) AS total_pnl,
    countIf(pnl > 0) / count() AS win_rate,
    avgIf(pnl_percent, pnl > 0) AS avg_win,
    avgIf(pnl_percent, pnl < 0) AS avg_loss
FROM trader_curtis.trades
WHERE status = 'closed'
GROUP BY toDate(timestamp)
