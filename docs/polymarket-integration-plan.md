# Polymarket Integration Plan (Bookmark-Informed)

Date: 2026-02-23
Owner: Curtis + Trader Agent

## Goal
Integrate Polymarket idea generation + execution into the existing `trader-curtis` stack so it can:
- discover markets aligned with your existing macro/sentiment/liquidity pipelines,
- generate measurable Polymarket trade ideas,
- execute with strict controls,
- learn from outcomes.

## Inputs Reviewed
### Your bookmark export (`docs/x-bookmarks.json`, `docs/x-bookmarks.txt`)
Observed theme mix:
- Quant/research-heavy accounts/posts (Data/quant focus)
- AI-agent/build workflows
- Crypto/sentiment signal accounts

These are a good fit for prediction-market alpha because they emphasize:
- probability framing,
- event timing,
- narrative shifts,
- systematic execution.

### Official Polymarket docs (primary sources)
- Authentication (L1/L2): `https://docs.polymarket.com/developers/CLOB/authentication`
- CLOB overview: `https://docs.polymarket.com/developers/CLOB/trades/:slug*`
- Client methods: `https://docs.polymarket.com/developers/CLOB/clients/methods-overview`
- Base endpoints: `https://docs.polymarket.com/quickstart/reference/endpoints`
- Developer quickstart (Gamma/CLOB/Data/WebSocket): `https://docs.polymarket.com/quickstart/overview`
- Python trading client repo: `https://github.com/Polymarket/py-clob-client`

## Target Architecture
Add one idea pipeline and one execution adapter:

1. `pipeline_polymarket.py` (ideas)
- Pull tradeable events/markets from Gamma API.
- Join with existing internal signals:
  - `event_alerts`
  - `pipeline_signals` (A/B/C/CHART_LIQUIDITY)
  - social sentiment tables
- Compute model probability vs market implied probability.
- Emit candidate ideas with edge score.

2. `execution_polymarket.py` (execution)
- Use `py-clob-client` for order creation/posting.
- Apply dedicated controls (position limits, per-market cap, max spread).
- Store order/trade lifecycle for learning feedback.

## Strategy Stack (Integrated + Separable)
Run three strategies under one Polymarket execution layer:

1. Copy Trading (`POLY_COPY`)
- Track curated X/accounts/newsletters you trust.
- Extract explicit directional calls on events/markets.
- Convert to candidate with source confidence weighting.
- Execute only if risk + spread filters pass.

2. Arbitrage (`POLY_ARB`)
- Identify pricing inefficiencies:
  - same event mispricing across related outcomes
  - complement inconsistency (`YES + NO` deviation from fair total after fees)
  - cross-venue divergence (where available)
- Execute delta-neutral/hedged ideas only if expected edge clears fee/slippage threshold.

3. Internal Alpha (`POLY_ALPHA`)
- Use your existing pipeline outputs (`event_alerts`, `source_scores`, quant gate, sentiment, chart liquidity)
- Build model probability and compare against market implied probability.
- Trade only when `edge >= polymarket_min_edge_pct`.

All three strategies share:
- one routing queue
- one execution adapter
- one controls layer
- one learning loop

Each keeps separate `strategy_id` so performance can be isolated.

## New Data Model (SQLite)
Add tables:

1. `polymarket_markets`
- `market_id`, `event_id`, `slug`, `question`, `outcomes`, `outcome_prices`, `liquidity`, `volume_24h`, `active`, `closed`, `fetched_at`

2. `polymarket_candidates`
- `created_at`, `strategy_id`, `market_id`, `outcome`, `implied_prob`, `model_prob`, `edge`, `confidence`, `source_tag`, `rationale`, `status`

3. `polymarket_orders`
- `created_at`, `strategy_id`, `route_id`, `market_id`, `outcome`, `side`, `price`, `size`, `order_id`, `status`, `notes`

4. `polymarket_outcomes`
- `resolved_at`, `strategy_id`, `market_id`, `outcome`, `entry_price`, `exit_or_settle_price`, `pnl_pct`, `result`, `notes`

## Controls (extend `execution_controls`)
Add:
- `enable_polymarket_auto` (`0/1`)
- `allow_polymarket_live` (`0/1`)
- `polymarket_max_notional_usd`
- `polymarket_max_open_markets`
- `polymarket_min_edge_pct`
- `polymarket_max_spread_pct`
- `polymarket_copy_enabled`
- `polymarket_arb_enabled`
- `polymarket_alpha_enabled`
- `polymarket_copy_max_notional_usd`
- `polymarket_arb_max_notional_usd`
- `polymarket_alpha_max_notional_usd`

Defaults:
- auto off, live off, small notional, strict spread/edge checks.

## Pipeline Logic
## Phase 1: Market Discovery + Candidate Generation
1. Fetch active markets/events from Gamma API.
2. Filter to strategy-relevant categories (politics, macro, crypto, tech regulation, war/geopolitics).
3. Convert outcome prices to implied probabilities.
4. Build internal model probability from existing signals:
   - event alert confidence
   - source reliability (`source_scores`, `source_learning_stats`)
   - quant gate context
5. Create candidate only when `model_prob - implied_prob >= min_edge`.

Strategy-specific candidate rules:
- Copy: requires trusted source hit + recency window + no contradiction from hard risk events.
- Arb: requires net edge after fees/slippage and sufficient depth.
- Alpha: requires quant/risk pass + internal edge threshold.

## Phase 2: Route + Execute
1. Route as `source_tag=POLYMARKET`.
2. Apply strategy-specific caps and unified risk/quant checks before posting order.
3. Post order via CLOB client (L2 credentials).
4. Track open orders/positions in `polymarket_orders`.

## Phase 3: Outcome Learning
1. On resolution/exit, compute PnL%.
2. Write to `polymarket_outcomes`.
3. Feed into source ranking and quant validation.

## Security / Key Handling
For CLOB trading you need:
- private key signer for L1
- API creds for L2 (derived from L1 flow)
- funder/signature type per wallet setup

Store in `.env` only (no hardcoded keys):
- `POLY_PRIVATE_KEY`
- `POLY_FUNDER`
- `POLY_SIGNATURE_TYPE`
- `POLY_CLOB_HOST` (`https://clob.polymarket.com`)
- `POLY_CHAIN_ID` (`137`)

If using API creds directly:
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`

## Dashboard Additions
Add cards/endpoints:
- `Polymarket Markets` (clickable market URLs)
- `Polymarket Candidates` (implied vs model prob, edge)
- `Polymarket Orders` (status lifecycle)
- `Polymarket PnL` (resolved outcomes)
- `Strategy Breakdown` (`POLY_COPY`, `POLY_ARB`, `POLY_ALPHA` win rate, EV, drawdown, notional)

## Execution Plan (Concrete)
1. Build `pipeline_polymarket.py` with strategy modules:
   - `build_copy_candidates()`
   - `build_arb_candidates()`
   - `build_alpha_candidates()`
2. Add dashboard visibility for markets/candidates + strategy split (no live trading yet).
3. Add `execution_polymarket.py` in paper/shadow mode with per-strategy caps.
4. Add controls + kill switch per strategy + global.
5. Enable micro-notional live by strategy (one at a time) after validation.

## Acceptance Gates
Before live:
- 14 days paper/shadow data
- positive edge realization net of fees/slippage
- no unresolved auth/order-state errors for 7 consecutive days
- max drawdown within configured budget

## Why This Matches Your Bookmarks
Your saved posts skew toward quant + systematic + AI workflows.  
This plan turns that into:
- probability-based event trading,
- measurable edge vs market price,
- controlled execution,
- continuous feedback loop.
