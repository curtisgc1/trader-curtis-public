# Trader Curtis Quant System

Event-driven multi-venue quant pipeline for:
- `stocks` (Alpaca paper/live-gated)
- `crypto` (Hyperliquid test/live-gated)
- `prediction markets` (Polymarket)

The system ingests many signal families (bookmarks, event feeds, breakthroughs, free data, tracked X handles), routes candidates through hard controls, executes only when allowed, and runs a separate learning/alignment loop.

## Core Architecture

1. Signal ingestion
- `pipeline_*.py` jobs write to `pipeline_signals`, `external_signals`, `copy_trades`, and related staging tables.

2. Candidate generation and routing
- `generate_trade_candidates.py` builds `trade_candidates`.
- `signal_router.py` applies policy/risk controls and writes `signal_routes`.

3. Execution
- `execution_worker.py` (stocks/crypto) and `execution_polymarket.py` (prediction markets).
- Execution is always control-gated via `execution_controls`.

4. Learning feedback
- `update_learning_feedback.py` refreshes `route_outcomes`, source/strategy stats, and feature stats.

5. GRPO/HGRM alignment lane (shadow-safe by default)
- `grpo_hgrm_weekly.py` computes hierarchical reward samples and optional weight updates.
- `training/grpo/build_grpo_dataset.py` creates `datasets/grpo_train.jsonl` and `datasets/grpo_eval.jsonl`.

## Main Entry Points

- Full cycle: `./run-all-scans.sh`
- Scheduled cycle wrapper: `./scripts/trader_cycle_locked.sh <mode>`
- Full audit: `./scripts/full_pipeline_audit.sh`
- Local stack check: `./scripts/check_local_grpo_stack.sh`
- Kaggle ingest (daily-gated): `./scripts/run_kaggle_ingest.sh`

## Safety Model

- `grpo_apply_weight_updates=0` is the default safe mode.
- Trading remains blocked unless venue-specific controls are enabled.
- Policy/alignment logic does not bypass execution guards.

## Kaggle Role

Kaggle is used to complement training/alignment data, not as live execution truth.

Current Kaggle ingest requirements:
1. `~/.kaggle/kaggle.json` present (API credentials)
2. `kaggle_poly_dataset_slug` set in `execution_controls`
3. Daily/min-hour limits respected by `scripts/run_kaggle_ingest.sh`

## Local Runtime Notes

- Mac hardware detected: Apple Silicon (M3 Ultra class)
- Ollama local model support is active (`qwen2.5:14b` available)
- MLX/MLX-LM runtime is installed for local training/inference workflows

## Quick Ops Commands

```bash
# Health/status
./scripts/check_local_grpo_stack.sh
./scripts/full_pipeline_audit.sh

# Force one Kaggle ingest attempt (for validation)
FORCE_KAGGLE_INGEST=1 ./scripts/run_kaggle_ingest.sh

# Rebuild GRPO datasets from local outcomes
./training/grpo/build_grpo_dataset.py --include-operational
./training/grpo/compare_sources.py --file datasets/grpo_train.jsonl
```

## Important Tables

- Live flow: `pipeline_signals`, `trade_candidates`, `signal_routes`, `execution_orders`, `polymarket_orders`
- Learning: `route_outcomes`, `source_learning_stats`, `strategy_learning_stats`, `input_feature_stats`
- Alignment: `alignment_reward_samples`, `alignment_policy_runs`
- Kaggle training data: `polymarket_kaggle_markets`
