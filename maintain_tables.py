#!/usr/bin/env python3
"""
Lightweight retention maintenance for high-churn tables.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        # Keep active working set compact.
        cur.execute("DELETE FROM pipeline_signals WHERE id NOT IN (SELECT id FROM pipeline_signals ORDER BY id DESC LIMIT 2000)")
        cur.execute("DELETE FROM signal_routes WHERE id NOT IN (SELECT id FROM signal_routes ORDER BY id DESC LIMIT 5000)")
        cur.execute("DELETE FROM execution_orders WHERE id NOT IN (SELECT id FROM execution_orders ORDER BY id DESC LIMIT 5000)")
        cur.execute("DELETE FROM risk_events WHERE id NOT IN (SELECT id FROM risk_events ORDER BY id DESC LIMIT 10000)")
        cur.execute("DELETE FROM event_alerts WHERE id NOT IN (SELECT id FROM event_alerts ORDER BY id DESC LIMIT 3000)")
        # Daily hygiene: remove stale not-taken candidates/routes so UI is not noisy.
        cur.execute(
            """
            DELETE FROM signal_routes
            WHERE datetime(COALESCE(routed_at, '1970-01-01')) < datetime('now', '-1 day')
              AND COALESCE(decision,'') <> 'approved'
            """
        )
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trade_candidates'").fetchone():
            cur.execute("DELETE FROM trade_candidates")
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='polymarket_candidates'").fetchone():
            cur.execute(
                """
                DELETE FROM polymarket_candidates
                WHERE datetime(COALESCE(created_at, '1970-01-01')) < datetime('now', '-1 day')
                  AND COALESCE(status,'') IN ('new','awaiting_approval','stale')
                """
            )
        conn.commit()
        print("Maintenance: retention policy applied")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
