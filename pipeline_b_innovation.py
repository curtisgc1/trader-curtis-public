#!/usr/bin/env python3
"""
Pipeline B: Long-term innovation signal generator.
Uses local watchlist + optional conviction scores.
"""

import json
from pathlib import Path
from pipeline_store import connect, init_pipeline_tables, insert_signal

WATCHLIST_PATH = Path(__file__).parent / "docs" / "innovation-watchlist.json"

DEFAULT_WATCHLIST = [
    {"asset": "NVDA", "theme": "ai_infra", "conviction": 0.62},
    {"asset": "ASML", "theme": "semicap", "conviction": 0.58},
    {"asset": "TSM", "theme": "foundry", "conviction": 0.57},
    {"asset": "ISRG", "theme": "robotics_health", "conviction": 0.56},
    {"asset": "CRSP", "theme": "gene_editing", "conviction": 0.53},
]


def load_watchlist():
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return DEFAULT_WATCHLIST


def main() -> int:
    watchlist = load_watchlist()
    conn = connect()
    try:
        init_pipeline_tables(conn)
        created = 0
        for item in watchlist:
            asset = str(item.get("asset", "")).upper().strip()
            if not asset:
                continue
            conviction = float(item.get("conviction", 0.50))
            score = round(conviction * 100, 2)
            rationale = f"theme={item.get('theme','innovation')}, conviction={conviction:.2f}"
            insert_signal(
                conn=conn,
                pipeline_id="B_LONGTERM",
                asset=asset,
                direction="long",
                horizon="position",
                confidence=conviction,
                score=score,
                rationale=rationale,
                source_refs="innovation-watchlist",
                ttl_minutes=60 * 24 * 14,
            )
            created += 1
        print(f"Pipeline B: created {created} long-term signals")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
