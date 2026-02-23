# Agent Signal Commands (DB Ingest)

Use these from Trader Curtis so commands directly update DB tables used by dashboard and routing.

## Copy Trade Ingest (`copy_trades`)

```bash
python3 /Users/Shared/curtis/trader-curtis/agent_signal_ingest.py --text "copy trade @NoLimitGains long TSLA entry 210 stop 199 target 240 notes fast momentum"
```

Direct version:

```bash
python3 /Users/Shared/curtis/trader-curtis/add_copy_trade_signal.py \
  --source NoLimitGains \
  --ticker TSLA \
  --direction long \
  --entry 210 \
  --stop 199 \
  --target 240 \
  --status OPEN \
  --notes "fast momentum"
```

## External Signal Ingest (`external_signals`)

```bash
python3 /Users/Shared/curtis/trader-curtis/agent_signal_ingest.py --text "external signal source ZenomTrader ticker NVDA short conf 0.74 url https://x.com/... notes gap fade"
```

Direct version:

```bash
python3 /Users/Shared/curtis/trader-curtis/add_external_signal.py \
  --source ZenomTrader \
  --url "https://x.com/..." \
  --ticker NVDA \
  --direction short \
  --confidence 0.74 \
  --notes "gap fade"
```

## Validation

```bash
sqlite3 /Users/Shared/curtis/trader-curtis/data/trades.db "select id,source,ticker,direction,confidence from external_signals order by id desc limit 5;"
sqlite3 /Users/Shared/curtis/trader-curtis/data/trades.db "select id,source_handle,ticker,call_type,status from copy_trades order by id desc limit 5;"
```

## Dashboard Pages

- Main: `http://127.0.0.1:8090/`
- Signals: `http://127.0.0.1:8090/signals`
- Polymarket: `http://127.0.0.1:8090/polymarket`
- Learning: `http://127.0.0.1:8090/learning`

## Polymarket Triggers (Operator + Agent)

Use one command path so behavior is deterministic:

```bash
cd /Users/Shared/curtis/trader-curtis
```

Check state:

```bash
./scripts/polymarket_control.sh status
```

Set pre-trade caps:

```bash
./scripts/polymarket_control.sh set-max 5 20
# first arg = max per trade USD
# second arg = max daily USD (optional)
```

Go live:

```bash
./scripts/polymarket_control.sh go-live 5 20 0
# args: per-trade, daily, manual_approval(0/1)
```

Run one cycle now:

```bash
./scripts/polymarket_control.sh run
```

Approve specific candidates:

```bash
./scripts/polymarket_control.sh approve 3041 3042
```

Return to paper-safe mode:

```bash
./scripts/polymarket_control.sh paper-safe 5 20
```

### Truth Rules

- `polymarket_candidates` are ideas, not executions.
- Only rows in `polymarket_orders` represent execution attempts/results.
- `mode=live` + statuses like `submitted_live`/`filled_live` mean real-money path.
- `mode=paper` means simulation only.
