---
title: handoff-2026-02-22-autotrade-live-hl-and-dashboard-controls
date: '2026-02-22'
type: handoff
workingOn:
  - Auto-trading enablement (Alpaca paper + Hyperliquid live test) and dashboard controls
blocked: []
nextSteps:
  - Add explicit UI warning badge when HL notional < exchange minimum for selected symbol
  - Normalize/cleanup legacy `execution_orders` rows from earlier simulation stage
  - Wire route-outcome learning to broker fills/close events for stronger source grading
---

# Session Handoff

## Completed
- Enabled Alpaca paper auto-execution for approved paper routes.
- Added signed Hyperliquid live execution path behind controls.
- Added dashboard controls API and UI actions to toggle/update execution controls.
- Added and kept automatic learning pipeline (`execution_learning`, `route_outcomes`, `source_learning_stats`) in runtime flow.

## Critical Finding
- Hyperliquid BTC orders have a practical minimum notional of **$10**.
- `$1` live attempts were rejected by exchange response.
- Control default moved to `hyperliquid_test_notional_usd=10` for executable live test behavior.

## Validation Evidence
- Alpaca paper order: submitted (AAPL).
- Hyperliquid live BTC order: submitted and filled at ~$10 notional (`totalSz` around `0.00015`).
- Exchange rejection path correctly marked as blocked/failed for under-minimum attempts.

## Current Safe Control State
- `allow_live_trading=0`
- `allow_hyperliquid_live=1`
- `enable_alpaca_paper_auto=1`
- `enable_hyperliquid_test_auto=1`
- `hyperliquid_test_notional_usd=10`

## Key Files
- `execution_adapters.py`
- `execution_worker.py`
- `execution_guard.py`
- `scripts/enable_autotrade_test_mode.sh`
- `dashboard-ui/app.py`
- `dashboard-ui/data.py`
- `dashboard-ui/static/index.html`
- `dashboard-ui/static/app.js`
