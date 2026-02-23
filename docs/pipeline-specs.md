# Pipeline Specs (Execution Design)

Date: 2026-02-22
Status: Design finalized, implementation in progress.

## Shared Contract (All Pipelines)

Output schema (`pipeline_signals` logical model):
- `generated_at` (UTC)
- `pipeline_id` (`A_SCALP`, `B_LONGTERM`, `C_EVENT`, `D_BOOKMARK`)
- `asset` (ticker/symbol)
- `direction` (`long`, `short`, `hedge`, `watch`)
- `horizon` (`intraday`, `swing`, `position`)
- `confidence` (0.0-1.0)
- `score` (0-100 normalized)
- `rationale` (short human-readable reason)
- `source_refs` (comma-delimited or JSON refs)
- `ttl_minutes` (expiry)

Routing rules:
- Signals pass through `execution_guard.py`.
- Guard output is persisted via `signal_router.py`.
- Rejected signals are retained for evaluation (important for false-negative analysis).

## Pipeline A: Liquidity Scalp

Objective:
- Generate intraday entries from liquidity patterns and structure breaks.

Inputs:
- `institutional_patterns`
- intraday bars/orderflow proxy (Alpaca + Hyperliquid streams)
- optional sentiment as tie-breaker only

Primary score:
- `A_score = 0.55*pattern_quality + 0.25*session_context + 0.20*execution_quality`

Constraints:
- Hard time windows to avoid (first X mins, optional news blackout).
- Max N concurrent scalp trades.
- Mandatory stop + time-stop.

Outputs:
- Only `intraday` horizon.
- TTL: 15-120 minutes depending on setup type.

## Pipeline B: Long-Term Innovation

Objective:
- Build high-conviction position candidates from real innovation signals.

Inputs:
- SEC filings/XBRL trend deltas
- ClinicalTrials/openFDA milestone/risk updates
- macro regime proxies (FRED/BLS)

Primary score:
- `B_score = 0.40*fundamental_delta + 0.30*milestone_strength + 0.20*valuation_regime + 0.10*sentiment_regime`

Constraints:
- Must include thesis + invalidation text.
- Max sector concentration.
- Staggered entries; no all-in execution.

Outputs:
- `position` or `swing` horizon.
- TTL: days/weeks.

## Pipeline C: Event/Macro/Geopolitical

Objective:
- Convert high-impact events into tradable expressions quickly and safely.

Inputs:
- ACLED, GDELT, Federal Register, EIA, sanctions feeds
- market regime confirmation from price action

Primary score:
- `C_score = 0.45*event_confidence + 0.30*market_confirmation + 0.15*impact_fit + 0.10*timeliness`

Constraints:
- Multi-source confirmation required.
- Fast TTL expiry.
- Lower initial size on first signal burst.

Outputs:
- Mostly `intraday` / `swing`, occasionally `hedge`.
- TTL: 30-360 minutes.

## Pipeline D: Bookmarks / External Thesis

Objective:
- Transform external ideas into structured, testable, risk-controlled signals.

Inputs:
- `docs/x-bookmarks.json` + user links
- optional copy-trade source streams

Primary score:
- `D_score = 0.35*source_quality + 0.25*thesis_clarity + 0.25*market_alignment + 0.15*recency`

Constraints:
- Probationary sizing for new sources.
- No direct execution bypass.
- Mandatory source attribution.

Outputs:
- Any horizon (depends on parsed thesis).
- TTL parsed from thesis or defaulted by classifier.

## Cross-Pipeline Resolver

When multiple pipelines conflict on same asset:
1. Prefer higher-confidence signal.
2. Prefer shorter TTL only if same direction.
3. If opposite directions with close score: no trade, log conflict.
4. Event signals can temporarily override long-term entries for hedging.

## Existing API Availability (Confirmed)

Configured in workspace `.env`:
- Alpaca
- Hyperliquid
- XAI/Grok
- Brave
- OpenAI

Implication:
- No key-provisioning phase required.
- Move directly to ingestion + calibration + scoring.
