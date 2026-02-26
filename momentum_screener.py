#!/usr/bin/env python3
"""
Momentum Screener — Qullamaggie-style top 100 momentum stocks + top 10 crypto.

Sources (all free, no API key required):
  Stocks : Finviz public screener
             Filters: small-cap+, above 50-day SMA, up 10%+ in last quarter
             Sort   : 52-week performance descending
  Crypto : CoinGecko /coins/markets  (30-day price change)

Stores results to momentum_signals table.  Run daily.
"""

import json
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "data" / "trades.db"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Finviz screener: small-cap+, above 50-day SMA, up 10%+ in last quarter
# Sorted by 52-week performance descending (strongest momentum leaders first)
_FINVIZ_BASE = (
    "https://finviz.com/screener.ashx"
    "?v=111"
    "&f=cap_smallover,ta_sma50_price50a,ta_perf_q_o10"
    "&o=-perf52w"
)

# CoinGecko free API — top 100 coins by market cap + 30d price change
_COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=market_cap_desc&per_page=100"
    "&price_change_percentage=30d"
)

# Stablecoins to exclude from crypto momentum
_STABLES = {
    "usdt", "usdc", "usds", "usde", "dai", "busd", "tusd",
    "usdp", "frax", "lusd", "fdusd", "pyusd", "gusd",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch(url: str, headers: Dict[str, str], timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_stocks(target: int = 100) -> List[Dict]:
    """Return top momentum stocks ranked 1..target from Finviz screener."""
    tickers: List[str] = []
    page_size = 20

    for page in range((target // page_size) + 2):
        row_start = page * page_size + 1
        url = f"{_FINVIZ_BASE}&r={row_start}"
        try:
            body = _fetch(url, _HEADERS).decode("utf-8", errors="replace")
            page_tickers = list(dict.fromkeys(
                re.findall(r"quote\.ashx\?t=([A-Z]+)", body)
            ))
            if not page_tickers:
                break
            for t in page_tickers:
                if t not in tickers:
                    tickers.append(t)
            if len(page_tickers) < page_size or len(tickers) >= target:
                break
            time.sleep(0.6)
        except Exception as exc:
            print(f"  finviz page {page + 1} error: {exc}")
            break

    tickers = tickers[:target]
    total = len(tickers)
    out = []
    for rank, ticker in enumerate(tickers, start=1):
        # Rank 1 = best momentum; score normalised to [0, 1]
        score = round(1.0 - (rank - 1) / max(total, 1), 4)
        out.append({
            "ticker": ticker,
            "asset_class": "stock",
            "rank": rank,
            "rank_of": total,
            "momentum_score": score,
            "pct_30d": None,
        })
    return out


def fetch_crypto(target: int = 10) -> List[Dict]:
    """Return top momentum crypto by 30-day price change from CoinGecko."""
    try:
        body = _fetch(_COINGECKO_URL, {"User-Agent": "trader-curtis/1.0"})
        coins = json.loads(body)
        tradeable = [
            c for c in coins
            if c.get("symbol", "").lower() not in _STABLES
            and (c.get("price_change_percentage_30d_in_currency") or 0) > 0
        ]
        tradeable.sort(
            key=lambda c: c.get("price_change_percentage_30d_in_currency") or 0,
            reverse=True,
        )
        tradeable = tradeable[:target]
        out = []
        for rank, coin in enumerate(tradeable, start=1):
            pct = float(coin.get("price_change_percentage_30d_in_currency") or 0)
            # Normalise: 200 % gain → score 1.0
            score = round(min(1.0, max(0.0, pct / 200.0)), 4)
            out.append({
                "ticker": coin["symbol"].upper(),
                "asset_class": "crypto",
                "rank": rank,
                "rank_of": len(tradeable),
                "momentum_score": score,
                "pct_30d": round(pct, 2),
            })
        return out
    except Exception as exc:
        print(f"  coingecko error: {exc}")
        return []


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS momentum_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            asset_class TEXT NOT NULL DEFAULT 'stock',
            rank        INTEGER NOT NULL,
            rank_of     INTEGER NOT NULL DEFAULT 100,
            momentum_score REAL NOT NULL DEFAULT 0.0,
            pct_30d     REAL,
            batch_ts    TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_momentum_ticker "
        "ON momentum_signals(ticker, created_at)"
    )
    conn.commit()


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=20000")
    try:
        ensure_table(conn)
        batch_ts = _now()

        print("Fetching momentum stocks from Finviz …")
        stocks = fetch_stocks(100)
        print(f"  {len(stocks)} stocks.  Top 10: {[s['ticker'] for s in stocks[:10]]}")

        print("Fetching momentum crypto from CoinGecko …")
        cryptos = fetch_crypto(10)
        print(f"  {len(cryptos)} crypto.  Top 5: {[c['ticker'] for c in cryptos[:5]]}")

        all_signals = stocks + cryptos
        if not all_signals:
            print("No signals — skipping DB write")
            return 1

        # Keep only the latest batch in the table (rolling replace)
        conn.execute(
            "DELETE FROM momentum_signals "
            "WHERE batch_ts = (SELECT MAX(batch_ts) FROM momentum_signals)"
        )
        conn.executemany(
            """
            INSERT INTO momentum_signals
              (created_at, ticker, asset_class, rank, rank_of, momentum_score, pct_30d, batch_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    _now(), s["ticker"], s["asset_class"],
                    s["rank"], s["rank_of"], s["momentum_score"],
                    s.get("pct_30d"), batch_ts,
                )
                for s in all_signals
            ],
        )
        conn.commit()
        print(f"Stored {len(all_signals)} momentum signals (batch_ts={batch_ts})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
