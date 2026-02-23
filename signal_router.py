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

DB_PATH = Path(__file__).parent / "data" / "trades.db"


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
    conn.commit()


def fetch_candidates(conn: sqlite3.Connection, limit: int) -> List[Dict]:
    cur = conn.cursor()
    if _table_exists(conn, "trade_candidates"):
        cur.execute(
            """
            SELECT ticker, direction, score, source_tag
            FROM trade_candidates
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
            }
            for row in rows
        ]
    return []


def clear_old_queue(conn: sqlite3.Connection, mode: str) -> None:
    conn.execute("DELETE FROM signal_routes WHERE status='queued' AND mode=?", (mode,))
    conn.commit()


def route_signals(limit: int, mode: str, default_notional: float) -> int:
    conn = _connect()
    try:
        init_controls(conn)
        ensure_route_table(conn)
        ensure_quant_tables(conn)
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

            q_ok, q_reason, q_metrics = evaluate_quant_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                candidate_score=score,
            )
            ok, reason = evaluate_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                candidate_score=score,
                proposed_notional=notional,
                mode=mode,
            )
            if ok and not q_ok:
                ok = False
                reason = f"quant_gate_failed: {q_reason}"
            decision = "approved" if ok else "rejected"
            status = "queued" if ok else "blocked"
            if ok:
                approved += 1
            routed += 1

            cur.execute(
                """
                INSERT INTO signal_routes
                (routed_at, ticker, direction, score, source_tag, proposed_notional, mode, validation_id, decision, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    ticker,
                    direction,
                    score,
                    source,
                    notional,
                    mode,
                    int(q_metrics.get("validation_id") or 0),
                    decision,
                    reason,
                    status,
                ),
            )
            log_risk_event(
                conn=conn,
                ticker=ticker,
                direction=direction,
                candidate_score=score,
                proposed_notional=notional,
                approved=ok,
                reason=reason,
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
