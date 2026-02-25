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
- GRPO readiness gate: `./scripts/grpo_readiness_gate.sh`
- Kaggle ingest (daily-gated): `./scripts/run_kaggle_ingest.sh`
  - isolated daily job (separate from OpenClaw trading cycle)
- MLX training (daily-gated): `./scripts/run_mlx_grpo_train.sh`
  - isolated daily job, intentionally decoupled from `run-all-scans.sh` / OpenClaw execution path
- Learning heavy resolver pass (daily-gated): `./scripts/run_learning_feedback_daily.sh`
  - runs missed-opportunity + multi-horizon counterfactual evaluation in isolated daily lane
- Realized close/settle reconciler (daily-gated): `./scripts/run_realized_reconciler.sh`
  - runs Alpaca sync + Polymarket settlement reconciliation + realized feedback refresh

## Safety Model

- `grpo_apply_weight_updates=0` is the default safe mode.
- Trading remains blocked unless venue-specific controls are enabled.
- Policy/alignment logic does not bypass execution guards.
- Realized outcome truth is isolated: use `route_outcomes` with `outcome_type='realized'`.
- Counterfactual/multi-horizon outcomes are stored separately in `route_outcomes_horizons`.

## Input Weighting + Overrides

Candidate scoring is assembled in `generate_trade_candidates.py` with this effective pattern:

- family contribution:
  - `base_component * family_weight`
- source/pipeline/pattern contribution:
  - `base_component * family_weight * specific_key_weight`
- strategy-aware family contribution:
  - `base_component * family_weight * strategy_family_weight`
- X handle contribution:
  - `0.05 * weight_for('x:<handle>') * tracked_x_sources.source_weight`

All of these weights are in `input_source_controls`:

- global family keys: `family:social`, `family:pattern`, `family:external`, `family:copy`, `family:pipeline`, `family:liquidity`
- source keys: `source:<source_tag>`
- pipeline keys: `pipeline:<PIPELINE_ID>`
- X keys: `x:<handle>`
- strategy family keys: `strategy:<PIPELINE_ID>:family:<family>`

Example DB overrides:

```sql
-- Heavier liquidity for scalp profile, moderate for long-term.
UPDATE input_source_controls SET manual_weight=1.35 WHERE source_key='family:liquidity';
UPDATE input_source_controls SET manual_weight=2.40 WHERE source_key='strategy:CHART_LIQUIDITY:family:liquidity';
UPDATE input_source_controls SET manual_weight=1.15 WHERE source_key='strategy:B_LONGTERM:family:liquidity';
```

## Ticker-Specific Routing Profiles

Ticker-level route controls are in `ticker_trade_profiles` and enforced in `signal_router.py` before route approval.

Main fields:
- `ticker` (e.g., `BTC`)
- `preferred_venue` (`stocks` | `crypto` | `prediction` | empty)
- `allowed_venues_json` (list)
- `required_inputs_json` (list of candidate input keys, e.g. `family:liquidity`)
- `min_score`
- `notional_override`

Example profile for BTC scalp routing on HL:

```sql
INSERT INTO ticker_trade_profiles
(created_at, updated_at, ticker, active, preferred_venue, allowed_venues_json, required_inputs_json, min_score, notional_override, notes)
VALUES
(datetime('now'), datetime('now'), 'BTC', 1, 'crypto', '["crypto"]', '["family:liquidity","family:pipeline"]', 60, 10, 'BTC scalp profile')
ON CONFLICT(ticker) DO UPDATE SET
  updated_at=excluded.updated_at,
  active=excluded.active,
  preferred_venue=excluded.preferred_venue,
  allowed_venues_json=excluded.allowed_venues_json,
  required_inputs_json=excluded.required_inputs_json,
  min_score=excluded.min_score,
  notional_override=excluded.notional_override,
  notes=excluded.notes;
```

## Outcome Truth + Timeframes

- Source of truth for realized performance: closed/finalized trades linked into `route_outcomes` (`outcome_type='realized'`).
- Operational quality lane (fills/blocks/missed proxies): `route_outcomes` (`outcome_type='operational'`).
- Multi-timeframe counterfactual lane (scalp/1d/1w/1m+): `route_outcomes_horizons`.
- Learning stats by timeframe/source: `source_horizon_learning_stats`.
- Runtime guardrails for resolver jobs are control-driven via:
  - `learning_resolver_http_timeout_seconds`
  - `mtm_resolver_max_runtime_seconds`
  - `missed_opportunity_max_runtime_seconds`
  - `horizon_resolver_max_runtime_seconds`

## Kaggle Role

Kaggle is used to complement training/alignment data, not as live execution truth.

Current Kaggle ingest requirements:
1. Kaggle auth via either:
   - `~/.kaggle/kaggle.json`, or
   - `KAGGLE_API_TOKEN` (env or keychain service `kaggle_api_token`)
2. `kaggle_poly_dataset_slug` set in `execution_controls`
3. Daily/min-hour limits respected by `scripts/run_kaggle_ingest.sh`

MLX training requirements:
1. `grpo_mlx_train_enabled=1` in `execution_controls`
2. `mlx` + `mlx_lm` installed for Python runtime
3. Base model set in `grpo_mlx_base_model` (default: `mlx-community/Qwen2.5-7B-Instruct-4bit`)
4. Daily/min-hour limits respected by `scripts/run_mlx_grpo_train.sh`

## Local Runtime Notes

- Mac hardware detected: Apple Silicon (M3 Ultra class)
- Ollama local model support is active (`qwen2.5:14b` available)
- MLX/MLX-LM runtime is installed for local training/inference workflows

## Quick Ops Commands

```bash
# Health/status
./scripts/check_local_grpo_stack.sh
./scripts/full_pipeline_audit.sh
./scripts/grpo_readiness_gate.sh

# Force one Kaggle ingest attempt (for validation)
FORCE_KAGGLE_INGEST=1 ./scripts/run_kaggle_ingest.sh

# Rebuild GRPO datasets from local outcomes
./training/grpo/build_grpo_dataset.py --include-operational
./training/grpo/compare_sources.py --file datasets/grpo_train.jsonl
./training/grpo/build_mlx_lora_dataset.py

# Force one MLX train attempt (bypass daily/hourly gate)
FORCE_MLX_GRPO_TRAIN=1 ./scripts/run_mlx_grpo_train.sh
```

## Important Tables

- Live flow: `pipeline_signals`, `trade_candidates`, `signal_routes`, `execution_orders`, `polymarket_orders`
- Learning: `route_outcomes`, `source_learning_stats`, `strategy_learning_stats`, `input_feature_stats`
- Alignment: `alignment_reward_samples`, `alignment_policy_runs`
- Kaggle training data: `polymarket_kaggle_markets`
