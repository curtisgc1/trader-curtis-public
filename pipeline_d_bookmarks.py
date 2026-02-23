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
import requests

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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked_x_sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          handle TEXT NOT NULL UNIQUE,
          role_copy INTEGER NOT NULL DEFAULT 1,
          role_alpha INTEGER NOT NULL DEFAULT 1,
          active INTEGER NOT NULL DEFAULT 1,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def load_tracked_sources(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT lower(COALESCE(handle,'')), COALESCE(role_copy,1), COALESCE(role_alpha,1), COALESCE(active,1)
        FROM tracked_x_sources
        """
    )
    out = {}
    for handle, role_copy, role_alpha, active in cur.fetchall():
        h = str(handle or "").strip()
        if not h:
            continue
        out[h] = {
            "role_copy": int(role_copy or 0) == 1,
            "role_alpha": int(role_alpha or 0) == 1,
            "active": int(active or 0) == 1,
        }
    return out


def classify_handle(handle: str) -> tuple[str, str, float]:
    lower = handle.lower()
    if any(k in lower for k in ["thisguyknowsai", "jasonkimvc", "llmjunky", "sama", "openai"]):
        return ("innovation", "position", 0.68)
    if any(k in lower for k in ["github.com", "arxiv.org", "nature.com", "science.org", "k-dense.ai"]):
        return ("innovation", "position", 0.66)
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
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    if host and host not in {"x.com", "twitter.com"}:
        return host
    path = parsed.path.strip("/")
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


def resolve_url(url: str) -> str:
    try:
        # Follow short-links (t.co etc.) to actual source domain.
        res = requests.get(url, timeout=15, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        final = str(getattr(res, "url", "") or "").strip()
        if final:
            return final
    except Exception:
        pass
    return url


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
        tracked = load_tracked_sources(conn)
        cur = conn.cursor()
        inserted = 0
        promoted = 0
        for raw_url in urls:
            url = resolve_url(raw_url)
            handle = parse_handle(url)
            thesis_type, horizon, confidence = classify_handle(handle)
            strategy_tag = classify_strategy(handle, url)
            meta = tracked.get(str(handle).lower().strip())
            if meta and meta.get("active"):
                if meta.get("role_copy"):
                    strategy_tag = "POLY_COPY"
                elif meta.get("role_alpha"):
                    strategy_tag = "POLY_ALPHA"
                confidence = min(0.90, float(confidence) + 0.10)
            cur.execute(
                """
                INSERT INTO bookmark_theses
                (created_at, source_handle, source_url, thesis_type, horizon, confidence, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, 'new', '')
                ON CONFLICT(source_url) DO UPDATE SET
                  source_handle=excluded.source_handle,
                  thesis_type=excluded.thesis_type,
                  horizon=excluded.horizon,
                  confidence=excluded.confidence,
                  status='new'
                """,
                (now_iso(), handle, url, thesis_type, horizon, confidence),
            )
            inserted += 1

            cur.execute(
                """
                INSERT INTO bookmark_alpha_ideas
                (created_at, source_handle, source_url, strategy_tag, thesis_type, horizon, confidence, idea_text, promoted_to_signal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(source_url) DO UPDATE SET
                  source_handle=excluded.source_handle,
                  strategy_tag=excluded.strategy_tag,
                  thesis_type=excluded.thesis_type,
                  horizon=excluded.horizon,
                  confidence=excluded.confidence,
                  idea_text=excluded.idea_text
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
