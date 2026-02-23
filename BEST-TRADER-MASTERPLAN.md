# Best Trader Masterplan (v1)

Date: 2026-02-22
Owner: Curtis + ORION
Mission: Build a multi-pipeline trading intelligence + execution system with strict risk controls and measurable edge.

---

## 1) Mission Definition

Primary goals:
- Pipeline A: Intraday/scalp trading from liquidity structure.
- Pipeline B: Long-term alpha from life-changing innovation (AI/biotech/robotics).
- Pipeline C: Event-driven geopolitical/macro alpha (war, policy, shipping/logistics shocks).
- Pipeline D: X/bookmark thesis ingestion + source ranking + selective copy-trade.

Hard constraints:
- Paper-first and small-size live rollout.
- Every signal must be attributable, scored, and auditable.
- No discretionary override without logged reason.

Success criteria:
- Positive expectancy over rolling 60 trading days.
- Max drawdown inside risk budget.
- Daily operating discipline (alerts, queue, post-trade review).

---

## 2) Reality Check: "$100/day" Target

$100/day is a valid target, but capital + risk determine feasibility.

Example return requirement:
- $10k account -> 1.0%/day gross target (aggressive, hard to sustain).
- $25k account -> 0.4%/day gross target.
- $50k account -> 0.2%/day gross target.

System design implication:
- We optimize for consistency and downside control first.
- If realized edge is lower than target, increase capital before increasing leverage.

---

## 3) System Architecture

### 3.1 Data Layers

Bronze (raw ingest):
- Social posts, news headlines, macro releases, price streams, bookmarks.

Silver (normalized):
- Canonical schema (`timestamp`, `asset`, `source`, `signal_type`, `payload`, `quality_score`).

Gold (decision tables):
- `trade_candidates`, `signal_routes`, `risk_events`, `executions`, `post_trade_eval`.

### 3.2 Decision Layers

1) Signal generation (pipeline-specific).
2) Cross-pipeline scoring and conflict resolution.
3) Risk guard (hard limits, kill switches).
4) Router (paper/live queue).
5) Executor (broker/exchange adapter).
6) Reviewer (outcome attribution + source grades).

### 3.3 Current Status (already implemented)

- Candidate generation: `generate_trade_candidates.py`
- Risk guard: `execution_guard.py`
- Routing queue: `signal_router.py`
- Dashboard APIs/UI for candidates + routes + controls

Gap:
- Pipelines are not yet fully independent and do not yet have distinct alpha models + portfolio sleeves.

---

## 4) Pipeline A — Liquidity Scalping

Objective:
- Intraday setups targeting repeatable micro-edge from liquidity behavior.

Signal inputs:
- Price/volume streams (1m/5m/15m bars)
- Pattern engine (QML, liquidity grab, fakeout, stop hunt, etc.)
- Session context (open, lunch, close)
- Volatility regime

Model:
- Pattern score (structure quality)
- Context score (trend/regime alignment)
- Execution score (spread/slippage/funding constraints)

Execution policy:
- Max concurrent scalp positions.
- Strict per-trade stop and time stop.
- No entry during banned windows if strategy says so.

KPI:
- Win rate by pattern.
- R multiple per trade.
- Slippage-adjusted expectancy.

---

## 5) Pipeline B — Long-Term Innovation Alpha

Objective:
- Build a conviction portfolio from non-consensus innovation signals.

Theme buckets:
- AI infrastructure and model deployment
- Robotics/autonomy
- Biotech/longevity/drug discovery platforms
- Energy/storage/compute infrastructure

Research graph:
- Company -> Product -> Scientific/engineering milestone -> Commercial traction -> Valuation regime

Signal inputs:
- SEC filings and XBRL trend extraction
- Patent/research/clinical signals
- Earnings and guidance deltas
- Capital flow proxies (funding, capex, partnerships)

Portfolio policy:
- Sleeve-based allocation (core + satellite).
- Rebalance cadence (weekly/monthly).
- Thesis invalidation criteria required per hold.

KPI:
- 3/6/12 month alpha vs benchmark basket.
- Hit rate of thesis milestones.
- Drawdown and concentration control.

---

## 6) Pipeline C — Event/Macro/Geopolitical Alpha

Objective:
- Detect high-impact events early and map them to tradable expressions.

Example user intent:
- "If Iran conflict escalates and shipping risk rises, evaluate short BTC / risk-off basket."

Event engine:
- Parse event stream -> classify event type -> map to playbook.

Playbook examples:
- Middle East escalation -> risk-off, energy up, shipping/logistics stress.
- Tariff escalation -> FX/rates/commodity + specific sector impacts.
- Surprise central bank shift -> duration, USD, growth assets.

Guardrails:
- Require multi-source confirmation and confidence threshold.
- Expire stale event signals quickly.
- Require volatility-aware sizing.

KPI:
- Event alert precision/recall.
- PnL by event family.
- False positive rate reduction month-over-month.

---

## 7) Pipeline D — X/Bookmarks/External Thesis

Objective:
- Convert bookmarked threads/links into structured hypotheses and tradable candidates.

Flow:
1. Ingest URL -> extract author, timestamp, thesis, horizon, assets.
2. Label thesis type (scalp/swing/long-term/event).
3. Assign source credibility score.
4. Route through same risk guard and scoring stack.

Source ranking:
- Track Brier score + realized trade outcome.
- Decay old performance; emphasize recent regime relevance.
- Auto-demote noisy sources.

Current status:
- Bookmark export files exist; structured thesis extraction is pending.

---

## 8) Exchange/Broker Strategy

Use best venue by instrument, not ideology:
- Hyperliquid: crypto perps/spot where available.
- Alpaca: equities paper/live where supported.

Important:
- Hyperliquid is not a full US-stock venue replacement.
- Keep unified portfolio/risk view above venue level.

---

## 9) Risk and Capital Framework

Global controls:
- Max daily loss
- Max weekly drawdown
- Max open positions
- Max notional per trade
- Max exposure per sector/theme

Pipeline-level budgets:
- A (Scalp): highest turnover, tightest risk.
- B (Long-term): lower turnover, wider but thesis-based stops/invalidation.
- C (Event): short-lived, confidence-gated.
- D (External/bookmark): probationary sizing until source proves edge.

Kill switches:
- Data feed failure
- Exchange degradation
- Abnormal slippage spikes
- Strategy drift (expectancy collapse)

---

## 10) Build Roadmap (Deep Work Plan)

### Phase 1: Research + Spec (8-12 focused hours)
- Build source inventory and quality matrix.
- Define schemas per pipeline.
- Define scoring math and confidence calibration.
- Create event-to-trade playbook mappings.

Deliverables:
- `docs/alpha-source-matrix.md`
- `docs/pipeline-specs.md`
- `docs/event-playbooks.md`

### Phase 2: Pipeline Implementation (12-20 hours)
- Implement dedicated collectors/normalizers for A/B/C/D.
- Add source reliability engine.
- Add conflict resolver and cross-pipeline ranker.

Deliverables:
- `pipeline_a_liquidity.py`
- `pipeline_b_innovation.py`
- `pipeline_c_event.py`
- `pipeline_d_bookmarks.py`
- `source_ranker.py`

### Phase 3: Execution + Controls (8-12 hours)
- Finalize queue worker (paper).
- Integrate venue adapters (Alpaca + Hyperliquid).
- Add retry/timeout/failover behavior.

Deliverables:
- `execution_worker.py`
- `adapters/alpaca_adapter.py`
- `adapters/hyperliquid_adapter.py`
- `risk_kill_switch.py`

### Phase 4: Evaluation + Tuning (ongoing weekly)
- Daily and weekly scorecards.
- Pattern/source ablation tests.
- Promotion/demotion rules for strategies and sources.

Deliverables:
- `reports/daily_scorecard_*.md`
- `reports/weekly_edge_review_*.md`

---

## 11) What We Left Off On

- Planning docs exist but are high-level.
- Execution guard and routing are wired.
- Bookmark exports exist but are not yet converted into structured thesis objects.
- Next deep-work step is Phase 1 deliverables above (not a quick patch; full research sprint).

---

## 12) Reality Status Matrix (2026-02-22 Audit)

Use this table as ground truth for validity checks.

| Component | File(s) | Status | Notes |
|---|---|---|---|
| Pipeline A (Liquidity) | `pipeline_a_liquidity.py` | Implemented (v1) | Heuristic weighting; needs idempotency + richer context features |
| Pipeline B (Innovation) | `pipeline_b_innovation.py` | Implemented (v1) | Watchlist-driven; no thesis invalidation automation yet |
| Pipeline C (Event) | `pipeline_c_event.py`, `event_alert_engine.py` | Implemented (v1) | Event mapping exists; confidence calibration still basic |
| Pipeline D (Bookmarks) | `pipeline_d_bookmarks.py` | Implemented (v1) | Ingests URLs into theses; extraction depth limited |
| Candidate Builder | `generate_trade_candidates.py` | Implemented | Downstream-ready; needs stronger dedupe contracts |
| Risk Guard + Router | `execution_guard.py`, `signal_router.py` | Implemented | Blocking logic works; needs fuller risk budget coverage |
| Execution Worker | `execution_worker.py` | Implemented (paper-first) | Live path intentionally blocked unless enabled |
| Source Ranking | `source_ranker.py` | Partial | Uses approval/execution rates, not realized expectancy |
| Dashboard UI | `dashboard-ui/` | Implemented (v1) | Good observability start; missing health/readiness panels |

## 13) Validity Gates (What Makes This Plan "Real")

The plan is considered valid only if all gates are true:

1. Repeatability gate:
   - Re-running full stack produces stable, explainable state changes.
2. Traceability gate:
   - Each routed trade can be traced to upstream signal(s) with source and rationale.
3. Risk gate:
   - Hard limits are enforced in code, not only documented.
4. Outcome gate:
   - Source ranking is tied to realized results, not just internal approvals.
5. Operations gate:
   - Dashboard shows system health + live readiness at a glance.

## 14) Next Session Sprint (Priority Ordered)

1. Define and implement signal idempotency keys across A/B/C/D.
2. Add `pipeline_runs` telemetry table and write per-run success/failure metadata.
3. Expand risk controls to daily/weekly drawdown + exposure budget blocking.
4. Upgrade source ranker to include realized outcome metrics and recency decay.
5. Add dashboard "System Health" and "Live Readiness" panels.
