#!/usr/bin/env python3
"""
Ripster-style 34/50 EMA cloud market regime filter.

Computes a trend regime (bullish/bearish) for SPY (stocks) and BTC-USD (crypto)
using 34/50 EMA on hl2 source (high+low)/2 — matching the Ripster47 Cloud 3
convention. The result gates the signal router: red cloud = no longs for that
asset class (and vice versa for shorts).
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    import urllib.request
    import urllib.error
    requests = None  # type: ignore[assignment]

DB_PATH = Path(__file__).parent / "data" / "trades.db"

REGIME_SYMBOLS = {
    "stocks": "SPY",
    "crypto": "BTC-USD",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_regime_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            ema_fast REAL NOT NULL,
            ema_slow REAL NOT NULL,
            hl2_current REAL NOT NULL,
            trend TEXT NOT NULL,
            cloud_width_pct REAL NOT NULL DEFAULT 0.0,
            notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def fetch_daily_bars(symbol: str, days: int = 90) -> List[Dict[str, Any]]:
    """Fetch daily OHLC bars from Yahoo Finance v8 API."""
    encoded = symbol.replace("^", "%5E")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
    params_str = f"range={days}d&interval=1d&includePrePost=false"
    full_url = f"{url}?{params_str}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        if requests is not None:
            res = requests.get(url, params={"range": f"{days}d", "interval": "1d", "includePrePost": "false"},
                               headers=headers, timeout=20)
            if res.status_code >= 400:
                print(f"  Yahoo Finance HTTP {res.status_code} for {symbol}")
                return []
            data = res.json()
        else:
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"  Yahoo Finance fetch error for {symbol}: {exc}")
        return []

    chart = (data.get("chart") or {}).get("result") or []
    if not chart:
        return []

    item = chart[0]
    ts_list = item.get("timestamp") or []
    q = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    highs = q.get("high") or []
    lows = q.get("low") or []
    closes = q.get("close") or []

    out: List[Dict[str, Any]] = []
    for i, t in enumerate(ts_list):
        try:
            h = float(highs[i]) if highs[i] is not None else None
            lo = float(lows[i]) if lows[i] is not None else None
            c = float(closes[i]) if closes[i] is not None else None
        except (IndexError, TypeError, ValueError):
            continue
        if h is None or lo is None or c is None:
            continue
        hl2 = (h + lo) / 2.0
        out.append({"ts": int(t), "high": h, "low": lo, "close": c, "hl2": hl2})

    return out


def compute_ema(values: List[float], period: int) -> List[float]:
    """Standard EMA: alpha = 2/(period+1), seed with first value."""
    if not values or period < 1:
        return []
    alpha = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1.0 - alpha) * result[-1])
    return result


def compute_regime(bars: List[Dict[str, Any]], fast: int = 34, slow: int = 50) -> Optional[Dict[str, Any]]:
    """Compute 34/50 EMA on hl2 and return regime dict."""
    if len(bars) < slow + 5:
        return None

    hl2_values = [b["hl2"] for b in bars]
    ema_fast = compute_ema(hl2_values, fast)
    ema_slow = compute_ema(hl2_values, slow)

    latest_fast = ema_fast[-1]
    latest_slow = ema_slow[-1]
    latest_hl2 = hl2_values[-1]

    trend = "bullish" if latest_fast >= latest_slow else "bearish"
    cloud_width_pct = abs(latest_fast - latest_slow) / latest_slow * 100.0 if latest_slow else 0.0

    return {
        "trend": trend,
        "ema_fast": round(latest_fast, 4),
        "ema_slow": round(latest_slow, 4),
        "hl2_current": round(latest_hl2, 4),
        "cloud_width_pct": round(cloud_width_pct, 4),
    }


def update_regime(conn: sqlite3.Connection, asset_class: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch bars, compute regime, write to DB. Returns regime dict or None."""
    bars = fetch_daily_bars(symbol, days=90)
    if not bars:
        print(f"  No bars for {symbol} — skipping regime update")
        return None

    regime = compute_regime(bars)
    if regime is None:
        print(f"  Not enough bars for {symbol} to compute 34/50 EMA")
        return None

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes = f"bars={len(bars)} fast=34 slow=50 src=hl2"

    conn.execute(
        """
        INSERT INTO market_regime_state
        (fetched_at, asset_class, symbol, ema_fast, ema_slow, hl2_current, trend, cloud_width_pct, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now_iso, asset_class, symbol, regime["ema_fast"], regime["ema_slow"],
         regime["hl2_current"], regime["trend"], regime["cloud_width_pct"], notes),
    )
    conn.commit()

    return {**regime, "asset_class": asset_class, "symbol": symbol, "fetched_at": now_iso}


def get_regime(conn: sqlite3.Connection, asset_class: str, stale_hours: float = 26.0) -> Optional[Dict[str, Any]]:
    """Read latest regime for asset_class. Returns None if missing or stale."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT fetched_at, symbol, ema_fast, ema_slow, hl2_current, trend, cloud_width_pct
        FROM market_regime_state
        WHERE asset_class = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (asset_class,),
    )
    row = cur.fetchone()
    if not row:
        return None

    fetched_at_str = str(row[0])
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600.0
    if age_hours > stale_hours:
        return None

    return {
        "fetched_at": fetched_at_str,
        "symbol": str(row[1]),
        "ema_fast": float(row[2]),
        "ema_slow": float(row[3]),
        "hl2_current": float(row[4]),
        "trend": str(row[5]),
        "cloud_width_pct": float(row[6]),
    }


def main() -> int:
    print("EMA Cloud Regime — 34/50 on hl2 (Ripster Cloud 3)")
    conn = _connect()
    try:
        ensure_table(conn)
        results = []
        for ac, sym in REGIME_SYMBOLS.items():
            print(f"  Updating {ac} ({sym})...")
            r = update_regime(conn, ac, sym)
            if r:
                print(f"    {r['trend'].upper()} — EMA34={r['ema_fast']:.2f}  EMA50={r['ema_slow']:.2f}  cloud={r['cloud_width_pct']:.2f}%")
                results.append(r)
            else:
                print(f"    FAILED — no regime computed")
        if not results:
            print("No regimes updated — check network / Yahoo Finance")
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
