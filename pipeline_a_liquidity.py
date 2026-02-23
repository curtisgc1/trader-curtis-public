#!/usr/bin/env python3
"""
Pipeline A: Liquidity scalp signal generator.
"""

import sqlite3
from pipeline_store import connect, init_pipeline_tables, insert_signal

PATTERN_WEIGHTS = {
    "qml": 0.75,
    "institutional_reversal": 0.74,
    "flag_limit": 0.73,
    "liquidity_grab": 0.72,
    "supply_demand_flip": 0.70,
    "stop_hunt": 0.70,
    "fakeout": 0.68,
    "compression_expansion": 0.65,
}


def main() -> int:
    conn = connect()
    try:
        init_pipeline_tables(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.ticker, p.pattern_type, p.direction, COALESCE(s.overall_score, 50) AS sentiment
            FROM institutional_patterns p
            LEFT JOIN (
              SELECT ticker, overall_score
              FROM unified_social_sentiment
              WHERE id IN (
                SELECT MAX(id) FROM unified_social_sentiment GROUP BY ticker
              )
            ) s ON s.ticker = p.ticker
            ORDER BY p.id DESC
            LIMIT 20
            """
        )
        rows = cur.fetchall()
        created = 0
        seen = set()
        for ticker, ptype, direction, sentiment in rows:
            if ticker in seen:
                continue
            seen.add(ticker)
            pattern_score = PATTERN_WEIGHTS.get((ptype or "").lower(), 0.50)
            confidence = min(0.95, max(0.25, 0.55 * pattern_score + 0.45 * (float(sentiment) / 100.0)))
            score = round(confidence * 100, 2)
            signal_dir = "short" if str(direction).lower() in {"bearish", "short"} else "long"
            rationale = f"pattern={ptype}, sentiment={sentiment}"
            insert_signal(
                conn=conn,
                pipeline_id="A_SCALP",
                asset=ticker,
                direction=signal_dir,
                horizon="intraday",
                confidence=confidence,
                score=score,
                rationale=rationale,
                source_refs="institutional_patterns,unified_social_sentiment",
                ttl_minutes=120,
            )
            created += 1
        print(f"Pipeline A: created {created} scalp signals")
        return 0
    except sqlite3.OperationalError as exc:
        print(f"Pipeline A skipped: {exc}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
