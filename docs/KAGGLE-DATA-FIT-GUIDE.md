# Kaggle Data Fit Guide (Stocks + Crypto + Prediction)

Use Kaggle for **training and calibration**, not for live execution truth.

## What fits your system

1. `prediction markets` (highest value for your GRPO supervision)
- Must have a market `question` and a resolved `outcome`.
- Best if it includes `close/resolved time`.
- Your ingest expects resolved binary outcomes (yes/no/up/down/long/short equivalents).

2. `stocks OHLCV` (feature enrichment + regime learning)
- Must include timestamp/date + open/high/low/close (+ volume preferred).
- Works for feature engineering and non-live backfill.

3. `crypto OHLCV` (same as stocks, separate regime)
- Same schema as stocks.
- Useful for venue-specific threshold tuning.

## What to avoid

1. Datasets with no resolved label
- Good for exploration, not good for reward modeling.

2. Blog/sentiment dumps without event timestamps
- Hard to align with route outcomes.

3. Synthetic/demo datasets
- Can poison source weights and policy updates.

## Selection checklist (pass/fail)

1. Has event/market identity?
2. Has timestamp or resolution time?
3. Has resolved direction/label?
4. Data history long enough (>6 months preferred)?
5. License allows your usage?

If any of `1-3` fail, do not wire it into GRPO supervision.

## Integration rule for your stack

1. `pipeline_j_kaggle_polymarket.py` should only ingest resolved prediction rows into `polymarket_kaggle_markets`.
2. Stocks/crypto Kaggle data should be treated as auxiliary feature data unless labeled outcomes are available and aligned.
3. Keep Kaggle ingest gated daily; never let it run every cycle.

## Recommended operating mode

1. Start with one high-quality prediction dataset slug.
2. Run for 1-2 weeks in shadow mode (`grpo_apply_weight_updates=0`).
3. Promote only after realized outcome coverage and stability checks pass.
