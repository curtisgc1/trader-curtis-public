#!/usr/bin/env python3
"""
Polymarket execution scaffold.
Safe by default: requires explicit controls + credentials to place orders.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _control(conn: sqlite3.Connection, key: str, default: str = "0") -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          strategy_id TEXT NOT NULL DEFAULT '',
          candidate_id INTEGER NOT NULL DEFAULT 0,
          market_id TEXT NOT NULL DEFAULT '',
          outcome TEXT NOT NULL DEFAULT '',
          side TEXT NOT NULL DEFAULT '',
          price REAL NOT NULL DEFAULT 0,
          size REAL NOT NULL DEFAULT 0,
          order_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'queued',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def main() -> int:
    conn = _connect()
    try:
        ensure_table(conn)
        enabled = _control(conn, "enable_polymarket_auto", "0") == "1"
        live = _control(conn, "allow_polymarket_live", "0") == "1"
        if not enabled:
            print("POLY_EXEC: skipped (enable_polymarket_auto=0)")
            return 0
        # Placeholder for live/posting integration via py-clob-client.
        # Keep safe until credentials + dry-run tests are validated.
        mode = "live" if live else "paper"
        print(f"POLY_EXEC: scaffold active in {mode} mode (no order posting yet)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
