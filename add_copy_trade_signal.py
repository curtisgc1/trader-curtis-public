#!/usr/bin/env python3
"""
Add copy-trade call rows into copy_trades for downstream candidate generation.
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
        CREATE TABLE IF NOT EXISTS copy_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_handle TEXT,
            ticker TEXT,
            call_type TEXT,
            entry_price REAL,
            call_timestamp TEXT,
            copied_timestamp TEXT,
            shares INTEGER,
            copied_entry REAL,
            stop_loss REAL,
            target REAL,
            status TEXT,
            outcome TEXT,
            pnl_pct REAL,
            lag_seconds INTEGER,
            notes TEXT
        )
        """
    )
    conn.commit()


def normalize_direction(value: str) -> str:
    v = str(value or "").strip().lower()
    if v in {"long", "buy", "bull", "bullish", "calls"}:
        return "LONG"
    if v in {"short", "sell", "bear", "bearish", "puts"}:
        return "SHORT"
    return "LONG"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="copy source handle, e.g. NoLimitGains")
    parser.add_argument("--ticker", required=True, help="ticker symbol")
    parser.add_argument("--direction", required=True, help="long/short")
    parser.add_argument("--entry", type=float, default=0.0, help="entry/call price")
    parser.add_argument("--stop", type=float, default=0.0, help="stop loss price")
    parser.add_argument("--target", type=float, default=0.0, help="target price")
    parser.add_argument("--shares", type=int, default=0, help="optional intended shares")
    parser.add_argument("--status", default="OPEN", help="OPEN|PENDING|CLOSED")
    parser.add_argument("--call-ts", default="", help="ISO timestamp for original call")
    parser.add_argument("--notes", default="", help="notes")
    args = parser.parse_args()

    call_ts = args.call_ts.strip() or now_iso()
    copied_ts = now_iso()
    direction = normalize_direction(args.direction)
    status = str(args.status or "OPEN").strip().upper()
    if status not in {"OPEN", "PENDING", "CLOSED"}:
        status = "OPEN"

    conn = sqlite3.connect(str(DB_PATH))
    try:
        init_table(conn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO copy_trades
            (source_handle, ticker, call_type, entry_price, call_timestamp, copied_timestamp, shares,
             copied_entry, stop_loss, target, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.source.strip(),
                args.ticker.strip().upper(),
                direction,
                float(args.entry or 0.0),
                call_ts,
                copied_ts,
                int(args.shares or 0),
                float(args.entry or 0.0),
                float(args.stop or 0.0),
                float(args.target or 0.0),
                status,
                args.notes.strip(),
            ),
        )
        conn.commit()
        print(
            f"Added copy trade id={cur.lastrowid} "
            f"source={args.source.strip()} ticker={args.ticker.strip().upper()} dir={direction} status={status}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

