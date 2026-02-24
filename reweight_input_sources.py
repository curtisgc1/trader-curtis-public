#!/usr/bin/env python3
"""
Auto-reweight input sources from historical outcomes.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


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

        conn.commit()
        print(f"INPUT_REWEIGHT updates={updates} disabled={disabled} min_samples={min_samples} floor={floor} ceiling={ceiling}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
