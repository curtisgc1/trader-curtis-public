# GRPO Training Stack (Trader Curtis)

## Goal
Train/alignment loop using resolved outcomes:
1. ingest data (Polymarket + internal outcomes + market data)
2. build prompt/reward groups
3. run GRPO training locally (MLX) or Colab (Unsloth)
4. validate and feed back to route/input weights

## Data Inputs
- Internal: `data/trades.db` tables (`route_outcomes`, `route_feedback_features`, `polymarket_candidates`, `polymarket_orders`)
- External: Polymarket Kaggle export CSV/JSON (optional)
- Optional: Hyperliquid snapshots + stock market context
- Current Kaggle baseline slug: `dhruvgup/polymarket-closed-2025-markets-7-day-price-history`

## Outcome Truth Policy
- Ground truth for model promotion/live-weight updates: `route_outcomes` where `outcome_type='realized'`.
- Fast feedback/proxy labels: `route_outcomes` where `outcome_type='operational'`.
- Multi-timeframe counterfactual scoring (scalp/week/month/quarter): `route_outcomes_horizons`.

## Scripts
- `training/grpo/build_grpo_dataset.py`
  - Builds grouped training dataset from internal + optional external files.
- `training/grpo/build_mlx_lora_dataset.py`
  - Converts GRPO artifacts into MLX LoRA format (`prompt/completion` JSONL).
- `scripts/run_grpo_alignment.sh`
  - Runs weekly HGRM alignment in shadow/live-weight-update mode.
- `scripts/run_mlx_grpo_train.sh`
  - Daily-gated MLX LoRA trainer (enabled via `execution_controls`).
  - Runs as isolated background workload (separate from OpenClaw trading cycle).
- `scripts/grpo_readiness_gate.sh`
  - Enforces readiness thresholds before enabling live GRPO weight updates.

## Output Artifacts
- `datasets/grpo_train.jsonl`
- `datasets/grpo_eval.jsonl`
- `datasets/grpo_summary.json`
- `datasets/mlx_grpo_lora/train.jsonl`
- `datasets/mlx_grpo_lora/valid.jsonl`
- `datasets/mlx_grpo_lora/test.jsonl`
- `datasets/mlx_grpo_lora/summary.json`

## Recommended Cadence
- Daily: collect data + outcomes.
- Daily: Kaggle ingest + optional MLX LoRA train pass (24h gated).
- Weekly: alignment pass and policy review.
- Monthly: heavy model fine-tune run and promotion check.

## MLX Enablement Controls
- `grpo_mlx_train_enabled=1`
- `grpo_mlx_base_model=mlx-community/Qwen2.5-7B-Instruct-4bit`
- `grpo_mlx_min_hours_between_runs=24`
- `grpo_mlx_daily_train_limit=1`
- `grpo_mlx_min_train_rows=40`

Runtime keys:
- `runtime:grpo_mlx_last_train_utc`
- `runtime:grpo_mlx_last_status`
- `runtime:grpo_mlx_last_model`
