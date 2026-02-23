# Alpha Source Matrix (Deep Research v1)

Date: 2026-02-22
Scope: Select high-signal, low-cost sources for four trading pipelines.

## Selection Criteria
- Signal latency
- Historical availability
- Programmatic reliability
- Cost/free tier
- Direct tradability mapping
- Noise/false-positive risk

## Pipeline A: Liquidity Scalping

1. Market microstructure and execution
- Alpaca Trading + order state streaming.
- Hyperliquid exchange + info endpoints (for crypto execution and state).
- Why: direct executable signals, not narrative proxies.

2. Pattern engine inputs
- Existing `institutional_patterns` table in `trades.db`.
- Existing sentiment tables as secondary confirmation.
- Why: keep scalp engine chart/structure-first, not headline-first.

3. Recommended additions
- Real-time bar feed (1m/5m) from broker/exchange stream.
- Slippage monitor (entry vs expected).

## Pipeline B: Long-Term Innovation Alpha

1. SEC fundamentals and disclosures
- SEC Submissions API (`data.sec.gov/submissions/CIK*.json`).
- SEC XBRL company facts APIs for trend extraction.
- Why: primary-source regulatory filings, near real-time updates.

2. Clinical/scientific milestone feeds
- ClinicalTrials.gov modern API v2 (daily refresh Mon–Fri).
- openFDA datasets for adverse events/safety/regulatory context.
- Why: objective milestone and risk signals for biotech/health innovation sleeves.

3. Macro tailwind confirmation
- FRED API (v1/v2; release-level observations in v2).
- BLS API v2 (labor/inflation releases).
- Why: validate theme regime (risk-on/off, rate sensitivity).

## Pipeline C: Event/Macro/Geopolitical Alpha

1. Event stream sources
- ACLED API (OAuth/cookie auth model).
- GDELT DOC 2.0 (global media event discovery/search).
- Federal Register API v1 (policy/regulatory publication signals).
- Why: structured + unstructured event blend with broad coverage.

2. Domain-specific stress indicators
- EIA API v2 for energy data shocks.
- OFAC Sanctions List Service (official sanctions updates).
- Why: convert geopolitics into concrete sector/asset impact.

3. Optional shipping-risk enrichment
- Commercial AIS/maritime feeds (paid; add only after event alpha proves edge).

## Pipeline D: X / Bookmarks / External Thesis

1. Current workspace assets
- `docs/x-bookmarks.json`, `docs/x-bookmarks.txt`.
- `external_signals` table and `add_external_signal.py`.

2. Required upgrades
- Parse each URL into thesis object:
  - source handle
  - asset universe
  - horizon (scalp/swing/long-term)
  - direction + invalidation clues
- Score source quality using realized outcomes (rolling windows).

3. Governance
- External thesis cannot bypass risk guard.
- New source starts with probationary size.

## Cost/Complexity Prioritization

Immediate (free/low friction):
- SEC, FRED, BLS, ClinicalTrials, openFDA, GDELT, Federal Register, existing Alpaca/HL.

Medium (auth/config overhead):
- ACLED OAuth workflow.

Deferred (paid/complex):
- Premium shipping intelligence feeds.

## Source-to-Action Mapping

- Filing acceleration + guidance strength -> long-term candidate boost.
- Clinical milestone + sentiment divergence -> watchlist promotion.
- Geopolitical escalation + energy/sanctions confirmation -> event hedge candidate.
- Liquidity sweep + pattern confirmation -> scalp route candidate.

## References
- SEC EDGAR APIs: https://www.sec.gov/edgar/sec-api-documentation
- SEC developer resources: https://www.sec.gov/about/developer-resources
- ClinicalTrials API v2: https://clinicaltrials.gov/api/gui
- openFDA APIs: https://open.fda.gov/apis/
- FRED API: https://fred.stlouisfed.org/docs/api/fred/licenses/fred.html
- FRED API v2: https://fred.stlouisfed.org/docs/api/fred/v2/index.html
- BLS API signatures v2: https://www.bls.gov/developers/api_signature_v2.htm
- EIA Open Data: https://www.eia.gov/opendata/index.php
- EIA API technical docs: https://www.eia.gov/opendata/documentation.php
- ACLED API authentication: https://acleddata.com/reactivation/api-authentication
- GDELT DOC 2.0: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- Federal Register API v1: https://www.federalregister.gov/developers/api/v1
- Hyperliquid exchange endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
- Hyperliquid nonces/API wallets: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets
- Alpaca orders: https://docs.alpaca.markets/docs/trading/orders/
- Alpaca market data overview: https://docs.alpaca.markets/docs/about-market-data-api
