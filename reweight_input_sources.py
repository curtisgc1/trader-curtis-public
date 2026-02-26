#!/usr/bin/env python3
"""
Auto-reweight input sources from historical outcomes.

Sources are scored against multiple time horizons:
  24h  = 1-day (scalp)
  168h = 7-day (swing)
  336h = 14-day (medium)
  720h = 30-day (long-term)

Horizon stats are written to input_source_controls.notes as JSON so the dashboard
can display per-input performance by time horizon.

auto_weight blends 24h and 168h win rates equally when both have samples.
Falls back to all-time win rate when horizon data is thin.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

HORIZON_LABELS: Dict[int, str] = {
    24: "1d",
    168: "7d",
    336: "14d",
    720: "30d",
}


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_table(conn: sqlite3.Connection) -> None:
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


def _ctl(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def _weight_from_perf(win_rate: float, sample_size: int, min_samples: int, floor: float, ceiling: float) -> float:
    if sample_size < min_samples:
        return 1.0
    confidence = min(1.0, float(sample_size) / 30.0)
    drift = ((float(win_rate) - 50.0) / 50.0) * 0.8 * confidence
    w = 1.0 + drift
    return max(floor, min(ceiling, round(w, 6)))


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA busy_timeout=20000")
    try:
        ensure_table(conn)
        enabled = _ctl(conn, "input_auto_reweight_enabled", "1") == "1"
        if not enabled:
            print("INPUT_REWEIGHT disabled")
            return 0

        min_samples = int(float(_ctl(conn, "input_weight_min_samples", "5") or 5))
        floor = float(_ctl(conn, "input_weight_floor", "0.6") or 0.6)
        ceiling = float(_ctl(conn, "input_weight_ceiling", "1.6") or 1.6)
        auto_disable_threshold = float(_ctl(conn, "input_auto_disable_threshold", "0.0") or 0.0)
        updates = 0
        disabled = 0
        cur = conn.cursor()

        if table_exists(conn, "source_learning_stats"):
            cur.execute(
                """
                SELECT source_tag, sample_size, win_rate
                FROM source_learning_stats
                """
            )
            for source_tag, sample_size, win_rate in cur.fetchall():
                tag = str(source_tag or "").strip()
                if not tag:
                    continue
                w = _weight_from_perf(float(win_rate or 0.0), int(sample_size or 0), min_samples, floor, ceiling)
                enabled_flag = 0 if (auto_disable_threshold > 0 and int(sample_size or 0) >= min_samples and w < auto_disable_threshold) else 1
                for key in (f"source:{tag.lower()}",):
                    conn.execute(
                        """
                        INSERT INTO input_source_controls
                        (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                        VALUES (datetime('now'), datetime('now'), ?, ?, 'source_tag', ?, 1.0, ?, '')
                        ON CONFLICT(source_key) DO UPDATE SET
                          updated_at=datetime('now'),
                          enabled=excluded.enabled,
                          auto_weight=excluded.auto_weight
                        """,
                        (key, f"Source {tag}", int(enabled_flag), float(w)),
                    )
                    updates += 1
                    if enabled_flag == 0:
                        disabled += 1

        if table_exists(conn, "strategy_learning_stats"):
            cur.execute(
                """
                SELECT strategy_tag, sample_size, win_rate
                FROM strategy_learning_stats
                """
            )
            for strategy_tag, sample_size, win_rate in cur.fetchall():
                tag = str(strategy_tag or "").strip().upper()
                if not tag:
                    continue
                w = _weight_from_perf(float(win_rate or 0.0), int(sample_size or 0), min_samples, floor, ceiling)
                enabled_flag = 0 if (auto_disable_threshold > 0 and int(sample_size or 0) >= min_samples and w < auto_disable_threshold) else 1
                conn.execute(
                    """
                    INSERT INTO input_source_controls
                    (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                    VALUES (datetime('now'), datetime('now'), ?, ?, 'pipeline', ?, 1.0, ?, '')
                    ON CONFLICT(source_key) DO UPDATE SET
                      updated_at=datetime('now'),
                      enabled=excluded.enabled,
                      auto_weight=excluded.auto_weight
                    """,
                    (f"pipeline:{tag}", f"Pipeline {tag}", int(enabled_flag), float(w)),
                )
                updates += 1
                if enabled_flag == 0:
                    disabled += 1

        if table_exists(conn, "input_feature_stats"):
            cur.execute(
                """
                SELECT dimension, dimension_value, sample_size, win_rate
                FROM input_feature_stats
                WHERE outcome_type='all'
                  AND dimension IN ('source_tag','strategy_tag')
                """
            )
            for dim, dim_val, sample_size, win_rate in cur.fetchall():
                d = str(dim or "")
                v = str(dim_val or "").strip()
                if not v:
                    continue
                w = _weight_from_perf(float(win_rate or 0.0), int(sample_size or 0), min_samples, floor, ceiling)
                enabled_flag = 0 if (auto_disable_threshold > 0 and int(sample_size or 0) >= min_samples and w < auto_disable_threshold) else 1
                if d == "source_tag":
                    key = f"source:{v.lower()}"
                    label = f"Source {v}"
                    klass = "source_tag"
                else:
                    key = f"pipeline:{v.upper()}"
                    label = f"Pipeline {v}"
                    klass = "pipeline"
                conn.execute(
                    """
                    INSERT INTO input_source_controls
                    (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                    VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, 1.0, ?, '')
                    ON CONFLICT(source_key) DO UPDATE SET
                      updated_at=datetime('now'),
                      enabled=excluded.enabled,
                      auto_weight=excluded.auto_weight
                    """,
                    (key, label, klass, int(enabled_flag), float(w)),
                )
                updates += 1
                if enabled_flag == 0:
                    disabled += 1

        # ── Horizon-aware reweighting from source_horizon_learning_stats ──
        # Reads wins/losses per source per horizon (1d, 7d, 14d, 30d).
        # Stores horizon breakdown in notes JSON for dashboard visibility.
        # Updates auto_weight with blended 1d+7d score when data is sufficient.
        horizon_updates = 0
        if table_exists(conn, "source_horizon_learning_stats"):
            # Aggregate horizon stats per source_tag
            cur.execute(
                """
                SELECT source_tag, horizon_hours, wins, losses, pushes, win_rate, sample_size
                FROM source_horizon_learning_stats
                WHERE horizon_hours IN (24, 168, 336, 720)
                ORDER BY source_tag, horizon_hours
                """
            )
            horizon_map: Dict[str, Dict[int, Dict]] = {}
            for tag, h_hours, wins, losses, pushes, win_rate_h, sample_h in cur.fetchall():
                t = str(tag or "").strip()
                if not t:
                    continue
                if t not in horizon_map:
                    horizon_map[t] = {}
                horizon_map[t][int(h_hours)] = {
                    "wins": int(wins or 0),
                    "losses": int(losses or 0),
                    "pushes": int(pushes or 0),
                    "win_rate": round(float(win_rate_h or 0.0), 1),
                    "sample": int(sample_h or 0),
                }

            for tag, horizons in horizon_map.items():
                # Build notes JSON with per-horizon breakdown
                horizon_notes: Dict[str, Dict] = {}
                for h_hours, stats in horizons.items():
                    label = HORIZON_LABELS.get(h_hours, f"{h_hours}h")
                    horizon_notes[label] = stats

                # Compute blended auto_weight from 1d and 7d win rates (primary trading horizons)
                d1 = horizons.get(24, {})
                d7 = horizons.get(168, {})
                d1_wr = float(d1.get("win_rate", 0.0))
                d7_wr = float(d7.get("win_rate", 0.0))
                d1_n = int(d1.get("sample", 0))
                d7_n = int(d7.get("sample", 0))

                # Only update auto_weight if we have enough horizon samples
                if d1_n >= min_samples or d7_n >= min_samples:
                    total_n = d1_n + d7_n
                    blended_wr = (
                        (d1_wr * d1_n + d7_wr * d7_n) / total_n
                        if total_n > 0 else 50.0
                    )
                    blended_n = max(d1_n, d7_n)
                    w = _weight_from_perf(blended_wr, blended_n, min_samples, floor, ceiling)
                    enabled_flag = 0 if (auto_disable_threshold > 0 and blended_n >= min_samples and w < auto_disable_threshold) else 1

                    notes_str = json.dumps({
                        "horizons": horizon_notes,
                        "blended_1d7d_win_rate": round(blended_wr, 1),
                        "auto_weight_source": "horizon_blend_1d7d",
                    }, separators=(",", ":"))

                    key = f"source:{tag.lower()}"
                    conn.execute(
                        """
                        INSERT INTO input_source_controls
                        (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                        VALUES (datetime('now'), datetime('now'), ?, ?, 'source_tag', ?, 1.0, ?, ?)
                        ON CONFLICT(source_key) DO UPDATE SET
                          updated_at=datetime('now'),
                          enabled=excluded.enabled,
                          auto_weight=excluded.auto_weight,
                          notes=excluded.notes
                        """,
                        (key, f"Source {tag}", int(enabled_flag), float(w), notes_str),
                    )
                    horizon_updates += 1
                else:
                    # Not enough data to update weight — just store the horizon notes
                    notes_str = json.dumps({
                        "horizons": horizon_notes,
                        "auto_weight_source": "insufficient_samples",
                    }, separators=(",", ":"))
                    key = f"source:{tag.lower()}"
                    conn.execute(
                        """
                        INSERT INTO input_source_controls
                        (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                        VALUES (datetime('now'), datetime('now'), ?, ?, 'source_tag', 1, 1.0, 1.0, ?)
                        ON CONFLICT(source_key) DO UPDATE SET
                          updated_at=datetime('now'),
                          notes=excluded.notes
                        """,
                        (key, f"Source {tag}", notes_str),
                    )

        conn.commit()
        print(
            f"INPUT_REWEIGHT updates={updates} horizon_updates={horizon_updates} "
            f"disabled={disabled} min_samples={min_samples} floor={floor} ceiling={ceiling}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
