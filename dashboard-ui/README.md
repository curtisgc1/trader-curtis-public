# Trader Curtis Dashboard (Local)

## Run
```bash
cd /Users/Shared/curtis/trader-curtis/dashboard-ui
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:8090

## Data Sources
- Trades + patterns: `/Users/Shared/curtis/trader-curtis/data/trades.db`
- X bookmarks: `/Users/Shared/curtis/trader-curtis/docs/x-bookmarks.json`

## Add external signal from X/link
```bash
cd /Users/Shared/curtis/trader-curtis
./add_external_signal.py \
  --source ZenomTrader \
  --url "https://x.com/ZenomTrader/status/2025198060536578298" \
  --ticker BTC \
  --direction long \
  --confidence 0.68 \
  --notes "Imported from external strategy link"
```

This populates `external_signals` in `data/trades.db` and appears in dashboard panels:
- `External Signals`
- `Top Candidates`

## Build Candidate Queue
```bash
cd /Users/Shared/curtis/trader-curtis
./generate_trade_candidates.py
```

This writes normalized candidates to `trade_candidates` and the dashboard will read from that table first.

## Route Candidates Through Risk Guard
```bash
cd /Users/Shared/curtis/trader-curtis
./signal_router.py --mode paper --limit 12 --notional 100
```

This writes `signal_routes` and `risk_events` tables and powers dashboard panels:
- `Risk Controls`
- `Signal Routes`

## Ingest X Bookmarks Into Thesis Queue (Pipeline D)
```bash
cd /Users/Shared/curtis/trader-curtis
./pipeline_d_bookmarks.py
```

This writes `bookmark_theses` and powers dashboard panel:
- `Bookmark Theses`

## Run Multi-Pipeline Stack
```bash
cd /Users/Shared/curtis/trader-curtis
./run-all-scans.sh
```

This now includes:
- Pipeline A: liquidity scalp signals
- Pipeline B: long-term innovation signals
- Pipeline C: event/geopolitical signals
- Pipeline D: bookmark thesis ingestion
- Execution worker (paper queue consumer)
- Source reliability scoring
- Structured event alerts mapped from playbooks
