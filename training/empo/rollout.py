#!/usr/bin/env python3
"""
EMPO² Rollout — Dual-mode trade evaluation (with/without memory tips).

Paper reference: arXiv:2602.23008, Section 3.1

Two rollout modes per iteration:
  1. Memory mode (prob p): Generate evaluation conditioned on retrieved tips
  2. Standard mode (prob 1-p): Generate evaluation without tips

This dual-mode approach teaches the model to internalize memory insights
into its parameters, so it performs well even without memory at test time.
"""

import json
import random
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory_buffer import (
    format_tips_for_prompt,
    retrieve_tips,
    generate_tip,
    store_tip,
    compute_exploration_bonus,
)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "trades.db"

# Probability of using memory-augmented rollout (paper: tuned per task)
DEFAULT_MEMORY_PROB = 0.6

# Probability of off-policy update for memory trajectories (paper: q)
DEFAULT_OFFPOLICY_PROB = 0.4


def build_prompt(
    ticker: str,
    venue: str,
    source_tag: str,
    strategy_tag: str = "",
    route_score: float = 0.0,
    timeframe: str = "",
    extra_context: str = "",
) -> str:
    """Build base evaluation prompt (no tips)."""
    return (
        "You are an event-driven trader.\n"
        f"Ticker: {ticker}\n"
        f"Venue: {venue}\n"
        f"Source: {source_tag}\n"
        f"Strategy: {strategy_tag}\n"
        f"Route score: {route_score:.2f}\n"
        + (f"Timeframe: {timeframe}\n" if timeframe else "")
        + (f"Context: {extra_context}\n" if extra_context else "")
        + "Task: output direction (long/short/neutral), expected move strength (weak/strong), and concise rationale."
    )


def build_prompt_with_tips(
    ticker: str,
    venue: str,
    source_tag: str,
    strategy_tag: str = "",
    route_score: float = 0.0,
    timeframe: str = "",
    tips: Optional[List[Dict[str, Any]]] = None,
    extra_context: str = "",
) -> str:
    """Build evaluation prompt with retrieved memory tips."""
    base = build_prompt(
        ticker, venue, source_tag, strategy_tag, route_score,
        timeframe, extra_context,
    )
    tip_section = format_tips_for_prompt(tips or [])
    if tip_section:
        return f"{tip_section}\n\n{base}"
    return base


def dual_mode_rollout(
    conn: sqlite3.Connection,
    trade_context: Dict[str, Any],
    memory_prob: float = DEFAULT_MEMORY_PROB,
) -> Dict[str, Any]:
    """
    Paper Algorithm 1: Dual-mode rollout for a single trade evaluation.

    With probability p: use memory-augmented prompt
    With probability 1-p: use standard prompt

    Returns:
        {
            "prompt_standard": str,
            "prompt_memory": str (or None),
            "tips": list,
            "mode": "memory" | "standard",
            "exploration_bonus": float,
            "use_offpolicy": bool,
        }
    """
    ticker = trade_context.get("ticker", "")
    venue = trade_context.get("venue", "")
    source_tag = trade_context.get("source_tag", "")
    strategy_tag = trade_context.get("strategy_tag", "")
    route_score = float(trade_context.get("route_score", 0))
    timeframe = trade_context.get("timeframe", "")

    # Always build standard prompt
    prompt_standard = build_prompt(
        ticker, venue, source_tag, strategy_tag, route_score, timeframe,
    )

    # Determine rollout mode
    use_memory = random.random() < memory_prob

    tips = []
    prompt_memory = None
    exploration_bonus = 0.0

    if use_memory:
        # Retrieve relevant tips from memory buffer
        tips = retrieve_tips(
            conn, ticker=ticker, venue=venue, source_tag=source_tag,
            timeframe=timeframe,
        )
        prompt_memory = build_prompt_with_tips(
            ticker, venue, source_tag, strategy_tag, route_score,
            timeframe, tips=tips,
        )

    # Compute exploration bonus (novel states get higher bonus)
    exploration_bonus = compute_exploration_bonus(
        conn, ticker, venue, source_tag, timeframe,
    )

    # For memory trajectories, decide on/off-policy update mode
    use_offpolicy = use_memory and (random.random() < DEFAULT_OFFPOLICY_PROB)

    return {
        "prompt_standard": prompt_standard,
        "prompt_memory": prompt_memory,
        "tips": tips,
        "mode": "memory" if use_memory else "standard",
        "exploration_bonus": exploration_bonus,
        "use_offpolicy": use_offpolicy,
    }


def post_episode_tip_generation(
    conn: sqlite3.Connection,
    trade_context: Dict[str, Any],
    outcome: Dict[str, Any],
    ollama_model: Optional[str] = None,
) -> Optional[int]:
    """
    Paper: After episode terminates, generate reflective tip and store in memory.

    Args:
        trade_context: ticker, venue, source_tag, etc.
        outcome: pnl_percent, hgrm_reward, direction, etc.
        ollama_model: Optional LLM for richer tips

    Returns: tip ID if stored, None if skipped
    """
    ticker = trade_context.get("ticker", "")
    venue = trade_context.get("venue", "")
    source_tag = trade_context.get("source_tag", "")
    timeframe = trade_context.get("timeframe", "")
    regime = trade_context.get("market_regime", "")

    pnl_pct = float(outcome.get("pnl_percent", 0))
    hgrm = float(outcome.get("hgrm_reward", 0))
    direction = str(outcome.get("direction", ""))
    route_score = float(outcome.get("route_score", 0))
    strategy_tag = trade_context.get("strategy_tag", "")

    tip_text = generate_tip(
        ticker=ticker, venue=venue, source_tag=source_tag,
        direction=direction, pnl_percent=pnl_pct,
        route_score=route_score, hgrm_reward=hgrm,
        strategy_tag=strategy_tag, timeframe=timeframe,
        market_regime=regime, ollama_model=ollama_model,
    )

    tip_id = store_tip(
        conn, tip_text=tip_text, ticker=ticker, venue=venue,
        source_tag=source_tag, timeframe=timeframe,
        market_regime=regime,
        route_id=outcome.get("route_id"),
        hgrm_reward=hgrm, pnl_percent=pnl_pct,
        direction=direction,
        metadata={"strategy_tag": strategy_tag},
    )

    return tip_id


def batch_rollout(
    conn: sqlite3.Connection,
    trade_contexts: List[Dict[str, Any]],
    memory_prob: float = DEFAULT_MEMORY_PROB,
) -> List[Dict[str, Any]]:
    """
    Generate rollouts for a batch of trade evaluations.
    Used during training to build the training batch.
    """
    return [
        dual_mode_rollout(conn, ctx, memory_prob)
        for ctx in trade_contexts
    ]
