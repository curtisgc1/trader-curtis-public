#!/usr/bin/env python3
"""
Build learning feedback from executed routes and realized trade outcomes.
This gives the agent a persistent mistakes/wins memory pipeline.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"
STRATEGY_TAGS = {"A_SCALP", "B_LONGTERM", "C_EVENT", "D_BOOKMARKS", "POLY_ALPHA", "POLY_COPY", "POLY_ARB"}


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_learning_stats (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          wins INTEGER NOT NULL,
          losses INTEGER NOT NULL,
          pushes INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_learning_stats (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at TEXT NOT NULL,
          strategy_tag TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          wins INTEGER NOT NULL,
          losses INTEGER NOT NULL,
          pushes INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL
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
    if table_exists(conn, "route_outcomes") and not column_exists(conn, "route_outcomes", "outcome_type"):
        conn.execute("ALTER TABLE route_outcomes ADD COLUMN outcome_type TEXT NOT NULL DEFAULT 'realized'")
        conn.execute(
            """
            UPDATE route_outcomes
            SET outcome_type = CASE
              WHEN lower(COALESCE(notes,'')) LIKE 'operational_%' THEN 'operational'
              ELSE 'realized'
            END
            """
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_outcomes_source ON route_outcomes(source_tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_outcomes_type ON route_outcomes(outcome_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_links_state ON route_trade_links(state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_learning_route ON execution_learning(route_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_route ON trades(route_id)")
    conn.commit()


def backfill_route_links(conn: sqlite3.Connection, limit: int = 2000) -> int:
    if not table_exists(conn, "execution_orders") or not table_exists(conn, "route_trade_links"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT eo.route_id, eo.ticker, eo.direction, eo.mode, eo.order_status,
               COALESCE(eo.broker_order_id,''), COALESCE(eo.notes,''), COALESCE(sr.source_tag,'internal')
        FROM execution_orders eo
        LEFT JOIN route_trade_links l ON l.route_id = eo.route_id
        LEFT JOIN signal_routes sr ON sr.id = eo.route_id
        WHERE l.route_id IS NULL
        ORDER BY eo.id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    for route_id, ticker, direction, mode, order_status, broker_order_id, notes, source_tag in rows:
        status = str(order_status or "").lower()
        state = "pending"
        if status in {"rejected", "canceled", "expired", "stopped", "blocked", "failed"}:
            state = "failed"
        elif status in {"filled"}:
            state = "open"
        venue = "alpaca" if str(notes).lower().startswith("alpaca paper:") else (
            "hyperliquid" if "hyperliquid" in str(notes).lower() else "paper-sim"
        )
        side = "sell" if str(direction).lower() in {"short", "bearish", "sell"} else "buy"
        cur.execute(
            """
            INSERT OR REPLACE INTO route_trade_links
            (
              route_id, created_at, updated_at, ticker, source_tag, venue, direction, mode,
              entry_side, entry_order_id, entry_status, state, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(route_id),
                now_iso(),
                now_iso(),
                str(ticker or "").upper(),
                source_tag,
                venue,
                str(direction or ""),
                str(mode or ""),
                side,
                str(broker_order_id or ""),
                str(order_status or ""),
                state,
                str(notes or "")[:240],
            ),
        )
    conn.commit()
    return len(rows)


def strategy_for(source_tag: str) -> str:
    src = str(source_tag or "").strip().upper()
    if src in STRATEGY_TAGS:
        return src
    if src.startswith("POLY_"):
        return src
    return "UNSPECIFIED"


def clean_legacy_placeholder_outcomes(conn: sqlite3.Connection) -> int:
    """
    Remove old placeholder 'closed' outcomes that were inserted with zero PnL.
    These should be replaced by true realized PnL from trades when available.
    """
    if not table_exists(conn, "route_outcomes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM route_outcomes
        WHERE outcome_type='realized'
          AND ABS(COALESCE(pnl, 0)) < 0.000001
          AND ABS(COALESCE(pnl_percent, 0)) < 0.000001
          AND lower(COALESCE(notes,'')) LIKE 'route_link_closed:%'
        """
    )
    deleted = int(cur.rowcount or 0)
    conn.commit()
    return deleted


def resolve_route_outcomes(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "signal_routes"):
        return 0

    cur = conn.cursor()
    inserted = 0

    # 0) Realized outcomes from closed trades (best signal quality).
    if table_exists(conn, "trades"):
        cur.execute(
            """
            SELECT r.id, r.ticker, COALESCE(r.source_tag, 'internal'), r.routed_at
            FROM signal_routes r
            LEFT JOIN route_outcomes o ON o.route_id = r.id
            WHERE r.status='executed'
              AND r.decision='approved'
              AND (o.route_id IS NULL OR o.outcome_type='operational')
            ORDER BY r.id DESC
            LIMIT 300
            """
        )
        routes = cur.fetchall()
        for route_id, ticker, source_tag, routed_at in routes:
            # Deterministic route linkage if trades row carries route_id.
            if column_exists(conn, "trades", "route_id"):
                cur.execute(
                    """
                    SELECT COALESCE(pnl, 0), COALESCE(pnl_percent, 0), COALESCE(exit_date, created_at, ?)
                    FROM trades
                    WHERE route_id = ?
                      AND (COALESCE(status,'') IN ('closed','done','sold') OR COALESCE(exit_date,'') <> '')
                    ORDER BY datetime(COALESCE(exit_date, created_at, ?)) DESC
                    LIMIT 1
                    """,
                    (now_iso(), int(route_id), now_iso()),
                )
                by_route = cur.fetchone()
                if by_route:
                    pnl = float(by_route[0] or 0.0)
                    pnl_percent = float(by_route[1] or 0.0)
                    resolved_at = str(by_route[2] or now_iso())
                    if pnl > 0:
                        resolution = "win"
                    elif pnl < 0:
                        resolution = "loss"
                    else:
                        resolution = "push"
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO route_outcomes
                        (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(route_id),
                            ticker,
                            source_tag,
                            "realized",
                            resolution,
                            pnl,
                            pnl_percent,
                            resolved_at,
                            f"linked from trades.route_id; routed_at={routed_at}",
                        ),
                    )
                    inserted += 1
                    continue

            cur.execute(
                """
                SELECT COALESCE(pnl, 0), COALESCE(pnl_percent, 0), COALESCE(exit_date, created_at, ?)
                FROM trades
                WHERE upper(COALESCE(ticker,'')) = upper(?)
                  AND (COALESCE(status,'') IN ('closed','done','sold') OR COALESCE(exit_date,'') <> '')
                  AND datetime(COALESCE(exit_date, created_at, ?)) >= datetime(COALESCE(?, '1970-01-01'))
                  AND datetime(COALESCE(exit_date, created_at, ?)) <= datetime(COALESCE(?, '1970-01-01'), '+7 day')
                ORDER BY ABS(julianday(datetime(COALESCE(exit_date, created_at, ?))) - julianday(datetime(COALESCE(?, '1970-01-01')))) ASC
                LIMIT 1
                """,
                (now_iso(), ticker, now_iso(), routed_at, now_iso(), routed_at, now_iso(), routed_at),
            )
            row = cur.fetchone()
            if not row:
                continue

            pnl = float(row[0] or 0.0)
            pnl_percent = float(row[1] or 0.0)
            resolved_at = str(row[2] or now_iso())
            if pnl > 0:
                resolution = "win"
            elif pnl < 0:
                resolution = "loss"
            else:
                resolution = "push"

            cur.execute(
                """
                INSERT OR REPLACE INTO route_outcomes
                (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(route_id),
                    ticker,
                    source_tag,
                    "realized",
                    resolution,
                    pnl,
                    pnl_percent,
                    resolved_at,
                    f"linked from trades table; routed_at={routed_at}",
                ),
            )
            inserted += 1

    # 1) Operational failures from deterministic route links.
    if table_exists(conn, "route_trade_links"):
        cur.execute(
            """
            SELECT l.route_id, l.ticker, COALESCE(r.source_tag,'internal'), l.state, l.entry_status, COALESCE(l.notes,'')
            FROM route_trade_links l
            LEFT JOIN route_outcomes o ON o.route_id = l.route_id
            LEFT JOIN signal_routes r ON r.id = l.route_id
            WHERE o.route_id IS NULL
              AND lower(COALESCE(l.state,'')) IN ('failed')
            ORDER BY l.route_id DESC
            LIMIT 500
            """
        )
        for route_id, ticker, source_tag, state, entry_status, notes in cur.fetchall():
            cur.execute(
                """
                INSERT OR REPLACE INTO route_outcomes
                (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(route_id),
                    ticker,
                    source_tag,
                    "operational",
                    "loss",
                    0.0,
                    -0.25,
                    now_iso(),
                    f"route_link_{state}:{entry_status}; {notes[:140]}",
                ),
            )
            inserted += 1

    # 2) Operational failures from blocked/rejected execution (learn from mistakes immediately).
    if table_exists(conn, "execution_learning"):
        cur.execute(
            """
            SELECT el.route_id, el.ticker, COALESCE(el.source_tag,'internal'), el.order_status, COALESCE(el.reason,'')
            FROM execution_learning el
            LEFT JOIN route_outcomes o ON o.route_id = el.route_id
            WHERE o.route_id IS NULL
              AND lower(COALESCE(el.order_status,'')) IN ('blocked','rejected','canceled','expired','stopped')
            ORDER BY el.id DESC
            LIMIT 300
            """
        )
        for route_id, ticker, source_tag, order_status, reason in cur.fetchall():
            # Operational misses get a small negative score to down-rank noisy sources over time.
            cur.execute(
                """
                INSERT OR REPLACE INTO route_outcomes
                (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(route_id),
                    ticker,
                    source_tag,
                    "operational",
                    "loss",
                    0.0,
                    -0.25,
                    now_iso(),
                    f"operational_{order_status}: {reason[:180]}",
                ),
            )
            inserted += 1

    conn.commit()
    return inserted


def refresh_source_learning(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "route_outcomes"):
        return 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT source_tag,
               COUNT(*) AS n,
               SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN resolution='loss' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN resolution='push' THEN 1 ELSE 0 END) AS pushes,
               AVG(pnl) AS avg_pnl,
               AVG(pnl_percent) AS avg_pnl_percent
        FROM route_outcomes
        GROUP BY source_tag
        """
    )
    rows = cur.fetchall()

    cur.execute("DELETE FROM source_learning_stats")
    for source_tag, n, wins, losses, pushes, avg_pnl, avg_pnl_percent in rows:
        n = int(n or 0)
        wins = int(wins or 0)
        losses = int(losses or 0)
        pushes = int(pushes or 0)
        win_rate = round((wins / n) * 100.0, 2) if n else 0.0
        cur.execute(
            """
            INSERT INTO source_learning_stats
            (computed_at, source_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                source_tag,
                n,
                wins,
                losses,
                pushes,
                win_rate,
                round(float(avg_pnl or 0.0), 4),
                round(float(avg_pnl_percent or 0.0), 4),
            ),
        )
    conn.commit()
    return len(rows)


def refresh_strategy_learning(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "route_outcomes") or not table_exists(conn, "signal_routes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(r.source_tag, o.source_tag, 'UNSPECIFIED') AS tag,
               COUNT(*) AS n,
               SUM(CASE WHEN o.resolution='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN o.resolution='loss' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN o.resolution='push' THEN 1 ELSE 0 END) AS pushes,
               AVG(o.pnl) AS avg_pnl,
               AVG(o.pnl_percent) AS avg_pnl_percent
        FROM route_outcomes o
        LEFT JOIN signal_routes r ON r.id = o.route_id
        GROUP BY tag
        """
    )
    raw_rows = cur.fetchall()
    rolled = {}
    for tag, n, wins, losses, pushes, avg_pnl, avg_pnl_percent in raw_rows:
        key = strategy_for(str(tag or ""))
        bucket = rolled.get(
            key,
            {"n": 0, "wins": 0, "losses": 0, "pushes": 0, "sum_pnl": 0.0, "sum_pnl_pct": 0.0},
        )
        ni = int(n or 0)
        bucket["n"] += ni
        bucket["wins"] += int(wins or 0)
        bucket["losses"] += int(losses or 0)
        bucket["pushes"] += int(pushes or 0)
        bucket["sum_pnl"] += float(avg_pnl or 0.0) * ni
        bucket["sum_pnl_pct"] += float(avg_pnl_percent or 0.0) * ni
        rolled[key] = bucket

    cur.execute("DELETE FROM strategy_learning_stats")
    for strategy_tag, bucket in sorted(rolled.items()):
        n = int(bucket["n"] or 0)
        wins = int(bucket["wins"] or 0)
        losses = int(bucket["losses"] or 0)
        pushes = int(bucket["pushes"] or 0)
        win_rate = round((wins / n) * 100.0, 2) if n else 0.0
        avg_pnl = (bucket["sum_pnl"] / n) if n else 0.0
        avg_pnl_percent = (bucket["sum_pnl_pct"] / n) if n else 0.0
        cur.execute(
            """
            INSERT INTO strategy_learning_stats
            (computed_at, strategy_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                strategy_tag,
                n,
                wins,
                losses,
                pushes,
                win_rate,
                round(float(avg_pnl or 0.0), 4),
                round(float(avg_pnl_percent or 0.0), 4),
            ),
        )
    conn.commit()
    return len(rolled)


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        ensure_tables(conn)
        cleaned = clean_legacy_placeholder_outcomes(conn)
        backfilled = backfill_route_links(conn)
        resolved = resolve_route_outcomes(conn)
        sources = refresh_source_learning(conn)
        strategies = refresh_strategy_learning(conn)
        print(
            f"Learning feedback: cleaned {cleaned} placeholders, backfilled {backfilled} route links, "
            f"resolved {resolved} new route outcomes, refreshed {sources} source stats, {strategies} strategy stats"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
