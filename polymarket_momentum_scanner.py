#!/usr/bin/env python3
"""
Polymarket 5-min / 15-min crypto momentum lag scanner.

Exploits the proven momentum lag on ultra-short crypto prediction markets:
spot price moves first, market pricing lags by 30-90 seconds.

Generates POLY_MOMENTUM candidates when spot momentum diverges from market pricing,
and POLY_ARB_MICRO candidates for risk-free dual-directional pair trades.
"""

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
GAMMA_BASE = "https://gamma-api.polymarket.com"

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "BNB": "binancecoin",
    "LTC": "litecoin",
}

MICRO_SLUG_PATTERNS = [
    re.compile(r"(5-?min|5\s*minute|15-?min|15\s*minute)", re.IGNORECASE),
    re.compile(r"(price.?up|price.?down|up.?or.?down|updown)", re.IGNORECASE),
]

TICKER_EXTRACT = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|solana|sol|dogecoin|doge|xrp|ripple|"
    r"cardano|ada|avalanche|avax|polkadot|dot|chainlink|link|bnb|litecoin|ltc)\b",
    re.IGNORECASE,
)

NAME_TO_TICKER = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL",
    "dogecoin": "DOGE", "doge": "DOGE",
    "xrp": "XRP", "ripple": "XRP",
    "cardano": "ADA", "ada": "ADA",
    "avalanche": "AVAX", "avax": "AVAX",
    "polkadot": "DOT", "dot": "DOT",
    "chainlink": "LINK", "link": "LINK",
    "bnb": "BNB",
    "litecoin": "LTC", "ltc": "LTC",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row else default


def _is_micro_market(slug: str, question: str) -> bool:
    text = f"{slug} {question}"
    return any(p.search(text) for p in MICRO_SLUG_PATTERNS)


def _extract_ticker(question: str, slug: str) -> Optional[str]:
    text = f"{question} {slug}".lower()
    m = TICKER_EXTRACT.search(text)
    if m:
        return NAME_TO_TICKER.get(m.group(1).lower())
    return None


def _coingecko_spot_price(ticker: str) -> Optional[float]:
    cg_id = COINGECKO_IDS.get(ticker.upper())
    if not cg_id:
        return None
    try:
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd",
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return float(data.get(cg_id, {}).get("usd", 0)) or None
    except Exception:
        return None


def _coingecko_price_change_pct(ticker: str, minutes: int = 15) -> Optional[float]:
    """Get recent price change % using CoinGecko market chart."""
    cg_id = COINGECKO_IDS.get(ticker.upper())
    if not cg_id:
        return None
    try:
        now_ts = int(time.time())
        from_ts = now_ts - (minutes * 60) - 120
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart/range"
            f"?vs_currency=usd&from={from_ts}&to={now_ts}",
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        prices = resp.json().get("prices", [])
        if len(prices) < 2:
            return None
        old_price = float(prices[0][1])
        new_price = float(prices[-1][1])
        if old_price <= 0:
            return None
        return ((new_price - old_price) / old_price) * 100.0
    except Exception:
        return None


def _detect_market_direction(question: str, outcome: str) -> str:
    """Detect if this outcome bets on price going up or down."""
    q = question.lower()
    o = outcome.lower()
    up_signals = ("up", "above", "higher", "rise", "yes")
    down_signals = ("down", "below", "lower", "fall", "no")

    if any(s in o for s in up_signals):
        return "up"
    if any(s in o for s in down_signals):
        return "down"
    if "up or down" in q:
        if o in ("yes", "y", "true", "1"):
            return "up"
        return "down"
    return "unknown"


def scan(conn: Optional[sqlite3.Connection] = None) -> int:
    """Scan for momentum lag opportunities on micro-window crypto markets."""
    own_conn = conn is None
    if own_conn:
        conn = _connect()

    try:
        if not _table_exists(conn, "polymarket_markets"):
            return 0
        if not _table_exists(conn, "polymarket_candidates"):
            return 0

        enabled = _get_control(conn, "polymarket_momentum_enabled", "1")
        if enabled != "1":
            return 0

        min_gap_pct = float(_get_control(conn, "polymarket_momentum_min_gap_pct", "3.0"))
        min_liquidity = float(_get_control(conn, "polymarket_momentum_min_liquidity", "3000"))

        cur = conn.cursor()
        cur.execute(
            """
            SELECT market_id, slug, question, outcomes_json, outcome_prices_json,
                   liquidity, volume_24h, market_url
            FROM polymarket_markets
            WHERE active=1 AND closed=0
            ORDER BY volume_24h DESC
            LIMIT 500
            """
        )
        rows = cur.fetchall()

        # Add arb_pair_id column if missing
        if not _column_exists(conn, "polymarket_candidates", "arb_pair_id"):
            conn.execute("ALTER TABLE polymarket_candidates ADD COLUMN arb_pair_id TEXT NOT NULL DEFAULT ''")

        created = 0
        for market_id, slug, question, outcomes_json, prices_json, liquidity, volume_24h, market_url in rows:
            if not _is_micro_market(slug, question):
                continue
            if float(liquidity or 0) < min_liquidity:
                continue

            ticker = _extract_ticker(question, slug)
            if not ticker:
                continue

            try:
                outcomes = json.loads(outcomes_json or "[]")
                prices = [float(x) for x in json.loads(prices_json or "[]")]
            except Exception:
                continue
            if not outcomes or not prices or len(outcomes) != len(prices):
                continue

            # Determine time window from slug/question
            minutes = 15
            text = f"{slug} {question}".lower()
            if "5-min" in text or "5 min" in text or "5min" in text:
                minutes = 5

            # Get spot momentum
            momentum_pct = _coingecko_price_change_pct(ticker, minutes=minutes)
            if momentum_pct is None:
                continue

            # Check dual-directional arb (gabagool micro)
            if len(prices) >= 2:
                cost_per_pair = prices[0] + prices[1]
                if cost_per_pair > 0.01 and cost_per_pair < 0.96:
                    arb_profit_pct = ((1.0 - cost_per_pair) / cost_per_pair) * 100.0
                    taker_fee_pct = float(_get_control(conn, "polymarket_taker_fee_pct", "3.15"))
                    net_profit_pct = arb_profit_pct - (taker_fee_pct * 2)
                    if net_profit_pct > 0.5:
                        pair_id = f"micro-arb-{market_id}-{int(time.time())}"
                        for i, outcome in enumerate(outcomes[:2]):
                            implied = max(0.01, min(0.99, float(prices[i])))
                            cur.execute(
                                """
                                INSERT INTO polymarket_candidates
                                (created_at, strategy_id, market_id, slug, question, outcome,
                                 implied_prob, model_prob, edge, confidence, source_tag,
                                 rationale, market_url, status, arb_pair_id)
                                VALUES (?, 'POLY_ARB_MICRO', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                                """,
                                (
                                    now_iso(), market_id, slug, question, str(outcome),
                                    implied, implied, round(net_profit_pct, 4), 0.85,
                                    "POLY_ARB_MICRO:book",
                                    f"micro-arb net_profit={net_profit_pct:.2f}% cost={cost_per_pair:.4f} "
                                    f"ticker={ticker} window={minutes}m",
                                    market_url, pair_id,
                                ),
                            )
                            created += 1

            # Check momentum lag for each outcome
            for i, outcome in enumerate(outcomes[:2]):
                implied = max(0.01, min(0.99, float(prices[i] if i < len(prices) else 0)))
                direction = _detect_market_direction(question, str(outcome))

                if direction == "unknown":
                    continue

                # Calculate expected probability from momentum
                if direction == "up":
                    momentum_signal = momentum_pct
                else:
                    momentum_signal = -momentum_pct

                gap = momentum_signal - ((implied - 0.5) * 100.0)

                if abs(gap) < min_gap_pct:
                    continue

                # Momentum suggests price should be higher/lower than market implies
                if momentum_signal > 0:
                    model_prob = min(0.95, implied + (abs(gap) / 200.0))
                else:
                    model_prob = max(0.05, implied - (abs(gap) / 200.0))

                edge = round((model_prob - implied) * 100.0, 4)
                conf = round(min(0.90, 0.55 + abs(gap) / 40.0), 4)

                if abs(edge) < 1.5:
                    continue

                cur.execute(
                    """
                    INSERT INTO polymarket_candidates
                    (created_at, strategy_id, market_id, slug, question, outcome,
                     implied_prob, model_prob, edge, confidence, source_tag,
                     rationale, market_url, status, arb_pair_id)
                    VALUES (?, 'POLY_MOMENTUM', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '')
                    """,
                    (
                        now_iso(), market_id, slug, question, str(outcome),
                        implied, model_prob, edge, conf,
                        f"POLY_MOMENTUM:{ticker}:{minutes}m",
                        f"momentum_lag ticker={ticker} spot_change={momentum_pct:+.2f}% "
                        f"gap={gap:+.2f}% dir={direction} window={minutes}m "
                        f"liq={liquidity:.0f}",
                        market_url,
                    ),
                )
                created += 1

        conn.commit()
        return created
    finally:
        if own_conn:
            conn.close()


def main() -> int:
    conn = _connect()
    try:
        created = scan(conn)
        print(f"POLY_MOMENTUM: candidates={created}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
