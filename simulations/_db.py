"""Shared DB helpers for simulation modules.

Provides connection factory and table management for simulation_runs
so each layer can persist results without coupling to the main trading DB.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trades.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS simulation_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at     TEXT    NOT NULL,
    layer      TEXT    NOT NULL,
    contract   TEXT    NOT NULL DEFAULT '',
    ticker     TEXT    NOT NULL DEFAULT '',
    params     TEXT    NOT NULL DEFAULT '{}',
    result     TEXT    NOT NULL DEFAULT '{}',
    brier      REAL,
    edge_pct   REAL,
    n_paths    INTEGER,
    elapsed_ms REAL
)
"""

_CREATE_IDX = """
CREATE INDEX IF NOT EXISTS idx_sim_runs_contract ON simulation_runs(contract, layer, run_at)
"""


def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a connection with simulation_runs table guaranteed to exist."""
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_IDX)
    conn.commit()
    return conn


def save_run(
    conn: sqlite3.Connection,
    *,
    layer: str,
    contract: str = "",
    ticker: str = "",
    params: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    brier: float | None = None,
    edge_pct: float | None = None,
    n_paths: int | None = None,
    elapsed_ms: float | None = None,
) -> int:
    """Insert a simulation run and return the row id."""
    cur = conn.execute(
        """INSERT INTO simulation_runs
           (run_at, layer, contract, ticker, params, result, brier, edge_pct, n_paths, elapsed_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            layer,
            contract,
            ticker,
            json.dumps(params or {}, default=str),
            json.dumps(result or {}, default=str),
            brier,
            edge_pct,
            n_paths,
            elapsed_ms,
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def latest_run(
    conn: sqlite3.Connection,
    *,
    layer: str,
    contract: str = "",
    max_age_hours: float = 24.0,
) -> Optional[Dict[str, Any]]:
    """Fetch the most recent simulation run for a layer/contract, if fresh enough."""
    cur = conn.execute(
        """SELECT id, run_at, params, result, brier, edge_pct, n_paths, elapsed_ms
           FROM simulation_runs
           WHERE layer = ? AND contract = ?
           ORDER BY datetime(run_at) DESC LIMIT 1""",
        (layer, contract),
    )
    row = cur.fetchone()
    if not row:
        return None
    run_at = row[1]
    try:
        age_h = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(run_at.replace("Z", "+00:00"))
        ).total_seconds() / 3600.0
    except Exception:
        age_h = 999.0
    if age_h > max_age_hours:
        return None
    return {
        "id": row[0],
        "run_at": run_at,
        "params": json.loads(row[2]) if row[2] else {},
        "result": json.loads(row[3]) if row[3] else {},
        "brier": row[4],
        "edge_pct": row[5],
        "n_paths": row[6],
        "elapsed_ms": row[7],
        "age_hours": round(age_h, 2),
    }


def fetch_settlements(conn: sqlite3.Connection, limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch Polymarket settlement outcomes for backtesting."""
    cur = conn.execute(
        """SELECT question, resolved_direction, close_time, category, market_slug
           FROM polymarket_settlement_outcomes
           ORDER BY datetime(close_time) DESC LIMIT ?""",
        (limit,),
    )
    return [
        {
            "question": r[0],
            "direction": r[1],
            "close_time": r[2],
            "category": r[3],
            "slug": r[4],
        }
        for r in cur.fetchall()
    ]
