# QUICK REFERENCE (CURRENT)

## 1) One-Liner Truth

- `polymarket_candidates` = ideas
- `polymarket_orders` = execution truth
- no order event = no trade

## 2) Pre-Trade Controls

```bash
cd /Users/Shared/curtis/trader-curtis
./scripts/polymarket_control.sh status
./scripts/polymarket_control.sh set-max 3 15
./scripts/polymarket_control.sh set-edge 5.0
```

## 3) Live / Paper Mode

```bash
# live
./scripts/polymarket_control.sh go-live 3 15 0 5.0

# paper-safe
./scripts/polymarket_control.sh paper-safe 3 15
```

## 4) Execute and Verify

```bash
./scripts/polymarket_control.sh run
sqlite3 data/trades.db "select id,created_at,mode,status,notional from polymarket_orders order by id desc limit 10;"
```

## 5) Dashboard

- Main: `http://127.0.0.1:8090/`
- Polymarket: `http://127.0.0.1:8090/polymarket`
- Signals: `http://127.0.0.1:8090/signals`
- Learning: `http://127.0.0.1:8090/learning`

## 6) Do Not Say

- "I executed" unless there is an order row.
- "80% confidence means trade" (not true).
- "after 5 approvals auto-trade" unless controls/code match.
- "next scan at X" unless schedule is confirmed.
