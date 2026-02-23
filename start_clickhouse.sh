#!/bin/bash
# Start ClickHouse server for Trader Curtis

CLICKHOUSE_DATA="/Users/shared/curtis/trader-curtis/data/clickhouse"
mkdir -p $CLICKHOUSE_DATA

echo "Starting ClickHouse server..."
clickhouse server --config-file=/dev/null \
  --log_level=warning \
  --path=$CLICKHOUSE_DATA \
  --tcp_port=9000 \
  --http_port=8123 \
  --mysql_port=9004 &

sleep 3

echo "Initializing database..."
clickhouse-client --port=9000 < /Users/shared/curtis/trader-curtis/data/init_clickhouse.sql

echo "ClickHouse ready on port 9000"
