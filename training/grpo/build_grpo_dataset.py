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


def _hgrm_target(pnl_pct: float, route_score: float, predicted_direction: str) -> Dict[str, Any]:
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

    if dir_gate == 0:
        reward = -0.5 + 0.2 * (pnl_score * 2.0 - 1.0)
    else:
        reward = 0.55 * dir_score + 0.35 * pnl_score + 0.10 * mag_score

    return {
        "predicted_direction": pred,
        "realized_direction": realized_dir,
        "trading_strength": _strength_from_abs(float(pnl_pct)),
        "dir_gate": dir_gate,
        "dir_score": round(dir_score, 6),
        "magnitude_score": round(mag_score, 6),
        "pnl_score": round(pnl_score, 6),
        "hgrm_reward": round(float(reward), 6),
    }


def _internal_rows(include_operational: bool) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        where = "1=1" if include_operational else "COALESCE(ro.outcome_type,'realized')='realized'"
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
              COALESCE(rf.route_score,0.0)
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
        ) in cur.fetchall():
            target = _hgrm_target(float(pnl_pct or 0.0), float(route_score or 0.0), str(pred_dir or ""))
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
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    args = parser.parse_args()

    rows: List[Dict[str, Any]] = []
    if not bool(args.no_internal):
        rows.extend(_internal_rows(include_operational=bool(args.include_operational)))
    if not bool(args.no_kaggle_table):
        rows.extend(_kaggle_table_rows())
    if args.kaggle_file:
        rows.extend(_load_kaggle(Path(args.kaggle_file)))

    train, eval_rows = _split(rows, eval_ratio=float(args.eval_ratio))
    train_path = OUT_DIR / "grpo_train.jsonl"
    eval_path = OUT_DIR / "grpo_eval.jsonl"
    summary_path = OUT_DIR / "grpo_summary.json"

    _write_jsonl(train_path, train)
    _write_jsonl(eval_path, eval_rows)

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": len(rows),
        "train_rows": len(train),
        "eval_rows": len(eval_rows),
        "include_operational": bool(args.include_operational),
        "kaggle_file": args.kaggle_file or "",
        "sources": {
            "internal": sum(1 for r in rows if r.get("source") == "internal"),
            "kaggle_polymarket": sum(1 for r in rows if r.get("source") == "kaggle_polymarket"),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary))
    print(f"Wrote: {train_path}")
    print(f"Wrote: {eval_path}")
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
