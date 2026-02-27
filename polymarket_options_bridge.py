#!/usr/bin/env python3
"""
Options-implied probability arbitrage: Options chain → Polymarket.

Uses the Moontower Meta approach:
  z = ln(Strike/Spot) / (IV * sqrt(T))
  probability = norm_cdf(z)

When options-implied probability diverges from Polymarket pricing by > threshold,
generates POLY_OPTIONS_ARB candidates.

Also writes options_implied_signals table for crossover with equity pipeline.
"""

import json
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"

DERIBIT_BASE = "https://www.deribit.com/api/v2/public"

CRYPTO_TICKERS = {"BTC", "ETH", "SOL"}
DERIBIT_CURRENCIES = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL"}

STRIKE_PATTERN = re.compile(
    r"\b(?:above|below|hit|reach|exceed)\s+\$?([\d,]+(?:\.\d+)?)\b",
    re.IGNORECASE,
)

TICKER_PATTERN = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|solana|sol)\b",
    re.IGNORECASE,
)

NAME_TO_TICKER = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row else default


def _norm_cdf(z: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    if z > 6:
        return 1.0
    if z < -6:
        return 0.0
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911
    sign = 1.0 if z >= 0 else -1.0
    x = abs(z) / math.sqrt(2.0)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)


def _options_implied_probability(
    spot: float,
    strike: float,
    iv: float,
    time_to_expiry_years: float,
    direction: str = "above",
) -> float:
    """
    Calculate probability of price being above/below strike using lognormal framework.
    z = ln(Strike/Spot) / (IV * sqrt(T))
    P(above) = 1 - norm_cdf(z)
    """
    if spot <= 0 or strike <= 0 or iv <= 0 or time_to_expiry_years <= 0:
        return 0.5
    z = math.log(strike / spot) / (iv * math.sqrt(time_to_expiry_years))
    prob_below = _norm_cdf(z)
    if direction == "above":
        return 1.0 - prob_below
    return prob_below


def _deribit_spot_and_iv(currency: str) -> Tuple[Optional[float], Optional[float], Optional[Dict]]:
    """Fetch spot price and nearest-expiry ATM implied vol from Deribit."""
    try:
        # Get spot/index price
        resp = requests.get(
            f"{DERIBIT_BASE}/get_index_price",
            params={"index_name": f"{currency.lower()}_usd"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None, None, None
        spot = float(resp.json().get("result", {}).get("index_price", 0))
        if spot <= 0:
            return None, None, None

        # Get nearest options instruments
        resp2 = requests.get(
            f"{DERIBIT_BASE}/get_book_summary_by_currency",
            params={"currency": currency, "kind": "option"},
            timeout=12,
        )
        if resp2.status_code != 200:
            return spot, None, None

        options = resp2.json().get("result", [])
        if not options:
            return spot, None, None

        # Find nearest ATM call with reasonable volume
        now_ms = int(time.time() * 1000)
        best = None
        best_dist = float("inf")

        for opt in options:
            name = str(opt.get("instrument_name", ""))
            if not name.endswith("-C"):
                continue
            parts = name.split("-")
            if len(parts) < 3:
                continue
            try:
                strike = float(parts[2])
            except ValueError:
                continue
            dist = abs(strike - spot)
            mark_iv = float(opt.get("mark_iv", 0) or 0)
            if mark_iv <= 0:
                continue
            if dist < best_dist:
                best_dist = dist
                best = {
                    "strike": strike,
                    "iv": mark_iv / 100.0,
                    "instrument": name,
                    "volume": float(opt.get("volume", 0) or 0),
                }

        if best:
            return spot, best["iv"], best
        return spot, None, None
    except Exception:
        return None, None, None


def _extract_strike_from_question(question: str) -> Optional[float]:
    m = STRIKE_PATTERN.search(question)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def _extract_ticker_from_question(question: str, slug: str) -> Optional[str]:
    text = f"{question} {slug}".lower()
    m = TICKER_PATTERN.search(text)
    if m:
        return NAME_TO_TICKER.get(m.group(1).lower())
    return None


def _detect_direction(question: str, outcome: str) -> str:
    q = question.lower()
    o = outcome.lower()
    if "above" in q or "hit" in q or "reach" in q or "exceed" in q:
        if o in ("yes", "y", "true", "1"):
            return "above"
        return "below"
    if "below" in q or "under" in q:
        if o in ("yes", "y", "true", "1"):
            return "below"
        return "above"
    return "above"


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create options_implied_signals table for cross-pipeline use."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS options_implied_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          spot_price REAL NOT NULL DEFAULT 0,
          strike REAL NOT NULL DEFAULT 0,
          implied_vol REAL NOT NULL DEFAULT 0,
          time_to_expiry_years REAL NOT NULL DEFAULT 0,
          options_prob REAL NOT NULL DEFAULT 0,
          market_prob REAL NOT NULL DEFAULT 0,
          divergence_pct REAL NOT NULL DEFAULT 0,
          direction TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT 'deribit',
          market_id TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_options_signals_ticker ON options_implied_signals(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_options_signals_created ON options_implied_signals(created_at)")
    conn.commit()


def scan(conn: Optional[sqlite3.Connection] = None) -> int:
    """Scan for options-implied probability arbitrage opportunities."""
    own_conn = conn is None
    if own_conn:
        conn = _connect()

    try:
        ensure_tables(conn)

        if not _table_exists(conn, "polymarket_markets"):
            return 0
        if not _table_exists(conn, "polymarket_candidates"):
            return 0

        enabled = _get_control(conn, "polymarket_options_arb_enabled", "1")
        if enabled != "1":
            return 0

        min_divergence_pct = float(_get_control(conn, "polymarket_options_min_divergence_pct", "8.0"))

        # Fetch IV data for supported crypto currencies
        iv_cache: Dict[str, Tuple[float, float]] = {}
        for ticker, currency in DERIBIT_CURRENCIES.items():
            spot, iv, _meta = _deribit_spot_and_iv(currency)
            if spot and iv:
                iv_cache[ticker] = (spot, iv)

        if not iv_cache:
            return 0

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

        # Clear old signals (keep last 24h)
        conn.execute(
            "DELETE FROM options_implied_signals WHERE datetime(created_at) < datetime('now', '-24 hours')"
        )

        created = 0
        for market_id, slug, question, outcomes_json, prices_json, liquidity, volume_24h, market_url in rows:
            ticker = _extract_ticker_from_question(question, slug)
            if not ticker or ticker not in iv_cache:
                continue

            strike = _extract_strike_from_question(question)
            if not strike:
                continue

            spot, iv = iv_cache[ticker]

            # Estimate time to expiry from market context
            # Default to 7 days if we can't determine
            time_to_expiry_years = 7.0 / 365.0
            q = question.lower()
            if "tomorrow" in q or "24h" in q or "24 hour" in q:
                time_to_expiry_years = 1.0 / 365.0
            elif "this week" in q or "friday" in q:
                time_to_expiry_years = 5.0 / 365.0
            elif "this month" in q or "end of month" in q:
                time_to_expiry_years = 30.0 / 365.0
            elif "march" in q or "april" in q or "may" in q:
                time_to_expiry_years = 45.0 / 365.0

            try:
                outcomes = json.loads(outcomes_json or "[]")
                prices = [float(x) for x in json.loads(prices_json or "[]")]
            except Exception:
                continue
            if not outcomes or not prices or len(outcomes) != len(prices):
                continue

            for i, outcome in enumerate(outcomes[:2]):
                implied_market = max(0.01, min(0.99, float(prices[i] if i < len(prices) else 0)))
                direction = _detect_direction(question, str(outcome))

                options_prob = _options_implied_probability(
                    spot=spot,
                    strike=strike,
                    iv=iv,
                    time_to_expiry_years=time_to_expiry_years,
                    direction=direction,
                )
                options_prob = max(0.01, min(0.99, options_prob))

                divergence_pct = abs(options_prob - implied_market) * 100.0

                # Write signal for cross-pipeline use
                conn.execute(
                    """
                    INSERT INTO options_implied_signals
                    (created_at, ticker, spot_price, strike, implied_vol, time_to_expiry_years,
                     options_prob, market_prob, divergence_pct, direction, source, market_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'deribit', ?, ?)
                    """,
                    (
                        now_iso(), ticker, spot, strike, iv, time_to_expiry_years,
                        round(options_prob, 6), round(implied_market, 6),
                        round(divergence_pct, 4), direction, market_id,
                        f"spot={spot:.2f} strike={strike:.0f} iv={iv:.4f} T={time_to_expiry_years:.4f}",
                    ),
                )

                if divergence_pct < min_divergence_pct:
                    continue

                # Options-implied probability suggests market is mispriced
                edge = round((options_prob - implied_market) * 100.0, 4)
                conf = round(min(0.88, 0.50 + divergence_pct / 40.0), 4)

                if abs(edge) < 2.0:
                    continue

                # Add arb_pair_id column if missing
                if not _column_exists(conn, "polymarket_candidates", "arb_pair_id"):
                    conn.execute(
                        "ALTER TABLE polymarket_candidates ADD COLUMN arb_pair_id TEXT NOT NULL DEFAULT ''"
                    )

                cur.execute(
                    """
                    INSERT INTO polymarket_candidates
                    (created_at, strategy_id, market_id, slug, question, outcome,
                     implied_prob, model_prob, edge, confidence, source_tag,
                     rationale, market_url, status, arb_pair_id)
                    VALUES (?, 'POLY_OPTIONS_ARB', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '')
                    """,
                    (
                        now_iso(), market_id, slug, question, str(outcome),
                        implied_market, round(options_prob, 6), edge, conf,
                        f"POLY_OPTIONS_ARB:{ticker}:deribit",
                        f"options_arb ticker={ticker} spot={spot:.2f} strike={strike:.0f} "
                        f"iv={iv:.4f} options_prob={options_prob:.4f} "
                        f"market_prob={implied_market:.4f} divergence={divergence_pct:.2f}% "
                        f"dir={direction} liq={liquidity:.0f}",
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
        print(f"POLY_OPTIONS_BRIDGE: candidates={created}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
