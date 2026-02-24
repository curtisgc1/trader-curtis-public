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

## Scripts
- `training/grpo/build_grpo_dataset.py`
  - Builds grouped training dataset from internal + optional external files.
- `scripts/run_grpo_alignment.sh`
  - Runs weekly HGRM alignment in shadow/live-weight-update mode.

## Output Artifacts
- `datasets/grpo_train.jsonl`
- `datasets/grpo_eval.jsonl`
- `datasets/grpo_summary.json`

## Recommended Cadence
- Daily: collect data + outcomes.
- Weekly: build dataset + alignment.
- Monthly: heavy model fine-tune run and promotion check.
