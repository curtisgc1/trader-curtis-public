#!/usr/bin/env python3
"""
Pipeline E: Cross-modality breakthrough scanner.

Goal:
- Detect "major breakthroughs" across modalities from lightweight feeds.
- Convert events into investable public-market proxy signals.
- Feed pipeline_signals as E_BREAKTHROUGH so existing routing can use it.
"""

import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests

from pipeline_store import connect, init_pipeline_tables, insert_signal

BASE_DIR = Path(__file__).parent
FEEDS_PATH = BASE_DIR / "docs" / "breakthrough-feeds.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_FEEDS = [
    {"name": "GoogleNews Breakthrough Tech", "url": "https://news.google.com/rss/search?q=technology+breakthrough"},
    {"name": "GoogleNews Cancer Robotics", "url": "https://news.google.com/rss/search?q=cancer+blood+robotics"},
    {"name": "GoogleNews Quantum Breakthrough", "url": "https://news.google.com/rss/search?q=quantum+breakthrough"},
    {"name": "GoogleNews Fusion Breakthrough", "url": "https://news.google.com/rss/search?q=fusion+energy+breakthrough"},
    {"name": "GoogleNews Space Breakthrough", "url": "https://news.google.com/rss/search?q=space+breakthrough"},
    {"name": "NASA Breaking", "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss"},
]


@dataclass
class Event:
    source: str
    title: str
    summary: str
    url: str
    published_at: str


MODALITIES = {
    "oncology_bio": {
        "keywords": ["cancer", "oncology", "liquid biopsy", "blood test", "cell therapy", "gene editing", "crispr"],
        "tickers": ["GH", "NTRA", "ILMN", "CRSP", "BEAM", "NTLA", "RXRX", "TEM", "TMO", "DHR"],
        "horizon": "position",
    },
    "robotics_automation": {
        "keywords": ["robot", "robotic", "automation", "autonomous", "humanoid", "manufacturing line"],
        "tickers": ["ISRG", "ROK", "ABB", "SYM", "TER", "PATH"],
        "horizon": "swing",
    },
    "ai_compute": {
        "keywords": ["ai model", "foundation model", "training cluster", "inference", "gpu", "chip", "semiconductor"],
        "tickers": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MSFT", "GOOGL", "AMZN", "META"],
        "horizon": "position",
    },
    "quantum": {
        "keywords": ["quantum", "qubit", "fault tolerant", "quantum error correction"],
        "tickers": ["IONQ", "RGTI", "QBTS", "IBM", "GOOGL", "HON"],
        "horizon": "position",
    },
    "energy_climate": {
        "keywords": ["fusion", "grid scale", "battery breakthrough", "hydrogen", "carbon capture", "small modular reactor", "smr"],
        "tickers": ["CEG", "SMR", "OKLO", "NNE", "BE", "PLUG", "TSLA", "ENPH"],
        "horizon": "position",
    },
    "defense_space": {
        "keywords": ["hypersonic", "defense tech", "satellite constellation", "space launch", "missile defense", "drone swarm"],
        "tickers": ["LMT", "NOC", "RTX", "PLTR", "RKLB", "ASTS"],
        "horizon": "swing",
    },
    "policy_regulation": {
        "keywords": ["fda approval", "phase 3", "breakthrough designation", "regulatory clarity", "approved", "passed bill", "signed into law"],
        "tickers": ["XBI", "IBB", "SPY", "QQQ"],
        "horizon": "swing",
    },
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS breakthrough_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          event_hash TEXT NOT NULL UNIQUE,
          source TEXT NOT NULL,
          title TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '',
          source_url TEXT NOT NULL DEFAULT '',
          published_at TEXT NOT NULL DEFAULT '',
          modality TEXT NOT NULL DEFAULT '',
          score REAL NOT NULL DEFAULT 0,
          confidence REAL NOT NULL DEFAULT 0,
          mapped_tickers_json TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()


def load_feeds() -> List[Dict[str, str]]:
    if FEEDS_PATH.exists():
        try:
            data = json.loads(FEEDS_PATH.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return DEFAULT_FEEDS


def fetch_feed_items(url: str, timeout: int = 20) -> List[Event]:
    try:
        res = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return []
    if res.status_code >= 400:
        return []
    text = res.text or ""
    if not text.strip():
        return []
    try:
        root = ET.fromstring(text)
    except Exception:
        return []

    items: List[Event] = []
    # RSS
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if title and link:
            items.append(Event(source=url, title=title, summary=desc, url=link, published_at=pub))
    # Atom fallback
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for it in root.findall(".//a:entry", ns):
            title = (it.findtext("a:title", default="", namespaces=ns) or "").strip()
            summary = (it.findtext("a:summary", default="", namespaces=ns) or "").strip()
            pub = (it.findtext("a:updated", default="", namespaces=ns) or "").strip()
            link_el = it.find("a:link", ns)
            link = (link_el.attrib.get("href", "") if link_el is not None else "").strip()
            if title and link:
                items.append(Event(source=url, title=title, summary=summary, url=link, published_at=pub))
    return items


def event_hash(evt: Event) -> str:
    raw = f"{evt.title}|{evt.url}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()


def score_event(evt: Event) -> Dict[str, Dict[str, float]]:
    text = f"{evt.title} {evt.summary}".lower()
    out: Dict[str, Dict[str, float]] = {}
    for mod, cfg in MODALITIES.items():
        kws = cfg["keywords"]
        hits = 0
        for kw in kws:
            if kw in text:
                hits += 1
        if hits == 0:
            continue
        novelty = 0.0
        for cue in ["breakthrough", "first", "novel", "approved", "phase 3", "record", "milestone", "unprecedented"]:
            if cue in text:
                novelty += 0.05
        base = min(1.0, 0.45 + hits * 0.08 + novelty)
        out[mod] = {"hits": float(hits), "confidence": round(base, 4)}
    return out


def main() -> int:
    conn = connect()
    try:
        init_pipeline_tables(conn)
        ensure_tables(conn)
        feeds = load_feeds()
        fetched = 0
        inserted_events = 0
        inserted_signals = 0

        max_new_events = 18
        min_confidence = 0.58

        for feed in feeds:
            name = str(feed.get("name", "feed"))
            url = str(feed.get("url", "")).strip()
            if not url:
                continue
            items = fetch_feed_items(url)
            fetched += len(items)
            for evt in items[:25]:
                if inserted_events >= max_new_events:
                    break
                eh = event_hash(evt)
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM breakthrough_events WHERE event_hash=? LIMIT 1", (eh,))
                if cur.fetchone():
                    continue

                mod_scores = score_event(evt)
                if not mod_scores:
                    continue
                # Pick strongest modality.
                best_mod = max(mod_scores.items(), key=lambda kv: kv[1]["confidence"])[0]
                conf = float(mod_scores[best_mod]["confidence"])
                if conf < min_confidence:
                    continue
                score = round(conf * 100.0, 2)
                tickers = MODALITIES[best_mod]["tickers"][:6]
                horizon = MODALITIES[best_mod]["horizon"]

                conn.execute(
                    """
                    INSERT INTO breakthrough_events
                    (created_at, event_hash, source, title, summary, source_url, published_at, modality, score, confidence, mapped_tickers_json, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                    """,
                    (
                        now_iso(),
                        eh,
                        name,
                        evt.title[:300],
                        evt.summary[:1200],
                        evt.url[:500],
                        evt.published_at[:120],
                        best_mod,
                        score,
                        conf,
                        json.dumps(tickers),
                    ),
                )
                inserted_events += 1

                for t in tickers:
                    rationale = (
                        f"breakthrough modality={best_mod}, source={name}, confidence={conf:.2f}, "
                        f"title={evt.title[:120]}"
                    )
                    insert_signal(
                        conn=conn,
                        pipeline_id="E_BREAKTHROUGH",
                        asset=t,
                        direction="long",
                        horizon=horizon,
                        confidence=conf,
                        score=score,
                        rationale=rationale,
                        source_refs=evt.url,
                        ttl_minutes=60 * 24 * 7,
                    )
                    inserted_signals += 1
        conn.commit()
        print(f"E_BREAKTHROUGH: feeds={len(feeds)} fetched_items={fetched} new_events={inserted_events} new_signals={inserted_signals}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
