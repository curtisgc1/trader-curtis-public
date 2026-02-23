#!/usr/bin/env python3
"""
Add external strategy/call signals (e.g., X post URLs) into trader pipeline.
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT,
          source TEXT,
          source_url TEXT,
          ticker TEXT,
          direction TEXT,
          confidence REAL,
          notes TEXT,
          status TEXT DEFAULT 'new'
        )
        """
    )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="signal source handle, e.g. ZenomTrader")
    parser.add_argument("--url", required=True, help="source post/link")
    parser.add_argument("--ticker", required=True, help="ticker symbol")
    parser.add_argument("--direction", required=True, choices=["long", "short"], help="trade direction")
    parser.add_argument("--confidence", type=float, default=0.6, help="0.0-1.0 confidence")
    parser.add_argument("--notes", default="", help="thesis/notes")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        init_table(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO external_signals
            (created_at, source, source_url, ticker, direction, confidence, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
            """,
            (
                now_iso(),
                args.source,
                args.url,
                args.ticker.upper(),
                args.direction,
                max(0.0, min(args.confidence, 1.0)),
                args.notes,
            ),
        )
        conn.commit()
        print(f"Added external signal id={cur.lastrowid} source={args.source} ticker={args.ticker.upper()}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
