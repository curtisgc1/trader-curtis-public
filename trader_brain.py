#!/usr/bin/env python3
"""
trader_brain.py — Real-time smart money copy-trading daemon.

Connects to Predexon WSS for live order fills, qualifies wallets via
their profile API, checks convergence across multiple smart wallets,
and auto-executes via the Predexon Trading API.

Start:  tmux new -s trader-brain 'cd /Users/Shared/curtis/trader-curtis && python3 trader_brain.py'
Stop:   Ctrl-C (graceful shutdown)
Kill:   sqlite3 data/trades.db "UPDATE execution_controls SET value='0' WHERE key='tb_enabled'"
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import signal
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import websockets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from websockets.exceptions import ConnectionClosed

# ---------------------------------------------------------------------------
# Paths & URLs
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "data" / "trades.db"
SECRETS_PATH = Path.home() / ".secrets" / "predexon-api-keys.json"

PREDEXON_DATA_URL = "https://api.predexon.com/v2"
PREDEXON_TRADE_URL = "https://trade.predexon.com"
PREDEXON_WSS_URL = "wss://wss.predexon.com/v1"

KALSHI_API_URL = "https://trading-api.kalshi.com"
KALSHI_SECRETS_PATH = Path.home() / ".secrets" / "kalshi-api-keys.json"
KALSHI_PEM_PATH = Path.home() / ".secrets" / "kalshi-private-key.pem"

IMESSAGE_BUDDY = "+17602190832"

# ---------------------------------------------------------------------------
# Default thresholds (overridden at runtime from execution_controls)
# ---------------------------------------------------------------------------
MIN_TRADE_USDC = 5_000
MIN_WIN_RATE = 0.58
MIN_TRADES = 50
MIN_PNL = 5_000
CONVERGENCE_WINDOW_H = 2
CONVERGENCE_MIN = 2
KELLY_FRACTION = 0.25
MAX_NOTIONAL_PER_TRADE = 50

# ---------------------------------------------------------------------------
# In-memory caches
# ---------------------------------------------------------------------------
_wallet_cache: Dict[str, Tuple[dict, float]] = {}  # addr -> (profile, ts)
WALLET_CACHE_TTL = 3600  # 1 hour

_kalshi_markets_cache: Tuple[List[dict], float] = ([], 0.0)  # (markets, ts)
KALSHI_MARKETS_CACHE_TTL = 300  # 5 min

# Thread pool for blocking I/O (HTTP + SQLite)
_executor = ThreadPoolExecutor(max_workers=4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts() -> float:
    return time.time()


def _log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def _connect_db() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _evict_stale_cache() -> None:
    now = _ts()
    stale = [k for k, (_, ts) in _wallet_cache.items() if now - ts > WALLET_CACHE_TTL]
    for k in stale:
        del _wallet_cache[k]


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------
def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS brain_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            condition_id TEXT NOT NULL,
            token_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            size_usdc REAL NOT NULL,
            wallet_win_rate REAL DEFAULT 0,
            wallet_pnl REAL DEFAULT 0,
            convergence_count INTEGER DEFAULT 0,
            action TEXT NOT NULL DEFAULT 'watching',
            order_id TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS brain_wallet_cache (
            wallet_address TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL,
            qualified INTEGER NOT NULL DEFAULT 0,
            cached_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brain_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brain_arb_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT NOT NULL,
            poly_condition_id TEXT NOT NULL,
            kalshi_ticker TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            similarity INTEGER NOT NULL DEFAULT 0,
            poly_price REAL NOT NULL,
            kalshi_price REAL NOT NULL,
            spread REAL NOT NULL,
            spread_after_fees REAL NOT NULL,
            direction TEXT NOT NULL,
            poly_size_usd REAL DEFAULT 0,
            kalshi_size_usd REAL DEFAULT 0,
            action TEXT NOT NULL DEFAULT 'detected',
            poly_order_id TEXT DEFAULT '',
            kalshi_order_id TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Secrets & API keys
# ---------------------------------------------------------------------------
def _load_api_keys() -> Dict[str, str]:
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(f"Missing {SECRETS_PATH}")
    with open(SECRETS_PATH) as f:
        data = json.load(f)
    for k in ("trading_api_key", "data_api_key"):
        if k not in data:
            raise KeyError(f"Missing '{k}' in {SECRETS_PATH}")
    return data


# ---------------------------------------------------------------------------
# Predexon user management (sync — called via run_in_executor)
# ---------------------------------------------------------------------------
def _get_cached_user_id(conn: sqlite3.Connection) -> Optional[str]:
    cur = conn.execute(
        "SELECT value FROM brain_config WHERE key='predexon_user_id'"
    )
    row = cur.fetchone()
    return row[0] if row else None


def _cache_user_id(conn: sqlite3.Connection, user_id: str, wallet: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO brain_config (key, value) VALUES ('predexon_user_id', ?)",
        (user_id,),
    )
    conn.execute(
        "INSERT OR REPLACE INTO brain_config (key, value) VALUES ('predexon_wallet_address', ?)",
        (wallet,),
    )
    conn.commit()


def _setup_predexon_user_sync(trade_headers: Dict[str, str]) -> str:
    conn = _connect_db()
    try:
        _ensure_tables(conn)
        cached = _get_cached_user_id(conn)
        if cached:
            resp = requests.get(
                f"{PREDEXON_TRADE_URL}/api/users/{cached}",
                headers=trade_headers,
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "ready":
                    _log(f"Predexon user ready: {cached}")
                    return cached

        resp = requests.post(
            f"{PREDEXON_TRADE_URL}/api/users/create",
            headers=trade_headers,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        user_id = body["userId"]
        wallet = body.get("polymarketWalletAddress", "")
        _log(f"Created Predexon user: {user_id} wallet: {wallet}")

        for _ in range(30):
            time.sleep(2)
            check = requests.get(
                f"{PREDEXON_TRADE_URL}/api/users/{user_id}",
                headers=trade_headers,
                timeout=10,
            )
            if check.status_code == 200 and check.json().get("status") == "ready":
                break
        else:
            _log("WARNING: Predexon user not ready after 60s, proceeding anyway")

        _cache_user_id(conn, user_id, wallet)
        return user_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Controls loader
# ---------------------------------------------------------------------------
def _load_tb_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    cur = conn.execute(
        "SELECT key, value FROM execution_controls WHERE key LIKE 'tb_%'"
    )
    return {k: v for k, v in cur.fetchall()}


# ---------------------------------------------------------------------------
# Smart activity — market selection (sync)
# ---------------------------------------------------------------------------
def _get_smart_activity_markets_sync(data_headers: Dict[str, str]) -> List[str]:
    try:
        resp = requests.get(
            f"{PREDEXON_DATA_URL}/polymarket/markets/smart-activity",
            headers=data_headers,
            params={
                "min_realized_pnl": 5000,
                "min_win_rate": 0.55,
                "min_trades": 50,
                "window": "7d",
                "sort_by": "smart_volume",
                "limit": 10,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            _log(f"smart-activity HTTP {resp.status_code}")
            return []
        data = resp.json()
        markets = data.get("markets", [])
        return [m["condition_id"] for m in markets if m.get("condition_id")]
    except Exception as exc:
        _log(f"smart-activity error: {exc}")
        return []


# ---------------------------------------------------------------------------
# Wallet profiling (sync)
# ---------------------------------------------------------------------------
def _get_wallet_profile_sync(
    data_headers: Dict[str, str], address: str
) -> Optional[Dict[str, Any]]:
    now = _ts()
    cached = _wallet_cache.get(address)
    if cached and (now - cached[1]) < WALLET_CACHE_TTL:
        return cached[0]

    try:
        resp = requests.get(
            f"{PREDEXON_DATA_URL}/polymarket/wallet/{address}",
            headers=data_headers,
            timeout=10,
        )
        if resp.status_code == 404:
            _wallet_cache[address] = ({}, now)
            return None
        if resp.status_code != 200:
            return None
        profile = resp.json()
        _wallet_cache[address] = (profile, now)
        return profile
    except Exception as exc:
        _log(f"wallet profile error ({address[:10]}...): {exc}")
        return None


def _is_qualified_wallet(
    profile: Dict[str, Any], controls: Dict[str, str]
) -> bool:
    if not profile:
        return False

    min_wr = float(controls.get("tb_min_wallet_win_rate", str(MIN_WIN_RATE)))
    min_trades = int(float(controls.get("tb_min_wallet_trades", str(MIN_TRADES))))
    min_pnl = float(controls.get("tb_min_wallet_pnl", str(MIN_PNL)))

    styles = profile.get("trading_styles") or {}
    if styles.get("is_market_maker"):
        return False

    metrics = profile.get("metrics") or {}
    all_time = metrics.get("all_time") or {}

    win_rate = all_time.get("win_rate", 0) or 0
    trades = all_time.get("trades", 0) or 0
    realized_pnl = all_time.get("realized_pnl", 0) or 0

    return (
        float(win_rate) >= min_wr
        and int(trades) >= min_trades
        and float(realized_pnl) >= min_pnl
    )


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------
def _get_convergence(
    conn: sqlite3.Connection,
    condition_id: str,
    outcome: str,
    hours: int,
) -> int:
    cur = conn.execute(
        """
        SELECT COUNT(DISTINCT wallet_address)
        FROM brain_signals
        WHERE condition_id = ?
          AND outcome = ?
          AND action IN ('watching', 'executed')
          AND datetime(detected_at) >= datetime('now', ? || ' hours')
        """,
        (condition_id, outcome, f"-{hours}"),
    )
    return int(cur.fetchone()[0] or 0)


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------
def _kelly_size(
    win_rate: float,
    price: float,
    bankroll: float,
    max_notional: float,
    kelly_fraction: float,
) -> float:
    if price <= 0 or price >= 1:
        return 0.0
    b = (1.0 / price) - 1.0
    if b <= 0:
        return 0.0
    p = win_rate
    q = 1.0 - p
    f_star = (p * b - q) / b
    if f_star <= 0:
        return 0.0
    raw = f_star * kelly_fraction * bankroll
    return min(raw, max_notional)


# ---------------------------------------------------------------------------
# Order placement (sync)
# ---------------------------------------------------------------------------
def _place_order_sync(
    trade_headers: Dict[str, str],
    user_id: str,
    token_id: str,
    side: str,
    amount_usdc: float,
    price: Optional[float],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "venue": "polymarket",
        "tokenId": token_id,
        "side": side,
    }
    if price is not None:
        body["type"] = "limit"
        body["size"] = str(round(amount_usdc / price, 2))
        body["price"] = str(round(price, 2))
    else:
        body["type"] = "market"
        body["amount"] = str(round(amount_usdc, 2))

    resp = requests.post(
        f"{PREDEXON_TRADE_URL}/api/users/{user_id}/orders",
        headers=trade_headers,
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _get_balance_sync(trade_headers: Dict[str, str], user_id: str) -> float:
    resp = requests.get(
        f"{PREDEXON_TRADE_URL}/api/users/{user_id}/balance",
        headers=trade_headers,
        params={"venue": "polymarket"},
        timeout=10,
    )
    if resp.status_code != 200:
        return 0.0
    balances = resp.json().get("balances", [])
    for b in balances:
        if b.get("venue") == "polymarket":
            return float(b.get("available", "0"))
    return 0.0


# ---------------------------------------------------------------------------
# iMessage notification
# ---------------------------------------------------------------------------
def _notify_imessage(msg: str) -> None:
    escaped = msg.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'tell application "Messages" to send "{escaped}" '
        f'to buddy "{IMESSAGE_BUDDY}" of '
        f'(first account whose service type is iMessage)'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            timeout=10,
            capture_output=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Risk gate
# ---------------------------------------------------------------------------
def _check_risk_gate(
    conn: sqlite3.Connection, controls: Dict[str, str], notional: float
) -> Tuple[bool, str]:
    if controls.get("tb_enabled", "1") != "1":
        return False, "tb_enabled=0 (kill switch)"

    max_per_trade = float(
        controls.get("tb_max_notional_per_trade", str(MAX_NOTIONAL_PER_TRADE))
    )
    if notional > max_per_trade:
        return False, f"notional {notional:.2f} > cap {max_per_trade:.2f}"

    max_daily = float(controls.get("tb_max_daily_exposure", "200"))
    cur = conn.execute(
        """
        SELECT COALESCE(SUM(size_usdc), 0)
        FROM brain_signals
        WHERE action = 'executed'
          AND date(detected_at) = date('now')
        """
    )
    daily_used = float(cur.fetchone()[0] or 0)
    if daily_used + notional > max_daily:
        return False, f"daily exposure {daily_used + notional:.2f} > cap {max_daily:.2f}"

    max_open = int(float(controls.get("tb_max_open_positions", "10")))
    cur = conn.execute(
        """
        SELECT COUNT(DISTINCT condition_id)
        FROM brain_signals
        WHERE action = 'executed'
          AND date(detected_at) >= date('now', '-7 days')
        """
    )
    open_count = int(cur.fetchone()[0] or 0)
    if open_count >= max_open:
        return False, f"open positions {open_count} >= cap {max_open}"

    return True, "approved"


# ---------------------------------------------------------------------------
# Record keeping
# ---------------------------------------------------------------------------
def _record_signal(
    conn: sqlite3.Connection,
    wallet: str,
    condition_id: str,
    token_id: str,
    outcome: str,
    side: str,
    price: float,
    size_usdc: float,
    win_rate: float,
    pnl: float,
    convergence: int,
    action: str,
    order_id: str = "",
    notes: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO brain_signals
        (detected_at, wallet_address, condition_id, token_id, outcome, side,
         price, size_usdc, wallet_win_rate, wallet_pnl, convergence_count,
         action, order_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(), wallet, condition_id, token_id, outcome, side,
            price, size_usdc, win_rate, pnl, convergence,
            action, order_id, notes,
        ),
    )
    conn.commit()


def _record_order(
    conn: sqlite3.Connection,
    condition_id: str,
    outcome: str,
    token_id: str,
    price: float,
    size: float,
    order_id: str,
    status: str,
    notes: str,
    response_json: str,
) -> None:
    conn.execute(
        """
        INSERT INTO polymarket_orders
        (created_at, strategy_id, market_id, outcome, side, price, size,
         order_id, status, notes, token_id, mode, notional, response_json)
        VALUES (?, 'BRAIN_COPY', ?, ?, 'BUY', ?, ?, ?, ?, ?, ?, 'live', ?, ?)
        """,
        (
            now_iso(), condition_id, outcome, price, size,
            order_id, status, notes, token_id, round(price * size, 2),
            response_json,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Core fill handler (sync — offloaded to executor from async loop)
# ---------------------------------------------------------------------------
def _handle_fill_sync(
    event_data: Dict[str, Any],
    conn: sqlite3.Connection,
    data_headers: Dict[str, str],
    trade_headers: Dict[str, str],
    user_id: str,
    controls: Dict[str, str],
) -> bool:
    wallet = str(event_data.get("user") or event_data.get("taker") or "").lower()
    if not wallet:
        return False

    token_id = str(event_data.get("token_id") or "")
    condition_id = str(event_data.get("condition_id") or "")
    outcome = str(event_data.get("outcome") or "")
    side = str(event_data.get("side") or "").upper()
    price = float(event_data.get("price") or 0)
    shares = float(event_data.get("shares_normalized") or 0)
    market_slug = str(event_data.get("market_slug") or "")
    title = str(event_data.get("title") or market_slug)

    usdc_value = shares * price
    min_trade = float(controls.get("tb_min_trade_usdc", str(MIN_TRADE_USDC)))
    if usdc_value < min_trade:
        return False

    _log(f"Whale fill: ${usdc_value:,.0f} {side} '{title[:50]}' by {wallet[:10]}...")

    profile = _get_wallet_profile_sync(data_headers, wallet)
    if not _is_qualified_wallet(profile, controls):
        _log(f"  -> skip: wallet not qualified")
        if controls.get("tb_notify_on_signal", "0") == "1":
            _notify_imessage(
                f"SIGNAL (skip): ${usdc_value:,.0f} {side} '{title[:40]}' — wallet unqualified"
            )
        return False

    all_time = ((profile or {}).get("metrics") or {}).get("all_time") or {}
    win_rate = float(all_time.get("win_rate", 0) or 0)
    realized_pnl = float(all_time.get("realized_pnl", 0) or 0)

    # Record the watching signal FIRST, then query convergence
    _record_signal(
        conn, wallet, condition_id, token_id, outcome, side,
        price, usdc_value, win_rate, realized_pnl, 0, "watching",
    )

    conv_window = int(
        float(controls.get("tb_convergence_window_hours", str(CONVERGENCE_WINDOW_H)))
    )
    convergence = _get_convergence(conn, condition_id, outcome, conv_window)
    conv_min = int(float(controls.get("tb_convergence_min", str(CONVERGENCE_MIN))))

    if convergence < conv_min:
        _log(f"  -> watching: convergence {convergence}/{conv_min}")
        if controls.get("tb_notify_on_signal", "0") == "1":
            _notify_imessage(
                f"WATCHING: ${usdc_value:,.0f} {side} '{title[:40]}' — "
                f"{convergence}/{conv_min} smart wallets"
            )
        return False

    # For SELL signals, we need the complement token to buy the opposite side
    buy_token = token_id
    buy_price = price
    if side == "SELL":
        complement = str(event_data.get("complement_token_id") or "")
        if not complement:
            _log(f"  -> skip SELL: no complement token available")
            return False
        buy_token = complement
        buy_price = round(1.0 - price, 2)  # approximate for binary markets

    kelly_frac = float(controls.get("tb_kelly_fraction", str(KELLY_FRACTION)))
    max_notional = float(
        controls.get("tb_max_notional_per_trade", str(MAX_NOTIONAL_PER_TRADE))
    )
    bankroll = _get_balance_sync(trade_headers, user_id)
    if bankroll <= 0:
        _log(f"  -> skip: zero balance")
        return False

    size_usd = _kelly_size(win_rate, buy_price, bankroll, max_notional, kelly_frac)
    if size_usd < 1.0:
        _log(f"  -> skip: kelly size {size_usd:.2f} < $1")
        return False

    allowed, reason = _check_risk_gate(conn, controls, size_usd)
    if not allowed:
        _log(f"  -> blocked: {reason}")
        return False

    _log(
        f"  -> EXECUTE: ${size_usd:.2f} BUY @ {buy_price:.2f} "
        f"(conv={convergence}, wr={win_rate:.0%}, kelly={kelly_frac})"
    )

    try:
        result = _place_order_sync(
            trade_headers, user_id, buy_token, "buy", size_usd, buy_price
        )
        order_id = result.get("orderId", "")
        status = result.get("status", "submitted")

        _record_signal(
            conn, wallet, condition_id, token_id, outcome, side,
            buy_price, size_usd, win_rate, realized_pnl, convergence,
            "executed", order_id=order_id,
            notes=f"conv={convergence} wr={win_rate:.2f} kelly=${size_usd:.2f}",
        )
        _record_order(
            conn, condition_id, outcome, buy_token, buy_price,
            round(size_usd / buy_price, 2) if buy_price > 0 else 0,
            order_id, "filled_live" if status == "filled" else "submitted_live",
            f"brain_copy conv={convergence}",
            json.dumps(result),
        )
        _log(f"  -> ORDER {order_id} status={status}")

        if controls.get("tb_notify_on_execute", "1") == "1":
            _notify_imessage(
                f"FILL: ${size_usd:.0f} BUY '{title[:40]}' @ {buy_price:.2f} "
                f"— {convergence} smart wallets aligned"
            )
        return True

    except requests.HTTPError as exc:
        err_text = str(exc)
        try:
            err_text = exc.response.text[:200]
        except Exception:
            pass
        _log(f"  -> ORDER FAILED: {err_text}")
        return False
    except Exception as exc:
        _log(f"  -> ORDER ERROR: {exc}")
        return False


# ---------------------------------------------------------------------------
# Kalshi auth & execution (sync)
# ---------------------------------------------------------------------------
def _load_kalshi_keys() -> Dict[str, Any]:
    with open(KALSHI_SECRETS_PATH) as f:
        cfg = json.load(f)
    with open(KALSHI_PEM_PATH, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    return {"api_key_id": cfg["api_key_id"], "private_key": private_key}


def _kalshi_auth_headers(
    private_key: Any, api_key: str, method: str, path: str
) -> Dict[str, str]:
    ts = str(int(time.time() * 1000))
    msg = ts + method.upper() + path
    sig = private_key.sign(
        msg.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json",
    }


def _kalshi_get_sync(
    private_key: Any, api_key: str, path: str, params: Optional[dict] = None
) -> Optional[dict]:
    headers = _kalshi_auth_headers(private_key, api_key, "GET", path)
    resp = requests.get(
        f"{KALSHI_API_URL}{path}", headers=headers, params=params, timeout=15
    )
    if resp.status_code != 200:
        _log(f"Kalshi GET {path} -> {resp.status_code}")
        return None
    return resp.json()


def _get_kalshi_balance_sync(private_key: Any, api_key: str) -> float:
    data = _kalshi_get_sync(private_key, api_key, "/trade-api/v2/portfolio/balance")
    if not data:
        return 0.0
    return float(data.get("balance", 0)) / 100.0  # cents -> dollars


def _fetch_kalshi_active_markets_sync(
    private_key: Any, api_key: str
) -> List[dict]:
    global _kalshi_markets_cache
    cached, ts = _kalshi_markets_cache
    if cached and _ts() - ts < KALSHI_MARKETS_CACHE_TTL:
        return cached

    markets: List[dict] = []
    cursor: Optional[str] = None
    for _ in range(3):  # max 3 pages = 600 markets
        params: Dict[str, Any] = {"status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = _kalshi_get_sync(
            private_key, api_key, "/trade-api/v2/markets", params
        )
        if not data:
            break
        batch = data.get("markets", [])
        markets.extend(
            {
                "ticker": m.get("ticker", ""),
                "title": m.get("title", ""),
                "yes_ask": float(m.get("yes_ask", 0)) / 100.0,
                "no_ask": float(m.get("no_ask", 0)) / 100.0,
                "volume": int(m.get("volume", 0)),
                "event_ticker": m.get("event_ticker", ""),
            }
            for m in batch
            if m.get("ticker")
        )
        cursor = data.get("cursor")
        if not cursor or len(batch) < 200:
            break

    _kalshi_markets_cache = (markets, _ts())
    _log(f"Kalshi: cached {len(markets)} active markets")
    return markets


def _place_kalshi_order_sync(
    private_key: Any,
    api_key: str,
    ticker: str,
    side: str,
    count: int,
    price_cents: int,
) -> Dict[str, Any]:
    path = "/trade-api/v2/portfolio/orders"
    headers = _kalshi_auth_headers(private_key, api_key, "POST", path)
    body: Dict[str, Any] = {
        "ticker": ticker,
        "action": "buy",
        "side": side,
        "count": count,
        "type": "limit",
        "time_in_force": "fill_or_kill",
    }
    if side == "yes":
        body["yes_price"] = price_cents
    else:
        body["no_price"] = price_cents

    resp = requests.post(
        f"{KALSHI_API_URL}{path}", headers=headers, json=body, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Arb scanner (sync)
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize_title(title: str) -> set:
    stop = {"will", "the", "a", "an", "be", "by", "in", "on", "to", "of", "is", "at"}
    words = set(_WORD_RE.findall(title.lower())) - stop
    return words


def _fuzzy_match_titles(
    poly_markets: List[dict], kalshi_markets: List[dict], min_sim: int
) -> List[Tuple[dict, dict, int]]:
    threshold = min_sim / 100.0
    kalshi_indexed = [
        ({**m}, _normalize_title(m.get("title", ""))) for m in kalshi_markets
    ]
    matches: List[Tuple[dict, dict, int]] = []
    for pm in poly_markets:
        pw = _normalize_title(pm.get("question", "") or pm.get("title", ""))
        if len(pw) < 2:
            continue
        for km, kw in kalshi_indexed:
            if len(kw) < 2:
                continue
            intersection = pw & kw
            union = pw | kw
            jaccard = len(intersection) / len(union) if union else 0
            if jaccard >= threshold:
                matches.append((pm, km, int(jaccard * 100)))
    return matches


def _get_polymarket_price_sync(
    data_headers: Dict[str, str], token_id: str
) -> Optional[float]:
    try:
        resp = requests.get(
            f"{PREDEXON_DATA_URL}/polymarket/price",
            headers=data_headers,
            params={"token_id": token_id},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return float(resp.json().get("price", 0))
    except Exception:
        return None


def _scan_arb_opportunities_sync(
    conn: sqlite3.Connection,
    data_headers: Dict[str, str],
    trade_headers: Dict[str, str],
    user_id: str,
    kalshi_key: str,
    kalshi_pk: Any,
    controls: Dict[str, str],
) -> int:
    min_spread_pct = float(controls.get("tb_arb_min_spread_pct", "5.0"))
    min_similarity = int(float(controls.get("tb_arb_min_similarity", "95")))
    max_per_leg = float(controls.get("tb_arb_max_per_leg", "25"))
    poly_fee_rate = float(controls.get("tb_arb_poly_fee_pct", "3.15")) / 100.0
    kalshi_fee_rate = float(controls.get("tb_arb_kalshi_fee_pct", "7.0")) / 100.0

    # --- Source 1: Predexon matched pairs ---
    pairs: List[Tuple[str, str, str, int]] = []  # (poly_cid, kalshi_ticker, title, sim)
    try:
        resp = requests.get(
            f"{PREDEXON_DATA_URL}/matching-markets/pairs",
            headers=data_headers,
            params={
                "min_similarity": min_similarity,
                "active_only": "true",
                "limit": 50,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            for p in resp.json().get("pairs", []):
                poly_cid = p.get("polymarket_condition_id", "")
                k_ticker = p.get("kalshi_ticker", "")
                if poly_cid and k_ticker:
                    pairs.append((
                        poly_cid, k_ticker,
                        p.get("title", ""),
                        int(p.get("similarity", 95)),
                    ))
            _log(f"ARB: {len(pairs)} Predexon matched pairs")
    except Exception as exc:
        _log(f"ARB: Predexon pairs error: {exc}")

    # --- Source 2: Fuzzy-matched from DB + Kalshi ---
    kalshi_markets = _fetch_kalshi_active_markets_sync(kalshi_pk, kalshi_key)
    poly_rows = []
    try:
        cur = conn.execute(
            """SELECT condition_id, question, token_id
               FROM polymarket_markets
               WHERE active = 1
               ORDER BY volume_24h DESC LIMIT 100"""
        )
        poly_rows = [
            {"condition_id": r[0], "question": r[1], "token_id": r[2]}
            for r in cur.fetchall()
        ]
    except Exception:
        pass

    if poly_rows and kalshi_markets:
        fuzzy = _fuzzy_match_titles(poly_rows, kalshi_markets, min_similarity)
        seen = {(p[0], p[1]) for p in pairs}
        for pm, km, sim in fuzzy:
            key = (pm["condition_id"], km["ticker"])
            if key not in seen:
                pairs.append((pm["condition_id"], km["ticker"], km["title"], sim))
                seen.add(key)
        _log(f"ARB: {len(fuzzy)} fuzzy matches, {len(pairs)} total pairs")

    if not pairs:
        return 0

    # --- Evaluate each pair ---
    executed = 0
    poly_balance = _get_balance_sync(trade_headers, user_id)
    kalshi_balance = _get_kalshi_balance_sync(kalshi_pk, kalshi_key)
    _log(f"ARB: balances — Poly ${poly_balance:.2f}, Kalshi ${kalshi_balance:.2f}")

    for poly_cid, k_ticker, title, sim in pairs:
        # Fetch Kalshi price
        k_data = _kalshi_get_sync(
            kalshi_pk, kalshi_key, f"/trade-api/v2/markets/{k_ticker}"
        )
        if not k_data or not k_data.get("market"):
            continue
        k_market = k_data["market"]
        k_yes = float(k_market.get("yes_ask", 0)) / 100.0
        k_no = float(k_market.get("no_ask", 0)) / 100.0
        if k_yes <= 0 or k_no <= 0:
            continue

        # Fetch Poly price via condition_id token lookup
        p_price = None
        try:
            cur = conn.execute(
                "SELECT token_id FROM polymarket_markets WHERE condition_id = ? LIMIT 1",
                (poly_cid,),
            )
            row = cur.fetchone()
            if row:
                p_price = _get_polymarket_price_sync(data_headers, row[0])
        except Exception:
            pass
        if not p_price or p_price <= 0:
            continue

        # Direction A: buy YES on Poly + buy NO on Kalshi
        spread_a = 1.0 - p_price - k_no
        fee_a = p_price * poly_fee_rate + k_no * kalshi_fee_rate
        net_a = spread_a - fee_a

        # Direction B: buy NO on Poly + buy YES on Kalshi
        p_no = 1.0 - p_price  # complement price
        spread_b = 1.0 - p_no - k_yes
        fee_b = p_no * poly_fee_rate + k_yes * kalshi_fee_rate
        net_b = spread_b - fee_b

        # Pick best direction
        if net_a >= net_b:
            net_profit, direction = net_a, "poly_yes_kalshi_no"
            poly_leg_price, kalshi_leg_price = p_price, k_no
            kalshi_side = "no"
        else:
            net_profit, direction = net_b, "poly_no_kalshi_yes"
            poly_leg_price, kalshi_leg_price = p_no, k_yes
            kalshi_side = "yes"

        total_cost = poly_leg_price + kalshi_leg_price
        spread_pct = (net_profit / total_cost * 100) if total_cost > 0 else 0

        # Record detection regardless
        conn.execute(
            """INSERT INTO brain_arb_opportunities
               (detected_at, poly_condition_id, kalshi_ticker, title, similarity,
                poly_price, kalshi_price, spread, spread_after_fees, direction, action, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'detected', ?)""",
            (
                now_iso(), poly_cid, k_ticker, title[:200], sim,
                poly_leg_price, kalshi_leg_price,
                round(1.0 - total_cost, 4), round(net_profit, 4),
                direction, f"spread_pct={spread_pct:.1f}%",
            ),
        )
        conn.commit()

        if spread_pct < min_spread_pct:
            continue

        # --- Risk gate ---
        leg_size = min(max_per_leg, poly_balance * 0.25, kalshi_balance * 0.25)
        if leg_size < 1.0:
            _log(f"ARB: skip '{title[:40]}' — insufficient balance for leg")
            continue
        allowed, reason = _check_risk_gate(conn, controls, leg_size)
        if not allowed:
            _log(f"ARB: blocked '{title[:40]}' — {reason}")
            continue

        _log(
            f"ARB: EXECUTE '{title[:40]}' spread={spread_pct:.1f}% "
            f"${leg_size:.0f}/leg {direction}"
        )

        # --- Execute Poly leg ---
        poly_order_id = ""
        poly_ok = False
        try:
            token_row = conn.execute(
                "SELECT token_id FROM polymarket_markets WHERE condition_id = ? LIMIT 1",
                (poly_cid,),
            ).fetchone()
            if not token_row:
                continue
            poly_side = "buy"  # always buying
            result = _place_order_sync(
                trade_headers, user_id, token_row[0],
                poly_side, leg_size, poly_leg_price,
            )
            poly_order_id = result.get("orderId", "")
            poly_ok = True
        except Exception as exc:
            _log(f"ARB: Poly order failed: {exc}")

        # --- Execute Kalshi leg ---
        kalshi_order_id = ""
        kalshi_ok = False
        if poly_ok:
            try:
                count = max(1, int(leg_size / kalshi_leg_price))
                price_cents = int(kalshi_leg_price * 100)
                result = _place_kalshi_order_sync(
                    kalshi_pk, kalshi_key, k_ticker,
                    kalshi_side, count, price_cents,
                )
                kalshi_order_id = result.get("order", {}).get("order_id", "")
                kalshi_ok = True
            except Exception as exc:
                _log(f"ARB: Kalshi order failed: {exc}")
                _notify_imessage(
                    f"ARB PARTIAL: Poly leg filled but Kalshi failed on "
                    f"'{title[:40]}' — manual intervention needed"
                )

        action = "executed" if (poly_ok and kalshi_ok) else (
            "partial" if poly_ok else "skipped"
        )

        conn.execute(
            """UPDATE brain_arb_opportunities
               SET action = ?, poly_size_usd = ?, kalshi_size_usd = ?,
                   poly_order_id = ?, kalshi_order_id = ?, notes = ?
               WHERE id = (
                   SELECT id FROM brain_arb_opportunities
                   WHERE poly_condition_id = ? AND kalshi_ticker = ?
                     AND action = 'detected'
                   ORDER BY id DESC LIMIT 1
               )""",
            (
                action, leg_size if poly_ok else 0, leg_size if kalshi_ok else 0,
                poly_order_id, kalshi_order_id,
                f"spread_pct={spread_pct:.1f}% {action}",
                poly_cid, k_ticker,
            ),
        )
        conn.commit()

        if poly_ok and kalshi_ok:
            executed += 1
            _notify_imessage(
                f"ARB: ${net_profit * leg_size / kalshi_leg_price:.2f} spread on "
                f"'{title[:40]}' — {direction.replace('_', ' ')}"
            )

    _log(f"ARB: scan complete — {len(pairs)} pairs, {executed} executed")
    return executed


# ---------------------------------------------------------------------------
# WSS connection
# ---------------------------------------------------------------------------
async def _connect_wss(api_key: str):
    url = f"{PREDEXON_WSS_URL}/{api_key}"
    ws = await websockets.connect(url, ping_interval=20, ping_timeout=30)
    return ws


async def _subscribe_markets(ws, condition_ids: List[str]) -> None:
    if not condition_ids:
        return
    msg = {
        "action": "subscribe",
        "platform": "polymarket",
        "version": 1,
        "type": "orders",
        "filters": {"condition_ids": condition_ids},
    }
    await ws.send(json.dumps(msg))
    _log(f"Subscribed to {len(condition_ids)} markets")


async def _unsubscribe_all(ws) -> None:
    msg = {
        "action": "unsubscribe",
        "platform": "polymarket",
        "version": 1,
        "type": "orders",
        "filters": {"condition_ids": ["*"]},
    }
    try:
        await ws.send(json.dumps(msg))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main daemon loop
# ---------------------------------------------------------------------------
async def run_daemon() -> None:
    _log("trader_brain starting...")

    keys = _load_api_keys()
    data_api_key = keys["data_api_key"]
    data_headers = {"x-api-key": data_api_key}
    trade_headers = {"x-api-key": keys["trading_api_key"]}

    conn = _connect_db()
    _ensure_tables(conn)

    from execution_guard import init_controls
    init_controls(conn)

    loop = asyncio.get_running_loop()

    user_id = await loop.run_in_executor(
        _executor, _setup_predexon_user_sync, trade_headers
    )
    balance = await loop.run_in_executor(
        _executor, _get_balance_sync, trade_headers, user_id
    )
    _log(f"Predexon balance: ${balance:.2f}")

    # Load Kalshi keys for arb scanner
    kalshi_keys: Optional[Dict[str, Any]] = None
    try:
        kalshi_keys = _load_kalshi_keys()
        k_bal = await loop.run_in_executor(
            _executor, _get_kalshi_balance_sync,
            kalshi_keys["private_key"], kalshi_keys["api_key_id"],
        )
        _log(f"Kalshi balance: ${k_bal:.2f}")
    except Exception as exc:
        _log(f"Kalshi keys not loaded (arb disabled): {exc}")

    shutdown = asyncio.Event()

    def _sig_handler(sig, _frame):
        _log(f"Received {signal.Signals(sig).name}, shutting down...")
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: _sig_handler(s, None))

    backoff = 1
    current_markets: List[str] = []
    last_market_refresh = 0.0
    last_control_refresh = 0.0
    last_cache_evict = 0.0
    last_arb_scan = 0.0
    controls = _load_tb_controls(conn)

    signals_seen = 0
    trades_executed = 0

    while not shutdown.is_set():
        ws = None
        try:
            ws = await _connect_wss(data_api_key)
            _log("WSS connected")

            first_msg = await asyncio.wait_for(ws.recv(), timeout=10)
            first = json.loads(first_msg)
            if first.get("type") == "connected":
                _log(f"WSS handshake OK: {first.get('message', '')}")

            current_markets = await loop.run_in_executor(
                _executor, _get_smart_activity_markets_sync, data_headers
            )
            if not current_markets:
                _log("WARNING: no smart-activity markets found, retrying in 60s")
                await asyncio.sleep(60)
                continue

            await _subscribe_markets(ws, current_markets)
            last_market_refresh = _ts()
            backoff = 1

            while not shutdown.is_set():
                now = _ts()

                if now - last_control_refresh > 60:
                    controls = _load_tb_controls(conn)
                    last_control_refresh = now
                    if controls.get("tb_enabled", "1") != "1":
                        _log("Kill switch active (tb_enabled=0), pausing...")
                        await asyncio.sleep(10)
                        continue

                if now - last_cache_evict > 600:
                    _evict_stale_cache()
                    last_cache_evict = now

                if (
                    now - last_arb_scan > 300
                    and kalshi_keys
                    and controls.get("tb_arb_enabled", "1") == "1"
                ):
                    try:
                        arb_count = await loop.run_in_executor(
                            _executor,
                            _scan_arb_opportunities_sync,
                            conn, data_headers, trade_headers, user_id,
                            kalshi_keys["api_key_id"],
                            kalshi_keys["private_key"],
                            controls,
                        )
                        if arb_count > 0:
                            _log(f"ARB: executed {arb_count} opportunities")
                    except Exception as exc:
                        _log(f"ARB scan error: {exc}")
                    last_arb_scan = now

                if now - last_market_refresh > 300:
                    new_markets = await loop.run_in_executor(
                        _executor, _get_smart_activity_markets_sync, data_headers
                    )
                    if new_markets and new_markets != current_markets:
                        await _unsubscribe_all(ws)
                        current_markets = new_markets
                        await _subscribe_markets(ws, current_markets)
                        _log(f"Rotated to {len(current_markets)} markets")
                    last_market_refresh = now

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "error":
                    _log(f"WSS error: {msg.get('code')} — {msg.get('message')}")
                    continue

                if msg_type != "event":
                    continue

                event_data = msg.get("data") or {}
                event_type = str(
                    event_data.get("type") or msg.get("event_type") or ""
                )

                if event_type != "order_filled":
                    continue

                signals_seen += 1
                try:
                    executed = await loop.run_in_executor(
                        _executor,
                        _handle_fill_sync,
                        event_data, conn, data_headers, trade_headers,
                        user_id, controls,
                    )
                    if executed:
                        trades_executed += 1
                except Exception as exc:
                    sanitized = str(exc).replace(data_api_key, "***")
                    _log(f"handle_fill error: {sanitized}")

        except ConnectionClosed as exc:
            _log(f"WSS disconnected: code={exc.code}")
        except Exception as exc:
            sanitized = str(exc).replace(data_api_key, "***")
            _log(f"WSS error: {sanitized}")
        finally:
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass

        if not shutdown.is_set():
            _log(f"Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    conn.close()
    _executor.shutdown(wait=False)
    _log(f"Shutdown complete. signals={signals_seen} trades={trades_executed}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
