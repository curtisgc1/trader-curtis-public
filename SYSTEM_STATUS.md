# TRADER CURTIS - SYSTEM STATUS (CANONICAL)
## Date: 2026-02-23

This file replaces prior legacy status text.

## Runtime Truth

- Canonical execution model is **control-gated by DB** (`execution_controls`).
- Polymarket execution path is:
  1. `pipeline_polymarket.py` creates `polymarket_candidates` (ideas)
  2. `execution_polymarket.py` enforces controls and writes `polymarket_orders` (execution events)
  3. Dashboard `/polymarket` renders truth-labeled state (`REAL` vs `PAPER`)
- A candidate is **not** a trade.
- A trade claim is valid only with matching `polymarket_orders` rows.

## Forbidden Claims (Do Not Say)

- "I made trades" without an order event in DB.
- "After N approvals it auto-trades" unless that exact logic exists in controls/code.
- "Next scan at X" unless a real cron/schedule is confirmed.
- "Say execute and I'll trade" as a generic flow.

## Required Control Surface

Always use:

```bash
./scripts/polymarket_control.sh status
./scripts/polymarket_control.sh set-max <per_trade_usd> <daily_usd>
./scripts/polymarket_control.sh go-live <per_trade_usd> <daily_usd> <manual_approval:0|1> <min_edge_pct>
./scripts/polymarket_control.sh run
./scripts/polymarket_control.sh approve <candidate_id...>
```

## Verification Commands

```bash
./scripts/check_agent_awareness.sh
./scripts/check_polymarket_setup.sh
sqlite3 data/trades.db "select id,mode,status,notional from polymarket_orders order by id desc limit 20;"
```

## Notes

- Confidence scores are signal metadata, not execution authority.
- Execution authority comes from DB controls + passing risk gates + valid venue credentials.
