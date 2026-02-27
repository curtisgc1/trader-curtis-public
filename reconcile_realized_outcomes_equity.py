#!/usr/bin/env python3
"""
Reconcile realized outcomes for equity (Alpaca) and Hyperliquid trades.

Scans closed trades and open HL positions, computes actual P&L,
and writes realized outcome rows to route_outcomes.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _ctl(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def _has_realized_outcome(conn: sqlite3.Connection, route_id: int) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM route_outcomes WHERE route_id=? AND outcome_type='realized' LIMIT 1",
        (route_id,),
    )
    return cur.fetchone() is not None


def _resolution_from_pnl(pnl_percent: float) -> str:
    if pnl_percent > 0.05:
        return "win"
    if pnl_percent < -0.05:
        return "loss"
    return "push"


def reconcile_alpaca(conn: sqlite3.Connection, max_age_days: int) -> int:
    """Reconcile closed Alpaca trades that have route_id but no realized outcome."""
    if not table_exists(conn, "trades") or not table_exists(conn, "route_trade_links"):
        return 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    cur = conn.cursor()

    # Find closed trades with route_id that lack a realized outcome
    cur.execute(
        """
        SELECT t.trade_id, t.route_id, t.ticker, t.pnl, t.pnl_percent,
               t.exit_date, t.entry_price, t.exit_price,
               COALESCE(rtl.source_tag, '') as source_tag
        FROM trades t
        LEFT JOIN route_trade_links rtl ON rtl.route_id = t.route_id
        WHERE t.status = 'closed'
          AND COALESCE(t.route_id, 0) > 0
          AND datetime(COALESCE(t.exit_date, t.created_at, '1970-01-01')) >= datetime(?)
          AND NOT EXISTS (
            SELECT 1 FROM route_outcomes ro
            WHERE ro.route_id = t.route_id
              AND ro.outcome_type = 'realized'
          )
        """,
        (cutoff,),
    )
    rows = cur.fetchall()
    reconciled = 0

    for trade_id, route_id, ticker, pnl, pnl_percent, exit_date, entry_price, exit_price, source_tag in rows:
        route_id = int(route_id or 0)
        if route_id <= 0:
            continue

        pnl_val = float(pnl or 0.0)
        pnl_pct = float(pnl_percent or 0.0)
        resolution = _resolution_from_pnl(pnl_pct)
        resolved_at = str(exit_date or now_iso())

        # If no source_tag from route_trade_links, try signal_routes
        if not source_tag and table_exists(conn, "signal_routes"):
            cur.execute(
                "SELECT COALESCE(source_tag, '') FROM signal_routes WHERE id=? LIMIT 1",
                (route_id,),
            )
            sr = cur.fetchone()
            source_tag = str(sr[0]) if sr else ""

        conn.execute(
            """
            INSERT INTO route_outcomes
            (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
            VALUES (?, ?, ?, 'realized', ?, ?, ?, ?, ?)
            ON CONFLICT(route_id) DO UPDATE SET
              outcome_type='realized',
              resolution=excluded.resolution,
              pnl=excluded.pnl,
              pnl_percent=excluded.pnl_percent,
              resolved_at=excluded.resolved_at,
              notes=excluded.notes
            """,
            (
                route_id,
                str(ticker or ""),
                source_tag,
                resolution,
                pnl_val,
                pnl_pct,
                resolved_at,
                f"alpaca_reconciled trade_id={trade_id}",
            ),
        )

        # Update route_trade_links state
        conn.execute(
            """
            UPDATE route_trade_links
            SET state='closed', updated_at=?
            WHERE route_id=? AND state != 'closed'
            """,
            (now_iso(), route_id),
        )
        reconciled += 1

    conn.commit()
    return reconciled


def reconcile_hyperliquid(conn: sqlite3.Connection, max_age_days: int) -> int:
    """Reconcile HL positions via route_trade_links where venue='hyperliquid'."""
    if not table_exists(conn, "route_trade_links"):
        return 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    cur = conn.cursor()

    # Find open HL trade links without realized outcomes
    cur.execute(
        """
        SELECT rtl.route_id, rtl.ticker, rtl.source_tag, rtl.direction,
               rtl.entry_fill_price, rtl.entry_fill_qty, rtl.entry_filled_at
        FROM route_trade_links rtl
        WHERE rtl.venue = 'hyperliquid'
          AND rtl.state = 'open'
          AND datetime(COALESCE(rtl.entry_filled_at, rtl.created_at, '1970-01-01')) >= datetime(?)
          AND rtl.entry_fill_price > 0
          AND NOT EXISTS (
            SELECT 1 FROM route_outcomes ro
            WHERE ro.route_id = rtl.route_id
              AND ro.outcome_type = 'realized'
          )
        """,
        (cutoff,),
    )
    rows = cur.fetchall()

    if not rows:
        return 0

    # Check if we have HL fill data in trades table (synced by sync_alpaca_order_status or similar)
    reconciled = 0
    for route_id, ticker, source_tag, direction, entry_price, entry_qty, entry_filled_at in rows:
        route_id = int(route_id or 0)
        if route_id <= 0:
            continue

        entry_price = float(entry_price or 0.0)
        if entry_price <= 0:
            continue

        # Look for a matching closed trade with this route_id
        if table_exists(conn, "trades"):
            cur.execute(
                """
                SELECT pnl, pnl_percent, exit_date, exit_price
                FROM trades
                WHERE COALESCE(route_id, 0) = ?
                  AND status = 'closed'
                ORDER BY datetime(COALESCE(exit_date, '1970-01-01')) DESC
                LIMIT 1
                """,
                (route_id,),
            )
            trade_row = cur.fetchone()
            if trade_row:
                pnl_val = float(trade_row[0] or 0.0)
                pnl_pct = float(trade_row[1] or 0.0)
                resolved_at = str(trade_row[2] or now_iso())
                resolution = _resolution_from_pnl(pnl_pct)

                conn.execute(
                    """
                    INSERT INTO route_outcomes
                    (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                    VALUES (?, ?, ?, 'realized', ?, ?, ?, ?, ?)
                    ON CONFLICT(route_id) DO UPDATE SET
                      outcome_type='realized',
                      resolution=excluded.resolution,
                      pnl=excluded.pnl,
                      pnl_percent=excluded.pnl_percent,
                      resolved_at=excluded.resolved_at,
                      notes=excluded.notes
                    """,
                    (
                        route_id,
                        str(ticker or ""),
                        str(source_tag or ""),
                        resolution,
                        pnl_val,
                        pnl_pct,
                        resolved_at,
                        "hl_reconciled",
                    ),
                )

                conn.execute(
                    """
                    UPDATE route_trade_links
                    SET state='closed', updated_at=?
                    WHERE route_id=? AND state != 'closed'
                    """,
                    (now_iso(), route_id),
                )
                reconciled += 1

    conn.commit()
    return reconciled


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        # Ensure route_outcomes table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS route_outcomes (
              route_id INTEGER PRIMARY KEY,
              ticker TEXT NOT NULL,
              source_tag TEXT NOT NULL,
              outcome_type TEXT NOT NULL DEFAULT 'realized',
              resolution TEXT NOT NULL,
              pnl REAL NOT NULL,
              pnl_percent REAL NOT NULL,
              resolved_at TEXT NOT NULL,
              notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()

        equity_enabled = _ctl(conn, "reconcile_equity_enabled", "1") == "1"
        hl_enabled = _ctl(conn, "reconcile_hl_enabled", "1") == "1"
        max_age_days = int(float(_ctl(conn, "reconcile_max_age_days", "30") or 30))

        alpaca_count = 0
        hl_count = 0

        if equity_enabled:
            alpaca_count = reconcile_alpaca(conn, max_age_days)

        if hl_enabled:
            hl_count = reconcile_hyperliquid(conn, max_age_days)

        print(
            f"RECONCILE_REALIZED equity_enabled={int(equity_enabled)} hl_enabled={int(hl_enabled)} "
            f"max_age_days={max_age_days} alpaca_reconciled={alpaca_count} hl_reconciled={hl_count}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
