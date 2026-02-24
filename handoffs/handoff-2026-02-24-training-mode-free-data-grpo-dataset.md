# Handoff — 2026-02-24 — Training Mode + Free Data + GRPO Dataset

## Added
1. Training-mode override layer
- New file: `training_mode.py`
- Applies `training_*` control values when `training_mode_enabled=1`
- Keeps production thresholds intact (no destructive overwrite)

Integrated in:
- `execution_guard.py`
- `execution_worker.py`
- `execution_polymarket.py`
- `generate_trade_candidates.py`

2. Dashboard/API control allowlist extended
- `dashboard-ui/data.py` now accepts training keys:
  - `training_mode_enabled`
  - `training_min_candidate_score`
  - `training_consensus_min_confirmations`
  - `training_consensus_min_ratio`
  - `training_consensus_min_score`
  - `training_alpaca_min_route_score`
  - `training_hyperliquid_min_route_score`
  - `training_polymarket_min_confidence_pct`
  - `training_max_signal_notional_usd`
  - `training_max_daily_new_notional_usd`
  - `training_hyperliquid_test_notional_usd`
  - `training_polymarket_max_notional_usd`
  - `training_polymarket_max_daily_exposure`

3. New daily free-source ingest pipeline
- `pipeline_i_free_sources.py`
- Feed list: `docs/FREE-DATA-SOURCES.json`
- Inserts to `free_feed_items` and `external_signals`
- Cron added:
  - `trader-curtis-daily-free-source-ingest`
  - id: `720f779b-e7dd-4d2a-b1cf-39675df5f989`
  - schedule: `35 4 * * *` PT

4. GRPO dataset builder scaffold
- `training/grpo/build_grpo_dataset.py`
- outputs:
  - `datasets/grpo_train.jsonl`
  - `datasets/grpo_eval.jsonl`
  - `datasets/grpo_summary.json`
- Supports optional Kaggle file import: `--kaggle-file <csv/jsonl>`

5. Docs
- `training/grpo/README.md`
- `docs/FREE-TRAINING-STACK-ROADMAP.md`
- `docs/JANUSQ-HGRM-GRPO-IMPLEMENTATION-BLUEPRINT.md`
- `docs/TRADING-SYSTEM-EXPLAINED-LIKE-I-AM-14.md`

## Validation
- Python compile checks passed for modified/new files.
- `build_grpo_dataset.py` run:
  - realized only: 0 rows
  - including operational: 60 rows
- Free-source ingest currently inserted few unique items (dedupe working).

## Key Risk/Gap
- Realized outcomes are still near-zero; GRPO training quality is limited.
- Need stronger outcome reconciliation to convert more routes into realized labels.

## Source Flag Compare (internal vs kaggle)
- Build with both (default includes internal + kaggle table):
  - `./training/grpo/build_grpo_dataset.py --include-operational`
- Compare source composition:
  - `./training/grpo/compare_sources.py --file datasets/grpo_train.jsonl`
- Exclude internal for pure external experiments:
  - `./training/grpo/build_grpo_dataset.py --no-internal`
- Exclude kaggle table for internal-only experiments:
  - `./training/grpo/build_grpo_dataset.py --no-kaggle-table --include-operational`
