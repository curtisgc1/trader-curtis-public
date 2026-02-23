#!/usr/bin/env python3
"""
Build normalized trade candidates from internal + external signal tables.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"

PATTERN_RELIABILITY = {
    "qml": 0.75,
    "institutional_reversal": 0.74,
    "flag_limit": 0.73,
    "liquidity_grab": 0.72,
    "supply_demand_flip": 0.70,
    "stop_hunt": 0.70,
    "fakeout": 0.68,
    "compression_expansion": 0.65,
}

COPY_TRADE_SOURCE_BOOSTS = {
    "NoLimitGains": 0.08,
    "ZenomTrader": 0.05,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_candidates_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          generated_at TEXT,
          ticker TEXT,
          direction TEXT,
          score REAL,
          sentiment_score REAL,
          pattern_type TEXT,
          pattern_score REAL,
          external_confidence REAL,
          source_tag TEXT,
          rationale TEXT
        )
        """
    )
    conn.commit()


def latest_map(cur: sqlite3.Cursor, query: str):
    cur.execute(query)
    out = {}
    for row in cur.fetchall():
        ticker = row[0]
        if ticker not in out:
            out[ticker] = row[1:]
    return out


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_candidates_table(conn)
        cur = conn.cursor()

        sentiment = {}
        if table_exists(conn, "unified_social_sentiment"):
            sentiment = latest_map(
                cur,
                """
                SELECT ticker, overall_score, timestamp
                FROM unified_social_sentiment
                ORDER BY timestamp DESC
                """,
            )

        patterns = {}
        if table_exists(conn, "institutional_patterns"):
            patterns = latest_map(
                cur,
                """
                SELECT ticker, pattern_type, direction, timestamp
                FROM institutional_patterns
                ORDER BY timestamp DESC
                """,
            )

        external = {}
        if table_exists(conn, "external_signals"):
            external = latest_map(
                cur,
                """
                SELECT ticker, source, direction, confidence, created_at
                FROM external_signals
                WHERE status IN ('new', 'active')
                ORDER BY created_at DESC
                """,
            )

        copy_signals = {}
        if table_exists(conn, "copy_trades"):
            copy_signals = latest_map(
                cur,
                """
                SELECT ticker, source_handle, call_type, call_timestamp
                FROM copy_trades
                WHERE status IN ('OPEN', 'PENDING')
                ORDER BY call_timestamp DESC
                """,
            )

        pipeline_signals = {}
        if table_exists(conn, "pipeline_signals"):
            pipeline_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                ORDER BY generated_at DESC
                """,
            )

        tickers = (
            set(sentiment.keys())
            | set(patterns.keys())
            | set(external.keys())
            | set(copy_signals.keys())
            | set(pipeline_signals.keys())
        )
        rows = []

        for ticker in tickers:
            sent_score = float((sentiment.get(ticker) or (50, None))[0] or 50)
            pattern_type = (patterns.get(ticker) or ("none", "unknown", None))[0] or "none"
            pattern_direction = (patterns.get(ticker) or ("none", "unknown", None))[1] or "unknown"
            pattern_score = float(PATTERN_RELIABILITY.get(pattern_type, 0.50))

            ext_source, ext_direction, ext_conf = "internal", "unknown", 0.50
            if ticker in external:
                ext_source = external[ticker][0] or "external"
                ext_direction = external[ticker][1] or "unknown"
                ext_conf = float(external[ticker][2] or 0.50)

            copy_source, copy_direction = None, None
            source_boost = 0.0
            if ticker in copy_signals:
                copy_source = copy_signals[ticker][0] or ""
                copy_direction = copy_signals[ticker][1] or ""
                source_boost += COPY_TRADE_SOURCE_BOOSTS.get(copy_source, 0.03)

            pipe_score = 50.0
            pipe_direction = "unknown"
            pipe_source = None
            if ticker in pipeline_signals:
                pipe_score = float(pipeline_signals[ticker][0] or 50.0)
                pipe_direction = pipeline_signals[ticker][1] or "unknown"
                pipe_source = pipeline_signals[ticker][2] or ""
                source_boost += 0.04

            # Weighted blend + small source boost cap.
            blended = (
                (sent_score / 100.0) * 0.25
                + pattern_score * 0.30
                + ext_conf * 0.20
                + (pipe_score / 100.0) * 0.25
                + min(source_boost, 0.10)
            )
            final_score = round(min(blended, 1.0) * 100.0, 2)

            direction = pattern_direction
            if direction == "unknown":
                direction = ext_direction if ext_direction != "unknown" else copy_direction or "unknown"
            if direction == "unknown" and pipe_direction != "unknown":
                direction = pipe_direction

            source_tag = ext_source if ext_source != "internal" else (copy_source or pipe_source or "internal")
            rationale = (
                f"sent={sent_score:.0f}, pattern={pattern_type}, ext={ext_source}:{ext_conf:.2f}, "
                f"pipe={pipe_source or 'none'}:{pipe_score:.1f}"
            )
            rows.append(
                (
                    now_iso(),
                    ticker,
                    direction,
                    final_score,
                    sent_score,
                    pattern_type,
                    round(pattern_score, 4),
                    round(ext_conf, 4),
                    source_tag,
                    rationale,
                )
            )

        # Keep only fresh generated set.
        cur.execute("DELETE FROM trade_candidates")
        cur.executemany(
            """
            INSERT INTO trade_candidates
            (generated_at, ticker, direction, score, sentiment_score, pattern_type, pattern_score,
             external_confidence, source_tag, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        print(f"Generated {len(rows)} trade candidates")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
