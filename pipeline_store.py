#!/usr/bin/env python3
"""
Shared persistence for multi-pipeline signal generation.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def init_pipeline_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          generated_at TEXT NOT NULL,
          pipeline_id TEXT NOT NULL,
          asset TEXT NOT NULL,
          direction TEXT NOT NULL,
          horizon TEXT NOT NULL,
          confidence REAL NOT NULL,
          score REAL NOT NULL,
          rationale TEXT NOT NULL,
          source_refs TEXT NOT NULL DEFAULT '',
          ttl_minutes INTEGER NOT NULL DEFAULT 180,
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()


def insert_signal(
    conn: sqlite3.Connection,
    pipeline_id: str,
    asset: str,
    direction: str,
    horizon: str,
    confidence: float,
    score: float,
    rationale: str,
    source_refs: str = "",
    ttl_minutes: int = 180,
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_signals
        (generated_at, pipeline_id, asset, direction, horizon, confidence, score, rationale, source_refs, ttl_minutes, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
        """,
        (
            now_iso(),
            pipeline_id,
            asset.upper(),
            direction,
            horizon,
            float(confidence),
            float(score),
            rationale,
            source_refs,
            int(ttl_minutes),
        ),
    )
    conn.commit()
