#!/usr/bin/env python3
"""
Chart Liquidity pipeline (shadow/live signal feed).
Builds structured chart-liquidity signals from Alpaca bar data and stores clickable chart URLs.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from pipeline_store import connect, init_pipeline_tables, insert_signal

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chart_liquidity_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          direction TEXT NOT NULL,
          pattern TEXT NOT NULL,
          confidence REAL NOT NULL,
          score REAL NOT NULL,
          entry_hint REAL NOT NULL DEFAULT 0,
          stop_hint REAL NOT NULL DEFAULT 0,
          target_hint REAL NOT NULL DEFAULT 0,
          liquidity_high REAL NOT NULL DEFAULT 0,
          liquidity_low REAL NOT NULL DEFAULT 0,
          chart_url TEXT NOT NULL DEFAULT '',
          source_ref TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()


def get_universe(conn: sqlite3.Connection, limit: int = 20) -> List[str]:
    cur = conn.cursor()
    tickers: List[str] = []
    if _table_exists(conn, "trade_candidates"):
        cur.execute(
            """
            SELECT DISTINCT ticker
            FROM trade_candidates
            WHERE COALESCE(ticker,'') <> ''
            ORDER BY score DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        tickers.extend([str(r[0]).upper() for r in cur.fetchall() if r and r[0]])
    if not tickers and _table_exists(conn, "institutional_patterns"):
        cur.execute(
            """
            SELECT DISTINCT ticker
            FROM institutional_patterns
            WHERE COALESCE(ticker,'') <> ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        tickers.extend([str(r[0]).upper() for r in cur.fetchall() if r and r[0]])
    if not tickers:
        tickers = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "BTC"]
    return list(dict.fromkeys(tickers))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def fetch_bars(ticker: str, api_key: str, secret: str, timeframe: str = "1H", limit: int = 120) -> List[dict]:
    url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    params = {"timeframe": timeframe, "limit": int(limit), "adjustment": "raw", "feed": "iex"}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
    except Exception:
        return []
    if res.status_code >= 400:
        return []
    try:
        data = res.json()
    except Exception:
        return []
    bars = data.get("bars", []) if isinstance(data, dict) else []
    return bars if isinstance(bars, list) else []


def fetch_crypto_bars(ticker: str, api_key: str, secret: str, timeframe: str = "1H", limit: int = 120) -> List[dict]:
    base = str(ticker).upper().replace("USD", "").replace("/USD", "")
    symbol = f"{base}/USD"
    url = "https://data.alpaca.markets/v1beta3/crypto/us/bars"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    params = {"symbols": symbol, "timeframe": timeframe, "limit": int(limit)}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
    except Exception:
        return []
    if res.status_code >= 400:
        return []
    try:
        data = res.json()
    except Exception:
        return []
    bars_map = data.get("bars", {}) if isinstance(data, dict) else {}
    bars = bars_map.get(symbol, []) if isinstance(bars_map, dict) else []
    return bars if isinstance(bars, list) else []


def fetch_yahoo_bars(ticker: str) -> List[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": "3mo", "interval": "1h", "includePrePost": "false"}
    try:
        res = requests.get(url, params=params, timeout=20)
    except Exception:
        return []
    if res.status_code >= 400:
        return []
    try:
        data = res.json()
    except Exception:
        return []
    chart = (data.get("chart") or {}).get("result") or []
    if not chart:
        return []
    item = chart[0] if isinstance(chart, list) else {}
    timestamps = item.get("timestamp") or []
    quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    out: List[dict] = []
    for i, ts in enumerate(timestamps):
        try:
            o = float(opens[i]) if opens[i] is not None else None
            h = float(highs[i]) if highs[i] is not None else None
            l = float(lows[i]) if lows[i] is not None else None
            c = float(closes[i]) if closes[i] is not None else None
            v = float(volumes[i]) if volumes and volumes[i] is not None else 0.0
        except Exception:
            continue
        if None in (o, h, l, c):
            continue
        out.append({"t": ts, "o": o, "h": h, "l": l, "c": c, "v": v})
    return out


def analyze_liquidity(bars: List[dict]) -> Tuple[str, str, float, float, float, float, float, float]:
    """
    Returns: direction, pattern, confidence, entry, stop, target, liq_high, liq_low
    """
    if len(bars) < 30:
        return "neutral", "insufficient_data", 0.35, 0.0, 0.0, 0.0, 0.0, 0.0
    closes = [float(b.get("c", 0.0)) for b in bars if b.get("c") is not None]
    highs = [float(b.get("h", 0.0)) for b in bars if b.get("h") is not None]
    lows = [float(b.get("l", 0.0)) for b in bars if b.get("l") is not None]
    current = closes[-1]
    recent_high = max(highs[-40:-2]) if len(highs) > 42 else max(highs[:-2])
    recent_low = min(lows[-40:-2]) if len(lows) > 42 else min(lows[:-2])
    rng = max(1e-9, recent_high - recent_low)
    pos = (current - recent_low) / rng  # 0 bottom, 1 top

    # Simple liquidity-map heuristic:
    # near highs -> likely buy-side liquidity sweep risk -> short bias
    # near lows -> likely sell-side liquidity sweep risk -> long bias
    if pos >= 0.82:
        direction = "short"
        pattern = "liquidity_grab_high"
        confidence = min(0.85, 0.55 + (pos - 0.82) * 1.2)
        entry = current
        stop = recent_high * 1.003
        target = current - (0.6 * rng)
    elif pos <= 0.18:
        direction = "long"
        pattern = "liquidity_grab_low"
        confidence = min(0.85, 0.55 + (0.18 - pos) * 1.2)
        entry = current
        stop = recent_low * 0.997
        target = current + (0.6 * rng)
    else:
        direction = "neutral"
        pattern = "mid_range"
        confidence = 0.40
        entry = current
        stop = 0.0
        target = 0.0

    return direction, pattern, round(confidence, 4), round(entry, 4), round(stop, 4), round(target, 4), round(recent_high, 4), round(recent_low, 4)


def chart_url(ticker: str) -> str:
    return f"https://www.tradingview.com/chart/?symbol={ticker}"


def source_ref(ticker: str) -> str:
    return f"https://www.tradingview.com/symbols/{ticker}/"


def main() -> int:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        print("CHART_LIQUIDITY skipped: missing Alpaca credentials")
        return 0

    conn = connect()
    try:
        init_pipeline_tables(conn)
        ensure_table(conn)
        tickers = get_universe(conn, limit=20)
        created = 0
        for t in tickers:
            bars = fetch_bars(t, api_key=api_key, secret=secret, timeframe="1H", limit=120)
            if not bars and t in {"BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "LTC", "BNB", "SUI"}:
                bars = fetch_crypto_bars(t, api_key=api_key, secret=secret, timeframe="1H", limit=120)
            if not bars:
                bars = fetch_yahoo_bars(t)
            if not bars:
                continue
            direction, pattern, conf, entry, stop, target, liq_high, liq_low = analyze_liquidity(bars)
            score = round(conf * 100.0, 2)
            notes = f"pattern={pattern}; liq_high={liq_high}; liq_low={liq_low}; entry={entry}; stop={stop}; target={target}"

            conn.execute(
                """
                INSERT INTO chart_liquidity_signals
                (created_at, ticker, timeframe, direction, pattern, confidence, score, entry_hint, stop_hint, target_hint,
                 liquidity_high, liquidity_low, chart_url, source_ref, notes, status)
                VALUES (?, ?, '1H', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    now_iso(),
                    t,
                    direction,
                    pattern,
                    float(conf),
                    float(score),
                    float(entry),
                    float(stop),
                    float(target),
                    float(liq_high),
                    float(liq_low),
                    chart_url(t),
                    source_ref(t),
                    notes,
                ),
            )

            if direction in {"long", "short"}:
                insert_signal(
                    conn=conn,
                    pipeline_id="CHART_LIQUIDITY",
                    asset=t,
                    direction=direction,
                    horizon="intraday",
                    confidence=float(conf),
                    score=float(score),
                    rationale=f"{pattern}; entry={entry}; stop={stop}; target={target}",
                    source_refs=chart_url(t),
                    ttl_minutes=180,
                )
                created += 1
        conn.commit()
        print(f"CHART_LIQUIDITY: created {created} directional signals")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
