#!/usr/bin/env python3
"""
Execution adapters for broker/exchange actions used by execution_worker.
Alpaca orders are real paper orders.
Hyperliquid supports signed market execution when enabled by controls.
"""

import json
import sqlite3
from datetime import datetime, timezone
from decimal import ROUND_UP, Decimal
from pathlib import Path
from typing import Dict, Tuple

import requests

try:
    from eth_account import Account
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    HL_DEPS_OK = True
except Exception:
    Account = None  # type: ignore[assignment]
    Exchange = None  # type: ignore[assignment]
    Info = None  # type: ignore[assignment]
    HL_DEPS_OK = False

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "trades.db"
ENV_PATH = BASE_DIR / ".env"

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
HL_API_URL = "https://api.hyperliquid.xyz"

# Keep this list tight to symbols we are likely to route from event/sentiment.
HL_ELIGIBLE = {
    "BTC",
    "ETH",
    "SOL",
    "DOGE",
    "XRP",
    "AVAX",
    "BNB",
    "LTC",
    "SUI",
    "HYPE",
}


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


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_intents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT,
          venue TEXT,
          symbol TEXT,
          side TEXT,
          qty REAL,
          notional REAL,
          status TEXT,
          details TEXT
        )
        """
    )
    conn.commit()
    return conn


def record_intent(
    venue: str,
    symbol: str,
    side: str,
    qty: float,
    notional: float,
    status: str,
    details: Dict,
) -> int:
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO trade_intents
            (created_at, venue, symbol, side, qty, notional, status, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), venue, symbol, side, float(qty), float(notional), status, json.dumps(details)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def alpaca_submit_notional(symbol: str, side: str, notional: float) -> Tuple[bool, str, Dict]:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not api_key or not secret:
        return False, "missing Alpaca credentials", {}

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    payload = {
        "symbol": symbol.upper(),
        "notional": round(float(notional), 2),
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    try:
        res = requests.post(f"{base_url}/v2/orders", headers=headers, json=payload, timeout=20)
    except Exception as exc:
        return False, f"alpaca request error: {exc}", {}

    if res.status_code >= 400:
        body: Dict = {}
        try:
            body = res.json() if res.text else {}
        except Exception:
            body = {}
        existing_id = str(body.get("existing_order_id") or "").strip()
        if res.status_code == 403 and existing_id:
            # Idempotent behavior: treat duplicate/pending replace as reused order, not a hard failure.
            return True, "reused existing open order", {"id": existing_id, "reused": True}
        msg = res.text[:240]
        return False, f"alpaca error {res.status_code}: {msg}", body if isinstance(body, dict) else {}
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text[:240]}
    return True, "submitted", data


def alpaca_latest_price(symbol: str) -> Tuple[bool, str, float]:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        return False, "missing Alpaca credentials", 0.0
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    # v2 stocks latest trade endpoint.
    url = f"https://data.alpaca.markets/v2/stocks/{symbol.upper()}/trades/latest"
    try:
        res = requests.get(url, headers=headers, timeout=20)
    except Exception as exc:
        return False, f"alpaca latest price error: {exc}", 0.0
    if res.status_code >= 400:
        return False, f"alpaca latest price http {res.status_code}", 0.0
    try:
        data = res.json()
    except Exception:
        return False, "alpaca latest price parse error", 0.0
    trade = data.get("trade", {}) if isinstance(data, dict) else {}
    px = float(trade.get("p", 0.0) or 0.0)
    if px <= 0:
        return False, "latest price unavailable", 0.0
    return True, "ok", px


def alpaca_submit_qty(symbol: str, side: str, qty: int) -> Tuple[bool, str, Dict]:
    env = load_env()
    api_key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not api_key or not secret:
        return False, "missing Alpaca credentials", {}

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    payload = {
        "symbol": symbol.upper(),
        "qty": int(max(1, qty)),
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    try:
        res = requests.post(f"{base_url}/v2/orders", headers=headers, json=payload, timeout=20)
    except Exception as exc:
        return False, f"alpaca request error: {exc}", {}

    if res.status_code >= 400:
        body: Dict = {}
        try:
            body = res.json() if res.text else {}
        except Exception:
            body = {}
        existing_id = str(body.get("existing_order_id") or "").strip()
        if res.status_code == 403 and existing_id:
            return True, "reused existing open order", {"id": existing_id, "reused": True}
        msg = res.text[:240]
        return False, f"alpaca error {res.status_code}: {msg}", body if isinstance(body, dict) else {}
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text[:240]}
    return True, "submitted", data


def is_hl_eligible(symbol: str) -> bool:
    return symbol.upper() in HL_ELIGIBLE


def _fetch_hl_universe() -> Tuple[bool, str, set]:
    try:
        res = requests.post(HL_INFO_URL, json={"type": "meta"}, timeout=15)
    except Exception as exc:
        return False, f"hyperliquid meta request failed: {exc}", set()
    if res.status_code >= 400:
        return False, f"hyperliquid meta error {res.status_code}", set()
    try:
        data = res.json()
    except Exception:
        return False, "hyperliquid meta invalid json", set()
    universe = data.get("universe", []) if isinstance(data, dict) else []
    names = {str(x.get("name", "")).upper() for x in universe if isinstance(x, dict)}
    return True, "ok", names


def hyperliquid_test_intent(symbol: str, side: str, notional_usd: float) -> Tuple[bool, str, Dict]:
    """
    Intentionally records a $-sized test intent and verifies asset availability.
    Signed live order flow should be added as a separate guarded step.
    """
    symbol = symbol.upper()
    ok, msg, universe = _fetch_hl_universe()
    if not ok:
        details = {"symbol": symbol, "notional_usd": notional_usd, "reason": msg}
        intent_id = record_intent("hyperliquid", symbol, side, 0.0, float(notional_usd), "failed", details)
        return False, "hl meta unavailable", {"intent_id": intent_id, **details}

    listed = symbol in universe
    status = "queued" if listed else "rejected"
    reason = "asset available; intent queued (signed execution not wired)" if listed else "asset not listed on HL"
    details = {
        "symbol": symbol,
        "notional_usd": round(float(notional_usd), 2),
        "listed_on_hl": listed,
        "reason": reason,
    }
    intent_id = record_intent("hyperliquid", symbol, side, 0.0, float(notional_usd), status, details)
    return listed, reason, {"intent_id": intent_id, **details}


def hyperliquid_submit_notional_live(symbol: str, side: str, notional_usd: float) -> Tuple[bool, str, Dict]:
    """
    Signed live order submission on Hyperliquid using API wallet key.
    """
    env = load_env()
    private_key = env.get("HL_AGENT_PRIVATE_KEY")
    account_address = env.get("HL_WALLET_ADDRESS")
    symbol = symbol.upper()
    if not HL_DEPS_OK:
        details = {
            "symbol": symbol,
            "notional_usd": notional_usd,
            "reason": "missing dependencies: eth_account/hyperliquid",
        }
        intent_id = record_intent("hyperliquid", symbol, side, 0.0, float(notional_usd), "failed", details)
        return False, "hyperliquid dependencies not installed (eth_account/hyperliquid)", {"intent_id": intent_id, **details}
    if not private_key:
        return False, "missing HL_AGENT_PRIVATE_KEY", {}

    try:
        wallet = Account.from_key(private_key)
    except Exception as exc:
        return False, f"invalid HL private key: {exc}", {}

    try:
        info = Info(base_url=HL_API_URL, skip_ws=True, timeout=15)
        mids = info.all_mids()
        mid = float(mids.get(symbol, 0) or 0)
        meta = info.meta()
    except Exception as exc:
        details = {"symbol": symbol, "notional_usd": notional_usd, "reason": str(exc)}
        intent_id = record_intent("hyperliquid", symbol, side, 0.0, float(notional_usd), "failed", details)
        return False, f"failed to fetch HL market data: {exc}", {"intent_id": intent_id, **details}

    if mid <= 0:
        details = {"symbol": symbol, "notional_usd": notional_usd, "reason": "no mid price"}
        intent_id = record_intent("hyperliquid", symbol, side, 0.0, float(notional_usd), "failed", details)
        return False, f"no mid price for {symbol}", {"intent_id": intent_id, **details}

    sz_decimals = 5
    for asset in (meta.get("universe", []) if isinstance(meta, dict) else []):
        if str(asset.get("name", "")).upper() == symbol:
            sz_decimals = int(asset.get("szDecimals", 5))
            break

    # Round UP to valid size precision so tiny notionals do not underflow to 0.
    raw_size = Decimal(str(float(notional_usd) / mid))
    quantum = Decimal(10) ** Decimal(-sz_decimals)
    size = float(raw_size.quantize(quantum, rounding=ROUND_UP))

    if size <= 0:
        details = {"symbol": symbol, "notional_usd": notional_usd, "reason": "computed size <= 0", "sz_decimals": sz_decimals}
        intent_id = record_intent("hyperliquid", symbol, side, 0.0, float(notional_usd), "failed", details)
        return False, "computed size <= 0", {"intent_id": intent_id, **details}

    is_buy = side.lower() in {"buy", "long"}
    try:
        exchange = Exchange(
            wallet=wallet,
            base_url=HL_API_URL,
            account_address=account_address or None,
            timeout=20,
        )
        order_result = exchange.market_open(
            name=symbol,
            is_buy=is_buy,
            sz=size,
            slippage=0.05,
        )
    except Exception as exc:
        details = {
            "symbol": symbol,
            "notional_usd": notional_usd,
            "size": size,
            "mid": mid,
            "sz_decimals": sz_decimals,
            "reason": str(exc),
        }
        intent_id = record_intent("hyperliquid", symbol, side, size, float(notional_usd), "failed", details)
        return False, f"HL order submit failed: {exc}", {"intent_id": intent_id, **details}

    # Parse exchange response for embedded order errors.
    statuses = (
        ((order_result or {}).get("response") or {}).get("data") or {}
    ).get("statuses", [])
    embedded_errors = []
    for st in statuses:
        if isinstance(st, dict) and st.get("error"):
            embedded_errors.append(str(st.get("error")))
    if embedded_errors:
        # Persist explicit failed intent with exchange-side validation error.
        fail_details = {
            "symbol": symbol,
            "notional_usd": notional_usd,
            "size": size,
            "mid": mid,
            "error": "; ".join(embedded_errors),
            "live_order_result": order_result,
        }
        fail_intent_id = record_intent("hyperliquid", symbol, side, size, float(notional_usd), "failed", fail_details)
        return False, f"HL exchange rejected order: {embedded_errors[0]}", {"intent_id": fail_intent_id, "result": order_result}

    # Persist intent snapshot for successful submit path.
    intent_id = record_intent(
        venue="hyperliquid",
        symbol=symbol,
        side="buy" if is_buy else "sell",
        qty=size,
        notional=float(notional_usd),
        status="submitted",
        details={"live_order_result": order_result, "mid": mid},
    )
    return True, "submitted", {"intent_id": intent_id, "mid": mid, "size": size, "result": order_result}
