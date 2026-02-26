# Dashboard Data Audit (2026-02-25)

## Purpose
Explain what each dashboard panel really means, where its data comes from, what is trustworthy, and what can be removed or merged.

## Source-of-Truth Layers

1. Input layer (raw signals): pipeline tables and feeds
- `pipeline_signals`
- `external_signals`
- `chart_liquidity_signals`
- `unified_social_sentiment`
- `copy_trades`
- `polymarket_markets`, `polymarket_candidates`, `weather_market_probs`

2. Candidate layer (weighted scoring):
- `trade_candidates`
- `input_source_controls` (manual/auto weights)
- `tracked_x_sources` (handle-specific source weights)

3. Routing layer (decision/gating):
- `signal_routes`
- `venue_matrix`
- `ticker_trade_profiles`
- quant/allocator outputs (`quant_validations`, `allocator_decisions`)

4. Execution layer (what was actually attempted):
- `execution_orders`
- `execution_learning`
- `route_trade_links`
- `polymarket_orders`

5. Outcome/truth layer (what happened after the call):
- `route_outcomes`
- `route_outcomes_horizons`
- `trades`

6. Learning layer (performance by source/strategy/feature):
- `source_learning_stats`
- `strategy_learning_stats`
- `input_feature_stats`
- `source_scores`

## Live State Snapshot (as of 2026-02-25)

- `pipeline_signals`: 1649 rows, last at `2026-02-25T20:53:27Z`
- `signal_routes`: 798 rows, last at `2026-02-25T20:53:30Z`
- `trade_candidates`: **0 rows** (critical)
- `execution_orders`: 79 rows, last at `2026-02-24T21:12:07Z`
- `route_outcomes`: 184 rows, last at `2026-02-25T16:03:22Z`
- `external_signals`: 944 rows, last at `2026-02-25T21:46:25Z`
- `unified_social_sentiment`: 95 rows, last at `2026-02-20T12:31:15`
- `source_learning_stats`: 2 rows total (very low sample depth)

### Critical finding
`trade_candidates` is being wiped by maintenance, so many signal panels look empty even though upstream inputs are live. This is why "things run but nothing works" appears true in UI.

## Input Wiring (actual behavior)

### Core weighted score inputs
Candidate score is blended from these families:
- `family:social` from `unified_social_sentiment.overall_score`
- `family:pattern` from `institutional_patterns.pattern_type`
- `family:external` from `external_signals.confidence`
- `family:pipeline` from `pipeline_signals.score`
- `family:copy` from `copy_trades` presence
- `family:liquidity` from `chart_liquidity_signals` pattern/confidence/RR hit
- optional `x:<handle>` if tracked X source + X influence enabled

All are reweighted by `input_source_controls` (manual x auto), plus strategy-level overrides.

### Route approval path
- Candidate -> quant gate + allocator + ticker profile required inputs/min score + venue matrix score thresholds
- Result stored in `signal_routes` with `approved` or `rejected`
- Approved routes are consumed by execution worker into `execution_orders`

### Truth scoring path
- Outcomes from reconciler/links are written to `route_outcomes`
- Learning stats roll up into `source_learning_stats`, `strategy_learning_stats`, `input_feature_stats`

## Dashboard Panel Map (meaning + root source)

## Main (`/`)
- Hero PnL/Win/Open/Mode: mostly `trades` with fallback to `route_outcomes`
- Pulse rings: derived from `system-health`, `signal-readiness`, and automation flags in `execution_controls`
- Live Flow (Trades Made): `execution_orders` + `polymarket_orders` filtered to submitted/filled-like statuses
- Wallet and Awareness:
  - wallet values: `wallet_config` + live API calls to Alpaca/Hyperliquid + polymarket order aggregation
  - awareness/claim checks: controls + credential checks + freshness checks + queued routes
- Truth Layer and Missed Outcomes:
  - `learning_monitor` (`route_outcomes`, `route_outcomes_horizons`, `trades`)
  - missed opportunities from non-approved `signal_routes` joined with `route_outcomes`
- Performance curve: cumulative from `route_outcomes` (fallback `trades`)
- Why trades were taken: `recent_trade_decisions` from `execution_orders` joined with `signal_routes` + candidate rationale/input breakdown

## Signals (`/signals`)
- Core signal accordion: `core_signals` aggregate built from
  - controls in `input_source_controls`
  - hits from `signal_routes` + `trade_candidates`
  - source/strategy stats from `source_learning_stats` + `strategy_learning_stats`
- Signal control edits: writes back to `input_source_controls`
- Trade replay review: reads `trades`/`signal_routes`/`route_outcomes`/`trade_candidates`, writes to `trade_feedback_*`, can apply reweights
- Advanced diagnostics:
  - readiness: `signal-readiness`
  - routes: `signal_routes`
  - source score: `source_scores`
  - quant/allocator: `quant_validations`, `allocator_decisions`
  - breakthroughs/liquidity/events/bookmarks from their respective tables

## Consensus (`/consensus`)
- Trust state: controls + candidate counts + top source stats
- Consensus candidates: `trade_candidates` (flagged), enriched with `source_ratings` + polymarket market match heuristics
- Source ratings: merged `source_learning_stats` + `source_scores` (+ poly wallet scores)
- Aligned setups: `polymarket_aligned_setups`

## Learning (`/learning`)
- Learning health: 7-day coverage from `signal_routes` + `route_outcomes` (+ links)
- Memory integrity: consistency checks over routes/outcomes/links
- Trade intents: `trade_intents`
- Execution learning: `execution_learning`
- Source/strategy learning: `source_learning_stats`, `strategy_learning_stats`
- Input feature stats: `input_feature_stats`

## Polymarket (`/polymarket`)
- Overview: controls + daily order usage from `polymarket_orders`
- MM overview/snapshots: `polymarket_mm_overview`, `polymarket_mm_snapshots`
- Markets/candidates/orders: `polymarket_markets`, `polymarket_candidates`, `polymarket_orders`
- Weather probabilities: `weather_market_probs`
- Wallet watch/scoring: `tracked_polymarket_wallets`, `polymarket_wallet_scores`
- Source controls: `tracked_x_sources`, `input_source_controls`

## Redundancy and Noise Audit

## Keep (decision-critical)
- `System Pulse` (but single condensed card)
- `Why trade was taken` + route reason + input hits
- `Performance curve`
- `Truth layer` (coverage, realized/operational counts)
- `Signal controls` (weights + on/off)
- `Venue summary` (24h submitted/filled/blocked)

## Merge
- Merge `Awareness`, `Trade Claim Guard`, and `Wallet brief` into one compact `Execution Readiness` card
- Merge `Venue summary` + `Missed summary` into one `Execution vs Opportunity` card
- Merge repetitive source tables across pages into one shared "Source quality" view with filters

## Remove or default-hide
- Duplicate raw tables that restate the same event stream (`execution_orders` variants across pages)
- Panels that only mirror controls without performance context
- Constantly auto-updating feed by default (manual refresh should remain default)
- Any panel backed by empty/stale tables should show `stale` badge and collapse by default

## Biggest current trust gaps
1. `trade_candidates` gets cleared by retention, so signal pages lose real-time candidate context.
2. Social feed freshness is stale (`unified_social_sentiment` last update 2026-02-20).
3. Learning stats sample depth is very low (`source_learning_stats` has 2 rows), so per-source win rates are not stable yet.
4. Most routes are rejected/blocked (719 rejected blocked vs 62 approved executed), so you need clearer "top blockers" surfacing.

## Recommended Minimal Dashboard Set (rookie-friendly)

1. Health and readiness (single compact card)
- overall health
- candidate freshness
- route freshness
- trade-claim readiness
- top 3 blockers

2. Trade quality card
- total pnl
- win rate
- closed trades
- realized coverage
- missed winners (7d)

3. Execution card
- approved routes (24h)
- blocked routes (24h)
- submitted/filled by venue

4. Why-this-trade tool
- trade ID lookup
- plain-English explanation
- top input contributions
- one-click feedback/weight adjust

5. Signal controls card
- family-level weights only by default
- dropdown expand for sub-inputs (social/x/source)
- show sample size next to each adjustable input

