#!/usr/bin/env python3
"""
Execution worker for routed trade signals.
Paper mode is fully automated; live mode is explicitly blocked unless enabled by controls.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from training_mode import apply_training_mode
from execution_adapters import (
    alpaca_margin_capability,
    alpaca_latest_price,
    alpaca_submit_qty,
    alpaca_submit_notional,
    hyperliquid_submit_notional_live,
    hyperliquid_test_intent,
    is_hl_eligible,
)

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        CREATE TABLE IF NOT EXISTS execution_orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          route_id INTEGER NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          mode TEXT NOT NULL,
          notional REAL NOT NULL,
          leverage_used REAL NOT NULL DEFAULT 1.0,
          leverage_capable INTEGER NOT NULL DEFAULT 0,
          order_status TEXT NOT NULL,
          broker_order_id TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_learning (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          route_id INTEGER NOT NULL,
          ticker TEXT NOT NULL,
          source_tag TEXT NOT NULL DEFAULT '',
          pipeline_hint TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL,
          venue TEXT NOT NULL,
          decision TEXT NOT NULL,
          order_status TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT ''
        )
        """
    )
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
    if table_exists(conn, "execution_orders") and not column_exists(conn, "execution_orders", "leverage_used"):
        conn.execute("ALTER TABLE execution_orders ADD COLUMN leverage_used REAL NOT NULL DEFAULT 1.0")
    if table_exists(conn, "execution_orders") and not column_exists(conn, "execution_orders", "leverage_capable"):
        conn.execute("ALTER TABLE execution_orders ADD COLUMN leverage_capable INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def is_live_enabled(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "execution_controls"):
        return False
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key='allow_live_trading' LIMIT 1")
    row = cur.fetchone()
    return bool(row and row[0] == "1")


def load_controls(conn: sqlite3.Connection) -> dict:
    if not table_exists(conn, "execution_controls"):
        return {}
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    return apply_training_mode({k: v for k, v in cur.fetchall()})


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return float(default)


def _learning_row(
    conn: sqlite3.Connection,
    route_id: int,
    ticker: str,
    source_tag: str,
    mode: str,
    venue: str,
    decision: str,
    order_status: str,
    reason: str,
) -> None:
    pipeline_hint = source_tag if source_tag in {"A_SCALP", "B_LONGTERM", "C_EVENT", "D_BOOKMARKS"} else ""
    conn.execute(
        """
        INSERT INTO execution_learning
        (created_at, route_id, ticker, source_tag, pipeline_hint, mode, venue, decision, order_status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now_iso(), int(route_id), ticker, source_tag or "", pipeline_hint, mode, venue, decision, order_status, reason[:240]),
    )


def _upsert_route_link(
    conn: sqlite3.Connection,
    route_id: int,
    ticker: str,
    source_tag: str,
    venue: str,
    direction: str,
    mode: str,
    entry_side: str,
    entry_order_id: str,
    entry_status: str,
    notes: str,
) -> None:
    state = "pending"
    status = str(entry_status or "").lower()
    if status in {"rejected", "canceled", "expired", "stopped", "blocked", "failed"}:
        state = "failed"
    elif status in {"filled"}:
        state = "open"

    conn.execute(
        """
        INSERT INTO route_trade_links
        (
          route_id, created_at, updated_at, ticker, source_tag, venue, direction, mode,
          entry_side, entry_order_id, entry_status, state, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(route_id) DO UPDATE SET
          updated_at=excluded.updated_at,
          ticker=excluded.ticker,
          source_tag=excluded.source_tag,
          venue=excluded.venue,
          direction=excluded.direction,
          mode=excluded.mode,
          entry_side=excluded.entry_side,
          entry_order_id=CASE WHEN excluded.entry_order_id<>'' THEN excluded.entry_order_id ELSE route_trade_links.entry_order_id END,
          entry_status=excluded.entry_status,
          state=excluded.state,
          notes=excluded.notes
        """,
        (
            int(route_id),
            now_iso(),
            now_iso(),
            ticker,
            source_tag or "",
            venue or "",
            direction or "",
            mode or "",
            entry_side or "",
            str(entry_order_id or ""),
            str(entry_status or ""),
            state,
            str(notes or "")[:240],
        ),
    )


def process_queue(limit: int = 20) -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        ensure_tables(conn)
        if not table_exists(conn, "signal_routes"):
            print("Execution worker: signal_routes table missing, nothing to process")
            return 0

        live_enabled = is_live_enabled(conn)
        controls = load_controls(conn)
        master_enabled = controls.get("agent_master_enabled", "0") == "1"
        if not master_enabled:
            print("Execution worker: agent_master_enabled=0, execution paused")
            return 0
        enable_alpaca_paper_auto = controls.get("enable_alpaca_paper_auto", "1") == "1"
        allow_equity_shorts = controls.get("allow_equity_shorts", "1") == "1"
        enable_hl_test_auto = controls.get("enable_hyperliquid_test_auto", "1") == "1"
        allow_hl_live = controls.get("allow_hyperliquid_live", "0") == "1"
        hl_test_notional = float(controls.get("hyperliquid_test_notional_usd", "1") or 1.0)
        hl_leverage = float(controls.get("hyperliquid_test_leverage", "1") or 1.0)
        alpaca_min_score = _as_float(controls.get("alpaca_min_route_score", "60"), 60.0)
        hyperliquid_min_score = _as_float(controls.get("hyperliquid_min_route_score", "60"), 60.0)
        alp_ok, alp_margin_capable, alp_margin_mult, _alp_reason = alpaca_margin_capability()
        if not alp_ok:
            alp_margin_capable = False
            alp_margin_mult = 1.0
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, ticker, direction, mode, proposed_notional, decision, source_tag, COALESCE(score, 0), COALESCE(preferred_venue, '')
            FROM signal_routes
            WHERE status='queued'
            ORDER BY routed_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        processed = 0

        for route_id, ticker, direction, mode, notional, decision, source_tag, route_score, preferred_venue in rows:
            if decision != "approved":
                cur.execute("UPDATE signal_routes SET status='blocked' WHERE id=?", (route_id,))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=(ticker or "").upper().strip(),
                    source_tag=source_tag or "",
                    venue="none",
                    direction=direction,
                    mode=mode,
                    entry_side="",
                    entry_order_id="",
                    entry_status="blocked",
                    notes="decision not approved",
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="none",
                    decision=decision,
                    order_status="blocked",
                    reason="decision not approved",
                )
                continue

            if mode == "live" and not live_enabled:
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?)
                    """,
                    (now_iso(), route_id, ticker, direction, mode, float(notional), 1.0, 0, "live mode disabled by control"),
                )
                cur.execute("UPDATE signal_routes SET status='blocked', reason='live mode disabled by control' WHERE id=?", (route_id,))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=(ticker or "").upper().strip(),
                    source_tag=source_tag or "",
                    venue="none",
                    direction=direction,
                    mode=mode,
                    entry_side="",
                    entry_order_id="",
                    entry_status="blocked",
                    notes="live mode disabled by control",
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="none",
                    decision=decision,
                    order_status="blocked",
                    reason="live mode disabled by control",
                )
                processed += 1
                continue

            ticker_u = (ticker or "").upper().strip()
            side = "sell" if str(direction).lower() in {"short", "bearish", "sell"} else "buy"
            score_v = _as_float(route_score, 0.0)
            venue_pref = str(preferred_venue or "").strip().lower()

            if venue_pref == "prediction":
                reason = "prediction venue route; handled by execution_polymarket pipeline"
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?)
                    """,
                    (now_iso(), route_id, ticker_u, direction, mode, float(notional), 1.0, 0, reason),
                )
                cur.execute("UPDATE signal_routes SET status='blocked', reason=? WHERE id=?", (reason[:200], route_id))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    venue="polymarket",
                    direction=direction,
                    mode=mode,
                    entry_side=side,
                    entry_order_id="",
                    entry_status="blocked",
                    notes=reason,
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="polymarket",
                    decision=decision,
                    order_status="blocked",
                    reason=reason,
                )
                processed += 1
                continue

            if venue_pref in {"", "crypto"} and enable_hl_test_auto and is_hl_eligible(ticker_u) and score_v < hyperliquid_min_score:
                reason = f"hyperliquid score below threshold ({score_v:.2f} < {hyperliquid_min_score:.2f})"
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?)
                    """,
                    (now_iso(), route_id, ticker_u, direction, mode, float(notional), float(hl_leverage), 1, reason),
                )
                cur.execute("UPDATE signal_routes SET status='blocked', reason=? WHERE id=?", (reason[:200], route_id))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    venue="hyperliquid",
                    direction=direction,
                    mode=mode,
                    entry_side=side,
                    entry_order_id="",
                    entry_status="blocked",
                    notes=reason,
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="hyperliquid",
                    decision=decision,
                    order_status="blocked",
                    reason=reason,
                )
                processed += 1
                continue
            # Release any pending write transaction before adapter calls that may open their own DB writer.
            conn.commit()

            # Crypto path: $1 Hyperliquid test intent when enabled and symbol looks HL-eligible.
            if venue_pref in {"", "crypto"} and enable_hl_test_auto and is_hl_eligible(ticker_u):
                if allow_hl_live:
                    ok, reason, details = hyperliquid_submit_notional_live(ticker_u, side, hl_test_notional)
                    intent_id = details.get("intent_id", "")
                    status = "submitted" if ok else "blocked"
                    note = "hyperliquid live order"
                else:
                    ok, reason, details = hyperliquid_test_intent(ticker_u, side, hl_test_notional)
                    intent_id = details.get("intent_id", "")
                    status = "submitted" if ok else "blocked"
                    note = "hyperliquid test intent"
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, broker_order_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso(),
                        route_id,
                        ticker_u,
                        direction,
                        mode,
                        hl_test_notional,
                        float(hl_leverage),
                        1,
                        status,
                        str(intent_id),
                        f"{note}: {reason}",
                    ),
                )
                route_status = "executed" if ok else "blocked"
                cur.execute("UPDATE signal_routes SET status=?, reason=? WHERE id=?", (route_status, reason[:200], route_id))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    venue="hyperliquid",
                    direction=direction,
                    mode=mode,
                    entry_side=side,
                    entry_order_id=str(intent_id),
                    entry_status=status,
                    notes=f"{note}: {reason}",
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="hyperliquid",
                    decision=decision,
                    order_status=status,
                    reason=reason,
                )
                processed += 1
                continue

            if venue_pref == "crypto":
                reason = "crypto venue selected but HL path unavailable for ticker or disabled"
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?)
                    """,
                    (now_iso(), route_id, ticker_u, direction, mode, float(notional), float(hl_leverage), 1, reason),
                )
                cur.execute("UPDATE signal_routes SET status='blocked', reason=? WHERE id=?", (reason[:200], route_id))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    venue="hyperliquid",
                    direction=direction,
                    mode=mode,
                    entry_side=side,
                    entry_order_id="",
                    entry_status="blocked",
                    notes=reason,
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="hyperliquid",
                    decision=decision,
                    order_status="blocked",
                    reason=reason,
                )
                processed += 1
                continue

            # Equity/default path: Alpaca paper order when enabled.
            if venue_pref in {"", "stocks"} and enable_alpaca_paper_auto:
                if score_v < alpaca_min_score:
                    reason = f"alpaca score below threshold ({score_v:.2f} < {alpaca_min_score:.2f})"
                    cur.execute(
                        """
                        INSERT INTO execution_orders
                        (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?)
                        """,
                        (
                            now_iso(),
                            route_id,
                            ticker_u,
                            direction,
                            mode,
                            float(notional),
                            float(alp_margin_mult if alp_margin_capable else 1.0),
                            int(1 if alp_margin_capable else 0),
                            reason,
                        ),
                    )
                    cur.execute("UPDATE signal_routes SET status='blocked', reason=? WHERE id=?", (reason[:200], route_id))
                    _upsert_route_link(
                        conn=conn,
                        route_id=route_id,
                        ticker=ticker_u,
                        source_tag=source_tag or "",
                        venue="alpaca",
                        direction=direction,
                        mode=mode,
                        entry_side=side,
                        entry_order_id="",
                        entry_status="blocked",
                        notes=reason,
                    )
                    _learning_row(
                        conn=conn,
                        route_id=route_id,
                        ticker=ticker_u,
                        source_tag=source_tag or "",
                        mode=mode,
                        venue="alpaca",
                        decision=decision,
                        order_status="blocked",
                        reason=reason,
                    )
                    processed += 1
                    continue
                if side == "sell" and not allow_equity_shorts:
                    ok, reason, data = False, "equity shorting disabled by control", {}
                elif side == "sell":
                    ok_px, px_reason, px = alpaca_latest_price(ticker_u)
                    if ok_px and px > 0:
                        qty = max(1, int(float(notional) / px))
                        ok, reason, data = alpaca_submit_qty(ticker_u, side, qty)
                        reason = f"{reason}; short_qty={qty}; est_px={round(px,4)}"
                    else:
                        ok, reason, data = False, f"short price lookup failed: {px_reason}", {}
                else:
                    ok, reason, data = alpaca_submit_notional(ticker_u, side, float(notional))
                broker_id = data.get("id", "") if isinstance(data, dict) else ""
                status = "submitted" if ok else "blocked"
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, broker_order_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso(),
                        route_id,
                        ticker_u,
                        direction,
                        mode,
                        float(notional),
                        float(alp_margin_mult if alp_margin_capable else 1.0),
                        int(1 if alp_margin_capable else 0),
                        status,
                        str(broker_id),
                        f"alpaca paper: {reason}",
                    ),
                )
                route_status = "executed" if ok else "blocked"
                cur.execute("UPDATE signal_routes SET status=?, reason=? WHERE id=?", (route_status, reason[:200], route_id))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    venue="alpaca",
                    direction=direction,
                    mode=mode,
                    entry_side=side,
                    entry_order_id=str(broker_id),
                    entry_status=status,
                    notes=f"alpaca paper: {reason}",
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="alpaca",
                    decision=decision,
                    order_status=status,
                    reason=reason,
                )
                processed += 1
                continue

            if venue_pref == "stocks":
                reason = "stocks venue selected but Alpaca adapter disabled"
                cur.execute(
                    """
                    INSERT INTO execution_orders
                    (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?)
                    """,
                    (
                        now_iso(),
                        route_id,
                        ticker_u,
                        direction,
                        mode,
                        float(notional),
                        float(alp_margin_mult if alp_margin_capable else 1.0),
                        int(1 if alp_margin_capable else 0),
                        reason,
                    ),
                )
                cur.execute("UPDATE signal_routes SET status='blocked', reason=? WHERE id=?", (reason[:200], route_id))
                _upsert_route_link(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    venue="alpaca",
                    direction=direction,
                    mode=mode,
                    entry_side=side,
                    entry_order_id="",
                    entry_status="blocked",
                    notes=reason,
                )
                _learning_row(
                    conn=conn,
                    route_id=route_id,
                    ticker=ticker_u,
                    source_tag=source_tag or "",
                    mode=mode,
                    venue="alpaca",
                    decision=decision,
                    order_status="blocked",
                    reason=reason,
                )
                processed += 1
                continue

            # Fallback paper simulation if adapters disabled.
            synthetic_id = f"paper-{route_id}-{int(datetime.now().timestamp())}"
            cur.execute(
                """
                INSERT INTO execution_orders
                (created_at, route_id, ticker, direction, mode, notional, leverage_used, leverage_capable, order_status, broker_order_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, 'paper simulated order')
                """,
                (now_iso(), route_id, ticker_u, direction, mode, float(notional), 1.0, 0, synthetic_id),
            )
            cur.execute("UPDATE signal_routes SET status='executed' WHERE id=?", (route_id,))
            _upsert_route_link(
                conn=conn,
                route_id=route_id,
                ticker=ticker_u,
                source_tag=source_tag or "",
                venue="paper-sim",
                direction=direction,
                mode=mode,
                entry_side=side,
                entry_order_id=synthetic_id,
                entry_status="submitted",
                notes="paper simulated order",
            )
            _learning_row(
                conn=conn,
                route_id=route_id,
                ticker=ticker_u,
                source_tag=source_tag or "",
                mode=mode,
                venue="paper-sim",
                decision=decision,
                order_status="submitted",
                reason="fallback simulation",
            )
            processed += 1

        conn.commit()
        print(f"Execution worker: processed {processed} queued routes")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(process_queue())
