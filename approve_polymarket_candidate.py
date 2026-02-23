#!/usr/bin/env python3
"""Approve Polymarket candidates for execution."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve one or more polymarket candidates")
    parser.add_argument("ids", nargs="+", type=int, help="candidate ids")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        updated = 0
        for cid in args.ids:
            cur.execute(
                "UPDATE polymarket_candidates SET status='approved' WHERE id=?",
                (int(cid),),
            )
            updated += cur.rowcount
        conn.commit()
        print(f"approved_candidates={updated} at={now_iso()}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
