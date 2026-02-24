#!/usr/bin/env python3
"""
Training-mode control overrides.

When training_mode_enabled=1, selected runtime controls are replaced by
training_* values so the system can collect more labeled outcomes with
smaller risk limits, without overwriting production thresholds.
"""

from typing import Dict


OVERRIDES = {
    "min_candidate_score": "training_min_candidate_score",
    "consensus_min_confirmations": "training_consensus_min_confirmations",
    "consensus_min_ratio": "training_consensus_min_ratio",
    "consensus_min_score": "training_consensus_min_score",
    "alpaca_min_route_score": "training_alpaca_min_route_score",
    "hyperliquid_min_route_score": "training_hyperliquid_min_route_score",
    "polymarket_min_confidence_pct": "training_polymarket_min_confidence_pct",
    "max_signal_notional_usd": "training_max_signal_notional_usd",
    "max_daily_new_notional_usd": "training_max_daily_new_notional_usd",
    "hyperliquid_test_notional_usd": "training_hyperliquid_test_notional_usd",
    "polymarket_max_notional_usd": "training_polymarket_max_notional_usd",
    "polymarket_max_daily_exposure": "training_polymarket_max_daily_exposure",
}


def apply_training_mode(controls: Dict[str, str]) -> Dict[str, str]:
    out = dict(controls or {})
    enabled = str(out.get("training_mode_enabled", "0")).strip() == "1"
    if not enabled:
        return out
    for base_key, training_key in OVERRIDES.items():
        if training_key in out and str(out.get(training_key, "")).strip() != "":
            out[base_key] = str(out[training_key])
    return out

