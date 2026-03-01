#!/usr/bin/env python3
"""
Polymarket crypto momentum lag scanner.

Exploits the proven momentum lag on ultra-short crypto prediction markets:
spot price moves first, market pricing lags by 30-90 seconds.

Primary data source: Predexon API (get_crypto_updown endpoint).
Fallback: local polymarket_markets table + regex matching.

Generates POLY_MOMENTUM candidates when spot momentum diverges from market pricing,
and POLY_ARB_MICRO candidates for risk-free dual-directional pair trades.
"""

import json
import re
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from binance_ws_feed import (
        get_price_change_pct as _ws_price_change_pct,
        get_spot_price as _ws_spot_price,
        is_feed_running as _ws_is_running,
    )
    _HAS_WS_FEED = True
except ImportError:
    _HAS_WS_FEED = False

try:
    import predexon_client
    _HAS_PREDEXON = True
except ImportError:
    _HAS_PREDEXON = False

DB_PATH = Path(__file__).parent / "data" / "trades.db"

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

# Fallback regex patterns for local DB scan (when Predexon unavailable)
_FALLBACK_PATTERNS = [
    re.compile(
        r"(5-?min|5\s*minute|15-?min|15\s*minute|"
        r"up\s*or\s*down|updown|"
        r"price.?above|price.?below|"
        r"will.*price.*be\s+(above|below))",
        re.IGNORECASE,
    ),
]

_TICKER_EXTRACT = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|solana|sol|dogecoin|doge|xrp|ripple|"
    r"cardano|ada|avalanche|avax|polkadot|dot|chainlink|link|bnb|litecoin|ltc)\b",
    re.IGNORECASE,
)

_NAME_TO_TICKER = {
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

# Predexon asset codes → tickers
_ASSET_TO_TICKER = {"btc": "BTC", "eth": "ETH", "sol": "SOL", "xrp": "XRP"}

# Predexon timeframe → minutes
_TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "daily": 1440}


def _now_iso() -> str:
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


# ---------------------------------------------------------------------------
# Price feeds (Binance WS → CoinGecko fallback)
# ---------------------------------------------------------------------------

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


def _spot_price(ticker: str) -> Optional[float]:
    if _HAS_WS_FEED and _ws_is_running():
        price = _ws_spot_price(ticker)
        if price is not None:
            return price
    return _coingecko_spot_price(ticker)


def _price_change_pct(ticker: str, minutes: int = 15) -> Optional[float]:
    if _HAS_WS_FEED and _ws_is_running():
        change = _ws_price_change_pct(ticker, minutes)
        if change is not None:
            return change
    return _coingecko_price_change_pct(ticker, minutes)


# ---------------------------------------------------------------------------
# Direction detection
# ---------------------------------------------------------------------------

def _detect_market_direction(question: str, outcome: str) -> str:
    o = outcome.lower()
    q = question.lower()
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


# ---------------------------------------------------------------------------
# Predexon-powered market discovery (primary path)
# ---------------------------------------------------------------------------

def _fetch_predexon_markets() -> List[Dict[str, Any]]:
    """
    Fetch crypto up/down markets from Predexon API.

    Each market already has up_price, down_price, up_token_id, down_token_id.
    Returns normalized list for the scanner.
    """
    if not _HAS_PREDEXON:
        return []
    try:
        raw = predexon_client.get_open_crypto_markets(
            assets=["btc", "eth", "sol", "xrp"],
            timeframes=["5m", "15m", "1h", "4h"],
        )
    except Exception as e:
        print(f"  Predexon API error: {e}")
        return []

    results = []
    for m in raw:
        cid = m.get("condition_id", "")
        if not cid:
            continue
        asset = m.get("asset", "").lower()
        tf = m.get("timeframe", "1h")
        up_price = float(m.get("up_price", 0))
        down_price = float(m.get("down_price", 0))
        if up_price <= 0 and down_price <= 0:
            continue
        results.append({
            "condition_id": cid,
            "title": m.get("title", ""),
            "asset": asset,
            "ticker": _ASSET_TO_TICKER.get(asset, asset.upper()),
            "timeframe": tf,
            "minutes": _TF_MINUTES.get(tf, 60),
            "tokens": [
                {"token_id": m.get("up_token_id", ""), "price": up_price},
                {"token_id": m.get("down_token_id", ""), "price": down_price},
            ],
            "volume": float(m.get("total_volume_usd", 0)),
            "liquidity": float(m.get("liquidity_usd", 0)),
            "slug": m.get("market_slug", cid),
            "question": m.get("title", ""),
            "market_url": f"https://polymarket.com/event/{m.get('event_slug', m.get('market_slug', ''))}",
            "outcomes": ["Up", "Down"],
        })
    return results


def _fetch_smart_money_signal(condition_id: str) -> Optional[Dict[str, Any]]:
    """Fetch smart money positioning for a market (Dev tier)."""
    if not _HAS_PREDEXON:
        return None
    return predexon_client.enrich_with_smart_money(condition_id)


# ---------------------------------------------------------------------------
# Fallback: local DB regex scan (when Predexon unavailable)
# ---------------------------------------------------------------------------

def _fetch_local_markets(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Fallback: scan local polymarket_markets table with regex matching."""
    if not _table_exists(conn, "polymarket_markets"):
        return []

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

    results = []
    for market_id, slug, question, outcomes_json, prices_json, liq, vol, url in cur.fetchall():
        text = f"{slug} {question}"
        if not any(p.search(text) for p in _FALLBACK_PATTERNS):
            continue
        m = _TICKER_EXTRACT.search(f"{question} {slug}".lower())
        if not m:
            continue
        ticker = _NAME_TO_TICKER.get(m.group(1).lower())
        if not ticker:
            continue

        try:
            outcomes = json.loads(outcomes_json or "[]")
            prices = [float(x) for x in json.loads(prices_json or "[]")]
        except Exception:
            continue
        if not outcomes or not prices or len(outcomes) != len(prices):
            continue

        # Determine timeframe from text
        minutes = 60
        tl = text.lower()
        if "5-min" in tl or "5 min" in tl or "5min" in tl:
            minutes = 5
        elif "15-min" in tl or "15 min" in tl or "15min" in tl:
            minutes = 15

        tokens = [{"token_id": "", "price": p} for p in prices]
        results.append({
            "condition_id": market_id,
            "title": question,
            "asset": ticker.lower(),
            "ticker": ticker,
            "timeframe": f"{minutes}m",
            "minutes": minutes,
            "tokens": tokens,
            "volume": float(vol or 0),
            "slug": slug,
            "question": question,
            "market_url": url,
            "liquidity": float(liq or 0),
            "outcomes": outcomes,
        })
    return results


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------

def scan(conn: Optional[sqlite3.Connection] = None) -> int:
    """Scan for momentum lag opportunities on crypto up/down markets."""
    own_conn = conn is None
    if own_conn:
        conn = _connect()

    try:
        if not _table_exists(conn, "polymarket_candidates"):
            return 0

        enabled = _get_control(conn, "polymarket_momentum_enabled", "1")
        if enabled != "1":
            return 0

        min_gap_pct = float(_get_control(conn, "polymarket_momentum_min_gap_pct", "3.0"))
        min_liquidity = float(_get_control(conn, "polymarket_momentum_min_liquidity", "3000"))

        # Add arb_pair_id column if missing
        if not _column_exists(conn, "polymarket_candidates", "arb_pair_id"):
            conn.execute(
                "ALTER TABLE polymarket_candidates ADD COLUMN arb_pair_id TEXT NOT NULL DEFAULT ''"
            )

        # Primary: Predexon API. Fallback: local DB regex scan.
        markets = _fetch_predexon_markets()
        source = "predexon"
        if not markets:
            markets = _fetch_local_markets(conn)
            source = "local_db"
            if not markets:
                return 0

        print(f"  source={source} markets_found={len(markets)}")

        cur = conn.cursor()
        created = 0

        for mkt in markets:
            condition_id = mkt["condition_id"]
            ticker = mkt["ticker"]
            minutes = mkt["minutes"]
            title = mkt.get("title", "")
            tokens = mkt.get("tokens", [])

            # Need exactly 2 tokens for binary market
            if len(tokens) != 2:
                continue

            prices = [t["price"] for t in tokens]

            # Volume / liquidity filter
            vol = mkt.get("volume", 0)
            liq = mkt.get("liquidity", vol)
            if liq < min_liquidity and vol < min_liquidity:
                continue

            # Get spot momentum
            momentum_pct = _price_change_pct(ticker, minutes=minutes)
            if momentum_pct is None:
                continue

            # Build common fields
            slug = mkt.get("slug", condition_id)
            question = mkt.get("question", title)
            market_url = mkt.get("market_url", f"https://polymarket.com/event/{slug}")

            # For Predexon markets, derive outcomes from title
            outcomes = mkt.get("outcomes", ["Up", "Down"])
            if len(outcomes) < 2:
                outcomes = ["Up", "Down"]

            # --- Dual-directional arb (binary markets only) ---
            cost_per_pair = prices[0] + prices[1]
            if 0.01 < cost_per_pair < 0.96:
                arb_profit_pct = ((1.0 - cost_per_pair) / cost_per_pair) * 100.0
                taker_fee_pct = float(_get_control(conn, "polymarket_taker_fee_pct", "3.15"))
                net_profit_pct = arb_profit_pct - (taker_fee_pct * 2)
                if net_profit_pct > 0.5:
                    pair_id = f"micro-arb-{condition_id[:16]}-{int(time.time())}"
                    for i, outcome in enumerate(outcomes[:2]):
                        implied = max(0.01, min(0.99, prices[i]))
                        cur.execute(
                            """
                            INSERT INTO polymarket_candidates
                            (created_at, strategy_id, market_id, slug, question, outcome,
                             implied_prob, model_prob, edge, confidence, source_tag,
                             rationale, market_url, status, arb_pair_id)
                            VALUES (?, 'POLY_ARB_MICRO', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                            """,
                            (
                                _now_iso(), condition_id, slug, question, str(outcome),
                                implied, implied, round(net_profit_pct, 4), 0.85,
                                f"POLY_ARB_MICRO:{source}",
                                f"micro-arb net_profit={net_profit_pct:.2f}% cost={cost_per_pair:.4f} "
                                f"ticker={ticker} window={minutes}m vol={vol:.0f}",
                                market_url, pair_id,
                            ),
                        )
                        created += 1

            # --- Momentum lag for each outcome ---
            # Try smart money enrichment (Dev tier)
            smart_money = _fetch_smart_money_signal(condition_id) if source == "predexon" else None
            smart_bias = 0.0
            if smart_money and smart_money.get("smart_wallet_count", 0) >= 3:
                net_buy = smart_money.get("net_buyers", 0)
                net_sell = smart_money.get("net_sellers", 0)
                total = net_buy + net_sell
                if total > 0:
                    smart_bias = ((net_buy - net_sell) / total) * 5.0  # up to +/-5% edge boost

            for i, outcome in enumerate(outcomes[:2]):
                implied = max(0.01, min(0.99, prices[i] if i < len(prices) else 0))
                direction = _detect_market_direction(question, str(outcome))

                if direction == "unknown":
                    continue

                if direction == "up":
                    momentum_signal = momentum_pct + smart_bias
                else:
                    momentum_signal = -momentum_pct - smart_bias

                gap = momentum_signal - ((implied - 0.5) * 100.0)

                if abs(gap) < min_gap_pct:
                    continue

                if momentum_signal > 0:
                    model_prob = min(0.95, implied + (abs(gap) / 200.0))
                else:
                    model_prob = max(0.05, implied - (abs(gap) / 200.0))

                edge = round((model_prob - implied) * 100.0, 4)
                conf = round(min(0.90, 0.55 + abs(gap) / 40.0), 4)

                if abs(edge) < 1.5:
                    continue

                smart_note = ""
                if smart_money and smart_money.get("smart_wallet_count", 0) >= 3:
                    smart_note = (
                        f" smart_wallets={smart_money['smart_wallet_count']}"
                        f" net_buy={smart_money.get('net_buyers', 0)}"
                        f" bias={smart_bias:+.1f}%"
                    )

                cur.execute(
                    """
                    INSERT INTO polymarket_candidates
                    (created_at, strategy_id, market_id, slug, question, outcome,
                     implied_prob, model_prob, edge, confidence, source_tag,
                     rationale, market_url, status, arb_pair_id)
                    VALUES (?, 'POLY_MOMENTUM', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '')
                    """,
                    (
                        _now_iso(), condition_id, slug, question, str(outcome),
                        implied, model_prob, edge, conf,
                        f"POLY_MOMENTUM:{ticker}:{minutes}m:{source}",
                        f"momentum_lag ticker={ticker} spot_change={momentum_pct:+.2f}% "
                        f"gap={gap:+.2f}% dir={direction} window={minutes}m "
                        f"vol={vol:.0f}{smart_note}",
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
