# Handoff — 2026-02-24 — 3-Venue Matrix + Independent Audit

## What was implemented

### 1) 3-venue routing matrix (stocks/crypto/prediction)
- Added schema expansion on `signal_routes`:
  - `venue_scores_json`
  - `venue_decisions_json`
  - `preferred_venue`
- Added `venue_matrix` table with per-venue controls:
  - `venue` (stocks|crypto|prediction)
  - `enabled`
  - `min_score`
  - `max_notional`
  - `mode`
- Router now computes per-venue scores from each candidate and persists venue decisions.
- Router chooses `preferred_venue` using highest positive margin above venue threshold.
- Notional is capped by selected venue max notional.
- Prediction-preferred routes are explicitly blocked in `signal_routes` with reason to avoid accidental cross-venue execution (Polymarket executes via its own candidate lane).

Files:
- `signal_router.py`

### 2) Worker honors preferred venue
- `execution_worker.py` now reads `preferred_venue` from routed signals.
- Venue-specific behavior:
  - `crypto`: only HL path allowed; otherwise explicit block.
  - `stocks`: only Alpaca path allowed; otherwise explicit block.
  - `prediction`: explicit block with reason that polymarket pipeline handles execution.

Files:
- `execution_worker.py`

### 3) Dashboard API for venue control + readiness
- Added `venue_matrix` API read/update + venue readiness snapshot:
  - `GET /api/venue-matrix`
  - `POST /api/venue-matrix`
  - `GET /api/venue-readiness`
- Added backend functions:
  - `_ensure_venue_matrix`
  - `get_venue_matrix`
  - `set_venue_matrix`
  - `get_venue_readiness`
- Fixed DB lock risk in `_ensure_venue_matrix` by removing nested connection usage.

Files:
- `dashboard-ui/data.py`
- `dashboard-ui/app.py`

## Validation performed
- Python compile checks passed:
  - `signal_router.py`, `execution_worker.py`, `dashboard-ui/data.py`, `dashboard-ui/app.py`
- Router run succeeded and persisted venue scoring fields.
- Venue APIs return expected structures.
- `venue_matrix` currently seeded from existing controls.

## Independent audit findings (priority)

### High
1. Route starvation due to open-position cap
- Evidence: `open_trades=52` while `max_open_positions=50`; recent routes blocked with `open position cap reached`.
- Impact: New high-quality signals are blocked before execution.
- Recommendation: close stale open trades and/or temporarily raise cap while reconciliation catches up.

2. Live-mode risk posture currently aggressive
- Evidence: `allow_live_trading=1`, `enable_alpaca_paper_auto=1`, `enable_hyperliquid_test_auto=1`, `enable_polymarket_auto=1`.
- Impact: System can attempt multi-venue live behavior while readiness quality is mixed.
- Recommendation: keep one venue live at a time until realized coverage improves.

### Medium
3. Signal readiness currently bad due to candidate freshness and matured realized outcomes
- Evidence: `Candidates (6h)=0`, `Realized Matured (7d >24h)=0/64`.
- Impact: learning loop cannot reliably calibrate with realized outcomes.
- Recommendation: ensure candidate generator cadence and outcome resolver cadence are aligned; prioritize realized outcome backfill.

4. Full pipeline audit script emits warn state when no queued routes
- Evidence: trade claim guard warning with `approved_queued_routes=0`.
- Impact: operational false alarms when market/filters are quiet.
- Recommendation: classify as informational when no fresh candidates exist.

### Low
5. Python runtime warning (`LibreSSL` vs `OpenSSL`) in some checks
- Impact: noise; potential future TLS compatibility issues.
- Recommendation: standardize runtime on Python/OpenSSL build for network jobs.

## Suggested next actions
1. Reconcile `trades` open statuses vs actual broker/exchange state and clear stale opens.
2. Add venue matrix controls to dashboard UI panel (currently API-ready).
3. Add route-to-polymarket bridge if you want prediction routes generated in `signal_routes` to auto-forward into `polymarket_candidates`.
4. Tighten live gate: require `signal_readiness.state != bad` before any live execution path.
