# Janus-Q HGRM + GRPO Implementation Blueprint (For Current Trader Build)

## Bottom Line
Yes, this is complementary to your system.
Do not replace your live router/execution logic.
Add this as a policy-alignment layer that learns from real outcomes and gradually updates input weights/policy.

## What Janus-Q Adds That Matters
1. Event-centric supervision (not just price action)
2. Hierarchical reward design:
- hard direction gate first
- then event consistency + pnl + magnitude shaping
3. GRPO training:
- multiple candidate responses per input
- relative ranking inside each group
- optimize toward better-ranked decisions

## Mapping Janus-Q -> Your Existing Components
1. Janus "event sample"
- Your equivalent: route + candidate + pipeline context + external signals
- Tables: `route_feedback_features`, `trade_candidates`, `pipeline_signals`, `external_signals`

2. Janus "CAR / realized market reaction"
- Your equivalent now: realized outcome from `route_outcomes` + trade fills/price deltas
- Note: currently mostly operational outcomes; need more realized outcomes

3. Janus HGRM reward
- Your equivalent now: `grpo_hgrm_weekly.py` builds reward samples with:
  - direction gate
  - magnitude consistency
  - pnl shaping
- Table: `alignment_reward_samples`

4. Janus policy optimization via GRPO
- Your equivalent path:
  - `MLX-GRPO` trainer in isolated local train loop
  - feed training pairs/groups from your reward samples
  - produce updated policy artifacts or weight recommendations

## Correct Implementation Phases
### Phase 1 (Now): Shadow Alignment Only
- Keep trading engine unchanged.
- Run weekly HGRM scoring.
- Track source/pipeline reward means.
- `grpo_apply_weight_updates=0` (OFF)

Exit criteria:
- >= 100 realized route outcomes
- >= 8 samples for at least 10 sources/strategies

### Phase 2: Controlled Weight Updates
- Enable smoothed updates to `input_source_controls.auto_weight`.
- Keep hard risk/router gates unchanged.
- Daily scans use updated weights, but execution still guarded.

Safety:
- clamp weights to `[0.6, 1.6]`
- EMA blending (e.g., 70% old / 30% new)

### Phase 3: True GRPO Fine-Tuning Track
- Build grouped training dataset from real outcomes:
  - per event/context: generate N decisions/reasonings
  - compute HGRM reward per completion
  - rank within group
- Train local model with MLX-GRPO in isolated job.
- Export weekly policy memo and optional policy-suggestion file.

### Phase 4: Policy-Assisted Routing (Optional)
- Use trained policy as advisory score only at first.
- Require router consensus + risk controls to pass before execution.

## Data Sufficiency (Current)
Current blocker is realized outcomes density.
You need consistent true realized outcomes (not operational placeholders) to make GRPO meaningful.

Recommended minimums before live policy influence:
1. 100-300 realized outcomes total
2. 20+ per main venue (alpaca/hyperliquid/polymarket)
3. 8-10+ samples per active source key

## Schedule Recommendation
1. Daily:
- run integrated trading cycle
- reconcile executions and outcomes
- update learning stats

2. Weekly (Monday early AM):
- run HGRM/GRPO alignment
- produce top/bottom source and strategy report

3. Monthly:
- run heavier GRPO fine-tuning cycle (longer training)
- promote only if validation improves

## Validation Rules Before Promotion
Any GRPO/policy update must beat baseline on:
1. Direction accuracy
2. Reward stability (lower variance)
3. Drawdown control proxy
4. No degradation in high-confidence trade cohorts

If not better, keep old policy/weights.

## Practical Notes on MLX-GRPO in Your Environment
1. GRPO is method, not model.
2. Use existing local MLX model cache first (no extra large downloads).
3. Keep training isolated from live runtime.
4. Never let training scripts submit orders.

## Immediate Next Steps
1. Increase true realized outcome capture quality.
2. Add dashboard card:
- HGRM samples
- realized-only sample count
- top/bottom reward sources
- last policy run
3. After sample threshold, enable `grpo_apply_weight_updates=1`.

This keeps your system fast, safe, and actually self-improving.
