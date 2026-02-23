import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DASH_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DB_PATH = BASE_DIR / "data" / "trades.db"
STATE_PATH = DASH_DIR / "runtime-state.json"

DEFAULT_STATE = {
    "mode": "paper",
    "max_trade_notional": 100.0,
    "max_open_positions": 5,
    "daily_loss_limit": 200.0,
    "allow_hl_live": False,
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


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        save_state(DEFAULT_STATE)
        return dict(DEFAULT_STATE)
    try:
        data = json.loads(STATE_PATH.read_text())
    except Exception:
        save_state(DEFAULT_STATE)
        return dict(DEFAULT_STATE)
    merged = dict(DEFAULT_STATE)
    merged.update(data)
    return merged


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def _db_conn() -> sqlite3.Connection:
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


def _record_intent(venue: str, symbol: str, side: str, qty: float, notional: float, status: str, details: Dict[str, Any]) -> int:
    conn = _db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO trade_intents (created_at, venue, symbol, side, qty, notional, status, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), venue, symbol, side, qty, notional, status, json.dumps(details)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _alpaca_submit(env: Dict[str, str], symbol: str, side: str, qty: float) -> Dict[str, Any]:
    api_key = env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_SECRET_KEY")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not api_key or not secret:
        raise RuntimeError("Missing Alpaca credentials")

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    payload = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    res = requests.post(f"{base_url}/v2/orders", headers=headers, json=payload, timeout=15)
    if res.status_code >= 400:
        raise RuntimeError(f"Alpaca error {res.status_code}: {res.text[:300]}")
    return res.json()


def submit_order(venue: str, symbol: str, side: str, qty: float, price_hint: float | None = None) -> Dict[str, Any]:
    state = load_state()
    env = load_env()

    if venue not in ("alpaca", "hyperliquid"):
        raise ValueError("Unsupported venue")
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy/sell")
    if qty <= 0:
        raise ValueError("qty must be > 0")

    estimated_notional = qty * (price_hint or 1.0)
    if estimated_notional > float(state["max_trade_notional"]):
        raise ValueError("order exceeds max_trade_notional cap")

    if venue == "alpaca":
        order = _alpaca_submit(env, symbol, side, qty)
        intent_id = _record_intent(
            venue="alpaca",
            symbol=symbol,
            side=side,
            qty=qty,
            notional=estimated_notional,
            status="submitted",
            details={"alpaca_order_id": order.get("id"), "mode": state["mode"]},
        )
        return {
            "intent_id": intent_id,
            "status": "submitted",
            "venue": "alpaca",
            "order": order,
        }

    # Hyperliquid execution adapter placeholder: record intent and fail closed.
    # This avoids accidental live execution until signed order flow is wired.
    intent_id = _record_intent(
        venue="hyperliquid",
        symbol=symbol,
        side=side,
        qty=qty,
        notional=estimated_notional,
        status="queued",
        details={
            "reason": "HL signed execution not yet wired",
            "wallet": env.get("HL_WALLET_ADDRESS", ""),
            "allow_hl_live": bool(state.get("allow_hl_live", False)),
        },
    )
    return {
        "intent_id": intent_id,
        "status": "queued",
        "venue": "hyperliquid",
        "message": "Recorded intent only. Hyperliquid signed order flow not wired yet.",
    }
