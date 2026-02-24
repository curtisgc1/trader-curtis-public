#!/usr/bin/env python3
"""
Pipeline H: Kyle Williams Strategy

Encodes a structured version of the setup notes:
- First red day short after multi-day run
- Panic dip buy only when deeply below anchored VWAP
- Parabolic short into exhaustion
- Gap-and-crap short after failed gap-up
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from pipeline_store import connect, init_pipeline_tables, insert_signal

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
PIPELINE_ID = "KYLE_WILLIAMS"


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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def get_universe(conn: sqlite3.Connection, limit: int = 28) -> List[str]:
    tickers: List[str] = []
    cur = conn.cursor()
    if _table_exists(conn, "trade_candidates"):
        cur.execute(
            """
            SELECT DISTINCT UPPER(COALESCE(ticker,''))
            FROM trade_candidates
            WHERE COALESCE(ticker,'') <> ''
            ORDER BY score DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        tickers.extend([str(r[0]) for r in cur.fetchall() if r and r[0]])

    if _table_exists(conn, "chart_liquidity_signals"):
        cur.execute(
            """
            SELECT DISTINCT UPPER(COALESCE(ticker,''))
            FROM chart_liquidity_signals
            WHERE COALESCE(ticker,'') <> ''
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        tickers.extend([str(r[0]) for r in cur.fetchall() if r and r[0]])

    # High-beta defaults consistent with this style.
    tickers.extend(
        [
            "TSLA",
            "NVDA",
            "MARA",
            "PLTR",
            "COIN",
            "SMCI",
            "SOFI",
            "UPST",
            "RIVN",
            "QQQ",
            "SPY",
        ]
    )
    out = []
    seen = set()
    for t in tickers:
        u = str(t).upper().strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out[:limit]


def fetch_daily_bars_alpaca(ticker: str, api_key: str, secret: str, limit: int = 60) -> List[dict]:
    url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=150)
    params = {
        "timeframe": "1Day",
        "limit": int(limit),
        "adjustment": "raw",
        "feed": "iex",
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code >= 400:
            return []
        data = res.json()
        bars = data.get("bars", []) if isinstance(data, dict) else []
        return bars if isinstance(bars, list) else []
    except Exception:
        return []


def fetch_daily_bars_yahoo(ticker: str) -> List[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": "6mo", "interval": "1d", "includePrePost": "false"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=20)
        if res.status_code >= 400:
            return []
        data = res.json()
    except Exception:
        return []
    chart = (data.get("chart") or {}).get("result") or []
    if not chart:
        return []
    item = chart[0]
    ts = item.get("timestamp") or []
    q = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    o = q.get("open") or []
    h = q.get("high") or []
    l = q.get("low") or []
    c = q.get("close") or []
    v = q.get("volume") or []
    out: List[dict] = []
    for i, _ in enumerate(ts):
        try:
            oi = float(o[i]) if o[i] is not None else None
            hi = float(h[i]) if h[i] is not None else None
            li = float(l[i]) if l[i] is not None else None
            ci = float(c[i]) if c[i] is not None else None
            vi = float(v[i]) if v[i] is not None else 0.0
        except Exception:
            continue
        if None in (oi, hi, li, ci):
            continue
        out.append({"o": oi, "h": hi, "l": li, "c": ci, "v": vi})
    return out


def anchored_vwap_lookback(bars: List[dict], n: int = 20) -> float:
    if not bars:
        return 0.0
    seg = bars[-n:] if len(bars) >= n else bars
    pv = 0.0
    vol = 0.0
    for b in seg:
        h = float(b.get("h") or 0.0)
        l = float(b.get("l") or 0.0)
        c = float(b.get("c") or 0.0)
        v = float(b.get("v") or 0.0)
        tp = (h + l + c) / 3.0
        pv += tp * max(v, 0.0)
        vol += max(v, 0.0)
    if vol <= 0:
        return float(seg[-1].get("c") or 0.0)
    return pv / vol


def analyze_setups(bars: List[dict]) -> List[Tuple[str, str, float, str, int]]:
    if len(bars) < 8:
        return []
    d0 = bars[-1]
    d1 = bars[-2]
    d2 = bars[-3]
    d3 = bars[-4]

    o0, h0, l0, c0 = [float(d0.get(k) or 0.0) for k in ("o", "h", "l", "c")]
    o1, c1 = [float(d1.get(k) or 0.0) for k in ("o", "c")]
    o2, c2 = [float(d2.get(k) or 0.0) for k in ("o", "c")]
    c3 = float(d3.get("c") or 0.0)
    if min(c0, c1, c2, c3, o0, o1, o2) <= 0:
        return []

    avwap20 = anchored_vwap_lookback(bars, n=20)
    ext_vs_vwap = (c0 / max(avwap20, 1e-9)) - 1.0
    day_range_pct = (h0 - l0) / max(o0, 1e-9)
    upper_wick = (h0 - max(o0, c0)) / max(h0 - l0, 1e-9)
    rebound_from_low = (c0 - l0) / max(h0 - l0, 1e-9)
    ret_3d = (c0 / max(c3, 1e-9)) - 1.0
    gap_up = (o0 / max(c1, 1e-9)) - 1.0

    out: List[Tuple[str, str, float, str, int]] = []

    # 1) First red day short after extension.
    if (c2 > o2) and (c1 > o1) and (c0 < o0) and ext_vs_vwap >= 0.03:
        conf = min(0.88, 0.62 + min(0.20, ext_vs_vwap * 1.6))
        rationale = f"setup=first_red_day_short; ext_vs_vwap={ext_vs_vwap:.3f}; prior_green_days=2"
        out.append(("short", "first_red_day_short", round(conf, 4), rationale, 180))

    # 2) Panic dip buy only when deeply below VWAP and showing stabilization.
    if (ext_vs_vwap <= -0.08) and (day_range_pct >= 0.08) and (rebound_from_low >= 0.45):
        conf = min(0.86, 0.60 + min(0.18, abs(ext_vs_vwap) * 0.9))
        rationale = (
            f"setup=panic_dip_buy; ext_vs_vwap={ext_vs_vwap:.3f}; "
            f"range_pct={day_range_pct:.3f}; rebound={rebound_from_low:.3f}"
        )
        out.append(("long", "panic_dip_buy", round(conf, 4), rationale, 240))

    # 3) Parabolic short into exhaustion.
    if (ret_3d >= 0.20) and (upper_wick >= 0.45) and (c0 <= h0 * 0.97):
        conf = min(0.84, 0.58 + min(0.20, ret_3d * 0.6))
        rationale = f"setup=parabolic_short; ret_3d={ret_3d:.3f}; upper_wick={upper_wick:.3f}"
        out.append(("short", "parabolic_short", round(conf, 4), rationale, 180))

    # 4) Gap-and-crap short.
    if (gap_up >= 0.07) and (c0 < o0) and (c0 < c1):
        conf = min(0.85, 0.60 + min(0.18, gap_up * 0.9))
        rationale = f"setup=gap_and_crap_short; gap_up={gap_up:.3f}; close_below_open=1"
        out.append(("short", "gap_and_crap_short", round(conf, 4), rationale, 180))

    return out


def main() -> int:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY", "")

    conn = connect()
    try:
        init_pipeline_tables(conn)
        tickers = get_universe(conn, limit=28)
        created = 0
        for t in tickers:
            bars = []
            if api_key and secret:
                bars = fetch_daily_bars_alpaca(t, api_key=api_key, secret=secret, limit=80)
            if not bars:
                bars = fetch_daily_bars_yahoo(t)
            if not bars:
                continue
            setups = analyze_setups(bars)
            for direction, setup, confidence, rationale, ttl in setups:
                insert_signal(
                    conn=conn,
                    pipeline_id=PIPELINE_ID,
                    asset=t,
                    direction=direction,
                    horizon="intraday" if ttl <= 180 else "swing",
                    confidence=confidence,
                    score=round(confidence * 100.0, 2),
                    rationale=rationale,
                    source_refs="daily_bars,avwap20,kyle_williams_rules",
                    ttl_minutes=ttl,
                )
                created += 1

        print(f"Pipeline H (Kyle Williams): created {created} signals")
        return 0
    except sqlite3.OperationalError as exc:
        print(f"Pipeline H skipped: {exc}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

