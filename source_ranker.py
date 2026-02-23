#!/usr/bin/env python3
"""
Compute source reliability scores from routed decisions and execution outcomes.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_scores (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          approved_rate REAL NOT NULL,
          executed_rate REAL NOT NULL,
          reliability_score REAL NOT NULL
        )
        """
    )
    conn.commit()


def compute() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_table(conn)
        if not table_exists(conn, "signal_routes"):
            print("Source ranker: signal_routes missing, nothing to score")
            return 0

        cur = conn.cursor()
        learning = {}
        if table_exists(conn, "source_learning_stats"):
            cur.execute(
                """
                SELECT source_tag, sample_size, win_rate, avg_pnl_percent
                FROM source_learning_stats
                """
            )
            for src, n, win_rate, avg_pnl_pct in cur.fetchall():
                learning[src] = {
                    "n": int(n or 0),
                    "win_rate": float(win_rate or 0.0),
                    "avg_pnl_pct": float(avg_pnl_pct or 0.0),
                }

        cur.execute(
            """
            SELECT COALESCE(source_tag,'internal') AS src,
                   COUNT(*) AS total,
                   SUM(CASE WHEN decision='approved' THEN 1 ELSE 0 END) AS approved_count,
                   SUM(CASE WHEN status='executed' THEN 1 ELSE 0 END) AS executed_count
            FROM signal_routes
            WHERE COALESCE(source_tag,'') NOT LIKE 'manual-%'
            GROUP BY src
            """
        )
        rows = cur.fetchall()
        cur.execute("DELETE FROM source_scores")
        for src, total, approved_count, executed_count in rows:
            total = int(total or 0)
            approved_count = int(approved_count or 0)
            executed_count = int(executed_count or 0)
            if total <= 0:
                continue
            approved_rate = approved_count / total
            executed_rate = executed_count / total

            # Base reliability from routing/execution throughput.
            base = approved_rate * 0.65 + executed_rate * 0.35

            # Blend in realized learning if available.
            lr = learning.get(src)
            if lr and lr["n"] > 0:
                win_rate_component = max(0.0, min(1.0, lr["win_rate"] / 100.0))
                # Map avg pnl% to [0,1] with a conservative clamp.
                pnl_component = max(0.0, min(1.0, 0.5 + (lr["avg_pnl_pct"] / 20.0)))
                reliability = round((base * 0.60 + win_rate_component * 0.25 + pnl_component * 0.15) * 100, 2)
            else:
                reliability = round(base * 100, 2)

            cur.execute(
                """
                INSERT INTO source_scores
                (computed_at, source_tag, sample_size, approved_rate, executed_rate, reliability_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now_iso(), src, total, round(approved_rate, 4), round(executed_rate, 4), reliability),
            )
        conn.commit()
        print(f"Source ranker: scored {len(rows)} sources")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(compute())
