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
        cur.execute("DELETE FROM pipeline_signals WHERE id NOT IN (SELECT id FROM pipeline_signals ORDER BY id DESC LIMIT 2000)")
        cur.execute("DELETE FROM signal_routes WHERE id NOT IN (SELECT id FROM signal_routes ORDER BY id DESC LIMIT 5000)")
        cur.execute("DELETE FROM execution_orders WHERE id NOT IN (SELECT id FROM execution_orders ORDER BY id DESC LIMIT 5000)")
        cur.execute("DELETE FROM risk_events WHERE id NOT IN (SELECT id FROM risk_events ORDER BY id DESC LIMIT 10000)")
        cur.execute("DELETE FROM event_alerts WHERE id NOT IN (SELECT id FROM event_alerts ORDER BY id DESC LIMIT 3000)")
        conn.commit()
        print("Maintenance: retention policy applied")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
