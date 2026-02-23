# Auto Trade Protocol (Autonomous Test Mode)

Updated: 2026-02-23

## Goal
Run autonomous high-throughput testing of the trading pipeline with minimal human interaction.
Primary objective is system validation, data collection, and learning feedback quality.

## Execution Model
- Routing: automatic via `signal_router.py`
- Execution: automatic via `execution_worker.py`
- Learning refresh: automatic via `update_learning_feedback.py` + `source_ranker.py`
- Dashboard control surface: `http://127.0.0.1:8090/`

## Current Constraints
- Hyperliquid minimum order applies (BTC perps require roughly >= $10 order value)
- Polymarket live posting requires `POLY_PRIVATE_KEY` (if missing, worker falls back to paper mode)
- Use `./scripts/check_agent_awareness.sh` before claiming full venue readiness

## Operator Controls (DB: `execution_controls`)
Core:
- `allow_live_trading`
- `enable_alpaca_paper_auto`
- `enable_hyperliquid_test_auto`
- `allow_hyperliquid_live`
- `enable_polymarket_auto`
- `allow_polymarket_live`

Throughput:
- `auto_route_limit` (routes per cycle)
- `auto_route_notional` (default per-route sizing)
- `max_open_positions`
- `max_daily_new_notional_usd`
- `max_signal_notional_usd`
- `min_candidate_score`

Risk/strictness:
- `quant_gate_enforce` (`1` block on quant fail, `0` warn-only)

Leverage display/control:
- `hyperliquid_test_leverage`
- dashboard shows leverage-capability for HL/Alpaca

## Autonomous Behavior Rules
- If controls allow execution, trader executes without confirmation.
- If `quant_gate_enforce=0`, quant failures are logged as warnings and routing continues.
- Every cycle must update tables used by learning (`route_trade_links`, `route_outcomes`, `source_learning_stats`, `strategy_learning_stats`).

## Non-Interactive Commands
- Full cycle:
  - `./run-all-scans.sh`
- Signal-only validation (no execution calls):
  - `./scripts/run_signal_validation.sh`
- Dashboard restart:
  - `./scripts/restart_dashboard.sh`

## Ingest Commands (Agent -> DB)
- External signal:
  - `python3 agent_signal_ingest.py --text "external signal source ZenomTrader ticker NVDA short conf 0.74 url https://x.com/... notes gap fade"`
- Copy trade call:
  - `python3 agent_signal_ingest.py --text "copy trade @NoLimitGains long TSLA entry 210 stop 199 target 240 notes momentum"`

## Acceptance Checks
- `/api/system-health` responds and stays fresh
- `/api/signal-readiness` shows active candidate/routing flow
- dashboard `Execution Orders` shows leverage columns
- no schema drift errors in run logs
