#!/usr/bin/env python3
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).parent / "data" / "trades.db"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser(description="Add/update tracked polymarket wallet/profile")
    p.add_argument("--handle", required=True)
    p.add_argument("--profile-url", default="")
    p.add_argument("--role", default="alpha", choices=["alpha", "copy", "both"])
    p.add_argument("--notes", default="")
    args = p.parse_args()

    conn = sqlite3.connect(str(DB))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_polymarket_wallets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              handle TEXT NOT NULL UNIQUE,
              profile_url TEXT NOT NULL DEFAULT '',
              role_copy INTEGER NOT NULL DEFAULT 1,
              role_alpha INTEGER NOT NULL DEFAULT 1,
              active INTEGER NOT NULL DEFAULT 1,
              notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        role_copy = 1 if args.role in {"copy", "both"} else 0
        role_alpha = 1 if args.role in {"alpha", "both"} else 0
        conn.execute(
            """
            INSERT INTO tracked_polymarket_wallets
            (created_at, updated_at, handle, profile_url, role_copy, role_alpha, active, notes)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(handle) DO UPDATE SET
              updated_at=excluded.updated_at,
              profile_url=excluded.profile_url,
              role_copy=excluded.role_copy,
              role_alpha=excluded.role_alpha,
              notes=excluded.notes,
              active=1
            """,
            (now_iso(), now_iso(), args.handle.strip().lstrip("@"), args.profile_url.strip(), role_copy, role_alpha, args.notes.strip()),
        )
        conn.commit()
        cur = conn.cursor()
        cur.execute("SELECT handle, role_copy, role_alpha, active, profile_url FROM tracked_polymarket_wallets ORDER BY updated_at DESC LIMIT 10")
        for r in cur.fetchall():
            print("|".join([str(x) for x in r]))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
