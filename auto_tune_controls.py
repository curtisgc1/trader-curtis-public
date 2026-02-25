#!/usr/bin/env python3
"""
Background auto-tuner for execution controls.
Generates control recommendations from learning tables and applies only when explicitly enabled.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS control_tuning_recommendations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          key TEXT NOT NULL,
          current_value TEXT NOT NULL,
          proposed_value TEXT NOT NULL,
          confidence REAL NOT NULL,
          reason TEXT NOT NULL,
          applied INTEGER NOT NULL DEFAULT 0,
          applied_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_tuning_recommendations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL,
          recommendation TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _get_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    if not table_exists(conn, "execution_controls"):
        return {}
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    return {str(k): str(v) for k, v in cur.fetchall()}


def _f(v: object, d: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return float(d)


def _i(v: object, d: int = 0) -> int:
    try:
        return int(float(v))  # type: ignore[arg-type]
    except Exception:
        return int(d)


def _record_control_rec(
    conn: sqlite3.Connection,
    key: str,
    current: str,
    proposed: str,
    confidence: float,
    reason: str,
    apply_now: bool,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO control_tuning_recommendations
        (created_at, key, current_value, proposed_value, confidence, reason, applied, applied_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            key,
            str(current),
            str(proposed),
            float(confidence),
            str(reason)[:320],
            1 if apply_now else 0,
            now_iso() if apply_now else "",
        ),
    )
    if apply_now:
        conn.execute(
            """
            INSERT INTO execution_controls (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (str(key), str(proposed), now_iso()),
        )
    return int(cur.lastrowid or 0)


def _score_threshold_recommendation(conn: sqlite3.Connection, controls: Dict[str, str], apply_now: bool) -> int:
    if not table_exists(conn, "route_feedback_features") or not table_exists(conn, "route_outcomes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          SUM(CASE WHEN f.route_score >= 60 THEN 1 ELSE 0 END) AS hi_n,
          SUM(CASE WHEN f.route_score >= 60 AND o.resolution='win' THEN 1 ELSE 0 END) AS hi_w,
          SUM(CASE WHEN f.route_score < 60 THEN 1 ELSE 0 END) AS lo_n,
          SUM(CASE WHEN f.route_score < 60 AND o.resolution='win' THEN 1 ELSE 0 END) AS lo_w
        FROM route_outcomes o
        JOIN route_feedback_features f ON f.route_id = o.route_id
        WHERE COALESCE(o.outcome_type,'realized') IN ('realized','operational')
        """
    )
    row = cur.fetchone() or (0, 0, 0, 0)
    hi_n, hi_w, lo_n, lo_w = [int(x or 0) for x in row]
    if hi_n < 20 or lo_n < 20:
        return 0
    hi_wr = (hi_w / hi_n) * 100.0
    lo_wr = (lo_w / lo_n) * 100.0
    delta = hi_wr - lo_wr
    current = _i(controls.get("min_candidate_score"), 50)
    proposed = current
    reason = ""
    confidence = 0.0
    if delta >= 8 and current < 80:
        proposed = min(80, current + 5)
        reason = f"High-score routes outperform low-score routes by {delta:.2f}pp (n_hi={hi_n}, n_lo={lo_n})"
        confidence = min(0.9, 0.55 + (delta / 30.0))
    elif delta <= -8 and current > 35:
        proposed = max(35, current - 5)
        reason = f"Low-score routes outperform high-score routes by {abs(delta):.2f}pp (n_hi={hi_n}, n_lo={lo_n})"
        confidence = min(0.9, 0.55 + (abs(delta) / 30.0))
    if proposed == current:
        return 0
    _record_control_rec(
        conn=conn,
        key="min_candidate_score",
        current=str(current),
        proposed=str(proposed),
        confidence=round(confidence, 4),
        reason=reason,
        apply_now=apply_now,
    )
    return 1


def _venue_threshold_recommendations(conn: sqlite3.Connection, controls: Dict[str, str], apply_now: bool) -> int:
    if not table_exists(conn, "input_feature_stats"):
        return 0
    cur = conn.cursor()
    changed = 0
    venue_key_map: Dict[str, Tuple[str, int]] = {
        "alpaca": ("alpaca_min_route_score", _i(controls.get("alpaca_min_route_score"), 60)),
        "hyperliquid": ("hyperliquid_min_route_score", _i(controls.get("hyperliquid_min_route_score"), 60)),
    }
    for venue, (ctl_key, current) in venue_key_map.items():
        cur.execute(
            """
            SELECT sample_size, win_rate
            FROM input_feature_stats
            WHERE dimension='venue' AND dimension_value=? AND outcome_type IN ('realized','operational')
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (venue,),
        )
        row = cur.fetchone()
        if not row:
            continue
        n = int(row[0] or 0)
        wr = float(row[1] or 0.0)
        if n < 20:
            continue
        proposed = current
        confidence = 0.0
        reason = ""
        if wr < 35 and current < 85:
            proposed = min(85, current + 5)
            reason = f"{venue} win_rate={wr:.2f}% with n={n}; tighten threshold"
            confidence = min(0.85, 0.55 + ((35 - wr) / 35.0) * 0.25)
        elif wr > 55 and current > 45:
            proposed = max(45, current - 5)
            reason = f"{venue} win_rate={wr:.2f}% with n={n}; can loosen threshold"
            confidence = min(0.85, 0.55 + ((wr - 55) / 45.0) * 0.25)
        if proposed != current:
            _record_control_rec(conn, ctl_key, str(current), str(proposed), round(confidence, 4), reason, apply_now)
            changed += 1
    return changed


def _source_recommendations(conn: sqlite3.Connection, min_samples: int) -> int:
    if not table_exists(conn, "source_learning_stats"):
        return 0
    cur = conn.cursor()
    cur.execute("DELETE FROM source_tuning_recommendations")
    cur.execute(
        """
        SELECT source_tag, sample_size, win_rate, avg_pnl_percent
        FROM source_learning_stats
        WHERE sample_size >= ?
        ORDER BY sample_size DESC
        """,
        (int(min_samples),),
    )
    rows = cur.fetchall()
    written = 0
    for source_tag, n, wr, avgp in rows:
        n = int(n or 0)
        wr = float(wr or 0.0)
        avgp = float(avgp or 0.0)
        rec = "hold"
        if wr < 35 and avgp < 0:
            rec = "downweight_source"
        elif wr > 58 and avgp > 0:
            rec = "upweight_source"
        cur.execute(
            """
            INSERT INTO source_tuning_recommendations
            (created_at, source_tag, sample_size, win_rate, avg_pnl_percent, recommendation)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), str(source_tag), n, wr, avgp, rec),
        )
        written += 1
    return written


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        ensure_tables(conn)
        controls = _get_controls(conn)
        apply_now = str(controls.get("auto_tuner_apply", "0")).strip() == "1"
        thresholds_unlocked = str(controls.get("threshold_override_unlocked", "0")).strip() == "1"
        if apply_now and not thresholds_unlocked:
            apply_now = False
        min_samples = _i(controls.get("allocator_min_source_samples"), 12)

        control_changes = 0
        control_changes += _score_threshold_recommendation(conn, controls, apply_now)
        # Refresh controls after possible change.
        controls = _get_controls(conn)
        control_changes += _venue_threshold_recommendations(conn, controls, apply_now)
        source_rows = _source_recommendations(conn, min_samples=min_samples)

        conn.commit()
        mode = "apply" if apply_now else "propose"
        print(
            f"Auto-tuner ({mode}): control_recommendations={control_changes}, "
            f"source_recommendations={source_rows}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
