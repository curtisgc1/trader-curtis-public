#!/usr/bin/env python3
"""
Reconcile realized outcomes from exchange-side settlements.

Current coverage:
- Polymarket filled orders -> settlement outcomes (when market is closed)
- Route-level realized labels are written when route_id is available
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _as_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return float(default)


def _parse_json_list(raw: object) -> List[Any]:
    try:
        v = json.loads(str(raw or "[]"))
    except Exception:
        return []
    return v if isinstance(v, list) else []


def _resolution(pnl: float, eps: float = 1e-8) -> str:
    if pnl > eps:
        return "win"
    if pnl < -eps:
        return "loss"
    return "push"


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_settlement_outcomes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          polymarket_order_id INTEGER NOT NULL UNIQUE,
          route_id INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT '',
          settled_at TEXT NOT NULL DEFAULT '',
          market_id TEXT NOT NULL DEFAULT '',
          outcome TEXT NOT NULL DEFAULT '',
          side TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL DEFAULT '',
          entry_price REAL NOT NULL DEFAULT 0,
          settle_price REAL NOT NULL DEFAULT 0,
          size REAL NOT NULL DEFAULT 0,
          notional REAL NOT NULL DEFAULT 0,
          pnl_usd REAL NOT NULL DEFAULT 0,
          pnl_percent REAL NOT NULL DEFAULT 0,
          resolution TEXT NOT NULL DEFAULT 'push',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_settle_market ON polymarket_settlement_outcomes(market_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_settle_route ON polymarket_settlement_outcomes(route_id)")
    conn.commit()


def _infer_outcome_index(outcomes: List[Any], outcome_name: str) -> int:
    target = str(outcome_name or "").strip().lower()
    for i, label in enumerate(outcomes):
        if str(label or "").strip().lower() == target:
            return i
    if target in {"yes", "y", "true", "1"}:
        return 0
    if target in {"no", "n", "false", "0"}:
        return 1
    return 0


def _closed_market_settle_price(conn: sqlite3.Connection, market_id: str, outcome_name: str) -> Tuple[float, str, str]:
    if not _table_exists(conn, "polymarket_markets"):
        return 0.0, "", "polymarket_markets missing"
    cur = conn.cursor()
    cur.execute(
        """
        SELECT outcomes_json, outcome_prices_json, fetched_at
        FROM polymarket_markets
        WHERE market_id=?
          AND COALESCE(closed,0)=1
        ORDER BY datetime(COALESCE(fetched_at,'1970-01-01')) DESC
        LIMIT 1
        """,
        (str(market_id),),
    )
    row = cur.fetchone()
    if not row:
        return 0.0, "", "market not closed or missing"
    outcomes = _parse_json_list(row[0])
    prices_raw = _parse_json_list(row[1])
    prices = [_as_float(x, 0.0) for x in prices_raw]
    idx = _infer_outcome_index(outcomes, outcome_name)
    if idx >= len(prices):
        return 0.0, str(row[2] or ""), "settle price missing"
    settle = max(0.0, min(1.0, float(prices[idx])))
    return settle, str(row[2] or ""), "ok"


def _fallback_entry_price(conn: sqlite3.Connection, market_id: str, outcome: str, created_at: str) -> float:
    if not _table_exists(conn, "polymarket_candidates"):
        return 0.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(implied_prob,0)
        FROM polymarket_candidates
        WHERE market_id=?
          AND lower(COALESCE(outcome,''))=lower(?)
          AND datetime(COALESCE(created_at,'1970-01-01')) <= datetime(COALESCE(?, '1970-01-01'))
        ORDER BY datetime(COALESCE(created_at,'1970-01-01')) DESC
        LIMIT 1
        """,
        (str(market_id), str(outcome), str(created_at or "")),
    )
    row = cur.fetchone()
    if row and row[0] is not None:
        return max(0.0, min(1.0, _as_float(row[0], 0.0)))
    return 0.0


def _upsert_route_realized(
    conn: sqlite3.Connection,
    route_id: int,
    market_id: str,
    resolution: str,
    pnl_usd: float,
    pnl_pct: float,
    settled_at: str,
    note: str,
) -> int:
    if route_id <= 0 or not _table_exists(conn, "route_outcomes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM route_outcomes WHERE route_id=? AND COALESCE(outcome_type,'realized')='realized' LIMIT 1",
        (int(route_id),),
    )
    if cur.fetchone():
        return 0

    ticker = f"POLY:{market_id}"
    source_tag = "POLYMARKET"
    if _table_exists(conn, "signal_routes"):
        cur.execute(
            """
            SELECT COALESCE(ticker,''), COALESCE(source_tag,'POLYMARKET')
            FROM signal_routes
            WHERE id=?
            LIMIT 1
            """,
            (int(route_id),),
        )
        row = cur.fetchone()
        if row:
            if row[0]:
                ticker = str(row[0])
            if row[1]:
                source_tag = str(row[1])

    cur.execute(
        """
        INSERT OR REPLACE INTO route_outcomes
        (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(route_id),
            str(ticker),
            str(source_tag),
            "realized",
            str(resolution),
            round(float(pnl_usd), 8),
            round(float(pnl_pct), 8),
            str(settled_at or now_iso()),
            str(note)[:240],
        ),
    )
    return 1


def reconcile_polymarket_settlements(conn: sqlite3.Connection, limit: int = 2000) -> Dict[str, int]:
    stats = {
        "candidates": 0,
        "settled_written": 0,
        "orders_settled_status_updated": 0,
        "route_realized_written": 0,
        "skipped_not_closed": 0,
    }
    if not _table_exists(conn, "polymarket_orders"):
        return stats

    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, COALESCE(p.route_id,0), COALESCE(p.created_at,''), COALESCE(p.market_id,''), COALESCE(p.outcome,''),
               COALESCE(p.side,'BUY'), COALESCE(p.mode,'paper'),
               COALESCE(p.price,0), COALESCE(p.size,0), COALESCE(p.notional,0), COALESCE(p.status,'')
        FROM polymarket_orders p
        LEFT JOIN polymarket_settlement_outcomes s ON s.polymarket_order_id = p.id
        WHERE s.polymarket_order_id IS NULL
          AND lower(COALESCE(p.status,'')) LIKE 'filled%'
        ORDER BY p.id ASC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    stats["candidates"] = len(rows)

    for (
        po_id,
        route_id,
        created_at,
        market_id,
        outcome,
        side,
        mode,
        price,
        size,
        notional,
        status,
    ) in rows:
        settle_price, settled_at, settle_note = _closed_market_settle_price(conn, str(market_id), str(outcome))
        if settle_price <= 0 and settle_price != 0.0:
            # Defensive only; settle_price constrained above.
            settle_price = 0.0
        if settle_note != "ok":
            stats["skipped_not_closed"] += 1
            continue

        entry_price = float(price or 0.0)
        if entry_price <= 0:
            entry_price = _fallback_entry_price(conn, str(market_id), str(outcome), str(created_at or ""))
        if entry_price <= 0:
            # Last-resort neutral entry if we only have notional-size info.
            entry_price = 0.5

        qty = float(size or 0.0)
        if qty <= 0 and float(notional or 0.0) > 0:
            qty = float(notional or 0.0) / max(entry_price, 0.01)
        if qty <= 0:
            continue

        side_l = str(side or "BUY").strip().lower()
        if side_l == "sell":
            pnl_usd = (entry_price - settle_price) * qty
            pnl_pct = ((entry_price - settle_price) / max(entry_price, 1e-6)) * 100.0
        else:
            pnl_usd = (settle_price - entry_price) * qty
            pnl_pct = ((settle_price - entry_price) / max(entry_price, 1e-6)) * 100.0
        resolution = _resolution(float(pnl_usd))
        position_notional = float(notional or 0.0)
        if position_notional <= 0:
            position_notional = qty * entry_price

        note = f"polymarket_settlement status={status} settle_note={settle_note}"
        cur.execute(
            """
            INSERT OR REPLACE INTO polymarket_settlement_outcomes
            (polymarket_order_id, route_id, created_at, settled_at, market_id, outcome, side, mode,
             entry_price, settle_price, size, notional, pnl_usd, pnl_percent, resolution, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(po_id),
                int(route_id or 0),
                str(created_at or ""),
                str(settled_at or now_iso()),
                str(market_id or ""),
                str(outcome or ""),
                str(side or ""),
                str(mode or ""),
                round(float(entry_price), 8),
                round(float(settle_price), 8),
                round(float(qty), 8),
                round(float(position_notional), 8),
                round(float(pnl_usd), 8),
                round(float(pnl_pct), 8),
                str(resolution),
                note[:240],
            ),
        )
        stats["settled_written"] += int(cur.rowcount or 0)

        settled_status = f"settled_{resolution}"
        cur.execute(
            "UPDATE polymarket_orders SET status=?, notes=notes || ' | settled' WHERE id=?",
            (settled_status, int(po_id)),
        )
        stats["orders_settled_status_updated"] += int(cur.rowcount or 0)

        stats["route_realized_written"] += _upsert_route_realized(
            conn=conn,
            route_id=int(route_id or 0),
            market_id=str(market_id or ""),
            resolution=str(resolution),
            pnl_usd=float(pnl_usd),
            pnl_pct=float(pnl_pct),
            settled_at=str(settled_at or now_iso()),
            note=note,
        )

    conn.commit()
    return stats


def main() -> int:
    if not DB_PATH.exists():
        print("realized_reconcile=skipped reason=db_missing")
        return 0
    conn = _connect()
    try:
        ensure_tables(conn)
        poly = reconcile_polymarket_settlements(conn)
        print(
            "realized_reconcile "
            f"poly_candidates={poly['candidates']} "
            f"poly_settled_written={poly['settled_written']} "
            f"poly_orders_status_updated={poly['orders_settled_status_updated']} "
            f"route_realized_written={poly['route_realized_written']} "
            f"poly_skipped_not_closed={poly['skipped_not_closed']}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
