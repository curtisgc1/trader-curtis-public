#!/usr/bin/env python3
"""
Predexon API client — prediction market data (Dev plan).

Base URL: https://api.predexon.com
Auth: x-api-key header
Plan: Dev (20 req/sec, 1M req/month)
Docs: https://docs.predexon.com

Endpoints covered:
  FREE: crypto-updown, markets, candlesticks, orderbooks
  DEV:  smart-activity, smart-money, binance candles/ticks, matched-pairs
"""

import os
import time
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.predexon.com"
_API_KEY = os.environ.get("PREDEXON_API_KEY", "")

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "x-api-key": _API_KEY,
            "Accept": "application/json",
        })
    return _session


def _get(path: str, params: Optional[Dict[str, Any]] = None,
         timeout: float = 15.0) -> Dict[str, Any]:
    """Make authenticated GET request with retry on 429."""
    s = _get_session()
    url = f"{BASE_URL}{path}"
    for attempt in range(3):
        resp = s.get(url, params=params, timeout=timeout)
        if resp.status_code == 429:
            wait = min(2 ** attempt, 8)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


# ---------------------------------------------------------------------------
# FREE endpoints
# ---------------------------------------------------------------------------

def get_crypto_updown(
    asset: Optional[str] = None,
    timeframe: Optional[str] = None,
    status: str = "open",
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    GET /v2/polymarket/crypto-updown

    List crypto prediction markets (BTC, ETH, SOL, XRP) across timeframes.

    Args:
        asset: btc, eth, sol, xrp (None = all)
        timeframe: 5m, 15m, 1h, 4h, daily (None = all)
        status: open or closed
        limit: 1-200
        offset: pagination offset
    """
    params: Dict[str, Any] = {"status": status, "limit": limit, "offset": offset}
    if asset:
        params["asset"] = asset.lower()
    if timeframe:
        params["timeframe"] = timeframe
    return _get("/v2/polymarket/crypto-updown", params)


def get_markets(
    status: str = "open",
    sort: str = "volume",
    order: str = "desc",
    condition_id: Optional[str] = None,
    token_ids: Optional[List[str]] = None,
    min_volume_1d: Optional[float] = None,
    min_volume_7d: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    GET /v2/polymarket/markets

    Query markets with filtering and sorting.
    """
    params: Dict[str, Any] = {
        "status": status, "sort": sort, "order": order,
        "limit": limit, "offset": offset,
    }
    if condition_id:
        params["condition_id"] = condition_id
    if token_ids:
        params["token_id"] = ",".join(token_ids)
    if min_volume_1d is not None:
        params["min_volume_1d"] = min_volume_1d
    if min_volume_7d is not None:
        params["min_volume_7d"] = min_volume_7d
    return _get("/v2/polymarket/markets", params)


def get_candlesticks(
    condition_id: str,
    interval: str = "1h",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    GET /v2/polymarket/candlesticks/{condition_id}

    Fetch OHLCV candlestick data.
    Intervals: 1m (7d max), 1h (30d max), 1d (365d max).
    """
    params: Dict[str, Any] = {"interval": interval}
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    if limit is not None:
        params["limit"] = limit
    return _get(f"/v2/polymarket/candlesticks/{condition_id}", params)


def get_orderbooks(
    condition_id: Optional[str] = None,
    token_id: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    GET /v2/polymarket/orderbooks

    Fetch historical orderbook snapshots.
    Timestamps in milliseconds.
    """
    params: Dict[str, Any] = {"limit": limit}
    if condition_id:
        params["condition_id"] = condition_id
    if token_id:
        params["token_id"] = token_id
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return _get("/v2/polymarket/orderbooks", params)


# ---------------------------------------------------------------------------
# DEV endpoints (smart money, binance, matching)
# ---------------------------------------------------------------------------

def get_smart_activity(
    min_realized_pnl: float = 5000,
    min_roi: float = 0.15,
    min_trades: int = 100,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    GET /v2/polymarket/markets/smart-activity

    Markets where profitable traders concentrate activity.
    """
    params: Dict[str, Any] = {
        "min_realized_pnl": min_realized_pnl,
        "min_roi": min_roi,
        "min_trades": min_trades,
        "limit": limit,
    }
    return _get("/v2/polymarket/markets/smart-activity", params)


def get_smart_money(
    condition_id: str,
    min_realized_pnl: float = 1000,
    min_roi: float = 0.15,
    min_trades: int = 100,
) -> Dict[str, Any]:
    """
    GET /v2/polymarket/market/{condition_id}/smart-money

    Profitable trader positioning on a specific market.
    Returns net_buyers, net_sellers, avg_entry prices, total volume.
    """
    params: Dict[str, Any] = {
        "min_realized_pnl": min_realized_pnl,
        "min_roi": min_roi,
        "min_trades": min_trades,
    }
    return _get(f"/v2/polymarket/market/{condition_id}/smart-money", params)


def get_binance_candles(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    GET /v2/binance/candles/{symbol}

    Binance OHLCV candlestick data.
    Symbols: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
    Intervals: 1s, 1m, 5m, 15m, 1h, 4h, 1d.
    """
    params: Dict[str, Any] = {"interval": interval, "limit": limit}
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return _get(f"/v2/binance/candles/{symbol}", params)


def get_binance_ticks(
    symbol: str = "BTCUSDT",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 10000,
) -> Dict[str, Any]:
    """
    GET /v2/binance/ticks/{symbol}

    Raw book ticker data at microsecond granularity.
    Symbols: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
    """
    params: Dict[str, Any] = {"limit": limit}
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    return _get(f"/v2/binance/ticks/{symbol}", params)


def find_matching_markets(
    polymarket_condition_id: Optional[str] = None,
    polymarket_market_slug: Optional[str] = None,
    kalshi_ticker: Optional[str] = None,
) -> Dict[str, Any]:
    """
    GET /v2/matching-markets

    Find equivalent markets across Polymarket and Kalshi.
    Provide exactly one identifier.
    """
    params: Dict[str, Any] = {}
    if polymarket_condition_id:
        params["polymarket_condition_id"] = polymarket_condition_id
    elif polymarket_market_slug:
        params["polymarket_market_slug"] = polymarket_market_slug
    elif kalshi_ticker:
        params["kalshi_ticker"] = kalshi_ticker
    return _get("/v2/matching-markets", params)


def get_matched_pairs(
    min_similarity: int = 95,
    sort_by: str = "similarity",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    GET /v2/matching-markets/pairs

    All active exact-matched market pairs across platforms.
    """
    params: Dict[str, Any] = {
        "min_similarity": min_similarity,
        "sort_by": sort_by,
        "limit": limit,
    }
    return _get("/v2/matching-markets/pairs", params)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

TICKER_TO_ASSET = {
    "BTC": "btc", "ETH": "eth", "SOL": "sol", "XRP": "xrp",
}

TIMEFRAME_MINUTES = {
    "5m": 5, "15m": 15, "1h": 60, "4h": 240, "daily": 1440,
}


def get_open_crypto_markets(
    assets: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all open crypto up/down markets, optionally filtered.
    Paginates automatically.
    """
    results: List[Dict[str, Any]] = []
    asset_list = assets or [None]
    tf_list = timeframes or [None]

    for asset in asset_list:
        for tf in tf_list:
            offset = 0
            while True:
                data = get_crypto_updown(
                    asset=asset, timeframe=tf, status="open",
                    limit=200, offset=offset,
                )
                markets = data.get("markets", [])
                results.extend(markets)
                pagination = data.get("pagination", {})
                if not pagination.get("has_more", False):
                    break
                offset += len(markets)
    return results


def enrich_with_smart_money(condition_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch smart money positioning for a market.
    Returns None on error (e.g. no smart wallets found).
    """
    try:
        return get_smart_money(condition_id)
    except requests.HTTPError:
        return None


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json as _json

    if not _API_KEY:
        print("ERROR: PREDEXON_API_KEY not set in environment")
        raise SystemExit(1)

    print("=" * 60)
    print("PREDEXON CLIENT — connectivity test")
    print("=" * 60)

    # 1. Crypto up/down markets
    print("\n--- Crypto Up/Down (BTC, open) ---")
    try:
        data = get_crypto_updown(asset="btc", status="open", limit=5)
        markets = data.get("markets", [])
        total = data.get("pagination", {}).get("total", "?")
        print(f"  Total BTC markets: {total}")
        for m in markets[:5]:
            print(f"  {m.get('title', '?')[:60]}  price={m.get('price', '?')}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 2. Smart activity
    print("\n--- Smart Activity (top 3) ---")
    try:
        data = get_smart_activity(limit=3)
        for m in data.get("markets", []):
            print(f"  {m.get('title', '?')[:50]}  wallets={m.get('smart_wallet_count', '?')}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 3. Binance candles
    print("\n--- Binance Candles (BTCUSDT 1h, last 3) ---")
    try:
        data = get_binance_candles("BTCUSDT", interval="1h", limit=3)
        for c in data.get("candlesticks", []):
            print(f"  ts={c.get('timestamp')} close={c.get('close')}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 4. Matched pairs
    print("\n--- Matched Pairs (top 3) ---")
    try:
        data = get_matched_pairs(limit=3)
        for p in data.get("pairs", []):
            pm = p.get("polymarket", {})
            k = p.get("kalshi", {})
            print(f"  sim={p.get('similarity')} PM={pm.get('title', '?')[:40]} <> K={k.get('title', '?')[:40]}")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\nDone.")
