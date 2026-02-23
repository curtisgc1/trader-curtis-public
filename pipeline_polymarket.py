#!/usr/bin/env python3
"""
Polymarket pipeline:
- ingest active markets from Gamma API
- compute strategy candidates: POLY_ALPHA / POLY_COPY / POLY_ARB
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
GAMMA_BASE = "https://gamma-api.polymarket.com"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_markets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          fetched_at TEXT NOT NULL,
          market_id TEXT NOT NULL UNIQUE,
          event_id TEXT NOT NULL DEFAULT '',
          slug TEXT NOT NULL DEFAULT '',
          question TEXT NOT NULL DEFAULT '',
          outcomes_json TEXT NOT NULL DEFAULT '[]',
          outcome_prices_json TEXT NOT NULL DEFAULT '[]',
          liquidity REAL NOT NULL DEFAULT 0,
          volume_24h REAL NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          closed INTEGER NOT NULL DEFAULT 0,
          market_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          strategy_id TEXT NOT NULL,
          market_id TEXT NOT NULL,
          slug TEXT NOT NULL DEFAULT '',
          question TEXT NOT NULL DEFAULT '',
          outcome TEXT NOT NULL,
          implied_prob REAL NOT NULL,
          model_prob REAL NOT NULL,
          edge REAL NOT NULL,
          confidence REAL NOT NULL,
          source_tag TEXT NOT NULL DEFAULT '',
          rationale TEXT NOT NULL DEFAULT '',
          market_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()


def fetch_markets(limit: int = 150) -> List[Dict[str, Any]]:
    # Try common Gamma endpoints with fallback.
    endpoints = [
        f"{GAMMA_BASE}/markets?active=true&closed=false&limit={limit}",
        f"{GAMMA_BASE}/events?active=true&closed=false&limit={limit}",
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=20)
            if res.status_code >= 400:
                continue
            data = res.json()
        except Exception:
            continue
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Common wrappers.
            for k in ("data", "markets", "events"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
    return []


def normalize_market(raw: Dict[str, Any]) -> Dict[str, Any]:
    market_id = str(raw.get("id") or raw.get("marketId") or raw.get("conditionId") or "")
    slug = str(raw.get("slug") or "")
    question = str(raw.get("question") or raw.get("title") or "")
    event_id = str(raw.get("eventId") or raw.get("event_id") or "")
    outcomes = raw.get("outcomes") or []
    outcome_prices = raw.get("outcomePrices") or raw.get("outcome_prices") or []
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
            outcome_prices = []
    liquidity = float(raw.get("liquidity") or raw.get("liquidityNum") or 0.0)
    volume_24h = float(raw.get("volume24hr") or raw.get("volume24h") or raw.get("volume") or 0.0)
    active = 1 if bool(raw.get("active", True)) else 0
    closed = 1 if bool(raw.get("closed", False)) else 0
    market_url = f"https://polymarket.com/market/{slug}" if slug else ""
    return {
        "market_id": market_id,
        "event_id": event_id,
        "slug": slug,
        "question": question,
        "outcomes": outcomes if isinstance(outcomes, list) else [],
        "outcome_prices": outcome_prices if isinstance(outcome_prices, list) else [],
        "liquidity": liquidity,
        "volume_24h": volume_24h,
        "active": active,
        "closed": closed,
        "market_url": market_url,
    }


def store_markets(conn: sqlite3.Connection, markets: List[Dict[str, Any]]) -> int:
    cur = conn.cursor()
    inserted = 0
    for m in markets:
        if not m["market_id"]:
            continue
        cur.execute(
            """
            INSERT INTO polymarket_markets
            (fetched_at, market_id, event_id, slug, question, outcomes_json, outcome_prices_json, liquidity, volume_24h, active, closed, market_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
              fetched_at=excluded.fetched_at,
              event_id=excluded.event_id,
              slug=excluded.slug,
              question=excluded.question,
              outcomes_json=excluded.outcomes_json,
              outcome_prices_json=excluded.outcome_prices_json,
              liquidity=excluded.liquidity,
              volume_24h=excluded.volume_24h,
              active=excluded.active,
              closed=excluded.closed,
              market_url=excluded.market_url
            """,
            (
                now_iso(),
                m["market_id"],
                m["event_id"],
                m["slug"],
                m["question"],
                json.dumps(m["outcomes"]),
                json.dumps(m["outcome_prices"]),
                m["liquidity"],
                m["volume_24h"],
                m["active"],
                m["closed"],
                m["market_url"],
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def _latest_source_reliability(conn: sqlite3.Connection) -> float:
    if not _table_exists(conn, "source_scores"):
        return 0.5
    cur = conn.cursor()
    cur.execute("SELECT AVG(reliability_score) FROM source_scores")
    v = float((cur.fetchone() or [50.0])[0] or 50.0)
    return max(0.0, min(1.0, v / 100.0))


def _event_bias(conn: sqlite3.Connection, question: str) -> float:
    if not _table_exists(conn, "event_alerts"):
        return 0.0
    q = question.lower()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(confidence,0.5), COALESCE(alert_message,''), COALESCE(direction,'')
        FROM event_alerts
        ORDER BY created_at DESC
        LIMIT 25
        """
    )
    bump = 0.0
    for conf, msg, direction in cur.fetchall():
        text = f"{msg} {direction}".lower()
        # rough keyword overlap.
        overlap = sum(1 for token in ("trump", "tariff", "iran", "btc", "fed", "war", "crypto", "election") if token in q and token in text)
        if overlap > 0:
            bump += min(0.08, 0.02 * overlap) * float(conf or 0.5)
    return max(-0.2, min(0.2, bump))


def build_candidates(conn: sqlite3.Connection, limit: int = 120) -> int:
    cur = conn.cursor()
    cur.execute("DELETE FROM polymarket_candidates")
    src_rel = _latest_source_reliability(conn)

    cur.execute(
        """
        SELECT market_id, slug, question, outcomes_json, outcome_prices_json, liquidity, volume_24h, market_url
        FROM polymarket_markets
        WHERE active=1 AND closed=0
        ORDER BY liquidity DESC, volume_24h DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()

    copy_handles = set()
    if _table_exists(conn, "bookmark_alpha_ideas"):
        cur.execute(
            """
            SELECT lower(COALESCE(source_handle,''))
            FROM bookmark_alpha_ideas
            WHERE strategy_tag='POLY_COPY'
            ORDER BY id DESC
            LIMIT 100
            """
        )
        copy_handles.update([str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()])
    if _table_exists(conn, "copy_trades"):
        cur.execute(
            """
            SELECT lower(COALESCE(source_handle,''))
            FROM copy_trades
            ORDER BY call_timestamp DESC
            LIMIT 100
            """
        )
        copy_handles.update([str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()])

    people_markets = (
        "election",
        "nominee",
        "president",
        "winner",
        "candidate",
        "poll",
        "prime minister",
        "parliament",
        "become the next",
        "next prime minister",
        "next president",
    )
    macro_markets = ("fed", "rate", "tariff", "war", "iran", "oil", "bitcoin", "btc", "ethereum", "eth", "crypto")
    created = 0
    for market_id, slug, question, outcomes_json, prices_json, liquidity, volume_24h, market_url in rows:
        try:
            outcomes = json.loads(outcomes_json or "[]")
            prices = [float(x) for x in json.loads(prices_json or "[]")]
        except Exception:
            continue
        if not outcomes or not prices or len(outcomes) != len(prices):
            continue
        # Use first outcome as YES-equivalent candidate where applicable.
        for i, outcome in enumerate(outcomes[:2]):
            implied = max(0.0, min(1.0, float(prices[i] if i < len(prices) else 0.0)))
            model = implied + (_event_bias(conn, question) * (1.1 if i == 0 else -1.1)) + (src_rel - 0.5) * 0.06
            model = max(0.01, min(0.99, model))
            edge = round((model - implied) * 100.0, 4)
            conf = round(max(0.35, min(0.9, abs(edge) / 20.0 + 0.45)), 4)

            strategy = "POLY_ALPHA"
            src_tag = "POLY_ALPHA:internal"
            q = question.lower()
            rationale = f"alpha model vs implied; liquidity={liquidity}; vol24h={volume_24h}"

            # Strong arb cue on binary complement dislocation.
            dislocation = 0.0
            if len(prices) >= 2:
                dislocation = abs((prices[0] + prices[1]) - 1.0)
            if dislocation >= 0.04 and float(liquidity or 0.0) >= 5000:
                strategy = "POLY_ARB"
                src_tag = "POLY_ARB:book"
                rationale = f"arb dislocation={round(dislocation,4)}; liq={round(float(liquidity or 0.0),2)}"
            else:
                copy_hit = any(h and h in q for h in copy_handles)
                person_topic = any(tok in q for tok in people_markets)
                macro_topic = any(tok in q for tok in macro_markets)
                if copy_hit or person_topic:
                    strategy = "POLY_COPY"
                    src_tag = "POLY_COPY:watchlist"
                    why = "handle-match" if copy_hit else "people-market"
                    rationale = f"copy prior market signal ({why}); liq={round(float(liquidity or 0.0),2)}"
                elif macro_topic:
                    strategy = "POLY_ALPHA"
                    src_tag = "POLY_ALPHA:macro"
                    rationale = f"macro-event alpha cue; liq={round(float(liquidity or 0.0),2)}"

            if abs(edge) < 1.0:
                continue
            cur.execute(
                """
                INSERT INTO polymarket_candidates
                (created_at, strategy_id, market_id, slug, question, outcome, implied_prob, model_prob, edge, confidence, source_tag, rationale, market_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    now_iso(),
                    strategy,
                    market_id,
                    slug,
                    question,
                    str(outcome),
                    implied,
                    model,
                    edge,
                    conf,
                    src_tag,
                    rationale,
                    market_url,
                ),
            )
            created += 1
    conn.commit()
    return created


def main() -> int:
    conn = _connect()
    try:
        ensure_tables(conn)
        raw = fetch_markets(limit=180)
        normalized = [normalize_market(x) for x in raw]
        markets_written = store_markets(conn, normalized)
        candidates_written = build_candidates(conn, limit=140)
        print(f"POLYMARKET: fetched={len(raw)} stored={markets_written} candidates={candidates_written}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
