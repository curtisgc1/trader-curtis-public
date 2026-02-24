# Tooling Runtime Playbook

This is the canonical map of what tools exist, when to use them, and where to verify truth.

## Core Rule
- No narrative claims without DB or API proof.
- If tool output conflicts with DB state, DB state wins.

## Mandatory Runtime Handshake
Run these in order before readiness/execution claims:

1. `./scripts/check_tooling_context.sh`
2. `./scripts/check_agent_awareness.sh`
3. `./scripts/trade_claim_guard.sh`
4. `./scripts/polymarket_control.sh status`

## Tool Families

### 1) Signal Generation
- Orchestrator: `./run-all-scans.sh`
- Pipelines:
  - `pipeline_a_liquidity.py`
  - `pipeline_b_innovation.py`
  - `pipeline_c_event.py`
  - `pipeline_d_bookmarks.py`
  - `pipeline_e_breakthroughs.py`
  - `pipeline_f_finviz.py`
  - `pipeline_g_weather.py`
  - `pipeline_h_kyle_williams.py`
  - `pipeline_chart_liquidity.py`
  - `pipeline_polymarket.py`
- Truth table: `pipeline_signals`

### 2) Route + Risk Validation
- Router: `signal_router.py`
- Quant checks: `quant_gate.py`
- Controls: `execution_controls`
- Truth tables:
  - `signal_routes`
  - `quant_validations`

### 3) Execution
- Worker: `execution_worker.py`
- Adapters: `execution_adapters.py`, `execution_polymarket.py`
- Venue control path:
  - `./scripts/polymarket_control.sh`
- Truth tables:
  - `execution_orders`
  - `polymarket_orders`
  - `trade_intents`

### 4) Learning + Feedback
- Learner: `update_learning_feedback.py`
- Tuning proposals: `auto_tune_controls.py`
- Ranking: `source_ranker.py`
- Truth tables:
  - `route_trade_links`
  - `route_outcomes`
  - `route_feedback_features`
  - `input_feature_stats`
  - `source_learning_stats`
  - `strategy_learning_stats`
  - `execution_learning`

### 5) Awareness + Audit
- Awareness check: `./scripts/check_agent_awareness.sh`
- Tooling context check: `./scripts/check_tooling_context.sh`
- Full audit: `./scripts/full_pipeline_audit.sh`
- Dashboard APIs:
  - `/api/system-health`
  - `/api/signal-readiness`
  - `/api/agent-awareness`
  - `/api/trade-claim-guard`
  - `/api/memory-integrity`

## Claim Discipline
- "Trade executed" requires matching order row in `execution_orders` or `polymarket_orders`.
- "Pipeline ready" requires:
  - tooling context check = good
  - awareness check not bad
  - claim guard not bad
- "Learning improved" requires new or updated rows in:
  - `route_outcomes`
  - `input_feature_stats`

## Failure Mode Behavior
- If a required tool is missing, report missing tool explicitly and block readiness claims.
- If API keys are missing, run paper-only path and state the limitation.
- If DB is unavailable, do not route or execute; run only diagnostics.
