#!/usr/bin/env python3
"""
Pipeline F: Finviz free RSS ingest -> external_signals.
"""

import sqlite3
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import requests

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "trades.db"

DEFAULT_TICKERS = [
    "SPY", "QQQ", "DIA", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "PLTR", "MARA", "ASTS", "NEM", "AEM",
]

POS_WORDS = {"surge", "beat", "beats", "upgrade", "upgrades", "bull", "bullish", "rally", "jumps", "jump", "record", "breakout"}
NEG_WORDS = {"miss", "misses", "downgrade", "downgrades", "bear", "bearish", "drop", "drops", "falls", "plunge", "plunges", "selloff"}


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
        CREATE TABLE IF NOT EXISTS finviz_headlines (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          title TEXT NOT NULL,
          source_url TEXT NOT NULL,
          published_at TEXT NOT NULL DEFAULT '',
          sentiment_hint TEXT NOT NULL DEFAULT 'neutral',
          UNIQUE(ticker, source_url)
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
    out = set(DEFAULT_TICKERS)
    cur = conn.cursor()
    if table_exists(conn, "trades"):
        cur.execute("SELECT DISTINCT upper(COALESCE(ticker,'')) FROM trades WHERE COALESCE(ticker,'')<>''")
        out.update([str(r[0]).strip().upper() for r in cur.fetchall() if str(r[0]).strip()])
    if table_exists(conn, "copy_trades"):
        cur.execute("SELECT DISTINCT upper(COALESCE(ticker,'')) FROM copy_trades WHERE COALESCE(ticker,'')<>''")
        out.update([str(r[0]).strip().upper() for r in cur.fetchall() if str(r[0]).strip()])
    return sorted([t for t in out if t and len(t) <= 8])[:40]


def parse_direction(title: str) -> Tuple[str, float]:
    txt = str(title or "").lower()
    score = 0
    for w in POS_WORDS:
        if w in txt:
            score += 1
    for w in NEG_WORDS:
        if w in txt:
            score -= 1
    if score > 0:
        return "long", min(0.78, 0.55 + score * 0.05)
    if score < 0:
        return "short", min(0.78, 0.55 + abs(score) * 0.05)
    return "long", 0.52


def fetch_rss(ticker: str) -> List[dict]:
    # Finviz RSS endpoint availability can vary by deployment; keep for compatibility.
    url = f"https://finviz.com/rss.ashx?t={ticker}"
    try:
        res = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code >= 400 or not res.text.strip():
            return []
        root = ET.fromstring(res.text)
    except Exception:
        return []

    items = []
    for item in root.findall(".//item")[:5]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "pub": pub})
    return items


def fetch_quote_news(ticker: str) -> List[dict]:
    url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
    try:
        res = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if res.status_code >= 400 or not res.text.strip():
            return []
        text = res.text
    except Exception:
        return []

    items: List[dict] = []
    row_re = re.compile(r"<tr[^>]*>.*?</tr>", re.IGNORECASE | re.DOTALL)
    for row in row_re.findall(text):
        date_m = re.search(r'<td[^>]*align=\"right\"[^>]*>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
        link_m = re.search(
            r'<a[^>]*class=\"tab-link-news\"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>',
            row,
            re.IGNORECASE | re.DOTALL,
        )
        if not link_m:
            continue
        raw_date = re.sub(r"<[^>]+>", "", (date_m.group(1) if date_m else "")).strip()
        raw_link = (link_m.group(1) or "").strip()
        raw_title = re.sub(r"<[^>]+>", "", link_m.group(2) or "").strip()
        if not raw_link or not raw_title:
            continue
        link = html.unescape(raw_link)
        if link.startswith("/"):
            link = f"https://finviz.com{link}"
        title = html.unescape(raw_title)
        pub = html.unescape(raw_date)
        items.append({"title": title, "link": link, "pub": pub})
        if len(items) >= 6:
            break
    return items


def main() -> int:
    conn = connect()
    try:
        ensure_tables(conn)
        cur = conn.cursor()
        tickers = ticker_universe(conn)
        inserted_news = 0
        inserted_signals = 0

        for t in tickers:
            rows = fetch_rss(t)
            if not rows:
                rows = fetch_quote_news(t)
            for row in rows:
                direction, conf = parse_direction(row["title"])
                try:
                    cur.execute(
                        """
                        INSERT INTO finviz_headlines (created_at, ticker, title, source_url, published_at, sentiment_hint)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (now_iso(), t, row["title"], row["link"], row["pub"], direction),
                    )
                    inserted_news += 1
                except sqlite3.IntegrityError:
                    continue

                cur.execute(
                    """
                    INSERT INTO external_signals
                    (created_at, source, source_url, ticker, direction, confidence, notes, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                    """,
                    (
                        now_iso(),
                        "finviz:rss",
                        row["link"],
                        t,
                        direction,
                        float(conf),
                        f"finviz headline: {row['title'][:180]}",
                    ),
                )
                inserted_signals += 1

        conn.commit()
        print(f"Pipeline F (Finviz): tickers={len(tickers)} headlines_inserted={inserted_news} external_signals={inserted_signals}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
