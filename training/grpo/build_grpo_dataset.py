#!/usr/bin/env python3
"""
Build GRPO training/eval datasets from internal outcomes + optional Kaggle polymarket export.

Outputs:
- datasets/grpo_train.jsonl
- datasets/grpo_eval.jsonl
- datasets/grpo_summary.json
"""

import argparse
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "trades.db"
OUT_DIR = ROOT / "datasets"


def _parse_dt(s: str) -> float:
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _direction_from_pnl(p: float) -> str:
    if p > 0.05:
        return "long"
    if p < -0.05:
        return "short"
    return "neutral"


def _strength_from_abs(p: float) -> str:
    return "strong" if abs(p) >= 1.0 else "weak"


def _sortino_adjustment(
    pnl_pct: float,
    volatility_pct: float,
    max_drawdown_pct: float,
) -> float:
    """Sortino-inspired risk adjustment: reward risk-efficient trades, penalize drawdown.

    Returns a value in [-0.3, +0.15] that adjusts the base HGRM reward.
    - Low-volatility wins get a bonus (up to +0.15)
    - High-drawdown trades get a penalty (up to -0.3)
    - Trades with no risk data get 0 (neutral)
    """
    if volatility_pct <= 0 and max_drawdown_pct <= 0:
        return 0.0

    adj = 0.0

    # Downside penalty: drawdown > 2% starts penalizing, caps at -0.3
    if max_drawdown_pct > 2.0:
        dd_penalty = min(0.3, (max_drawdown_pct - 2.0) / 10.0)
        adj -= dd_penalty

    # Risk-efficiency bonus for wins: low volatility + positive pnl = good
    if pnl_pct > 0.05 and volatility_pct > 0:
        # Sortino-like ratio: return / downside risk proxy
        sortino_like = pnl_pct / max(volatility_pct, 0.5)
        # Bonus capped at +0.15 for sortino_like >= 1.5
        adj += min(0.15, sortino_like * 0.1)

    # High-vol losses get extra penalty
    if pnl_pct < -0.05 and volatility_pct > 5.0:
        adj -= min(0.1, (volatility_pct - 5.0) / 20.0)

    return round(max(-0.3, min(0.15, adj)), 6)


def _hgrm_target(
    pnl_pct: float,
    route_score: float,
    predicted_direction: str,
    volatility_pct: float = 0.0,
    max_drawdown_pct: float = 0.0,
) -> Dict[str, Any]:
    realized_dir = _direction_from_pnl(float(pnl_pct))
    pred = (predicted_direction or "").lower().strip()
    if pred in {"buy", "bullish"}:
        pred = "long"
    elif pred in {"sell", "bearish"}:
        pred = "short"
    elif pred not in {"long", "short", "neutral"}:
        pred = "neutral"

    if pred == realized_dir:
        dir_score = 1.0
    elif pred == "neutral" or realized_dir == "neutral":
        dir_score = -0.2
    else:
        dir_score = -1.0
    dir_gate = 0 if dir_score < 0 else 1

    expected_mag = min(1.0, abs(float(route_score)) / 100.0)
    actual_mag = min(1.0, abs(float(pnl_pct)) / 10.0)
    mag_score = max(0.0, 1.0 - abs(expected_mag - actual_mag))
    pnl_score = (max(-1.0, min(1.0, (float(pnl_pct) / 5.0))) + 1.0) / 2.0

    sortino_adj = _sortino_adjustment(
        float(pnl_pct), float(volatility_pct), float(max_drawdown_pct),
    )

    if dir_gate == 0:
        reward = -0.5 + 0.2 * (pnl_score * 2.0 - 1.0) + sortino_adj
    else:
        reward = 0.55 * dir_score + 0.35 * pnl_score + 0.10 * mag_score + sortino_adj

    # Clamp final reward to [-1, 1]
    reward = max(-1.0, min(1.0, reward))

    return {
        "predicted_direction": pred,
        "realized_direction": realized_dir,
        "trading_strength": _strength_from_abs(float(pnl_pct)),
        "dir_gate": dir_gate,
        "dir_score": round(dir_score, 6),
        "magnitude_score": round(mag_score, 6),
        "pnl_score": round(pnl_score, 6),
        "sortino_adjustment": round(sortino_adj, 6),
        "hgrm_reward": round(float(reward), 6),
    }


def _internal_rows(include_operational: bool, wins_only: bool = False) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        where = "1=1" if include_operational else "COALESCE(ro.outcome_type,'realized')='realized'"
        if wins_only:
            where += " AND COALESCE(ro.resolution,'') = 'win'"

        # Check if quant_validations exists for Sortino enrichment
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quant_validations'")
        has_quant = cur.fetchone() is not None

        if has_quant:
            cur.execute(
                f"""
                SELECT
                  ro.route_id,
                  COALESCE(ro.resolved_at,''),
                  COALESCE(ro.outcome_type,'realized'),
                  COALESCE(ro.pnl_percent,0.0),
                  COALESCE(rf.ticker,''),
                  COALESCE(rf.source_tag,''),
                  COALESCE(rf.strategy_tag,''),
                  COALESCE(rf.venue,''),
                  COALESCE(rf.direction,''),
                  COALESCE(rf.route_score,0.0),
                  COALESCE(qv.volatility_percent, 0.0),
                  COALESCE(qv.max_drawdown_percent, 0.0)
                FROM route_outcomes ro
                LEFT JOIN route_feedback_features rf ON rf.route_id = ro.route_id
                LEFT JOIN quant_validations qv
                  ON UPPER(qv.ticker) = UPPER(COALESCE(rf.ticker,''))
                  AND qv.source_tag = COALESCE(rf.source_tag,'')
                  AND qv.id = (
                    SELECT qv2.id FROM quant_validations qv2
                    WHERE UPPER(qv2.ticker) = UPPER(COALESCE(rf.ticker,''))
                      AND qv2.source_tag = COALESCE(rf.source_tag,'')
                    ORDER BY ABS(julianday(qv2.validated_at) - julianday(COALESCE(ro.resolved_at,'')))
                    LIMIT 1
                  )
                WHERE {where}
                ORDER BY datetime(ro.resolved_at) ASC
                """
            )
        else:
            cur.execute(
                f"""
                SELECT
                  ro.route_id,
                  COALESCE(ro.resolved_at,''),
                  COALESCE(ro.outcome_type,'realized'),
                  COALESCE(ro.pnl_percent,0.0),
                  COALESCE(rf.ticker,''),
                  COALESCE(rf.source_tag,''),
                  COALESCE(rf.strategy_tag,''),
                  COALESCE(rf.venue,''),
                  COALESCE(rf.direction,''),
                  COALESCE(rf.route_score,0.0),
                  0.0,
                  0.0
                FROM route_outcomes ro
                LEFT JOIN route_feedback_features rf ON rf.route_id = ro.route_id
                WHERE {where}
                ORDER BY datetime(ro.resolved_at) ASC
                """
            )

        rows = []
        for (
            route_id,
            resolved_at,
            outcome_type,
            pnl_pct,
            ticker,
            source_tag,
            strategy_tag,
            venue,
            pred_dir,
            route_score,
            vol_pct,
            dd_pct,
        ) in cur.fetchall():
            target = _hgrm_target(
                float(pnl_pct or 0.0),
                float(route_score or 0.0),
                str(pred_dir or ""),
                volatility_pct=float(vol_pct or 0.0),
                max_drawdown_pct=float(dd_pct or 0.0),
            )
            prompt = (
                "You are an event-driven trader.\n"
                f"Ticker: {ticker}\n"
                f"Venue: {venue}\n"
                f"Source: {source_tag}\n"
                f"Strategy: {strategy_tag}\n"
                f"Route score: {float(route_score or 0.0):.2f}\n"
                "Task: output direction (long/short/neutral), expected move strength (weak/strong), and concise rationale."
            )
            rows.append(
                {
                    "group_id": f"internal:{int(route_id)}",
                    "timestamp": str(resolved_at or ""),
                    "source": "internal",
                    "outcome_type": str(outcome_type or "realized"),
                    "prompt": prompt,
                    "target": target,
                    "meta": {
                        "route_id": int(route_id),
                        "ticker": ticker,
                        "venue": venue,
                        "source_tag": source_tag,
                        "strategy_tag": strategy_tag,
                        "pnl_percent": float(pnl_pct or 0.0),
                        "volatility_pct": float(vol_pct or 0.0),
                        "max_drawdown_pct": float(dd_pct or 0.0),
                        "trade_taken": True,
                    },
                }
            )
        return rows
    finally:
        conn.close()


def _counterfactual_wins(horizon_hours: int = 24) -> List[Dict[str, Any]]:
    """
    Load WINS from route_outcomes_horizons for routes the agent did NOT take.
    These are calls the signal pipeline made correctly but were blocked by thresholds.
    Wins here improve input rankings (source_tag performance) and GRPO training quality.

    Only includes resolution='win' — losses are excluded to avoid training on noise.
    horizon_hours: which horizon to use as primary truth (default 24h = 1-day).
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        # Check table exists
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='route_outcomes_horizons'")
        if not cur.fetchone():
            return []
        cur.execute(
            """
            SELECT
              h.route_id,
              h.ticker,
              h.source_tag,
              h.venue,
              h.direction,
              h.decision,
              h.pnl_percent,
              h.horizon_hours,
              h.evaluated_at,
              h.outcome_type,
              COALESCE(rf.strategy_tag, '') as strategy_tag,
              COALESCE(rf.route_score, 0.0) as route_score
            FROM route_outcomes_horizons h
            LEFT JOIN route_feedback_features rf ON rf.route_id = h.route_id
            WHERE h.resolution = 'win'
              AND h.horizon_hours = ?
              AND COALESCE(h.pnl_percent, 0) > 0
            ORDER BY datetime(h.evaluated_at) ASC
            """,
            (int(horizon_hours),),
        )
        rows = []
        for (
            route_id, ticker, source_tag, venue, direction, decision,
            pnl_pct, h_hours, evaluated_at, outcome_type, strategy_tag, route_score
        ) in cur.fetchall():
            pnl = float(pnl_pct or 0.0)
            target = _hgrm_target(pnl, float(route_score or 0.0), str(direction or ""))
            was_taken = str(decision or "").lower() == "approved"
            prompt = (
                "You are an event-driven trader evaluating a signal that was flagged by the pipeline.\n"
                f"Ticker: {ticker}\n"
                f"Venue: {venue}\n"
                f"Source: {source_tag}\n"
                f"Strategy: {strategy_tag}\n"
                f"Route score: {float(route_score or 0.0):.2f}\n"
                f"Horizon: {h_hours}h\n"
                f"Trade taken by agent: {'yes' if was_taken else 'no (threshold blocked)'}\n"
                "Task: output direction (long/short/neutral), expected move strength (weak/strong), and concise rationale."
            )
            rows.append(
                {
                    "group_id": f"counterfactual:{int(route_id)}:h{h_hours}",
                    "timestamp": str(evaluated_at or ""),
                    "source": "counterfactual_win",
                    "outcome_type": str(outcome_type or "counterfactual"),
                    "horizon_hours": int(h_hours),
                    "trade_taken": was_taken,
                    "prompt": prompt,
                    "target": target,
                    "meta": {
                        "route_id": int(route_id),
                        "ticker": ticker,
                        "venue": venue,
                        "source_tag": source_tag,
                        "strategy_tag": strategy_tag,
                        "pnl_percent": pnl,
                        "horizon_hours": int(h_hours),
                        "trade_taken": was_taken,
                        "decision": str(decision or ""),
                    },
                }
            )
        return rows
    finally:
        conn.close()


def _load_kaggle(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            q = str(obj.get("question") or obj.get("market") or "").strip()
            if not q:
                continue
            outcome = str(obj.get("outcome") or obj.get("resolved_outcome") or obj.get("winner") or "").strip().lower()
            if outcome in {"yes", "up", "long", "true", "1"}:
                realized = "long"
            elif outcome in {"no", "down", "short", "false", "0"}:
                realized = "short"
            else:
                realized = "neutral"
            rows.append(
                {
                    "group_id": f"kaggle:{len(rows)+1}",
                    "timestamp": str(obj.get("resolved_at") or obj.get("end_date") or ""),
                    "source": "kaggle_polymarket",
                    "outcome_type": "realized",
                    "prompt": f"Market question: {q}\nTask: predict YES/NO direction and confidence.",
                    "target": {
                        "predicted_direction": "neutral",
                        "realized_direction": realized,
                        "trading_strength": "weak",
                        "dir_gate": 1,
                        "dir_score": 1.0,
                        "magnitude_score": 0.5,
                        "pnl_score": 0.5,
                        "hgrm_reward": 0.5,
                    },
                    "meta": {"question": q},
                }
            )
        return rows

    # csv fallback
    with path.open("r", newline="", encoding="utf-8", errors="ignore") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            q = str(r.get("question") or r.get("market") or r.get("title") or "").strip()
            if not q:
                continue
            outcome = str(r.get("outcome") or r.get("resolved_outcome") or r.get("winner") or "").strip().lower()
            if outcome in {"yes", "up", "long", "true", "1"}:
                realized = "long"
            elif outcome in {"no", "down", "short", "false", "0"}:
                realized = "short"
            else:
                realized = "neutral"
            rows.append(
                {
                    "group_id": f"kaggle:{len(rows)+1}",
                    "timestamp": str(r.get("resolved_at") or r.get("end_date") or ""),
                    "source": "kaggle_polymarket",
                    "outcome_type": "realized",
                    "prompt": f"Market question: {q}\nTask: predict YES/NO direction and confidence.",
                    "target": {
                        "predicted_direction": "neutral",
                        "realized_direction": realized,
                        "trading_strength": "weak",
                        "dir_gate": 1,
                        "dir_score": 1.0,
                        "magnitude_score": 0.5,
                        "pnl_score": 0.5,
                        "hgrm_reward": 0.5,
                    },
                    "meta": {"question": q},
                }
            )
    return rows


def _kaggle_table_rows() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              COALESCE(question,''),
              COALESCE(resolved_direction,'neutral'),
              COALESCE(close_time,''),
              COALESCE(category,''),
              COALESCE(market_slug,'')
            FROM polymarket_kaggle_markets
            ORDER BY datetime(close_time) ASC
            """
        )
        rows: List[Dict[str, Any]] = []
        for question, resolved, close_time, category, slug in cur.fetchall():
            q = str(question or "").strip()
            if not q:
                continue
            r = str(resolved or "neutral").strip().lower()
            if r not in {"long", "short", "neutral"}:
                r = "neutral"
            rows.append(
                {
                    "group_id": f"kaggle_table:{len(rows)+1}",
                    "timestamp": str(close_time or ""),
                    "source": "kaggle_polymarket",
                    "outcome_type": "realized",
                    "prompt": f"Market question: {q}\nTask: predict YES/NO direction and confidence.",
                    "target": {
                        "predicted_direction": "neutral",
                        "realized_direction": r,
                        "trading_strength": "weak",
                        "dir_gate": 1,
                        "dir_score": 1.0,
                        "magnitude_score": 0.5,
                        "pnl_score": 0.5,
                        "hgrm_reward": 0.5,
                    },
                    "meta": {"question": q, "category": category, "slug": slug},
                }
            )
        return rows
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _candidate_outcome_rows() -> List[Dict[str, Any]]:
    """Load scored candidate outcomes from the truth layer (candidate_horizon_outcomes)."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_horizon_outcomes'")
        if not cur.fetchone():
            return []
        cur.execute(
            """
            SELECT candidate_ticker, candidate_direction, candidate_source_tag,
                   candidate_score, horizon_hours, pnl_percent,
                   resolution, evaluated_at
            FROM candidate_horizon_outcomes
            WHERE entry_price > 0 AND eval_price > 0
            ORDER BY datetime(evaluated_at) ASC
            """
        )
        rows: List[Dict[str, Any]] = []
        for ticker, direction, source_tag, score, h_hours, pnl_pct, resolution, evaluated_at in cur.fetchall():
            target = _hgrm_target(float(pnl_pct or 0.0), float(score or 0.0), str(direction or ""))
            prompt = (
                "You are an event-driven trader evaluating a signal candidate.\n"
                f"Ticker: {ticker}\n"
                f"Source: {source_tag}\n"
                f"Candidate score: {float(score or 0.0):.2f}\n"
                f"Horizon: {h_hours}h\n"
                "Task: output direction (long/short/neutral), expected move strength (weak/strong), and concise rationale."
            )
            rows.append({
                "group_id": f"candidate:{ticker}:{evaluated_at}:h{h_hours}",
                "timestamp": str(evaluated_at or ""),
                "source": "candidate_outcome",
                "outcome_type": "candidate_counterfactual",
                "prompt": prompt,
                "target": target,
                "meta": {
                    "ticker": ticker,
                    "source_tag": source_tag,
                    "pnl_percent": float(pnl_pct or 0.0),
                    "horizon_hours": int(h_hours),
                    "trade_taken": False,
                },
            })
        return rows
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _split(rows: List[Dict[str, Any]], eval_ratio: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = sorted(rows, key=lambda x: _parse_dt(str(x.get("timestamp") or "")))
    if not rows:
        return [], []
    n_eval = max(1, int(len(rows) * eval_ratio))
    if len(rows) < 10:
        n_eval = min(1, len(rows))
    return rows[:-n_eval], rows[-n_eval:]


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GRPO dataset from internal + optional external outcomes")
    parser.add_argument("--kaggle-file", default="", help="Optional Kaggle Polymarket export (.csv or .jsonl)")
    parser.add_argument("--include-operational", action="store_true", help="Include operational outcomes (not recommended)")
    parser.add_argument("--no-internal", action="store_true", help="Exclude internal outcomes")
    parser.add_argument("--no-kaggle-table", action="store_true", help="Exclude rows from polymarket_kaggle_markets table")
    parser.add_argument("--no-counterfactual", action="store_true", help="Exclude counterfactual wins from non-taken routes")
    parser.add_argument("--wins-only", action="store_true",
                        help="Only include winning calls in GRPO training (recommended). "
                             "Losses excluded — model learns from what worked, not what didn't.")
    parser.add_argument("--counterfactual-horizon", type=int, default=24,
                        help="Which horizon (hours) to use for counterfactual wins (default: 24 = 1 day)")
    parser.add_argument("--kaggle-max-pct", type=float, default=0.0,
                        help="Maximum percentage of final dataset that can be Kaggle rows (0=exclude entirely)")
    parser.add_argument("--include-candidate-outcomes", action="store_true",
                        help="Include candidate_horizon_outcomes as training data (truth layer)")
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    args = parser.parse_args()

    rows: List[Dict[str, Any]] = []

    # Internal realized/operational outcomes from taken trades
    if not bool(args.no_internal):
        rows.extend(_internal_rows(
            include_operational=bool(args.include_operational),
            wins_only=bool(args.wins_only),
        ))

    # Counterfactual wins: calls the pipeline made correctly but agent didn't take
    # These teach the model what good signals look like regardless of threshold decisions
    if not bool(args.no_counterfactual):
        cf_rows = _counterfactual_wins(horizon_hours=int(args.counterfactual_horizon))
        rows.extend(cf_rows)

    # Candidate horizon outcomes (truth layer — scored candidates regardless of trade status)
    if bool(args.include_candidate_outcomes):
        co_rows = _candidate_outcome_rows()
        rows.extend(co_rows)

    # Kaggle Polymarket historical markets (gated by --kaggle-max-pct)
    kaggle_max_pct = float(args.kaggle_max_pct)
    kaggle_rows: List[Dict[str, Any]] = []
    if kaggle_max_pct > 0:
        if not bool(args.no_kaggle_table):
            kaggle_rows.extend(_kaggle_table_rows())
        if args.kaggle_file:
            kaggle_rows.extend(_load_kaggle(Path(args.kaggle_file)))

        # Cap Kaggle rows to max percentage of total dataset
        if kaggle_rows and rows:
            internal_count = len(rows)
            max_kaggle = int((internal_count / (1.0 - kaggle_max_pct / 100.0)) * (kaggle_max_pct / 100.0))
            if len(kaggle_rows) > max_kaggle:
                kaggle_rows = kaggle_rows[:max_kaggle]
        rows.extend(kaggle_rows)
    elif not bool(args.no_kaggle_table) and kaggle_max_pct <= 0:
        pass  # Skip Kaggle entirely when max_pct is 0

    train, eval_rows = _split(rows, eval_ratio=float(args.eval_ratio))
    train_path = OUT_DIR / "grpo_train.jsonl"
    eval_path = OUT_DIR / "grpo_eval.jsonl"
    summary_path = OUT_DIR / "grpo_summary.json"

    _write_jsonl(train_path, train)
    _write_jsonl(eval_path, eval_rows)

    cf_taken = sum(1 for r in rows if r.get("source") == "counterfactual_win" and r.get("trade_taken"))
    cf_not_taken = sum(1 for r in rows if r.get("source") == "counterfactual_win" and not r.get("trade_taken"))
    candidate_outcome_count = sum(1 for r in rows if r.get("source") == "candidate_outcome")
    kaggle_count = sum(1 for r in rows if r.get("source") == "kaggle_polymarket")
    internal_count = sum(1 for r in rows if r.get("source") == "internal")
    total = len(rows)
    kaggle_pct = round((kaggle_count / total) * 100.0, 1) if total > 0 else 0.0

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": total,
        "train_rows": len(train),
        "eval_rows": len(eval_rows),
        "wins_only": bool(args.wins_only),
        "include_operational": bool(args.include_operational),
        "include_candidate_outcomes": bool(args.include_candidate_outcomes),
        "kaggle_max_pct": float(args.kaggle_max_pct),
        "kaggle_actual_pct": kaggle_pct,
        "counterfactual_horizon_hours": int(args.counterfactual_horizon),
        "kaggle_file": args.kaggle_file or "",
        "sources": {
            "internal_taken": internal_count,
            "counterfactual_wins_taken": cf_taken,
            "counterfactual_wins_not_taken": cf_not_taken,
            "candidate_outcomes": candidate_outcome_count,
            "kaggle_polymarket": kaggle_count,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Wrote: {train_path}")
    print(f"Wrote: {eval_path}")
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
