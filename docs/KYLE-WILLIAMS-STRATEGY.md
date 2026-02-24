# Kyle Williams Strategy (Pipeline H)

This strategy converts the image notes into objective rules that can run in background.

## Setups Encoded

1. `first_red_day_short`
- Prior 2 days green (`close > open`)
- Current day red (`close < open`)
- Price extended above 20-day anchored VWAP by at least `+3%`
- Signal: `short`

2. `panic_dip_buy`
- Price at least `-8%` below 20-day anchored VWAP
- Wide daily range (>= `8%`) with rebound off lows
- Signal: `long`

3. `parabolic_short`
- 3-day return >= `20%`
- Strong upper wick (exhaustion)
- Signal: `short`

4. `gap_and_crap_short`
- Gap up >= `7%`
- Close below open and below prior close
- Signal: `short`

## Implementation

- Script: `pipeline_h_kyle_williams.py`
- Pipeline ID: `KYLE_WILLIAMS`
- Storage: `pipeline_signals`
- Data source preference:
  - Alpaca daily bars
  - Yahoo daily bars fallback

## How It Fits Existing Pipeline

- Already consumed by `generate_trade_candidates.py` via `pipeline_signals`.
- Routes still pass:
  - risk controls
  - quant gate
  - venue-specific thresholds
  - execution gating
- Learning path:
  - route outcomes + feature snapshots (`route_feedback_features`)
  - aggregate stats (`input_feature_stats`)

## Notes

- This is a strict rules engine version of a discretionary style.
- Market feel/fatigue and "if market not right, stand down" are approximated with existing risk controls and auto-tuner recommendations.
