#!/usr/bin/env python3
"""
Reconcile Alpaca order statuses into execution_orders/trades.

Also captures close-side fills so realized trade outcomes can be derived later.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Iterable

import requests

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "trades.db"
ENV_PATH = BASE_DIR / ".env"

TRACK_STATUSES = {"new", "accepted", "pending_new", "partially_filled", "submitted"}
TERMINAL_STATUSES = {"filled", "canceled", "expired", "rejected", "stopped"}
EPS = 1e-9


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


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def _as_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return float(default)


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alpaca_fill_sync (
          order_id TEXT PRIMARY KEY,
          symbol TEXT NOT NULL DEFAULT '',
          side TEXT NOT NULL DEFAULT '',
          filled_qty REAL NOT NULL DEFAULT 0,
          filled_price REAL NOT NULL DEFAULT 0,
          filled_at TEXT NOT NULL DEFAULT '',
          synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if not column_exists(conn, "trades", "route_id"):
        conn.execute("ALTER TABLE trades ADD COLUMN route_id INTEGER")
    if not column_exists(conn, "trades", "broker_order_id"):
        conn.execute("ALTER TABLE trades ADD COLUMN broker_order_id TEXT")
    if not column_exists(conn, "trades", "last_sync"):
        conn.execute("ALTER TABLE trades ADD COLUMN last_sync TEXT")
    if not column_exists(conn, "trades", "entry_side"):
        conn.execute("ALTER TABLE trades ADD COLUMN entry_side TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_ticker_status ON trades(ticker, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_route_id ON trades(route_id)")
    conn.commit()


def _fetch_order(headers: Dict[str, str], base_url: str, order_id: str) -> dict:
    url = f"{base_url}/v2/orders/{order_id}"
    try:
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code >= 400:
            return {}
        return res.json() if res.content else {}
    except Exception:
        return {}


def _fetch_recent_fills(headers: Dict[str, str], base_url: str, limit: int = 500) -> list[dict]:
    url = f"{base_url}/v2/orders?status=closed&limit={int(limit)}&direction=desc&nested=false"
    try:
        res = requests.get(url, headers=headers, timeout=25)
        if res.status_code >= 400:
            return []
        data = res.json() if res.content else []
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _fill_seen(conn: sqlite3.Connection, order_id: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM alpaca_fill_sync WHERE order_id=? LIMIT 1", (str(order_id),))
    return cur.fetchone() is not None


def _mark_fill_seen(
    conn: sqlite3.Connection,
    order_id: str,
    symbol: str,
    side: str,
    qty: float,
    px: float,
    filled_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO alpaca_fill_sync
        (order_id, symbol, side, filled_qty, filled_price, filled_at, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (str(order_id), str(symbol), str(side), float(qty), float(px), str(filled_at)),
    )


def _backfill_zero_share_trades(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE trades
        SET shares = (
            SELECT COALESCE(l.entry_fill_qty, 0)
            FROM route_trade_links l
            WHERE l.route_id = trades.route_id
            LIMIT 1
        ),
        last_sync=datetime('now')
        WHERE COALESCE(status,'')='open'
          AND COALESCE(shares,0) <= 0
          AND COALESCE(route_id,0) > 0
          AND EXISTS (
            SELECT 1
            FROM route_trade_links l
            WHERE l.route_id = trades.route_id
              AND COALESCE(l.entry_fill_qty,0) > 0
          )
        """
    )
    changed = int(cur.rowcount or 0)
    conn.commit()
    return changed


def _upsert_entry_trade(
    conn: sqlite3.Connection,
    route_id: int,
    ticker: str,
    broker_id: str,
    side: str,
    filled_at: str,
    fill_px: float,
    fill_qty: float,
    status: str,
) -> int:
    if fill_qty <= 0:
        return 0
    trade_id = f"route_{int(route_id)}" if int(route_id) > 0 else f"alpaca_order_{broker_id}"
    trade_status = "open" if status in {"filled", "partially_filled"} else "pending"
    conn.execute(
        """
        INSERT INTO trades
        (trade_id, route_id, broker_order_id, ticker, entry_date, entry_price, shares, status, entry_side, created_at, last_sync)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(trade_id) DO UPDATE SET
          route_id=excluded.route_id,
          broker_order_id=excluded.broker_order_id,
          ticker=excluded.ticker,
          entry_date=CASE WHEN excluded.entry_date<>'' THEN excluded.entry_date ELSE trades.entry_date END,
          entry_price=CASE WHEN excluded.entry_price>0 THEN excluded.entry_price ELSE trades.entry_price END,
          shares=CASE WHEN excluded.shares>0 THEN excluded.shares ELSE trades.shares END,
          status=CASE
            WHEN COALESCE(trades.exit_date,'') <> '' THEN trades.status
            ELSE excluded.status
          END,
          entry_side=CASE WHEN excluded.entry_side<>'' THEN excluded.entry_side ELSE trades.entry_side END,
          last_sync=datetime('now')
        """,
        (
            trade_id,
            int(route_id) if int(route_id) > 0 else None,
            str(broker_id),
            str(ticker).upper(),
            str(filled_at or ""),
            float(fill_px or 0.0),
            float(fill_qty or 0.0),
            trade_status,
            str(side or ""),
        ),
    )
    return 1


def _iter_open_candidates(conn: sqlite3.Connection, symbol: str, close_side: str) -> Iterable[tuple]:
    if close_side == "sell":
        side_clause = "(COALESCE(entry_side,'') IN ('buy',''))"
    else:
        side_clause = "(COALESCE(entry_side,'') = 'sell')"
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT trade_id, COALESCE(route_id,0), COALESCE(entry_date,created_at,''), COALESCE(entry_price,0), COALESCE(shares,0), COALESCE(entry_side,'')
        FROM trades
        WHERE upper(COALESCE(ticker,''))=upper(?)
          AND COALESCE(status,'')='open'
          AND COALESCE(exit_date,'')=''
          AND COALESCE(entry_price,0) > 0
          AND {side_clause}
        ORDER BY datetime(COALESCE(entry_date,created_at,'')) ASC
        """,
        (str(symbol).upper(),),
    )
    return cur.fetchall()


def _trade_exists_for_order(conn: sqlite3.Connection, order_id: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM trades WHERE COALESCE(broker_order_id,'')=? LIMIT 1",
        (str(order_id),),
    )
    return cur.fetchone() is not None


def _close_lots_with_fill(
    conn: sqlite3.Connection,
    symbol: str,
    close_side: str,
    fill_qty: float,
    fill_px: float,
    filled_at: str,
    order_id: str,
) -> tuple[int, int]:
    remaining = max(0.0, float(fill_qty))
    closed = 0
    opened = 0
    cur = conn.cursor()

    for trade_id, route_id, entry_date, entry_px, shares, entry_side in _iter_open_candidates(conn, symbol, close_side):
        if remaining <= EPS:
            break
        qty = max(0.0, float(shares or 0.0))
        if qty <= EPS:
            continue
        close_qty = min(remaining, qty)
        ep = float(entry_px or 0.0)
        if ep <= EPS:
            continue

        if str(entry_side or "") == "sell":
            pnl = (ep - float(fill_px)) * close_qty
            pnl_pct = ((ep - float(fill_px)) / ep) * 100.0
        else:
            pnl = (float(fill_px) - ep) * close_qty
            pnl_pct = ((float(fill_px) - ep) / ep) * 100.0

        if close_qty >= (qty - EPS):
            cur.execute(
                """
                UPDATE trades
                SET exit_date=?,
                    exit_price=?,
                    pnl=?,
                    pnl_percent=?,
                    status='closed',
                    shares=?,
                    broker_order_id=CASE
                      WHEN COALESCE(broker_order_id,'')='' THEN ?
                      ELSE broker_order_id
                    END,
                    last_sync=datetime('now')
                WHERE trade_id=?
                """,
                (
                    str(filled_at),
                    float(fill_px),
                    round(float(pnl), 8),
                    round(float(pnl_pct), 8),
                    float(qty),
                    str(order_id),
                    str(trade_id),
                ),
            )
            closed += 1
        else:
            # Partial close: reduce open lot and write a closed fragment row.
            remaining_qty = max(0.0, qty - close_qty)
            cur.execute(
                "UPDATE trades SET shares=?, last_sync=datetime('now') WHERE trade_id=?",
                (float(remaining_qty), str(trade_id)),
            )
            child_trade_id = f"{trade_id}:close:{order_id}:{int(close_qty * 1_000_000)}"
            cur.execute(
                """
                INSERT OR IGNORE INTO trades
                (trade_id, route_id, broker_order_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, pnl, pnl_percent, status, entry_side, created_at, last_sync)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?, datetime('now'), datetime('now'))
                """,
                (
                    child_trade_id,
                    int(route_id) if int(route_id or 0) > 0 else None,
                    str(order_id),
                    str(symbol).upper(),
                    str(entry_date or ""),
                    str(filled_at),
                    float(ep),
                    float(fill_px),
                    float(close_qty),
                    round(float(pnl), 8),
                    round(float(pnl_pct), 8),
                    str(entry_side or ""),
                ),
            )
            closed += 1
        remaining -= close_qty

    # Unmatched fill quantity represents a fresh position opened externally.
    if remaining > EPS and not _trade_exists_for_order(conn, order_id):
        trade_id = f"alpaca_unmatched_{order_id}"
        cur.execute(
            """
            INSERT OR IGNORE INTO trades
            (trade_id, broker_order_id, ticker, entry_date, entry_price, shares, status, entry_side, created_at, last_sync)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, datetime('now'), datetime('now'))
            """,
            (
                trade_id,
                str(order_id),
                str(symbol).upper(),
                str(filled_at),
                float(fill_px),
                float(remaining),
                str(close_side),
            ),
        )
        opened += int(cur.rowcount or 0)

    return closed, opened


def main() -> int:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")

    if not api_key or not secret:
        print("Alpaca sync skipped: missing credentials")
        return 0

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        ensure_tables(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, route_id, ticker, direction, mode, broker_order_id
            FROM execution_orders
            WHERE broker_order_id <> ''
              AND notes LIKE 'alpaca paper:%'
            ORDER BY id DESC
            LIMIT 500
            """
        )
        rows = cur.fetchall()

        checked = 0
        updated = 0
        entry_upserts = 0
        for row_id, route_id, ticker, direction, mode, broker_id in rows:
            checked += 1
            data = _fetch_order(headers, base_url, str(broker_id))
            status = str(data.get("status", "")).strip().lower()
            if not status or (status not in TRACK_STATUSES and status not in TERMINAL_STATUSES):
                continue

            fill_px = _as_float(data.get("filled_avg_price"), 0.0)
            fill_qty = _as_float(data.get("filled_qty"), 0.0)
            side = str(data.get("side", "")).strip().lower()
            filled_at = str(data.get("filled_at", "") or "")
            suffix = []
            if fill_px > 0:
                suffix.append(f"avg_fill={fill_px}")
            if fill_qty > 0:
                suffix.append(f"filled_qty={fill_qty}")
            suffix_text = f" | {'; '.join(suffix)}" if suffix else ""

            cur.execute(
                """
                UPDATE execution_orders
                SET order_status=?, notes=?
                WHERE id=?
                """,
                (status, f"alpaca paper: synced={status}{suffix_text}", int(row_id)),
            )

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
                    str(side),
                    str(broker_id),
                    str(status),
                    float(fill_px),
                    float(fill_qty),
                    str(filled_at),
                    str(link_state),
                    f"alpaca order sync: {status}",
                ),
            )

            if fill_qty > 0:
                entry_upserts += _upsert_entry_trade(
                    conn,
                    int(route_id),
                    str(ticker or "").upper(),
                    str(broker_id),
                    str(side),
                    str(filled_at),
                    float(fill_px),
                    float(fill_qty),
                    str(status),
                )
            updated += 1

        backfilled_qty = _backfill_zero_share_trades(conn)

        fills = _fetch_recent_fills(headers, base_url, limit=500)
        fills_processed = 0
        fill_closures = 0
        fill_opened = 0
        # Older fills first for deterministic lot processing.
        for item in reversed(fills):
            status = str(item.get("status", "")).strip().lower()
            if status != "filled":
                continue
            order_id = str(item.get("id", "")).strip()
            side = str(item.get("side", "")).strip().lower()
            symbol = str(item.get("symbol", "")).strip().upper()
            qty = _as_float(item.get("filled_qty"), 0.0)
            px = _as_float(item.get("filled_avg_price"), 0.0)
            filled_at = str(item.get("filled_at", "") or "")
            if not order_id or not symbol or side not in {"buy", "sell"} or qty <= EPS or px <= EPS:
                continue
            if _fill_seen(conn, order_id):
                continue
            c, o = _close_lots_with_fill(conn, symbol, side, qty, px, filled_at, order_id)
            fill_closures += int(c)
            fill_opened += int(o)
            _mark_fill_seen(conn, order_id, symbol, side, qty, px, filled_at)
            fills_processed += 1

        conn.commit()
        print(
            f"Alpaca sync: checked {checked}, updated {updated}, entry_upserts {entry_upserts}, "
            f"backfilled_qty {backfilled_qty}, fills_processed {fills_processed}, "
            f"fills_closed {fill_closures}, fills_opened {fill_opened}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
