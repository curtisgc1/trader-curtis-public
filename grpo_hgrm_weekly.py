#!/usr/bin/env python3
"""
Weekly HGRM/GRPO-style alignment pass using realized outcomes.
- Builds hierarchical-gated reward samples from live route outcomes.
- Produces per-input reward aggregates.
- Optionally applies smoothed weight updates to input_source_controls.
- Optionally asks local Ollama model for a concise policy note.

This is an alignment layer; it does NOT place trades or bypass risk controls.
"""

import json
import math
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def sign_direction_from_pnl(pnl_pct: float, eps: float = 0.05) -> str:
    if pnl_pct > eps:
        return "long"
    if pnl_pct < -eps:
        return "short"
    return "neutral"


def norm_direction(v: str) -> str:
    s = (v or "").strip().lower()
    if s in {"buy", "long", "bullish"}:
        return "long"
    if s in {"sell", "short", "bearish"}:
        return "short"
    return "neutral"


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alignment_reward_samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          route_id INTEGER NOT NULL UNIQUE,
          outcome_type TEXT NOT NULL,
          venue TEXT NOT NULL DEFAULT '',
          ticker TEXT NOT NULL DEFAULT '',
          source_tag TEXT NOT NULL DEFAULT '',
          strategy_tag TEXT NOT NULL DEFAULT '',
          predicted_direction TEXT NOT NULL DEFAULT 'neutral',
          realized_direction TEXT NOT NULL DEFAULT 'neutral',
          route_score REAL NOT NULL DEFAULT 0,
          pnl_percent REAL NOT NULL DEFAULT 0,
          dir_gate INTEGER NOT NULL DEFAULT 1,
          dir_score REAL NOT NULL DEFAULT 0,
          magnitude_score REAL NOT NULL DEFAULT 0,
          pnl_score REAL NOT NULL DEFAULT 0,
          hgrm_reward REAL NOT NULL DEFAULT 0,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alignment_policy_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ran_at TEXT NOT NULL,
          model TEXT NOT NULL DEFAULT '',
          sample_size INTEGER NOT NULL DEFAULT 0,
          applied_updates INTEGER NOT NULL DEFAULT 0,
          summary TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alignment_reward_source
        ON alignment_reward_samples(source_tag)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alignment_reward_strategy
        ON alignment_reward_samples(strategy_tag)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS input_source_controls (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          source_key TEXT NOT NULL UNIQUE,
          source_label TEXT NOT NULL DEFAULT '',
          source_class TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          manual_weight REAL NOT NULL DEFAULT 1.0,
          auto_weight REAL NOT NULL DEFAULT 1.0,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def build_samples(conn: sqlite3.Connection, lookback_days: int) -> int:
    if not table_exists(conn, "route_outcomes") or not table_exists(conn, "route_feedback_features"):
        return 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          ro.route_id,
          COALESCE(ro.outcome_type,'realized') AS outcome_type,
          COALESCE(ro.pnl_percent,0.0) AS pnl_percent,
          COALESCE(rf.venue,''),
          COALESCE(rf.ticker,''),
          COALESCE(rf.source_tag,''),
          COALESCE(rf.strategy_tag,''),
          COALESCE(rf.direction,''),
          COALESCE(rf.route_score,0.0)
        FROM route_outcomes ro
        LEFT JOIN route_feedback_features rf ON rf.route_id = ro.route_id
        WHERE datetime(ro.resolved_at) >= datetime('now', ?)
          AND COALESCE(ro.outcome_type,'realized') = 'realized'
        """,
        (f"-{int(lookback_days)} days",),
    )
    rows = cur.fetchall()
    written = 0

    for route_id, outcome_type, pnl_pct, venue, ticker, source_tag, strategy_tag, pred_dir_raw, route_score in rows:
        pnl_pct = float(pnl_pct or 0.0)
        route_score = float(route_score or 0.0)
        pred_dir = norm_direction(pred_dir_raw)
        real_dir = sign_direction_from_pnl(pnl_pct)

        if pred_dir == "neutral" and real_dir == "neutral":
            dir_score = 0.25
        elif pred_dir == real_dir:
            dir_score = 1.0
        elif real_dir == "neutral" or pred_dir == "neutral":
            dir_score = -0.2
        else:
            dir_score = -1.0

        dir_gate = 0 if dir_score < 0 else 1

        expected_mag = clamp(abs(route_score) / 100.0, 0.0, 1.0)
        actual_mag = clamp(abs(pnl_pct) / 10.0, 0.0, 1.0)
        magnitude_score = clamp(1.0 - abs(expected_mag - actual_mag), 0.0, 1.0)

        pnl_score = math.tanh(pnl_pct / 5.0)
        pnl_score_01 = (pnl_score + 1.0) / 2.0

        if dir_score < 0:
            hgrm_reward = -0.5 + 0.2 * pnl_score
        else:
            hgrm_reward = (
                0.55 * dir_score
                + 0.35 * pnl_score_01
                + 0.10 * magnitude_score
            )
            hgrm_reward = hgrm_reward if dir_gate else hgrm_reward * 0.25

        cur.execute(
            """
            INSERT INTO alignment_reward_samples
            (
              created_at, route_id, outcome_type, venue, ticker,
              source_tag, strategy_tag, predicted_direction, realized_direction,
              route_score, pnl_percent, dir_gate, dir_score, magnitude_score, pnl_score, hgrm_reward, notes
            )
            VALUES
            (
              datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ''
            )
            ON CONFLICT(route_id) DO UPDATE SET
              created_at=excluded.created_at,
              outcome_type=excluded.outcome_type,
              venue=excluded.venue,
              ticker=excluded.ticker,
              source_tag=excluded.source_tag,
              strategy_tag=excluded.strategy_tag,
              predicted_direction=excluded.predicted_direction,
              realized_direction=excluded.realized_direction,
              route_score=excluded.route_score,
              pnl_percent=excluded.pnl_percent,
              dir_gate=excluded.dir_gate,
              dir_score=excluded.dir_score,
              magnitude_score=excluded.magnitude_score,
              pnl_score=excluded.pnl_score,
              hgrm_reward=excluded.hgrm_reward
            """,
            (
                int(route_id),
                str(outcome_type),
                str(venue),
                str(ticker),
                str(source_tag),
                str(strategy_tag),
                pred_dir,
                real_dir,
                float(route_score),
                float(pnl_pct),
                int(dir_gate),
                float(dir_score),
                float(magnitude_score),
                float(pnl_score),
                float(hgrm_reward),
            ),
        )
        written += 1

    conn.commit()
    return written


def _target_weight(avg_reward: float, floor: float, ceiling: float) -> float:
    # Reward roughly in [-1, +1] -> weight in [floor, ceiling]
    w = 1.0 + (avg_reward - 0.5) * 0.8
    return clamp(round(w, 6), floor, ceiling)


def apply_updates(conn: sqlite3.Connection, min_samples: int, floor: float, ceiling: float, apply_live: bool) -> Tuple[int, Dict[str, Dict[str, float]]]:
    cur = conn.cursor()

    updates: Dict[str, Dict[str, float]] = {}

    cur.execute(
        """
        SELECT source_tag, COUNT(*) AS n, AVG(hgrm_reward) AS r
        FROM alignment_reward_samples
        WHERE COALESCE(source_tag,'') <> ''
        GROUP BY source_tag
        HAVING COUNT(*) >= ?
        """,
        (int(min_samples),),
    )
    for source_tag, n, avg_r in cur.fetchall():
        key = f"source:{str(source_tag).lower()}"
        updates[key] = {"n": int(n), "avg_r": float(avg_r or 0.0), "class": "source_tag", "label": f"Source {source_tag}"}

    cur.execute(
        """
        SELECT strategy_tag, COUNT(*) AS n, AVG(hgrm_reward) AS r
        FROM alignment_reward_samples
        WHERE COALESCE(strategy_tag,'') <> ''
        GROUP BY strategy_tag
        HAVING COUNT(*) >= ?
        """,
        (int(min_samples),),
    )
    for strategy_tag, n, avg_r in cur.fetchall():
        key = f"pipeline:{str(strategy_tag).upper()}"
        updates[key] = {"n": int(n), "avg_r": float(avg_r or 0.0), "class": "pipeline", "label": f"Pipeline {strategy_tag}"}

    applied = 0
    if apply_live:
        for key, payload in updates.items():
            new_w = _target_weight(payload["avg_r"], floor, ceiling)
            cur.execute("SELECT auto_weight FROM input_source_controls WHERE source_key=? LIMIT 1", (key,))
            row = cur.fetchone()
            old_w = float(row[0]) if row and row[0] is not None else 1.0
            blended = round(old_w * 0.7 + new_w * 0.3, 6)
            cur.execute(
                """
                INSERT INTO input_source_controls
                (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                VALUES (datetime('now'), datetime('now'), ?, ?, ?, 1, 1.0, ?, 'grpo_hgrm_weekly')
                ON CONFLICT(source_key) DO UPDATE SET
                  updated_at=datetime('now'),
                  auto_weight=excluded.auto_weight,
                  notes=excluded.notes
                """,
                (key, payload["label"], payload["class"], float(blended)),
            )
            applied += 1
        conn.commit()

    return applied, updates


def ollama_summary(model: str, updates: Dict[str, Dict[str, float]]) -> str:
    top = sorted(updates.items(), key=lambda kv: kv[1]["avg_r"], reverse=True)[:10]
    bottom = sorted(updates.items(), key=lambda kv: kv[1]["avg_r"])[:10]
    prompt = {
        "task": "Summarize weekly trading alignment from HGRM reward stats.",
        "format": "3 bullet policy notes, max 120 words, no hype.",
        "top": [{"key": k, **v} for k, v in top],
        "bottom": [{"key": k, **v} for k, v in bottom],
    }
    p = subprocess.run(
        ["ollama", "run", model],
        input=json.dumps(prompt),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    out = (p.stdout or "").strip()
    if not out:
        return f"No model output (code={p.returncode})"
    return out[:4000]


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        ensure_tables(conn)

        enabled = get_control(conn, "grpo_alignment_enabled", "1") == "1"
        if not enabled:
            print("GRPO_HGRM disabled")
            return 0

        lookback_days = int(float(get_control(conn, "grpo_alignment_lookback_days", "30") or 30))
        min_samples = int(float(get_control(conn, "grpo_alignment_min_samples", "8") or 8))
        floor = float(get_control(conn, "grpo_alignment_weight_floor", "0.6") or 0.6)
        ceiling = float(get_control(conn, "grpo_alignment_weight_ceiling", "1.6") or 1.6)
        apply_live = get_control(conn, "grpo_apply_weight_updates", "0") == "1"
        use_llm = get_control(conn, "grpo_llm_reasoner_enabled", "1") == "1"
        model = get_control(conn, "grpo_local_model", "qwen2.5:14b")

        sample_count = build_samples(conn, lookback_days=lookback_days)
        applied_updates, updates = apply_updates(
            conn,
            min_samples=min_samples,
            floor=floor,
            ceiling=ceiling,
            apply_live=apply_live,
        )

        summary = (
            f"samples={sample_count} inputs={len(updates)} applied={applied_updates} "
            f"lookback_days={lookback_days} min_samples={min_samples} apply_live={int(apply_live)}"
        )

        if use_llm and updates:
            try:
                llm = ollama_summary(model, updates)
                summary = summary + "\n" + llm
            except Exception as e:
                summary = summary + f"\nollama_summary_error={e}"

        conn.execute(
            """
            INSERT INTO alignment_policy_runs (ran_at, model, sample_size, applied_updates, summary)
            VALUES (datetime('now'), ?, ?, ?, ?)
            """,
            (str(model), int(sample_count), int(applied_updates), str(summary)),
        )
        conn.commit()

        print("GRPO_HGRM", summary)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
