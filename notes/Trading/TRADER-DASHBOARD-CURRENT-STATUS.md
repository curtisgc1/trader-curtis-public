# Trader Dashboard - Current Status Snapshot

Date: 2026-02-23
Dashboard URL: http://127.0.0.1:8090/

## Auto-Trade Controls
- min_candidate_score: 55
- enable_alpaca_paper_auto: 1
- enable_hyperliquid_test_auto: 1
- allow_hyperliquid_live: 1
- hyperliquid_test_notional_usd: 10

## System Counts
- signal_routes: 226
- execution_orders: 23
- route_trade_links: 23
- route_outcomes: 3
- quant_validations: 48

## Learning Health (7d)
- eligible_routes: 23
- tracked_routes: 23
- tracked_coverage_pct: 100.0
- resolved_routes: 3
- coverage_pct: 13.04
- system_health_overall: warn

## Notes
- Quant validation gate is integrated and writing to `quant_validations`.
- Route-to-order linkage is integrated via `route_trade_links`.
- Resolved learning is still low because most routes are not yet closed with realized PnL.
