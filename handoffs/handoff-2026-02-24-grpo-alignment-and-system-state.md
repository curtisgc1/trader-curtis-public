# Handoff — 2026-02-24 — GRPO Alignment + System State

## Objective
Continue building a cohesive multi-venue trading system (Alpaca paper + Hyperliquid + Polymarket) with:
- weighted multi-input decisioning,
- execution truthing,
- learning loop,
- low-token scheduled operation,
- optional local model alignment (GRPO-style) on real outcomes.

## What Is Built (Current State)
1. Core integrated trading cycle is active via `scripts/openclaw_trader_cycle.sh` -> `run-all-scans.sh`.
2. Input Weight Engine is implemented across all inputs (not just X):
- table: `input_source_controls`
- weights applied in `generate_trade_candidates.py`
- automatic reweighting in `reweight_input_sources.py`
3. Trade reasoning visibility added:
- candidate rationale + input breakdown surfaced into route reason + dashboard.
4. Missed opportunity tracking summary exists in Mission Control:
- API: `/api/master-overview` and `/api/missed-opportunities`.
5. Daily clutter cleanup exists in `maintain_tables.py`.
6. Cron/token optimization completed:
- kept integrated core scans and EOD
- disabled noisy redundant 4h and 2pm swarms.

## New Work Added This Session
### A) GRPO/HGRM alignment layer (shadow-safe)
Added `grpo_hgrm_weekly.py`:
- Builds `alignment_reward_samples` from realized route outcomes (`route_outcomes` + `route_feedback_features`).
- Uses hierarchical gated reward structure:
  - direction gate,
  - magnitude consistency,
  - pnl shaping.
- Writes run log to `alignment_policy_runs`.
- Can update `input_source_controls.auto_weight` with smoothing if enabled.
- Optional local Ollama policy-summary note.

Added runner script:
- `scripts/run_grpo_alignment.sh`

### B) Weekly alignment cron
Added cron job:
- name: `trader-curtis-weekly-grpo-alignment`
- id: `8b7c5763-79e2-40f8-b85d-65ca6e76c146`
- schedule: `20 3 * * 1` America/Los_Angeles
- purpose: run alignment weekly, report summary, no trading.

### C) Dashboard backend control allowlist updated
`dashboard-ui/data.py` `set_execution_controls` now accepts:
- `grpo_alignment_enabled`
- `grpo_alignment_lookback_days`
- `grpo_alignment_min_samples`
- `grpo_alignment_weight_floor`
- `grpo_alignment_weight_ceiling`
- `grpo_apply_weight_updates`
- `grpo_llm_reasoner_enabled`
- `grpo_local_model`

Seeded execution controls defaults:
- `grpo_alignment_enabled=1`
- `grpo_alignment_lookback_days=30`
- `grpo_alignment_min_samples=8`
- `grpo_alignment_weight_floor=0.6`
- `grpo_alignment_weight_ceiling=1.6`
- `grpo_apply_weight_updates=0` (shadow mode default)
- `grpo_llm_reasoner_enabled=1`
- `grpo_local_model=qwen2.5:14b`

## Runtime Notes / Constraints
1. GRPO alignment currently runs and records even when no enough samples; no execution side effects.
2. `grpo_apply_weight_updates` is OFF by default for safety.
3. Ollama model pull `qwen2.5:14b` was started and may still be downloading.
4. No direct trade logic was replaced by RL; risk gates still authoritative.

## What Next Dev Should Do Next
1. Confirm `qwen2.5:14b` download complete (`ollama list`).
2. Add UI fields on dashboard controls panel for GRPO keys (backend allowlist already done).
3. Add a simple GRPO status card:
- last run,
- sample count,
- updated inputs count,
- top/bottom reward sources.
4. Once enough resolved sample size is present, consider enabling:
- `grpo_apply_weight_updates=1`
5. Keep hard risk/execution gates unchanged; GRPO remains alignment/reweight layer.

## Validation Done
- Python compile checks passed for:
  - `grpo_hgrm_weekly.py`
  - `dashboard-ui/data.py`
- Manual run of GRPO script succeeded:
  - `GRPO_HGRM samples=0 inputs=0 applied=0 ...`
- Cron job creation confirmed in list.

## Key Files
- `grpo_hgrm_weekly.py`
- `scripts/run_grpo_alignment.sh`
- `dashboard-ui/data.py`
- `run-all-scans.sh`
- `scripts/openclaw_trader_cycle.sh`
- `handoffs/handoff-2026-02-24-grpo-alignment-and-system-state.md`
