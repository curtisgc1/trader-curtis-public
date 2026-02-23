#!/usr/bin/env python3
"""
Reconcile Alpaca paper order statuses into execution_orders.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict

import requests

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "trades.db"
ENV_PATH = BASE_DIR / ".env"

TRACK_STATUSES = {"new", "accepted", "pending_new", "partially_filled", "submitted"}
TERMINAL_STATUSES = {"filled", "canceled", "expired", "rejected", "stopped"}


def load_env() -> Dict[str, str]:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS route_trade_links (
          route_id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          source_tag TEXT NOT NULL DEFAULT '',
          venue TEXT NOT NULL DEFAULT '',
          direction TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL DEFAULT '',
          entry_side TEXT NOT NULL DEFAULT '',
          entry_order_id TEXT NOT NULL DEFAULT '',
          entry_status TEXT NOT NULL DEFAULT '',
          entry_fill_price REAL NOT NULL DEFAULT 0,
          entry_fill_qty REAL NOT NULL DEFAULT 0,
          entry_filled_at TEXT NOT NULL DEFAULT '',
          state TEXT NOT NULL DEFAULT 'pending',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
          trade_id TEXT PRIMARY KEY,
          ticker TEXT,
          entry_date TEXT,
          exit_date TEXT,
          entry_price REAL,
          exit_price REAL,
          shares INTEGER,
          pnl REAL,
          pnl_percent REAL,
          status TEXT,
          sentiment_reddit INTEGER,
          sentiment_twitter INTEGER,
          sentiment_trump INTEGER,
          source_reddit_wsb TEXT,
          source_reddit_stocks TEXT,
          source_reddit_investing TEXT,
          source_twitter_general TEXT,
          source_twitter_analysts TEXT,
          source_trump_posts TEXT,
          source_news TEXT,
          source_accuracy_score REAL,
          thesis TEXT,
          outcome_analysis TEXT,
          lesson_learned TEXT,
          decision_grade TEXT,
          created_at TEXT
        )
        """
    )
    if not column_exists(conn, "trades", "route_id"):
        conn.execute("ALTER TABLE trades ADD COLUMN route_id INTEGER")
    if not column_exists(conn, "trades", "broker_order_id"):
        conn.execute("ALTER TABLE trades ADD COLUMN broker_order_id TEXT")
    if not column_exists(conn, "trades", "last_sync"):
        conn.execute("ALTER TABLE trades ADD COLUMN last_sync TEXT")
    conn.commit()


def main() -> int:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not api_key or not secret:
        print("Alpaca sync skipped: missing credentials")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_tables(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, route_id, ticker, direction, mode, broker_order_id, notes
            FROM execution_orders
            WHERE broker_order_id <> ''
              AND notes LIKE 'alpaca paper:%'
            ORDER BY id DESC
            LIMIT 300
            """
        )
        rows = cur.fetchall()
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
        }

        checked = 0
        updated = 0
        for row_id, route_id, ticker, direction, mode, broker_id, notes in rows:
            checked += 1
            url = f"{base_url}/v2/orders/{broker_id}"
            try:
                res = requests.get(url, headers=headers, timeout=20)
            except Exception:
                continue
            if res.status_code >= 400:
                continue
            try:
                data = res.json()
            except Exception:
                continue

            status = str(data.get("status", "")).strip().lower()
            if not status:
                continue
            if status not in TRACK_STATUSES and status not in TERMINAL_STATUSES:
                continue

            fill_px = data.get("filled_avg_price")
            fill_qty = data.get("filled_qty")
            side = str(data.get("side", "")).strip().lower()
            filled_at = str(data.get("filled_at", "") or "")
            suffix = []
            if fill_px:
                suffix.append(f"avg_fill={fill_px}")
            if fill_qty:
                suffix.append(f"filled_qty={fill_qty}")
            suffix_text = f" | {'; '.join(suffix)}" if suffix else ""

            cur.execute(
                """
                UPDATE execution_orders
                SET order_status=?, notes=?
                WHERE id=?
                """,
                (status, f"alpaca paper: synced={status}{suffix_text}", row_id),
            )

            # Deterministic route->broker linkage for learning attribution.
            link_state = "pending"
            if status in {"filled"}:
                link_state = "open"
            elif status in {"canceled", "expired", "rejected", "stopped"}:
                link_state = "failed"
            cur.execute(
                """
                INSERT INTO route_trade_links
                (
                  route_id, created_at, updated_at, ticker, venue, direction, mode,
                  source_tag, entry_side, entry_order_id, entry_status, entry_fill_price, entry_fill_qty, entry_filled_at, state, notes
                )
                VALUES (?, datetime('now'), datetime('now'), ?, 'alpaca', ?, ?, COALESCE((SELECT source_tag FROM signal_routes WHERE id=?), ''), ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_id) DO UPDATE SET
                  updated_at=datetime('now'),
                  ticker=excluded.ticker,
                  venue='alpaca',
                  direction=excluded.direction,
                  mode=excluded.mode,
                  source_tag=excluded.source_tag,
                  entry_side=excluded.entry_side,
                  entry_order_id=excluded.entry_order_id,
                  entry_status=excluded.entry_status,
                  entry_fill_price=excluded.entry_fill_price,
                  entry_fill_qty=excluded.entry_fill_qty,
                  entry_filled_at=excluded.entry_filled_at,
                  state=excluded.state,
                  notes=excluded.notes
                """,
                (
                    int(route_id),
                    str(ticker or "").upper(),
                    str(direction or ""),
                    str(mode or ""),
                    int(route_id),
                    side,
                    str(broker_id),
                    status,
                    float(fill_px or 0.0),
                    float(fill_qty or 0.0),
                    filled_at,
                    link_state,
                    f"alpaca order sync: {status}",
                ),
            )

            # Deterministic trades row keyed by route id for future closed-trade attribution.
            trade_id = f"route_{int(route_id)}"
            trade_status = "open" if status in {"filled", "partially_filled"} else ("closed" if status in {"canceled", "expired", "rejected", "stopped"} else "pending")
            cur.execute(
                """
                INSERT INTO trades
                (trade_id, route_id, broker_order_id, ticker, entry_date, entry_price, shares, status, created_at, last_sync)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(trade_id) DO UPDATE SET
                  route_id=excluded.route_id,
                  broker_order_id=excluded.broker_order_id,
                  ticker=excluded.ticker,
                  entry_date=CASE WHEN excluded.entry_date<>'' THEN excluded.entry_date ELSE trades.entry_date END,
                  entry_price=CASE WHEN excluded.entry_price>0 THEN excluded.entry_price ELSE trades.entry_price END,
                  shares=CASE WHEN excluded.shares<>0 THEN excluded.shares ELSE trades.shares END,
                  status=excluded.status,
                  last_sync=datetime('now')
                """,
                (
                    trade_id,
                    int(route_id),
                    str(broker_id),
                    str(ticker or "").upper(),
                    filled_at,
                    float(fill_px or 0.0),
                    int(float(fill_qty or 0.0)),
                    trade_status,
                ),
            )
            updated += 1

        conn.commit()
        print(f"Alpaca sync: checked {checked}, updated {updated}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
