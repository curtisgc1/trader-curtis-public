---
title: handoff-2026-02-23-learning-health-loop
date: '2026-02-23'
type: handoff
workingOn:
  - PnL/ops learning loop + system health dashboard hardening
blocked: []
nextSteps:
  - Map filled Alpaca orders to actual close PnL lifecycle (entry->exit linkage)
  - Add min-notional map by HL symbol instead of static BTC baseline
  - Add health panel action buttons (run scan now, sync broker now)
---

# Session Handoff

## Completed
- Learning feedback loop improved:
  - Operational execution failures now become route outcomes (`route_outcomes`) with small negative penalty.
  - Source learning stats regenerate from route outcomes each cycle.
- Source ranker hardening:
  - Blends route throughput and learning stats.
  - Ignores `manual-*` test tags in production ranking table.
- System health layer:
  - Added `/api/system-health` with freshness + control-state checks.
  - Dashboard now shows health checks and status pill reflects overall health.
- Broker reconciliation:
  - Added `sync_alpaca_order_status.py` and integrated into full run cycle.

## Validation
- `run-all-scans.sh` executes all stages including broker sync + learning feedback.
- `get_system_health()` reports coherent status.
- `route_outcomes` now contains operational-loss events from blocked test executions.

## Key Files
- `update_learning_feedback.py`
- `source_ranker.py`
- `sync_alpaca_order_status.py`
- `run-all-scans.sh`
- `dashboard-ui/data.py`
- `dashboard-ui/app.py`
- `dashboard-ui/static/index.html`
- `dashboard-ui/static/app.js`
- `dashboard-ui/static/styles.css`

## Additional Update (Later Same Session)
- Added dashboard action controls:
  - Run scan now
  - Sync broker now
  - Refresh learning now
- Added backend action launcher with log sink: `dashboard-ui/logs/actions.log`.
- Enhanced route outcome linkage logic to prioritize post-route nearest closed trades within a bounded 7-day window.
