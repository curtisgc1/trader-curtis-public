#!/usr/bin/env python3
"""
Pipeline D: Convert X bookmark URLs into structured thesis records.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "trades.db"
BOOKMARKS_PATH = BASE_DIR / "docs" / "x-bookmarks.json"
ENV_PATH = BASE_DIR / ".env"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env() -> dict:
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def init_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookmark_theses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source_handle TEXT NOT NULL,
          source_url TEXT NOT NULL UNIQUE,
          thesis_type TEXT NOT NULL,
          horizon TEXT NOT NULL,
          confidence REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'new',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookmark_alpha_ideas (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source_handle TEXT NOT NULL,
          source_url TEXT NOT NULL UNIQUE,
          strategy_tag TEXT NOT NULL,
          thesis_type TEXT NOT NULL,
          horizon TEXT NOT NULL,
          confidence REAL NOT NULL,
          idea_text TEXT NOT NULL DEFAULT '',
          promoted_to_signal INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT,
          source TEXT,
          source_url TEXT,
          ticker TEXT,
          direction TEXT,
          confidence REAL,
          notes TEXT,
          status TEXT DEFAULT 'new'
        )
        """
    )
    conn.commit()


def classify_handle(handle: str) -> tuple[str, str, float]:
    lower = handle.lower()
    if any(k in lower for k in ["quant", "trader", "gains", "crypto"]):
        return ("trading", "intraday", 0.58)
    if any(k in lower for k in ["ai", "vc", "science", "bio"]):
        return ("innovation", "position", 0.55)
    return ("macro", "swing", 0.50)


def classify_strategy(handle: str, url: str) -> str:
    s = f"{handle} {url}".lower()
    if any(k in s for k in ["copy", "signal", "calls", "realgemsfinder", "moondev", "alexmasoncrypto"]):
        return "POLY_COPY"
    if any(k in s for k in ["arb", "arbitrage", "misprice", "spread"]):
        return "POLY_ARB"
    return "POLY_ALPHA"


def infer_ticker_and_direction(url: str, handle: str) -> tuple[str, str]:
    s = f"{url} {handle}".upper()
    if "BTC" in s:
        return "BTC", "short"
    if "ETH" in s:
        return "ETH", "long"
    if "SOL" in s:
        return "SOL", "long"
    if "SPY" in s:
        return "SPY", "short"
    if "QQQ" in s:
        return "QQQ", "short"
    return "SPY", "short"


def parse_handle(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "unknown"
    return re.split(r"/", path)[0] or "unknown"


def load_urls() -> list[str]:
    if not BOOKMARKS_PATH.exists():
        return []
    data = json.loads(BOOKMARKS_PATH.read_text())
    urls = []
    urls.extend(data.get("status_urls", []))
    urls.extend(data.get("external_urls", []))
    seen = set()
    out = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def main() -> int:
    env = load_env()
    promote_enabled = str(env.get("BOOKMARK_PROMOTE_TO_SIGNALS", "0")).strip() == "1"
    urls = load_urls()
    if not urls:
        print("No bookmark URLs found")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    try:
        init_table(conn)
        cur = conn.cursor()
        inserted = 0
        promoted = 0
        for url in urls:
            handle = parse_handle(url)
            thesis_type, horizon, confidence = classify_handle(handle)
            strategy_tag = classify_strategy(handle, url)
            cur.execute(
                """
                INSERT OR IGNORE INTO bookmark_theses
                (created_at, source_handle, source_url, thesis_type, horizon, confidence, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, 'new', '')
                """,
                (now_iso(), handle, url, thesis_type, horizon, confidence),
            )
            if cur.rowcount > 0:
                inserted += 1

            cur.execute(
                """
                INSERT OR IGNORE INTO bookmark_alpha_ideas
                (created_at, source_handle, source_url, strategy_tag, thesis_type, horizon, confidence, idea_text, promoted_to_signal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    now_iso(),
                    handle,
                    url,
                    strategy_tag,
                    thesis_type,
                    horizon,
                    confidence,
                    f"bookmark strategy={strategy_tag} thesis={thesis_type}",
                ),
            )

        if promote_enabled:
            # Promote unpromoted bookmark ideas into external signals only when explicitly enabled.
            cur.execute(
                """
                SELECT id, source_handle, source_url, strategy_tag, confidence, thesis_type, horizon
                FROM bookmark_alpha_ideas
                WHERE promoted_to_signal = 0
                ORDER BY id ASC
                LIMIT 200
                """
            )
            for idea_id, source_handle, source_url, strategy_tag, conf, thesis_type, horizon in cur.fetchall():
                ticker, direction = infer_ticker_and_direction(source_url, source_handle)
                cur.execute(
                    """
                    INSERT INTO external_signals
                    (created_at, source, source_url, ticker, direction, confidence, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                    """,
                    (
                        now_iso(),
                        f"{strategy_tag}:{source_handle}",
                        source_url,
                        ticker,
                        direction,
                        float(conf or 0.5),
                        f"bookmark-promoted; thesis={thesis_type}; horizon={horizon}",
                    ),
                )
                cur.execute("UPDATE bookmark_alpha_ideas SET promoted_to_signal = 1 WHERE id = ?", (int(idea_id),))
                promoted += 1
        conn.commit()
        mode = "enabled" if promote_enabled else "disabled"
        print(f"Pipeline D: processed {len(urls)} URLs, inserted {inserted} thesis records, promoted {promoted} ideas (promotion {mode})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
