# ClickHouse Migration - 2026-02-23

## Actions Completed
- ✅ Started ClickHouse server (v26.1.2.11) on ports 8123/9000
- ✅ Created 8 tables in ClickHouse
- ✅ Migrated SQLite data:
  - trades: 37 records
  - pipeline_signals: 1,215 records
  - route_outcomes: 9 records

## Key Findings
- 33 open positions across 13 tickers
- 1,215 pipeline signals (1,075 long, 140 short)
- Top holdings: NVDA (9), ASML (6), TSM (5), ISRG (5)
- Short signals have higher avg confidence (0.73) vs long (0.59)

## Server Details
- Data dir: ./clickhouse_data
- Report: ./clickhouse_migration/migration_report.md
