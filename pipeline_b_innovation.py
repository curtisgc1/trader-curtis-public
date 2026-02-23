#!/usr/bin/env python3
"""
Pipeline B: Long-term innovation signal generator.
Uses local watchlist + bookmark-derived innovation source boosts.
"""

import json
import sqlite3
from pathlib import Path
from pipeline_store import connect, init_pipeline_tables, insert_signal

WATCHLIST_PATH = Path(__file__).parent / "docs" / "innovation-watchlist.json"
SOURCE_MAP_PATH = Path(__file__).parent / "docs" / "innovation-source-map.json"

DEFAULT_WATCHLIST = [
    {"asset": "NVDA", "theme": "ai_infra", "conviction": 0.62},
    {"asset": "ASML", "theme": "semicap", "conviction": 0.58},
    {"asset": "TSM", "theme": "foundry", "conviction": 0.57},
    {"asset": "ISRG", "theme": "robotics_health", "conviction": 0.56},
    {"asset": "CRSP", "theme": "gene_editing", "conviction": 0.53},
]

DEFAULT_SOURCE_MAP = {
    "handles": {
        "thisguyknowsai": ["NVDA", "MSFT", "AMZN", "GOOGL", "PLTR"],
        "jasonkimvc": ["NVDA", "ASML", "TSM", "IONQ", "QBTS"],
        "llmjunky": ["NVDA", "MSFT", "GOOGL", "META", "AMD"],
    },
    "domains": {
        "arxiv.org": ["NVDA", "AMD", "TSM"],
        "nature.com": ["CRSP", "BEAM", "NTLA", "RXRX"],
        "science.org": ["CRSP", "BEAM", "NTLA"],
        "openai.com": ["MSFT", "NVDA", "AMD"],
        "deepmind.google": ["GOOGL", "NVDA"],
    },
}


def load_watchlist():
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return DEFAULT_WATCHLIST


def load_source_map():
    if SOURCE_MAP_PATH.exists():
        try:
            data = json.loads(SOURCE_MAP_PATH.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return DEFAULT_SOURCE_MAP


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def load_tracked_alpha_sources(conn: sqlite3.Connection) -> set[str]:
    if not table_exists(conn, "tracked_x_sources"):
        return set()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT lower(COALESCE(handle,''))
        FROM tracked_x_sources
        WHERE COALESCE(active,1)=1 AND COALESCE(role_alpha,1)=1
        """
    )
    return {str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()}


def load_innovation_mentions(conn: sqlite3.Connection) -> dict:
    mentions = {}
    if not table_exists(conn, "bookmark_theses"):
        return mentions
    cur = conn.cursor()
    cur.execute(
        """
        SELECT lower(COALESCE(source_handle,'')) AS source_key,
               COUNT(*) AS n,
               AVG(COALESCE(confidence, 0.5)) AS c
        FROM bookmark_theses
        WHERE thesis_type='innovation'
          AND datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', '-60 day')
        GROUP BY lower(COALESCE(source_handle,''))
        """
    )
    for source_key, n, c in cur.fetchall():
        mentions[str(source_key)] = {"count": int(n or 0), "avg_conf": float(c or 0.5)}
    return mentions


def main() -> int:
    watchlist = load_watchlist()
    source_map = load_source_map()
    conn = connect()
    try:
        init_pipeline_tables(conn)
        innovation_mentions = load_innovation_mentions(conn)
        tracked_alpha = load_tracked_alpha_sources(conn)
        for h in tracked_alpha:
            slot = innovation_mentions.setdefault(h, {"count": 0, "avg_conf": 0.5})
            slot["count"] = int(slot.get("count", 0)) + 1
            slot["avg_conf"] = max(float(slot.get("avg_conf", 0.5)), 0.60)

        base_assets = {}
        for item in watchlist:
            asset = str(item.get("asset", "")).upper().strip()
            if not asset:
                continue
            base_assets[asset] = {
                "theme": str(item.get("theme", "innovation")),
                "base_conviction": float(item.get("conviction", 0.50)),
                "sources": [],
                "boost": 0.0,
            }

        # Boost/add assets from innovation bookmarks (handles/domains).
        handle_map = source_map.get("handles", {}) if isinstance(source_map, dict) else {}
        domain_map = source_map.get("domains", {}) if isinstance(source_map, dict) else {}
        for source_key, meta in innovation_mentions.items():
            mapped = handle_map.get(source_key, []) or domain_map.get(source_key, [])
            if not mapped:
                continue
            count = int(meta.get("count", 0))
            avg_conf = float(meta.get("avg_conf", 0.5))
            # Each mention adds conviction, capped to avoid runaway scores.
            boost = min(0.18, count * 0.03 + max(0.0, (avg_conf - 0.5) * 0.20))
            for a in mapped:
                asset = str(a).upper().strip()
                if not asset:
                    continue
                slot = base_assets.setdefault(
                    asset,
                    {
                        "theme": "innovation_source",
                        "base_conviction": 0.50,
                        "sources": [],
                        "boost": 0.0,
                    },
                )
                slot["boost"] = min(0.20, float(slot.get("boost", 0.0)) + boost)
                slot["sources"].append(f"{source_key}:{count}")

        created = 0
        for asset, cfg in base_assets.items():
            base_conviction = float(cfg.get("base_conviction", 0.50))
            boost = float(cfg.get("boost", 0.0))
            conviction = min(0.92, max(0.45, base_conviction + boost))
            score = round(conviction * 100, 2)
            source_notes = ",".join(cfg.get("sources", [])[:4]) if cfg.get("sources") else "watchlist"
            rationale = (
                f"theme={cfg.get('theme','innovation')}, base={base_conviction:.2f}, "
                f"boost={boost:.2f}, conviction={conviction:.2f}, sources={source_notes}"
            )
            insert_signal(
                conn=conn,
                pipeline_id="B_LONGTERM",
                asset=asset,
                direction="long",
                horizon="position",
                confidence=conviction,
                score=score,
                rationale=rationale,
                source_refs="innovation-watchlist+bookmarks",
                ttl_minutes=60 * 24 * 14,
            )
            created += 1
        print(f"Pipeline B: created {created} long-term signals")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
