#!/usr/bin/env python3
"""
Pipeline I: Free source ingest (RSS/Atom) -> free_feed_items + external_signals.
Intended for once-daily ingestion to increase event/outcome training coverage.
"""

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "trades.db"
FEEDS_PATH = BASE / "docs" / "FREE-DATA-SOURCES.json"

POS_WORDS = {"beat", "beats", "raise", "raised", "surge", "approval", "approved", "contract", "wins", "record"}
NEG_WORDS = {"miss", "misses", "cut", "cuts", "downgrade", "lawsuit", "probe", "investigation", "fraud", "recall"}
FEED_FALLBACK = {
    "fed_press": ["SPY", "QQQ", "TLT", "DXY"],
    "bls_latest": ["SPY", "QQQ", "DXY"],
    "eia_press": ["USO", "XLE", "SPY"],
    "treasury_news": ["SPY", "QQQ", "TLT", "DXY"],
    "ecb_press": ["SPY", "QQQ", "TLT", "DXY"],
    "wsj_markets_rss": ["SPY", "QQQ", "DIA"],
    "marketwatch_topstories": ["SPY", "QQQ", "DIA"],
    "seekingalpha_market_currents": ["SPY", "QQQ", "DIA"],
    "coindesk_rss": ["BTC", "ETH", "SOL"],
    "cointelegraph_rss": ["BTC", "ETH", "SOL"],
    "sec_8k_current": ["SPY"],
    "sec_10q_current": ["SPY"],
    "sec_10k_current": ["SPY"],
    "sec_13d_current": ["SPY"],
    "sec_13g_current": ["SPY"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS free_feed_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source_name TEXT NOT NULL,
          title TEXT NOT NULL,
          link TEXT NOT NULL,
          published_at TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          UNIQUE(source_name, link)
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


def ticker_universe(conn: sqlite3.Connection) -> List[str]:
    out = {
        "SPY", "QQQ", "DIA", "IWM", "TLT", "GLD", "SLV", "USO", "UUP",
        "BTC", "ETH", "SOL", "XRP", "DOGE",
    }
    cur = conn.cursor()
    if table_exists(conn, "trade_candidates"):
        cur.execute("SELECT DISTINCT UPPER(COALESCE(ticker,'')) FROM trade_candidates WHERE COALESCE(ticker,'')<>''")
        out.update([str(r[0]).strip().upper() for r in cur.fetchall() if str(r[0]).strip()])
    if table_exists(conn, "trades"):
        cur.execute("SELECT DISTINCT UPPER(COALESCE(ticker,'')) FROM trades WHERE COALESCE(ticker,'')<>''")
        out.update([str(r[0]).strip().upper() for r in cur.fetchall() if str(r[0]).strip()])
    return sorted([t for t in out if t and len(t) <= 8])


def parse_direction(text: str) -> str:
    txt = (text or "").lower()
    pos = sum(1 for w in POS_WORDS if w in txt)
    neg = sum(1 for w in NEG_WORDS if w in txt)
    if pos > neg:
        return "long"
    if neg > pos:
        return "short"
    return "long"


def parse_confidence(text: str) -> float:
    txt = (text or "").lower()
    pos = sum(1 for w in POS_WORDS if w in txt)
    neg = sum(1 for w in NEG_WORDS if w in txt)
    strength = min(0.20, (abs(pos - neg) * 0.04))
    return round(0.50 + strength, 4)


def extract_tickers(text: str, universe: List[str]) -> List[str]:
    txt = (text or "")
    out = set()
    for m in re.findall(r"\$([A-Z]{1,6})\b", txt):
        out.add(m.upper())
    up = txt.upper()
    for t in universe:
        if re.search(rf"\b{re.escape(t)}\b", up):
            out.add(t)
    return sorted(out)


def feed_items(xml_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items

    # RSS style
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        summary = (node.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "pub": pub, "summary": summary})

    # Atom style
    for node in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        title = (node.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        pub = (node.findtext("{http://www.w3.org/2005/Atom}updated") or "").strip()
        summary = (node.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()
        link = ""
        lnode = node.find("{http://www.w3.org/2005/Atom}link")
        if lnode is not None:
            link = str(lnode.attrib.get("href", "")).strip()
        if title and link:
            items.append({"title": title, "link": link, "pub": pub, "summary": summary})

    return items[:120]


def main() -> int:
    if not FEEDS_PATH.exists():
        print("Pipeline I: feed list missing")
        return 1

    feeds = json.loads(FEEDS_PATH.read_text())
    conn = connect()
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        ensure_tables(conn)
        universe = ticker_universe(conn)
        cur = conn.cursor()

        feed_count = 0
        inserted_items = 0
        inserted_signals = 0

        for f in feeds:
            name = str(f.get("name") or "").strip()
            url = str(f.get("url") or "").strip()
            if not name or not url:
                continue
            feed_count += 1
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code >= 400 or not (r.text or "").strip():
                    continue
                rows = feed_items(r.text)
            except Exception:
                continue

            for row in rows:
                title = row.get("title", "")
                link = row.get("link", "")
                pub = row.get("pub", "")
                summary = row.get("summary", "")
                if not title or not link:
                    continue
                try:
                    cur.execute(
                        """
                        INSERT INTO free_feed_items
                        (created_at, source_name, title, link, published_at, summary)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (now_iso(), name, title[:500], link[:900], pub[:120], summary[:1500]),
                    )
                    inserted_items += 1
                except sqlite3.IntegrityError:
                    continue

                tickers = extract_tickers(f"{title} {summary}", universe)
                if not tickers:
                    tickers = FEED_FALLBACK.get(name, [])
                direction = parse_direction(f"{title} {summary}")
                conf = parse_confidence(f"{title} {summary}")

                for t in tickers[:4]:
                    cur.execute(
                        """
                        INSERT INTO external_signals
                        (created_at, source, source_url, ticker, direction, confidence, notes, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                        """,
                        (
                            now_iso(),
                            f"freefeed:{name}",
                            link[:900],
                            t,
                            direction,
                            float(conf),
                            f"{name} headline: {title[:180]}",
                        ),
                    )
                    inserted_signals += 1

        conn.commit()
        print(
            f"Pipeline I (Free Sources): feeds={feed_count} items_inserted={inserted_items} external_signals={inserted_signals}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
