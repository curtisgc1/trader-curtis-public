#!/usr/bin/env python3
"""
EMPO² Reward — Combined extrinsic + intrinsic reward computation.

Paper reference: arXiv:2602.23008, Section 3.2

Reward components:
  1. Extrinsic: HGRM reward from trade outcomes (direction, PnL, magnitude, Sortino)
  2. Intrinsic: Exploration bonus for novel market states (1/n visits)
  3. Group-relative advantage: Normalize across trajectory group

The combined reward drives both on-policy and off-policy updates.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def hgrm_reward(
    pnl_percent: float,
    route_score: float,
    predicted_direction: str,
    volatility_pct: float = 0.0,
    max_drawdown_pct: float = 0.0,
) -> float:
    """
    Hierarchical-Gated Reward Model (from existing GRPO pipeline).

    Returns reward in [-1, 1].
    """
    # Realize direction from PnL
    if pnl_percent > 0.05:
        realized = "long"
    elif pnl_percent < -0.05:
        realized = "short"
    else:
        realized = "neutral"

    pred = (predicted_direction or "").lower().strip()
    if pred in ("buy", "bullish"):
        pred = "long"
    elif pred in ("sell", "bearish"):
        pred = "short"
    elif pred not in ("long", "short", "neutral"):
        pred = "neutral"

    # Direction gate
    if pred == realized:
        dir_score = 1.0
    elif pred == "neutral" or realized == "neutral":
        dir_score = -0.2
    else:
        dir_score = -1.0
    dir_gate = 0 if dir_score < 0 else 1

    # Magnitude calibration
    expected_mag = min(1.0, abs(route_score) / 100.0)
    actual_mag = min(1.0, abs(pnl_percent) / 10.0)
    mag_score = max(0.0, 1.0 - abs(expected_mag - actual_mag))

    # PnL score normalized to [0, 1]
    pnl_score = (max(-1.0, min(1.0, pnl_percent / 5.0)) + 1.0) / 2.0

    # Sortino adjustment
    sortino_adj = _sortino_adjustment(pnl_percent, volatility_pct, max_drawdown_pct)

    if dir_gate == 0:
        reward = -0.5 + 0.2 * (pnl_score * 2.0 - 1.0) + sortino_adj
    else:
        reward = 0.55 * dir_score + 0.35 * pnl_score + 0.10 * mag_score + sortino_adj

    return max(-1.0, min(1.0, reward))


def _sortino_adjustment(
    pnl_pct: float, volatility_pct: float, max_drawdown_pct: float,
) -> float:
    """Sortino-inspired risk adjustment in [-0.3, +0.15]."""
    if volatility_pct <= 0 and max_drawdown_pct <= 0:
        return 0.0

    adj = 0.0
    if max_drawdown_pct > 2.0:
        adj -= min(0.3, (max_drawdown_pct - 2.0) / 10.0)
    if pnl_pct > 0.05 and volatility_pct > 0:
        sortino_like = pnl_pct / max(volatility_pct, 0.5)
        adj += min(0.15, sortino_like * 0.1)
    if pnl_pct < -0.05 and volatility_pct > 5.0:
        adj -= min(0.1, (volatility_pct - 5.0) / 20.0)

    return round(max(-0.3, min(0.15, adj)), 6)


def combined_reward(
    extrinsic: float,
    exploration_bonus: float,
    alpha: float = 0.1,
) -> float:
    """
    Paper: r_total = r_extrinsic + alpha * r_intrinsic

    Args:
        extrinsic: HGRM reward from trade outcome [-1, 1]
        exploration_bonus: Novelty bonus from memory buffer [0, 1]
        alpha: Weight for exploration term (default 0.1)
    """
    return extrinsic + alpha * exploration_bonus


def group_relative_advantage(
    rewards: List[float],
) -> List[float]:
    """
    Paper: A(at) = (R(i) - mean(R)) / sigma(R)

    Group-relative advantage normalization.
    Returns advantages for each trajectory in the group.
    """
    if not rewards:
        return []
    if len(rewards) == 1:
        return [0.0]

    arr = np.array(rewards, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr))

    if std < 1e-8:
        return [0.0] * len(rewards)

    return [float((r - mean) / std) for r in rewards]


def token_mask(
    log_prob: float,
    threshold: float = 0.01,
) -> float:
    """
    Paper Eq. 2: Token masking for off-policy stability.

    Suppresses advantage for low-probability tokens.
    Returns 1.0 if prob >= threshold, 0.0 otherwise.
    """
    prob = math.exp(log_prob) if log_prob < 0 else 1.0
    return 1.0 if prob >= threshold else 0.0


def clipped_importance_ratio(
    log_prob_new: float,
    log_prob_old: float,
    advantage: float,
    epsilon: float = 0.2,
) -> float:
    """
    Paper Eq. 1: PPO-style clipped objective.

    L = min(rho * A, clip(rho, 1-eps, 1+eps) * A)
    """
    log_ratio = log_prob_new - log_prob_old
    # Clamp for numerical stability
    log_ratio = max(-10.0, min(10.0, log_ratio))
    rho = math.exp(log_ratio)

    unclipped = rho * advantage
    clipped = max(1.0 - epsilon, min(1.0 + epsilon, rho)) * advantage

    return min(unclipped, clipped)


# ---------------------------------------------------------------------------
# Batch reward computation
# ---------------------------------------------------------------------------

def compute_batch_rewards(
    outcomes: List[Dict[str, Any]],
    exploration_bonuses: Optional[List[float]] = None,
    alpha: float = 0.1,
) -> List[Dict[str, float]]:
    """
    Compute rewards for a batch of trade outcomes.

    Each outcome dict should have:
        pnl_percent, route_score, predicted_direction,
        volatility_pct (optional), max_drawdown_pct (optional)

    Returns list of dicts with:
        extrinsic, intrinsic, combined, advantage
    """
    extrinsics = []
    for o in outcomes:
        r = hgrm_reward(
            pnl_percent=float(o.get("pnl_percent", 0)),
            route_score=float(o.get("route_score", 0)),
            predicted_direction=str(o.get("predicted_direction", "neutral")),
            volatility_pct=float(o.get("volatility_pct", 0)),
            max_drawdown_pct=float(o.get("max_drawdown_pct", 0)),
        )
        extrinsics.append(r)

    if exploration_bonuses is None:
        exploration_bonuses = [0.0] * len(outcomes)

    combined_list = [
        combined_reward(ext, exp_b, alpha)
        for ext, exp_b in zip(extrinsics, exploration_bonuses)
    ]

    advantages = group_relative_advantage(combined_list)

    results = []
    for i in range(len(outcomes)):
        results.append({
            "extrinsic": round(extrinsics[i], 6),
            "intrinsic": round(exploration_bonuses[i], 6),
            "combined": round(combined_list[i], 6),
            "advantage": round(advantages[i], 6),
        })
    return results
