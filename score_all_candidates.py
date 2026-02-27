#!/usr/bin/env python3
"""
Truth layer: score ALL trade candidates at configured horizons.

Evaluates every candidate in trade_candidates — not just routed ones —
against actual price movement at each horizon. This provides ground truth
for signal quality regardless of whether the trade was taken.

Results go to candidate_horizon_outcomes for use by:
- reweight_input_sources.py (Phase 3)
- build_grpo_dataset.py (Phase 4)
- Signal Scorecard dashboard (Phase 5)
"""

import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
ENV_PATH = Path(__file__).parent / ".env"

CRYPTO_TICKERS = {"BTC", "ETH", "SOL", "DOGE", "LTC", "XRP", "ADA", "AVAX", "DOT", "LINK", "MATIC", "BNB"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _ctl(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def _parse_iso(ts: str) -> datetime:
    s = str(ts or "").strip()
    if not s:
        return datetime.now(timezone.utc)
    if "T" not in s and " " in s:
        s = s.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


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


def _alpaca_price_at_time(
    ticker: str,
    ts_iso: str,
    env: Dict[str, str],
    timeout_seconds: float = 6.0,
) -> float:
    api_key = str(env.get("ALPACA_API_KEY", "")).strip()
    secret = str(env.get("ALPACA_SECRET_KEY", "")).strip()
    if not api_key or not secret:
        return 0.0
    base = str(env.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")).strip().rstrip("/")
    dt = _parse_iso(ts_iso).astimezone(timezone.utc)
    start = dt.isoformat().replace("+00:00", "Z")
    end = (dt + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    url = f"{base}/v2/stocks/{ticker}/bars?timeframe=1Min&start={start}&end={end}&limit=1&adjustment=raw&feed=iex&sort=asc"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    try:
        res = requests.get(url, headers=headers, timeout=float(timeout_seconds))
        if res.status_code >= 400:
            return 0.0
        payload = res.json() if res.content else {}
        bars = payload.get("bars", []) if isinstance(payload, dict) else []
        if bars:
            px = float((bars[0] or {}).get("c") or 0.0)
            if px > 0:
                return px
    except Exception:
        return 0.0
    return 0.0


# CoinGecko ID mapping for common crypto tickers
_COINGECKO_IDS: Dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
    "LTC": "litecoin", "XRP": "ripple", "ADA": "cardano", "AVAX": "avalanche-2",
    "DOT": "polkadot", "LINK": "chainlink", "MATIC": "matic-network", "BNB": "binancecoin",
    "SHIB": "shiba-inu", "UNI": "uniswap", "AAVE": "aave", "NEAR": "near",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism", "SUI": "sui",
    "PEPE": "pepe", "WIF": "dogwifcoin", "FIL": "filecoin", "ATOM": "cosmos",
}


def _coingecko_price_at_time(
    symbol: str,
    ts_iso: str,
    timeout_seconds: float = 8.0,
) -> float:
    """Fetch historical crypto price from CoinGecko free API.

    Uses /coins/{id}/market_chart/range which returns granular price data
    for a given time range. Free tier: ~30 req/min, no API key needed.
    """
    coin_id = _COINGECKO_IDS.get(symbol.upper(), symbol.lower())
    dt = _parse_iso(ts_iso).astimezone(timezone.utc)
    # Request a 10-minute window around the target time
    from_ts = int(dt.timestamp())
    to_ts = int((dt + timedelta(minutes=10)).timestamp())

    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
        f"?vs_currency=usd&from={from_ts}&to={to_ts}"
    )
    headers = {"User-Agent": "trader-curtis/1.0", "Accept": "application/json"}
    try:
        res = requests.get(url, headers=headers, timeout=float(timeout_seconds))
        if res.status_code == 429:
            # Rate limited — back off
            time.sleep(2)
            return 0.0
        if res.status_code >= 400:
            return 0.0
        payload = res.json() if res.content else {}
        prices = payload.get("prices", []) if isinstance(payload, dict) else []
        if prices:
            # prices is [[timestamp_ms, price], ...] — take first entry
            px = float(prices[0][1]) if len(prices[0]) >= 2 else 0.0
            if px > 0:
                return px
    except Exception:
        return 0.0
    return 0.0


def _alpaca_crypto_price_at_time(
    symbol: str,
    ts_iso: str,
    env: Dict[str, str],
    timeout_seconds: float = 6.0,
) -> float:
    """Alpaca crypto bars — fallback for coins on Alpaca's US exchange."""
    api_key = str(env.get("ALPACA_API_KEY", "")).strip()
    secret = str(env.get("ALPACA_SECRET_KEY", "")).strip()
    if not api_key or not secret:
        return 0.0
    base = str(env.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")).strip().rstrip("/")
    dt = _parse_iso(ts_iso).astimezone(timezone.utc)
    start = dt.isoformat().replace("+00:00", "Z")
    end = (dt + timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
    pair = f"{symbol.upper()}/USD"
    url = (
        f"{base}/v1beta3/crypto/us/bars?"
        f"symbols={pair}&timeframe=1Min&start={start}&end={end}&limit=1&sort=asc"
    )
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    try:
        res = requests.get(url, headers=headers, timeout=float(timeout_seconds))
        if res.status_code >= 400:
            return 0.0
        payload = res.json() if res.content else {}
        bars_map = payload.get("bars", {}) if isinstance(payload, dict) else {}
        bars = bars_map.get(pair, []) if isinstance(bars_map, dict) else []
        if bars:
            px = float((bars[0] or {}).get("c") or 0.0)
            if px > 0:
                return px
    except Exception:
        return 0.0
    return 0.0


def _get_price_at(ticker: str, ts_iso: str, env: Dict[str, str]) -> float:
    if ticker.upper() in CRYPTO_TICKERS:
        # CoinGecko primary, Alpaca fallback for crypto
        px = _coingecko_price_at_time(ticker, ts_iso)
        if px > 0:
            return px
        return _alpaca_crypto_price_at_time(ticker, ts_iso, env)
    return _alpaca_price_at_time(ticker, ts_iso, env)


def _resolution_from_pnl(pnl_percent: float, direction: str) -> str:
    # Direction-aware: a short that goes down is a win
    if abs(pnl_percent) < 0.05:
        return "push"
    if direction.lower() in ("short", "sell", "bearish"):
        return "win" if pnl_percent < -0.05 else "loss"
    return "win" if pnl_percent > 0.05 else "loss"


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_horizon_outcomes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          candidate_ticker TEXT NOT NULL,
          candidate_direction TEXT NOT NULL DEFAULT '',
          candidate_generated_at TEXT NOT NULL,
          candidate_source_tag TEXT NOT NULL DEFAULT '',
          candidate_score REAL NOT NULL DEFAULT 0,
          candidate_consensus_flag INTEGER NOT NULL DEFAULT 0,
          horizon_hours INTEGER NOT NULL,
          entry_price REAL NOT NULL DEFAULT 0,
          eval_price REAL NOT NULL DEFAULT 0,
          pnl_percent REAL NOT NULL DEFAULT 0,
          resolution TEXT NOT NULL DEFAULT 'push',
          evaluated_at TEXT NOT NULL,
          UNIQUE(candidate_ticker, candidate_generated_at, horizon_hours)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cho_source ON candidate_horizon_outcomes(candidate_source_tag)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cho_ticker ON candidate_horizon_outcomes(candidate_ticker)"
    )
    conn.commit()


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        enabled = _ctl(conn, "candidate_scoring_enabled", "1") == "1"
        if not enabled:
            print("CANDIDATE_SCORING disabled")
            return 0

        if not table_exists(conn, "trade_candidates"):
            print("CANDIDATE_SCORING no trade_candidates table")
            return 0

        ensure_table(conn)
        env = load_env()

        horizons_str = _ctl(conn, "candidate_scoring_horizons", "6,24")
        horizons = [int(h.strip()) for h in horizons_str.split(",") if h.strip().isdigit()]
        if not horizons:
            horizons = [6, 24]

        lookback_days = int(float(_ctl(conn, "candidate_scoring_lookback_days", "3") or 3))
        max_lookups = int(float(_ctl(conn, "candidate_scoring_max_lookups", "200") or 200))
        max_runtime_seconds = int(float(_ctl(conn, "candidate_scoring_max_runtime_seconds", "300") or 300))

        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        now = datetime.now(timezone.utc)

        cur = conn.cursor()

        # Get candidates within lookback window
        cur.execute(
            """
            SELECT id, ticker, direction, generated_at, source_tag, score, consensus_flag
            FROM trade_candidates
            WHERE datetime(COALESCE(generated_at, '1970-01-01')) >= datetime(?)
            ORDER BY datetime(generated_at) DESC
            """,
            (cutoff,),
        )
        candidates = cur.fetchall()

        lookups = 0
        scored = 0
        skipped = 0
        start_time = time.monotonic()

        for cand_id, ticker, direction, generated_at, source_tag, score, consensus_flag in candidates:
            if lookups >= max_lookups:
                break
            if (time.monotonic() - start_time) > max_runtime_seconds:
                break

            ticker = str(ticker or "").strip().upper()
            if not ticker:
                continue

            gen_dt = _parse_iso(str(generated_at or ""))

            for horizon_h in horizons:
                # Check if this horizon has elapsed
                eval_time = gen_dt + timedelta(hours=horizon_h)
                if eval_time > now:
                    continue

                # Check if already scored
                cur.execute(
                    """
                    SELECT 1 FROM candidate_horizon_outcomes
                    WHERE candidate_ticker=? AND candidate_generated_at=? AND horizon_hours=?
                    LIMIT 1
                    """,
                    (ticker, str(generated_at or ""), horizon_h),
                )
                if cur.fetchone():
                    skipped += 1
                    continue

                # Fetch entry price at generated_at
                entry_price = _get_price_at(ticker, str(generated_at or ""), env)
                lookups += 1
                if entry_price <= 0:
                    continue

                # Fetch eval price at generated_at + horizon
                eval_ts = eval_time.isoformat()
                eval_price = _get_price_at(ticker, eval_ts, env)
                lookups += 1
                if eval_price <= 0:
                    continue

                pnl_pct = round(((eval_price - entry_price) / entry_price) * 100.0, 4)
                direction_str = str(direction or "long").strip().lower()
                resolution = _resolution_from_pnl(pnl_pct, direction_str)

                conn.execute(
                    """
                    INSERT INTO candidate_horizon_outcomes
                    (candidate_ticker, candidate_direction, candidate_generated_at,
                     candidate_source_tag, candidate_score, candidate_consensus_flag,
                     horizon_hours, entry_price, eval_price, pnl_percent, resolution, evaluated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_ticker, candidate_generated_at, horizon_hours) DO NOTHING
                    """,
                    (
                        ticker,
                        direction_str,
                        str(generated_at or ""),
                        str(source_tag or ""),
                        float(score or 0.0),
                        int(consensus_flag or 0),
                        horizon_h,
                        entry_price,
                        eval_price,
                        pnl_pct,
                        resolution,
                        now_iso(),
                    ),
                )
                scored += 1

                if lookups >= max_lookups:
                    break
                if (time.monotonic() - start_time) > max_runtime_seconds:
                    break

        conn.commit()
        elapsed = round(time.monotonic() - start_time, 1)
        print(
            f"CANDIDATE_SCORING scored={scored} skipped={skipped} lookups={lookups} "
            f"candidates={len(candidates)} horizons={horizons} lookback_days={lookback_days} "
            f"max_lookups={max_lookups} elapsed={elapsed}s"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
