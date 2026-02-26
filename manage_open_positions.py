#!/usr/bin/env python3
"""
Build position-awareness snapshots and management intents for live open positions.

Current focus:
- Hyperliquid perp positions (primary concern raised by user)
- Stores awareness snapshots for auditability
- Emits manage_* intents when action is needed (take profit / tighten / cut)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "trades.db"
ENV_PATH = BASE_DIR / ".env"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip()
    for k, v in os.environ.items():
        if v is not None:
            env[k] = v
    return env


def _is_true(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _hl_info_url(env: Dict[str, str]) -> str:
    api_url = str(env.get("HL_API_URL", "") or "").strip().rstrip("/")
    if not api_url:
        if _is_true(env.get("HL_USE_TESTNET", "0")):
            api_url = "https://api.hyperliquid-testnet.xyz"
        else:
            api_url = "https://api.hyperliquid.xyz"
    info = str(env.get("HL_INFO_URL", "") or "").strip().rstrip("/")
    if info:
        return info
    return f"{api_url}/info"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _load_manage_controls(conn: sqlite3.Connection) -> Dict[str, float]:
    cfg: Dict[str, float] = {
        "position_take_profit_major_pct": 25.0,
        "position_take_profit_major_usd": 250.0,
        "position_take_profit_partial_pct": 12.0,
        "position_take_profit_partial_usd": 100.0,
        "position_trail_start_pct": 6.0,
        "position_trailing_stop_gap_pct": 2.5,
        "position_stop_loss_pct": 5.0,
        "position_manage_intent_cooldown_hours": 6.0,
    }
    if not _table_exists(conn, "execution_controls"):
        return cfg
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    for key, value in cur.fetchall():
        k = str(key or "")
        if k in cfg:
            cfg[k] = _as_float(value, cfg[k])
    return cfg


def _ensure_tables(conn: sqlite3.Connection) -> None:
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS position_awareness_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          venue TEXT NOT NULL,
          symbol TEXT NOT NULL,
          side TEXT NOT NULL,
          qty REAL NOT NULL DEFAULT 0,
          entry_price REAL NOT NULL DEFAULT 0,
          mark_price REAL NOT NULL DEFAULT 0,
          notional_usd REAL NOT NULL DEFAULT 0,
          unrealized_pnl_usd REAL NOT NULL DEFAULT 0,
          unrealized_pnl_pct REAL NOT NULL DEFAULT 0,
          action TEXT NOT NULL DEFAULT '',
          confidence REAL NOT NULL DEFAULT 0,
          reason TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pos_awareness_recent ON position_awareness_snapshots(created_at DESC, venue, symbol)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_intents_manage ON trade_intents(created_at DESC, venue, symbol, status)"
    )
    conn.commit()


def _recent_manage_intent_exists(
    conn: sqlite3.Connection,
    venue: str,
    symbol: str,
    status: str,
    within_hours: int,
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM trade_intents
        WHERE venue=?
          AND symbol=?
          AND status=?
          AND datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', ?)
        """,
        (venue, symbol, status, f"-{int(within_hours)} hour"),
    )
    return int((cur.fetchone() or [0])[0] or 0) > 0


def _record_manage_intent(
    conn: sqlite3.Connection,
    venue: str,
    symbol: str,
    side: str,
    qty: float,
    notional: float,
    status: str,
    details: Dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO trade_intents
        (created_at, venue, symbol, side, qty, notional, status, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            venue,
            symbol,
            side,
            float(qty),
            float(notional),
            status,
            json.dumps(details, separators=(",", ":"), ensure_ascii=True),
        ),
    )


def _pick_action(upnl_pct: float, upnl_usd: float, cfg: Dict[str, float]) -> Tuple[str, float, str]:
    major_pct = float(cfg.get("position_take_profit_major_pct", 25.0))
    major_usd = float(cfg.get("position_take_profit_major_usd", 250.0))
    partial_pct = float(cfg.get("position_take_profit_partial_pct", 12.0))
    partial_usd = float(cfg.get("position_take_profit_partial_usd", 100.0))
    trail_start_pct = float(cfg.get("position_trail_start_pct", 6.0))
    stop_loss_pct = abs(float(cfg.get("position_stop_loss_pct", 5.0)))

    if upnl_pct >= major_pct or upnl_usd >= major_usd:
        return "take_profit_major", 0.92, "lock in large winner"
    if upnl_pct >= partial_pct or upnl_usd >= partial_usd:
        return "take_profit_partial", 0.84, "winner at meaningful profit, de-risk"
    if upnl_pct >= trail_start_pct:
        return "trail_stop_tighten", 0.74, "winner building, tighten risk"
    if upnl_pct <= -stop_loss_pct:
        return "reduce_or_exit", 0.86, "losing position beyond risk limit"
    return "hold_monitor", 0.55, "within normal range, keep monitoring"


def _fetch_hl_positions(env: Dict[str, str], cfg: Dict[str, float]) -> Tuple[bool, str, List[Dict[str, Any]]]:
    wallet = str(env.get("HL_WALLET_ADDRESS", "") or "").strip()
    if not wallet:
        return False, "HL_WALLET_ADDRESS missing", []

    info_url = _hl_info_url(env)
    payload = {"type": "clearinghouseState", "user": wallet}
    try:
        res = requests.post(info_url, json=payload, timeout=20)
    except Exception as exc:
        return False, f"hyperliquid request error: {exc}", []
    if res.status_code >= 400:
        return False, f"hyperliquid info http {res.status_code}", []
    try:
        data = res.json()
    except Exception:
        return False, "hyperliquid info parse error", []

    out: List[Dict[str, Any]] = []
    for item in (data.get("assetPositions") or []):
        if not isinstance(item, dict):
            continue
        pos = item.get("position", {}) if isinstance(item.get("position"), dict) else {}
        coin = str(pos.get("coin") or "").upper().strip()
        if not coin:
            continue
        szi = float(pos.get("szi") or 0.0)
        if abs(szi) <= 1e-10:
            continue
        side = "long" if szi > 0 else "short"
        qty = abs(szi)
        entry_price = float(pos.get("entryPx") or 0.0)
        position_value = float(pos.get("positionValue") or 0.0)
        upnl_usd = float(pos.get("unrealizedPnl") or 0.0)
        mark_price = 0.0
        if qty > 0 and abs(position_value) > 0:
            mark_price = abs(position_value) / qty
        if mark_price <= 0:
            mark_price = float(pos.get("markPx") or 0.0)
        if mark_price <= 0:
            mark_price = float(pos.get("markPrice") or 0.0)

        upnl_pct = 0.0
        if entry_price > 0 and mark_price > 0:
            if side == "long":
                upnl_pct = ((mark_price - entry_price) / entry_price) * 100.0
            else:
                upnl_pct = ((entry_price - mark_price) / entry_price) * 100.0
        else:
            roe = float(pos.get("returnOnEquity") or 0.0)
            upnl_pct = roe * 100.0

        notional = abs(position_value) if abs(position_value) > 0 else (qty * mark_price)
        action, confidence, why = _pick_action(upnl_pct, upnl_usd, cfg)
        leverage = 1.0
        lev_raw = pos.get("leverage")
        if isinstance(lev_raw, dict):
            leverage = _as_float(lev_raw.get("value"), 1.0)
        elif lev_raw is not None:
            leverage = _as_float(lev_raw, 1.0)
        trailing_gap_pct = abs(float(cfg.get("position_trailing_stop_gap_pct", 2.5)))
        suggested_stop = 0.0
        if mark_price > 0 and trailing_gap_pct > 0:
            if side == "long":
                suggested_stop = mark_price * (1.0 - trailing_gap_pct / 100.0)
            else:
                suggested_stop = mark_price * (1.0 + trailing_gap_pct / 100.0)
        out.append(
            {
                "venue": "hyperliquid",
                "symbol": coin,
                "side": side,
                "qty": qty,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "notional_usd": notional,
                "unrealized_pnl_usd": upnl_usd,
                "unrealized_pnl_pct": upnl_pct,
                "leverage": leverage,
                "action": action,
                "confidence": confidence,
                "reason": why,
                "suggested_stop_price": suggested_stop,
            }
        )
    return True, "ok", out


def main() -> int:
    env = _load_env()
    conn = _connect()
    try:
        _ensure_tables(conn)
        cfg = _load_manage_controls(conn)
        ok, reason, rows = _fetch_hl_positions(env, cfg)
        if not ok:
            print(f"POSITION_AWARENESS: skipped reason={reason}")
            return 0

        snapshot_count = 0
        intent_count = 0
        cooldown_h = max(0, int(round(float(cfg.get("position_manage_intent_cooldown_hours", 6.0)))))
        for r in rows:
            conn.execute(
                """
                INSERT INTO position_awareness_snapshots
                (created_at, venue, symbol, side, qty, entry_price, mark_price, notional_usd, unrealized_pnl_usd, unrealized_pnl_pct, action, confidence, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    r["venue"],
                    r["symbol"],
                    r["side"],
                    float(r["qty"]),
                    float(r["entry_price"]),
                    float(r["mark_price"]),
                    float(r["notional_usd"]),
                    float(r["unrealized_pnl_usd"]),
                    float(r["unrealized_pnl_pct"]),
                    r["action"],
                    float(r["confidence"]),
                    r["reason"],
                ),
            )
            snapshot_count += 1

            action = str(r.get("action") or "")
            if action in {"take_profit_major", "take_profit_partial", "trail_stop_tighten", "reduce_or_exit"}:
                status = f"manage_{action}"
                if cooldown_h > 0 and _recent_manage_intent_exists(
                    conn,
                    "hyperliquid",
                    str(r["symbol"]),
                    status,
                    within_hours=cooldown_h,
                ):
                    continue
                details = {
                    "action": action,
                    "confidence": round(float(r["confidence"]), 4),
                    "reason": str(r["reason"]),
                    "pnl_pct": round(float(r["unrealized_pnl_pct"]), 4),
                    "upnl_usd": round(float(r["unrealized_pnl_usd"]), 4),
                    "entry_price": round(float(r["entry_price"]), 6),
                    "mark_price": round(float(r["mark_price"]), 6),
                    "leverage": round(float(r.get("leverage", 1.0) or 1.0), 4),
                    "suggested_stop_price": round(float(r.get("suggested_stop_price", 0.0) or 0.0), 6),
                    "configured_stop_loss_pct": round(float(cfg.get("position_stop_loss_pct", 5.0)), 4),
                    "configured_trail_start_pct": round(float(cfg.get("position_trail_start_pct", 6.0)), 4),
                    "configured_trailing_stop_gap_pct": round(float(cfg.get("position_trailing_stop_gap_pct", 2.5)), 4),
                    "generated_by": "manage_open_positions",
                }
                _record_manage_intent(
                    conn=conn,
                    venue="hyperliquid",
                    symbol=str(r["symbol"]),
                    side=str(r["side"]),
                    qty=float(r["qty"]),
                    notional=float(r["notional_usd"]),
                    status=status,
                    details=details,
                )
                intent_count += 1
        conn.commit()
        print(
            "POSITION_AWARENESS: "
            f"positions={len(rows)} snapshots={snapshot_count} manage_intents={intent_count} "
            f"tp_partial={cfg.get('position_take_profit_partial_pct', 12.0)}% "
            f"tp_major={cfg.get('position_take_profit_major_pct', 25.0)}% "
            f"trail_start={cfg.get('position_trail_start_pct', 6.0)}% "
            f"stop_loss={cfg.get('position_stop_loss_pct', 5.0)}%"
        )
        for r in rows[:12]:
            print(
                f" - {r['symbol']} {r['side']} qty={r['qty']:.6f} "
                f"uPnL=${r['unrealized_pnl_usd']:.2f} ({r['unrealized_pnl_pct']:.2f}%) "
                f"action={r['action']}"
            )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
