#!/usr/bin/env python3
"""
Route top trade candidates through execution_guard into a queue table.
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from execution_guard import evaluate_candidate, init_controls, log_risk_event
from quant_gate import evaluate_quant_candidate, ensure_tables as ensure_quant_tables
from allocator_causal import (
    ensure_tables as ensure_allocator_tables,
    allocate_candidate,
    log_allocator_decision,
)

DB_PATH = Path(__file__).parent / "data" / "trades.db"
HIGH_BETA_TICKERS = {
    "TSLA", "NVDA", "PLTR", "MSTR", "COIN", "MARA", "RIOT", "ASTS", "SMCI",
    "SOFI", "AFRM", "UPST", "HOOD", "RIVN", "NIO", "TQQQ", "SQQQ",
    "BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def ensure_route_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_routes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          routed_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          score REAL NOT NULL,
          source_tag TEXT NOT NULL,
          proposed_notional REAL NOT NULL,
          mode TEXT NOT NULL,
          validation_id INTEGER NOT NULL DEFAULT 0,
          decision TEXT NOT NULL,
          reason TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued'
        )
        """
    )
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "validation_id"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN validation_id INTEGER NOT NULL DEFAULT 0")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_factor"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_factor REAL NOT NULL DEFAULT 1.0")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_regime"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_regime TEXT NOT NULL DEFAULT 'neutral'")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_reason"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_reason TEXT NOT NULL DEFAULT ''")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_blocked"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_blocked INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def fetch_candidates(conn: sqlite3.Connection, limit: int) -> List[Dict]:
    cur = conn.cursor()
    if _table_exists(conn, "trade_candidates"):
        enforce_consensus = False
        if _table_exists(conn, "execution_controls"):
            cur.execute("SELECT value FROM execution_controls WHERE key='consensus_enforce' LIMIT 1")
            row = cur.fetchone()
            enforce_consensus = bool(row and str(row[0]) == "1")
        where = "WHERE consensus_flag=1" if enforce_consensus else ""
        cur.execute(
            """
            SELECT ticker, direction, score, source_tag, COALESCE(consensus_flag,0)
            FROM trade_candidates
            """ + where + """
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "ticker": row[0],
                "direction": row[1] or "unknown",
                "score": float(row[2] or 0.0),
                "source": row[3] or "internal",
                "consensus_flag": int(row[4] or 0),
            }
            for row in rows
        ]
    return []


def clear_old_queue(conn: sqlite3.Connection, mode: str) -> None:
    conn.execute("DELETE FROM signal_routes WHERE status='queued' AND mode=?", (mode,))
    conn.commit()


def _is_high_beta_ticker(conn: sqlite3.Connection, ticker: str, min_beta: float) -> bool:
    t = str(ticker or "").upper().strip()
    if not t:
        return False
    if t in HIGH_BETA_TICKERS:
        return True
    # Optional dynamic table support if user backfills with measured betas.
    if _table_exists(conn, "ticker_beta_snapshot"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(beta_1y, 0), COALESCE(beta_6m, 0)
            FROM ticker_beta_snapshot
            WHERE UPPER(ticker)=?
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (t,),
        )
        row = cur.fetchone()
        if row:
            b1 = float(row[0] or 0.0)
            b6 = float(row[1] or 0.0)
            return max(b1, b6) >= float(min_beta)
    return False


def route_signals(limit: int, mode: str, default_notional: float) -> int:
    conn = _connect()
    try:
        init_controls(conn)
        ensure_route_table(conn)
        ensure_quant_tables(conn)
        ensure_allocator_tables(conn)
        ctl = conn.cursor()
        ctl.execute("SELECT value FROM execution_controls WHERE key='quant_gate_enforce' LIMIT 1")
        row = ctl.fetchone()
        quant_gate_enforce = False if (row and str(row[0]) == "0") else True
        ctl.execute("SELECT value FROM execution_controls WHERE key='high_beta_only' LIMIT 1")
        row_beta = ctl.fetchone()
        high_beta_only = False if (row_beta and str(row_beta[0]) == "0") else True
        ctl.execute("SELECT value FROM execution_controls WHERE key='high_beta_min_beta' LIMIT 1")
        row_minb = ctl.fetchone()
        min_beta = float((row_minb[0] if row_minb else 1.5) or 1.5)
        candidates = fetch_candidates(conn, limit=limit)
        clear_old_queue(conn, mode=mode)

        routed = 0
        approved = 0
        cur = conn.cursor()
        for c in candidates:
            ticker = (c.get("ticker") or "").upper()
            direction = c.get("direction") or "unknown"
            score = float(c.get("score") or 0.0)
            source = c.get("source") or "internal"
            notional = float(default_notional)

            if high_beta_only and (not _is_high_beta_ticker(conn, ticker, min_beta)):
                reason = f"high_beta_only_filter: {ticker} below required beta profile"
                cur.execute(
                    """
                    INSERT INTO signal_routes
                    (routed_at, ticker, direction, score, source_tag, proposed_notional, mode, validation_id, decision, reason, status,
                     allocator_factor, allocator_regime, allocator_reason, allocator_blocked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso(),
                        ticker,
                        direction,
                        score,
                        source,
                        notional,
                        mode,
                        0,
                        "rejected",
                        reason[:260],
                        "blocked",
                        1.0,
                        "high_beta",
                        "pre-allocator high-beta gate",
                        1,
                    ),
                )
                log_risk_event(
                    conn=conn,
                    ticker=ticker,
                    direction=direction,
                    candidate_score=score,
                    proposed_notional=notional,
                    approved=False,
                    reason=reason,
                )
                routed += 1
                continue

            alloc = allocate_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                candidate_score=score,
                proposed_notional=notional,
            )
            log_allocator_decision(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                result=alloc,
                base_score=score,
                base_notional=notional,
            )

            score_adj = float(alloc.adjusted_score)
            notional_adj = float(alloc.adjusted_notional)

            q_ok, q_reason, q_metrics = evaluate_quant_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                candidate_score=score_adj,
            )
            ok, reason = evaluate_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                candidate_score=score_adj,
                proposed_notional=notional_adj,
                mode=mode,
            )
            allocator_blocked = 0
            if not alloc.allowed:
                ok = False
                allocator_blocked = 1
                reason = alloc.reason
            if ok and not q_ok:
                if quant_gate_enforce:
                    ok = False
                    reason = f"quant_gate_failed: {q_reason}"
                else:
                    reason = f"quant_gate_warn_only: {q_reason}"
            reason_full = f"{reason} | allocator={alloc.reason}"
            decision = "approved" if ok else "rejected"
            status = "queued" if ok else "blocked"
            if ok:
                approved += 1
            routed += 1

            cur.execute(
                """
                INSERT INTO signal_routes
                (routed_at, ticker, direction, score, source_tag, proposed_notional, mode, validation_id, decision, reason, status,
                 allocator_factor, allocator_regime, allocator_reason, allocator_blocked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    ticker,
                    direction,
                    score_adj,
                    source,
                    notional_adj,
                    mode,
                    int(q_metrics.get("validation_id") or 0),
                    decision,
                    reason_full[:260],
                    status,
                    float(alloc.factor),
                    alloc.regime,
                    alloc.reason[:260],
                    int(allocator_blocked),
                ),
            )
            log_risk_event(
                conn=conn,
                ticker=ticker,
                direction=direction,
                candidate_score=score_adj,
                proposed_notional=notional_adj,
                approved=ok,
                reason=reason_full,
            )

        conn.commit()
        print(f"Routed {routed} candidates ({approved} approved, {routed - approved} blocked) in {mode} mode")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Route trade candidates through risk controls.")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--notional", type=float, default=100.0)
    args = parser.parse_args()
    return route_signals(limit=args.limit, mode=args.mode, default_notional=args.notional)


if __name__ == "__main__":
    raise SystemExit(main())
