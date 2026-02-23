#!/usr/bin/env python3
import sqlite3
import math
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).parent / "data" / "trades.db"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def main():
    conn = sqlite3.connect(str(DB))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS polymarket_wallet_scores (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              computed_at TEXT NOT NULL,
              handle TEXT NOT NULL,
              sample_size INTEGER NOT NULL DEFAULT 0,
              wins INTEGER NOT NULL DEFAULT 0,
              losses INTEGER NOT NULL DEFAULT 0,
              win_rate REAL NOT NULL DEFAULT 0,
              avg_pnl_pct REAL NOT NULL DEFAULT 0,
              reliability_score REAL NOT NULL DEFAULT 0
            )
            """
        )
        if not table_exists(conn, "tracked_polymarket_wallets"):
            print("wallet_score: no tracked wallets")
            return 0
        cur = conn.cursor()
        cur.execute("DELETE FROM polymarket_wallet_scores")

        cur.execute("SELECT handle FROM tracked_polymarket_wallets WHERE COALESCE(active,1)=1")
        wallets = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]

        n = 0
        for h in wallets:
            hl = h.lower()
            sample_size = wins = losses = 0
            avg_pnl_pct = 0.0

            if table_exists(conn, "copy_trades"):
                cur.execute(
                    """
                    SELECT
                      COUNT(*) AS n,
                      SUM(CASE WHEN lower(COALESCE(outcome,'')) IN ('win','winner','profit') OR COALESCE(pnl_pct,0) > 0 THEN 1 ELSE 0 END) AS wins,
                      SUM(CASE WHEN lower(COALESCE(outcome,'')) IN ('loss','loser') OR COALESCE(pnl_pct,0) < 0 THEN 1 ELSE 0 END) AS losses,
                      AVG(COALESCE(pnl_pct,0)) AS avg_pnl
                    FROM copy_trades
                    WHERE lower(COALESCE(source_handle,''))=?
                    """,
                    (hl,),
                )
                row = cur.fetchone() or (0, 0, 0, 0.0)
                sample_size = int(row[0] or 0)
                wins = int(row[1] or 0)
                losses = int(row[2] or 0)
                avg_pnl_pct = float(row[3] or 0.0)

            if sample_size == 0 and table_exists(conn, "source_learning_stats"):
                cur.execute(
                    """
                    SELECT sample_size, wins, losses, avg_pnl_percent
                    FROM source_learning_stats
                    WHERE lower(COALESCE(source_tag,'')) IN (?, ?, ?)
                    ORDER BY sample_size DESC
                    LIMIT 1
                    """,
                    (hl, f"copy:{hl}", f"poly_copy:{hl}"),
                )
                row = cur.fetchone()
                if row:
                    sample_size = int(row[0] or 0)
                    wins = int(row[1] or 0)
                    losses = int(row[2] or 0)
                    avg_pnl_pct = float(row[3] or 0.0)

            # External wallet snapshot fallback (no local trade sample yet).
            if sample_size == 0 and table_exists(conn, "polymarket_wallet_performance"):
                cur.execute(
                    """
                    SELECT trades_count, pnl_all, volume_all
                    FROM polymarket_wallet_performance
                    WHERE lower(COALESCE(handle,''))=?
                    ORDER BY synced_at DESC
                    LIMIT 1
                    """,
                    (hl,),
                )
                row = cur.fetchone()
                if row:
                    trades_count = int(row[0] or 0)
                    pnl_all = float(row[1] or 0.0)
                    _volume_all = float(row[2] or 0.0)

                    # Conservative estimate until we have resolved, local outcomes.
                    win_rate_est = 50.0
                    if pnl_all > 0:
                        win_rate_est = 58.0
                    elif pnl_all < 0:
                        win_rate_est = 42.0

                    sample_size = max(0, trades_count)
                    wins = int(round((win_rate_est / 100.0) * sample_size))
                    losses = max(0, sample_size - wins)
                    avg_pnl_pct = 0.0

            total = max(1, wins + losses)
            win_rate = (wins / total) * 100.0 if (wins + losses) > 0 else 0.0
            reliability = max(0.0, min(100.0, 0.65 * win_rate + 0.35 * (50.0 + avg_pnl_pct * 2.0)))
            if sample_size > 0 and table_exists(conn, "polymarket_wallet_performance"):
                cur.execute(
                    """
                    SELECT pnl_all, trades_count
                    FROM polymarket_wallet_performance
                    WHERE lower(COALESCE(handle,''))=?
                    ORDER BY synced_at DESC
                    LIMIT 1
                    """,
                    (hl,),
                )
                row = cur.fetchone()
                if row:
                    pnl_all = float(row[0] or 0.0)
                    trades_count = int(row[1] or 0)
                    pnl_component = max(-20.0, min(20.0, math.tanh(pnl_all / 50000.0) * 20.0))
                    activity_component = max(0.0, min(15.0, math.log10(max(1, trades_count)) * 5.0))
                    reliability = max(0.0, min(100.0, reliability + pnl_component + activity_component))

            conn.execute(
                """
                INSERT INTO polymarket_wallet_scores
                (computed_at, handle, sample_size, wins, losses, win_rate, avg_pnl_pct, reliability_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now_iso(), h, sample_size, wins, losses, round(win_rate, 4), round(avg_pnl_pct, 4), round(reliability, 4)),
            )
            n += 1

        conn.commit()
        print(f"wallet_score: scored {n} wallets")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
