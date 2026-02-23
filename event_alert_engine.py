#!/usr/bin/env python3
"""
Generate structured event alerts from headline feeds and map them to trade ideas.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"
EVENTS_PATH = Path(__file__).parent / "data" / "event_headlines.json"

PLAYBOOKS = [
    {
        "id": "middle-east-escalation",
        "keywords": ["iran", "war", "naval", "strait", "strike", "escalation"],
        "priority": "critical",
        "trade_asset": "BTC",
        "direction": "short",
        "base_confidence": 0.78,
        "thesis": "geopolitical escalation can trigger risk-off positioning",
        "ttl_minutes": 180,
    },
    {
        "id": "tariff-shock",
        "keywords": ["tariff", "trade war", "export control", "retaliation"],
        "priority": "high",
        "trade_asset": "SPY",
        "direction": "short",
        "base_confidence": 0.69,
        "thesis": "tariff shock can pressure growth and broad risk assets",
        "ttl_minutes": 240,
    },
    {
        "id": "sanctions-energy",
        "keywords": ["sanction", "ofac", "embargo", "oil disruption"],
        "priority": "high",
        "trade_asset": "OIL",
        "direction": "long",
        "base_confidence": 0.71,
        "thesis": "sanctions can tighten supply and lift energy proxies",
        "ttl_minutes": 240,
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          playbook_id TEXT NOT NULL,
          priority TEXT NOT NULL,
          source TEXT NOT NULL,
          headline TEXT NOT NULL,
          proposed_asset TEXT NOT NULL,
          direction TEXT NOT NULL,
          confidence REAL NOT NULL,
          alert_message TEXT NOT NULL,
          ttl_minutes INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()


def load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    try:
        data = json.loads(EVENTS_PATH.read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else []


def make_message(playbook: dict, conf: float, headline: str) -> str:
    return (
        f"{playbook['priority'].upper()} Event Alpha: {playbook['thesis']}. "
        f"Proposed {playbook['trade_asset']} {playbook['direction']} (paper). "
        f"Confidence {conf:.2f}. Headline: {headline[:180]}"
    )


def main() -> int:
    events = load_events()
    if not events:
        print("Event alert engine: no events found")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    try:
        init_table(conn)
        cur = conn.cursor()
        inserted = 0
        for event in events[-300:]:
            headline = str(event.get("headline", "")).strip()
            if not headline:
                continue
            source = str(event.get("source", "event_feed"))
            lower = headline.lower()
            for pb in PLAYBOOKS:
                if any(k in lower for k in pb["keywords"]):
                    confidence = min(0.95, pb["base_confidence"] + (0.03 if source != "manual_watch" else 0.0))
                    msg = make_message(pb, confidence, headline)
                    cur.execute(
                        """
                        INSERT INTO event_alerts
                        (created_at, playbook_id, priority, source, headline, proposed_asset, direction, confidence,
                         alert_message, ttl_minutes, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                        """,
                        (
                            now_iso(),
                            pb["id"],
                            pb["priority"],
                            source,
                            headline,
                            pb["trade_asset"],
                            pb["direction"],
                            confidence,
                            msg,
                            int(pb["ttl_minutes"]),
                        ),
                    )
                    inserted += 1
                    break
        conn.commit()
        print(f"Event alert engine: inserted {inserted} alerts")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
