# Free Training Stack Roadmap (Actionable)

## Objective
Use free/open-source tools + datasets to improve trade decision quality and train with resolved outcomes.

## Stack Priority (in order)
1. Internal truth data first (already live)
- `route_outcomes`, `route_feedback_features`, `polymarket_orders`, `execution_orders`
- This is highest-quality label source for your own strategy.

2. Polymarket historical dataset (Kaggle/API)
- Use to expand yes/no event coverage.
- Feed into `training/grpo/build_grpo_dataset.py --kaggle-file <path>`.

3. Daily free source ingest (already added)
- Pipeline I uses free feeds (Fed/BLS/EIA/SEC current filings) once daily.
- Adds event context for candidate generation and later labeling.

4. GRPO alignment loop (already added)
- Weekly HGRM scoring + optional weight update.
- Promote to active weight updates after realized sample threshold.

## Repos to Evaluate (Free/Open)
1. TradingAgents (multi-agent orchestration)
- Best use: debate/risk manager layer for pre-trade reasoning only.

2. FinGPT
- Best use: event/news parsing and finance-specific language priors.

3. Polymarket tool repos (MCP/alpha bots)
- Best use: market discovery + liquidity/correlation features.

4. Hyperliquid open bots
- Best use: orderbook/microstructure feature extraction.

## Integration Rule
New repos should feed signals/features into your existing DB + routing system.
Do not let third-party agents place live orders directly.

## Data/Training Cadence
- Daily: ingest + route + execution + outcome reconciliation
- Weekly: GRPO/HGRM alignment + dataset rebuild
- Monthly: heavier model fine-tune run + promote only if metrics improve

## Promotion Requirements
Before enabling policy influence:
1. >=100 realized outcomes
2. sample depth across venues/sources
3. no regression on drawdown/accuracy metrics

## Current Status
- Training-mode override controls: added
- Free-source daily ingestion cron: added
- GRPO dataset builder: added
- Weekly GRPO alignment job: added

## Kaggle Autopull (Safe Setup)
Use this only for **resolved prediction-market datasets**.

1. Install CLI for runtime Python:
- `/opt/homebrew/opt/python@3.11/bin/python3.11 -m pip install --user kaggle`

2. Add Kaggle API credentials:
- Place `kaggle.json` in `~/.kaggle/kaggle.json`
- Set file mode to `600`

3. Configure execution controls:
- `kaggle_auto_pull_enabled=1`
- `kaggle_poly_dataset_slug=<owner/dataset>`

4. Test once:
- `./scripts/run_kaggle_ingest.sh`

5. Verify rows:
- `sqlite3 data/trades.db "SELECT COUNT(*) FROM polymarket_kaggle_markets;"`

Notes:
- Ingestion is now strict and only accepts rows with a resolved binary outcome (`yes/no/up/down/long/short` equivalents) to prevent non-market dataset contamination.
- Default state is `kaggle_auto_pull_enabled=0` until a valid dataset slug is set.
