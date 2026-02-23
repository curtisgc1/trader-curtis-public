# Trader-Curtis Build Plan (Execution-Valid)

Date: 2026-02-22
Owner: Curtis + ORION

## Objective
Turn the existing multi-pipeline stack into a measurable paper-trading system where each stage is auditable and promotion to live mode is gated by objective criteria.

## Current Baseline (Validated Against Code)

Implemented now:
- Pipeline A: `pipeline_a_liquidity.py` (pattern + sentiment weighted confidence)
- Pipeline B: `pipeline_b_innovation.py` (watchlist-driven long-term signals)
- Pipeline C: `pipeline_c_event.py` + `event_alert_engine.py` (event alerts -> signals)
- Pipeline D: `pipeline_d_bookmarks.py` (bookmark thesis ingestion)
- Candidate builder: `generate_trade_candidates.py`
- Risk guard/router: `execution_guard.py` + `signal_router.py`
- Paper queue worker: `execution_worker.py`
- Source scoring: `source_ranker.py`
- Observability UI: `dashboard-ui/`
- End-to-end runner: `run-all-scans.sh`

Partial / weak spots:
- No strong dedupe/idempotency contract across repeated scans.
- Source reliability uses approval/execution only, not realized outcomes.
- No hard data quality dashboard for stale feeds, null fields, schema drift.
- No formal go/no-go live readiness gate.

## Non-Negotiable Controls

- Paper-only default. `allow_live_trading` remains off by default.
- Every executed route must have: source, rationale, confidence, risk decision.
- Any manual override requires a logged reason (table + dashboard visibility).
- Daily loss and weekly drawdown thresholds must block routing, not just warn.

## Build Sequence (Best-Practice Order)

### Phase 0 - Environment and Schema Lock (same day)
Deliverables:
- `docs/pipeline-contracts.md` with required columns, TTL, and status transitions.
- `docs/env-contract.md` listing required env vars and default-safe values.
- DB migration script for missing indices/constraints in `data/trades.db`.

Acceptance:
- `run-all-scans.sh` finishes with no table-not-found errors on clean DB.
- Re-running the full stack does not create uncontrolled duplicate active signals.

### Phase 1 - Signal Integrity and Traceability (1-2 days)
Deliverables:
- Add deterministic `signal_key`/fingerprint to all pipeline outputs.
- Enforce upsert semantics for active signals by key + freshness window.
- Add `pipeline_runs` table (start/end time, row counts, failures, warnings).

Acceptance:
- Two back-to-back runs produce stable active signal counts (within expected TTL behavior).
- Every trade candidate links back to at least one upstream signal key.

### Phase 2 - Risk and Execution Hardening (1-2 days)
Deliverables:
- Extend `execution_guard.py` with explicit:
  - daily max loss
  - weekly drawdown
  - max open positions
  - max exposure per symbol/theme
- Add kill-switch status propagated to `signal_routes` and dashboard.
- Add execution retry policy with bounded attempts for paper/live adapters.

Acceptance:
- Guard rejects candidates when limits are crossed and writes reason codes.
- Worker never leaves queued routes in ambiguous state after processing pass.

### Phase 3 - Source Ranking That Reflects PnL (2-3 days)
Deliverables:
- Extend `source_ranker.py` to blend:
  - approval rate
  - execution conversion
  - realized expectancy by source (`R` or % return)
  - recency decay
- Add minimum sample gate and probation flag for new sources.

Acceptance:
- Rankings change when outcomes change (not only by approvals).
- Dashboard shows sample size and confidence interval/probation marker.

### Phase 4 - Dashboard and Ops Discipline (1-2 days)
Deliverables:
- Add "System Health" panel in `dashboard-ui`:
  - last pipeline run time
  - failures in past 24h
  - stale data warnings
- Add "Live Readiness" panel with pass/fail checklist.
- Add one-command daily scorecard output in `reports/`.

Acceptance:
- Operator can determine system status and safe mode in <60 seconds.
- All critical failures are visible without checking terminal logs.

### Phase 5 - Live Promotion Gate (paper-first checkpoint)
Required before enabling live:
- 60 trading-day paper window complete.
- Positive expectancy net of fees/slippage.
- No unresolved critical data-quality issues for 14 consecutive days.
- Max drawdown within defined risk budget.
- Override and kill-switch paths tested in drills.

## Operating Commands (Canonical)

Full stack:
```bash
cd /Users/Shared/curtis/trader-curtis
./run-all-scans.sh
```

Risk route only:
```bash
cd /Users/Shared/curtis/trader-curtis
./signal_router.py --mode paper --limit 12 --notional 100
./execution_worker.py
```

Dashboard:
```bash
cd /Users/Shared/curtis/trader-curtis/dashboard-ui
python app.py
```

## Immediate Next 5 Tasks

1. Write `docs/pipeline-contracts.md` and define idempotency keys per pipeline.
2. Add `pipeline_runs` tracking with pass/fail state for each script execution.
3. Add hard guardrails (daily/weekly/max exposure) as blocking logic.
4. Upgrade source ranking to include realized outcomes and recency decay.
5. Add dashboard health/readiness panels tied to the new guard + run metrics.

## References
- Core strategy: `docs/core-strategy.md`
- Master architecture: `BEST-TRADER-MASTERPLAN.md`
- Daily operating plan: `TRADING-PLAN-2026-02-23.md`
