#!/usr/bin/env python3
"""
Pipeline C: Event/macro/geopolitical signal generator.
Consumes structured `event_alerts` (preferred) or local headlines fallback.
"""

import json
from pathlib import Path
from pipeline_store import connect, init_pipeline_tables, insert_signal
import sqlite3

EVENTS_PATH = Path(__file__).parent / "data" / "event_headlines.json"

KEYWORDS = {
    "war": ("BTC", "short", 0.78, "war escalation risk-off"),
    "iran": ("BTC", "short", 0.76, "iran escalation risk-off"),
    "strait": ("OIL", "long", 0.74, "shipping chokepoint risk"),
    "tariff": ("SPY", "short", 0.69, "tariff shock growth risk"),
    "sanction": ("OIL", "long", 0.71, "sanctions supply shock"),
}


def load_events():
    if EVENTS_PATH.exists():
        try:
            data = json.loads(EVENTS_PATH.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def load_alerts(conn) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, proposed_asset, direction, confidence, alert_message
            FROM event_alerts
            WHERE status='new'
            ORDER BY id DESC
            LIMIT 100
            """
        )
    except sqlite3.OperationalError:
        return []
    out = []
    for alert_id, asset, direction, confidence, message in cur.fetchall():
        out.append(
            {
                "id": int(alert_id),
                "asset": asset,
                "direction": direction,
                "confidence": float(confidence or 0.5),
                "message": message or "",
            }
        )
    return out


def main() -> int:
    conn = connect()
    try:
        init_pipeline_tables(conn)
        alerts = load_alerts(conn)
        created = 0
        if alerts:
            for alert in alerts:
                score = round(alert["confidence"] * 100, 2)
                insert_signal(
                    conn=conn,
                    pipeline_id="C_EVENT",
                    asset=alert["asset"],
                    direction=alert["direction"],
                    horizon="swing",
                    confidence=alert["confidence"],
                    score=score,
                    rationale=alert["message"][:220],
                    source_refs="event_alerts",
                    ttl_minutes=180,
                )
                created += 1
                conn.execute("UPDATE event_alerts SET status='consumed' WHERE id=?", (alert["id"],))
            conn.commit()
        else:
            events = load_events()
            for event in events[-200:]:
                text = str(event.get("headline", "")).lower()
                src = str(event.get("source", "event_feed"))
                for kw, (asset, direction, conf, reason) in KEYWORDS.items():
                    if kw in text:
                        score = round(conf * 100, 2)
                        insert_signal(
                            conn=conn,
                            pipeline_id="C_EVENT",
                            asset=asset,
                            direction=direction,
                            horizon="swing",
                            confidence=conf,
                            score=score,
                            rationale=f"{reason}; headline={event.get('headline','')[:120]}",
                            source_refs=src,
                            ttl_minutes=180,
                        )
                        created += 1
                        break
        print(f"Pipeline C: created {created} event signals")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
