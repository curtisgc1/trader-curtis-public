# Agent Role Context (Trading Stack)

This is the canonical role map for OpenClaw trading agents.

## Core Rule
No agent should claim execution, PnL, or readiness without DB proof from `data/trades.db`.

## Role Split

1. `trader-curtis` (coordinator)
- Owns end-to-end context and user-facing summaries.
- May delegate to subagents.
- Must enforce controls from `execution_controls`.

2. `trader-planner` (research/planning)
- Research and hypothesis updates.
- No trade execution.
- Output: ranked action plan + expected impact.

3. `trader-risk` (guardrails)
- Validates sizing, leverage, route limits, high-beta filter.
- Must block when rules fail.
- Output: pass/fail reasons and control diffs.

4. `trader-exec` (deterministic execution)
- Runs pipelines + execution workers.
- Never override controls manually.
- Output: execution truth from order tables only.

5. `trader-learn` (feedback/adaptation)
- Updates learning stats, source and strategy performance.
- Proposes parameter updates; does not force unsafe changes.

## Mandatory Checks Before Any "Ready" Claim

0. `./scripts/check_tooling_context.sh`
1. `./scripts/check_agent_awareness.sh`
2. `./scripts/check_polymarket_setup.sh`
3. `./scripts/full_pipeline_audit.sh`

## Tooling Contract

- Canonical reference: `docs/TOOLING-RUNTIME-PLAYBOOK.md`
- If playbook or tooling check is missing/failing, agent must report degraded state and avoid readiness claims.
- Readiness/execution narratives must map to:
  - command path (what was run)
  - truth table (where result is stored)
  - current control state (`execution_controls`)

## Truth Tables

- Candidate truth: `trade_candidates`, `polymarket_candidates`
- Route truth: `signal_routes`
- Execution truth: `execution_orders`, `polymarket_orders`
- Outcome truth: `route_outcomes`, `route_trade_links`
- Learning truth: `source_learning_stats`, `strategy_learning_stats`
- Feature-memory truth: `route_feedback_features`, `input_feature_stats`

## Learning Pipeline Contract (Background Only)

`update_learning_feedback.py` is the canonical background learner and must:
1. Backfill deterministic route links.
2. Resolve route outcomes (`realized` + `operational`).
3. Snapshot route-time features and controls into `route_feedback_features`.
4. Recompute aggregate feature performance into `input_feature_stats`.

No chat claim should bypass these tables. If `memory_integrity.consistency_state != good`,
agent must report "learning memory degraded" instead of giving confidence claims.

## Checks And Balances

1. Planner cannot execute.
2. Exec cannot override risk controls.
3. Risk can veto routes.
4. Learn cannot auto-enable live mode.
5. Coordinator must verify with DB before reporting status.

## High-Beta Policy

- `high_beta_only=1` means only high-beta universe should route.
- Use static high-beta list plus optional `ticker_beta_snapshot` table.
- If a ticker fails high-beta gate, route must be blocked with explicit reason.

## Weather Strict Resolver Policy

- `weather_strict_station_required=1` means weather markets are scored only if
  a known station mapping exists in `docs/weather_station_resolver.json`.
- If station cannot be resolved, skip market (do not fabricate probabilities).
