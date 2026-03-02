#!/usr/bin/env python3
"""
EMPO² Dataset Builder — Convert trade outcomes to EMPO² training format.

Paper reference: arXiv:2602.23008

Builds on the existing GRPO dataset format but adds:
  1. Dual prompts (with/without tips) per sample
  2. Exploration bonuses
  3. Combined rewards (HGRM + intrinsic)
  4. On/off-policy labels per sample

Output: datasets/empo_train.jsonl, datasets/empo_eval.jsonl
"""

import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_buffer import (
    ensure_tables as ensure_memory_tables,
    retrieve_tips,
    format_tips_for_prompt,
    compute_exploration_bonus,
    store_tip,
    generate_tip,
    buffer_size,
)
from .reward import (
    hgrm_reward,
    combined_reward,
    group_relative_advantage,
)
from .rollout import (
    build_prompt,
    build_prompt_with_tips,
    DEFAULT_MEMORY_PROB,
    DEFAULT_OFFPOLICY_PROB,
)

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "trades.db"
OUT_DIR = ROOT / "datasets"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _load_internal_outcomes(
    include_operational: bool = True,
) -> List[Dict[str, Any]]:
    """Load realized trade outcomes from route_outcomes."""
    conn = _connect()
    try:
        cur = conn.cursor()
        where = "1=1" if include_operational else "COALESCE(ro.outcome_type,'realized')='realized'"

        cur.execute(
            f"""
            SELECT
              ro.route_id,
              COALESCE(ro.resolved_at, ''),
              COALESCE(ro.outcome_type, 'realized'),
              COALESCE(ro.pnl_percent, 0.0),
              COALESCE(rf.ticker, ''),
              COALESCE(rf.source_tag, ''),
              COALESCE(rf.strategy_tag, ''),
              COALESCE(rf.venue, ''),
              COALESCE(rf.direction, ''),
              COALESCE(rf.route_score, 0.0)
            FROM route_outcomes ro
            LEFT JOIN route_feedback_features rf ON rf.route_id = ro.route_id
            WHERE {where}
            ORDER BY datetime(ro.resolved_at) ASC
            """
        )

        rows = []
        for (route_id, resolved_at, outcome_type, pnl_pct, ticker,
             source_tag, strategy_tag, venue, pred_dir, route_score) in cur.fetchall():
            rows.append({
                "route_id": int(route_id),
                "resolved_at": str(resolved_at),
                "outcome_type": str(outcome_type),
                "pnl_percent": float(pnl_pct or 0),
                "ticker": str(ticker),
                "source_tag": str(source_tag),
                "strategy_tag": str(strategy_tag),
                "venue": str(venue),
                "predicted_direction": str(pred_dir),
                "route_score": float(route_score or 0),
            })
        return rows
    finally:
        conn.close()


def _load_polymarket_outcomes() -> List[Dict[str, Any]]:
    """Load resolved Polymarket orders as additional outcomes."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='polymarket_orders'")
        if not cur.fetchone():
            return []

        # polymarket_orders has: id, created_at, strategy_id, candidate_id,
        # market_id, outcome, side, price, size, order_id, status, notes
        # No resolved_at or pnl columns — derive from candidate data
        cur.execute(
            """
            SELECT
              po.id,
              COALESCE(po.created_at, ''),
              po.side,
              po.price,
              po.size,
              COALESCE(pc.slug, ''),
              COALESCE(pc.question, ''),
              COALESCE(pc.outcome, ''),
              COALESCE(pc.strategy_id, po.strategy_id, ''),
              COALESCE(pc.source_tag, ''),
              COALESCE(pc.implied_prob, 0.0),
              COALESCE(pc.model_prob, 0.0),
              COALESCE(pc.edge, 0.0)
            FROM polymarket_orders po
            LEFT JOIN polymarket_candidates pc ON pc.id = po.candidate_id
            WHERE po.status IN ('filled', 'resolved', 'matched')
            ORDER BY datetime(po.created_at) ASC
            """
        )

        rows = []
        for (order_id, created_at, side, price, size, slug, question,
             outcome, strategy_id, source_tag, implied, model_prob, edge) in cur.fetchall():
            # Use edge as proxy for PnL when no resolved outcome exists
            edge_f = float(edge or 0)
            direction = str(side or "").lower()
            if direction not in ("long", "short"):
                direction = "long" if edge_f > 0 else "neutral"
            rows.append({
                "route_id": int(order_id) + 100000,
                "resolved_at": str(created_at),
                "outcome_type": "operational",
                "pnl_percent": edge_f,
                "ticker": str(slug)[:20],
                "source_tag": str(source_tag or strategy_id),
                "strategy_tag": str(strategy_id),
                "venue": "polymarket",
                "predicted_direction": direction,
                "route_score": float(model_prob or 0) * 100,
            })
        return rows
    finally:
        conn.close()


def build_empo_dataset(
    memory_prob: float = DEFAULT_MEMORY_PROB,
    exploration_alpha: float = 0.1,
    train_ratio: float = 0.8,
    seed: int = 42,
    ollama_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build EMPO² training dataset from all available outcomes.

    For each outcome:
    1. Compute HGRM reward (extrinsic)
    2. Compute exploration bonus (intrinsic)
    3. Generate dual prompts (with/without tips)
    4. Generate post-episode tip and store in memory buffer
    5. Label on-policy vs off-policy

    Returns summary dict.
    """
    random.seed(seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load all outcomes
    internal = _load_internal_outcomes(include_operational=True)
    polymarket = _load_polymarket_outcomes()
    all_outcomes = internal + polymarket
    all_outcomes.sort(key=lambda x: x.get("resolved_at", ""))

    if not all_outcomes:
        print("EMPO²: No outcomes found. Need realized trades first.")
        return {"total": 0, "train": 0, "eval": 0}

    conn = _connect()
    ensure_memory_tables(conn)

    samples = []
    rewards_all = []

    for outcome in all_outcomes:
        ticker = outcome["ticker"]
        venue = outcome["venue"]
        source_tag = outcome["source_tag"]
        strategy_tag = outcome["strategy_tag"]
        route_score = outcome["route_score"]
        pnl_pct = outcome["pnl_percent"]
        pred_dir = outcome["predicted_direction"]

        # 1. Compute extrinsic reward
        ext_reward = hgrm_reward(
            pnl_percent=pnl_pct,
            route_score=route_score,
            predicted_direction=pred_dir,
        )

        # 2. Compute exploration bonus
        exp_bonus = compute_exploration_bonus(
            conn, ticker, venue, source_tag,
        )

        # 3. Combined reward
        total_reward = combined_reward(ext_reward, exp_bonus, exploration_alpha)
        rewards_all.append(total_reward)

        # 4. Build standard prompt (no tips)
        prompt_standard = build_prompt(
            ticker, venue, source_tag, strategy_tag, route_score,
        )

        # 5. Retrieve tips and build memory prompt
        tips = retrieve_tips(
            conn, ticker=ticker, venue=venue, source_tag=source_tag,
        )
        prompt_memory = build_prompt_with_tips(
            ticker, venue, source_tag, strategy_tag, route_score,
            tips=tips,
        )

        # 6. Determine rollout mode
        use_memory = random.random() < memory_prob
        use_offpolicy = use_memory and (random.random() < DEFAULT_OFFPOLICY_PROB)

        # 7. Build target completion (what the model should output)
        realized_dir = "long" if pnl_pct > 0.05 else "short" if pnl_pct < -0.05 else "neutral"
        strength = "strong" if abs(pnl_pct) > 3.0 else "weak"
        completion = (
            f"Direction: {realized_dir}\n"
            f"Strength: {strength}\n"
            f"Rationale: {source_tag} signal on {ticker} ({venue}) "
            f"resulted in {pnl_pct:+.1f}% PnL. "
            f"Route score was {route_score:.0f}."
        )

        sample = {
            "group_id": f"empo:{outcome['route_id']}",
            "timestamp": outcome["resolved_at"],
            "source": outcome.get("outcome_type", "realized"),
            "prompt_standard": prompt_standard,
            "prompt_memory": prompt_memory if tips else prompt_standard,
            "completion": completion,
            "tips_count": len(tips),
            "mode": "memory" if use_memory else "standard",
            "use_offpolicy": use_offpolicy,
            "reward": {
                "extrinsic": round(ext_reward, 6),
                "intrinsic": round(exp_bonus, 6),
                "combined": round(total_reward, 6),
            },
            "meta": {
                "route_id": outcome["route_id"],
                "ticker": ticker,
                "venue": venue,
                "source_tag": source_tag,
                "pnl_percent": pnl_pct,
                "route_score": route_score,
            },
        }
        samples.append(sample)

        # 8. Generate and store post-episode tip
        tip_text = generate_tip(
            ticker=ticker, venue=venue, source_tag=source_tag,
            direction=pred_dir, pnl_percent=pnl_pct,
            route_score=route_score, hgrm_reward=ext_reward,
            strategy_tag=strategy_tag,
            ollama_model=ollama_model,
        )
        store_tip(
            conn, tip_text=tip_text, ticker=ticker, venue=venue,
            source_tag=source_tag, route_id=outcome["route_id"],
            hgrm_reward=ext_reward, pnl_percent=pnl_pct,
            direction=pred_dir,
        )

    # Compute group-relative advantages
    advantages = group_relative_advantage(rewards_all)
    for i, sample in enumerate(samples):
        sample["reward"]["advantage"] = round(advantages[i], 6)

    # Temporal split (earliest 80% train, latest 20% eval)
    split_idx = int(len(samples) * train_ratio)
    train_samples = samples[:split_idx]
    eval_samples = samples[split_idx:]

    # Write output files
    train_path = OUT_DIR / "empo_train.jsonl"
    eval_path = OUT_DIR / "empo_eval.jsonl"

    with open(train_path, "w") as f:
        for s in train_samples:
            f.write(json.dumps(s) + "\n")
    with open(eval_path, "w") as f:
        for s in eval_samples:
            f.write(json.dumps(s) + "\n")

    # Summary
    summary = {
        "total": len(samples),
        "train": len(train_samples),
        "eval": len(eval_samples),
        "internal_outcomes": len(internal),
        "polymarket_outcomes": len(polymarket),
        "memory_buffer_size": buffer_size(conn),
        "avg_reward": round(sum(rewards_all) / len(rewards_all), 4) if rewards_all else 0,
        "memory_mode_count": sum(1 for s in samples if s["mode"] == "memory"),
        "offpolicy_count": sum(1 for s in samples if s["use_offpolicy"]),
        "built_at": datetime.now().isoformat(),
    }

    summary_path = OUT_DIR / "empo_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    conn.close()
    return summary


# ---------------------------------------------------------------------------
# MLX LoRA format conversion
# ---------------------------------------------------------------------------

def convert_to_mlx_lora(
    empo_jsonl: Path,
    output_path: Path,
) -> int:
    """
    Convert EMPO² dataset to MLX LoRA format (prompt/completion pairs).

    For memory-mode samples: uses prompt_memory
    For standard samples: uses prompt_standard
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(empo_jsonl) as fin, open(output_path, "w") as fout:
        for line in fin:
            if not line.strip():
                continue
            sample = json.loads(line)

            # Use appropriate prompt based on mode
            if sample.get("mode") == "memory" and not sample.get("use_offpolicy"):
                prompt = sample["prompt_memory"]
            else:
                prompt = sample["prompt_standard"]

            mlx_sample = {
                "prompt": prompt,
                "completion": sample["completion"],
            }
            fout.write(json.dumps(mlx_sample) + "\n")
            count += 1

    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build EMPO² training dataset")
    parser.add_argument("--memory-prob", type=float, default=DEFAULT_MEMORY_PROB)
    parser.add_argument("--alpha", type=float, default=0.1, help="Exploration bonus weight")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--ollama-model", type=str, default=None, help="LLM for tip generation")
    parser.add_argument("--mlx", action="store_true", help="Also generate MLX LoRA format")
    args = parser.parse_args()

    print("=" * 60)
    print("EMPO² DATASET BUILDER")
    print("=" * 60)

    summary = build_empo_dataset(
        memory_prob=args.memory_prob,
        exploration_alpha=args.alpha,
        train_ratio=args.train_ratio,
        ollama_model=args.ollama_model,
    )

    print(f"\n  Total samples:       {summary['total']}")
    print(f"  Train:               {summary['train']}")
    print(f"  Eval:                {summary['eval']}")
    print(f"  Internal outcomes:   {summary['internal_outcomes']}")
    print(f"  Polymarket outcomes: {summary['polymarket_outcomes']}")
    print(f"  Memory buffer tips:  {summary['memory_buffer_size']}")
    print(f"  Avg reward:          {summary['avg_reward']:.4f}")
    print(f"  Memory mode:         {summary['memory_mode_count']}")
    print(f"  Off-policy:          {summary['offpolicy_count']}")

    if args.mlx and summary["train"] > 0:
        print("\n  Converting to MLX LoRA format...")
        mlx_dir = OUT_DIR / "mlx_empo_lora"
        mlx_dir.mkdir(parents=True, exist_ok=True)

        train_count = convert_to_mlx_lora(
            OUT_DIR / "empo_train.jsonl",
            mlx_dir / "train.jsonl",
        )
        eval_count = convert_to_mlx_lora(
            OUT_DIR / "empo_eval.jsonl",
            mlx_dir / "valid.jsonl",
        )
        print(f"  MLX train: {train_count}, MLX valid: {eval_count}")

    print("\nDone.")
