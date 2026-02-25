#!/usr/bin/env python3
"""
Polymarket execution worker.

Truth model:
- Candidates are ideas only.
- Orders are written only as explicit lifecycle events.
- Mode is explicit: paper vs live (real money).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from training_mode import apply_training_mode
try:
    from eth_account import Account
    ETH_ACCOUNT_AVAILABLE = True
except Exception:
    Account = None  # type: ignore[assignment]
    ETH_ACCOUNT_AVAILABLE = False

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, AssetType, BalanceAllowanceParams, OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY

    CLOB_AVAILABLE = True
except Exception:
    ClobClient = None  # type: ignore[assignment]
    ApiCreds = None  # type: ignore[assignment]
    AssetType = None  # type: ignore[assignment]
    BalanceAllowanceParams = None  # type: ignore[assignment]
    OrderArgs = None  # type: ignore[assignment]
    OrderType = None  # type: ignore[assignment]
    BUY = "BUY"
    CLOB_AVAILABLE = False


DB_PATH = Path(__file__).parent / "data" / "trades.db"
DEFAULT_HOST = "https://clob.polymarket.com"
BOOL_TRUE = {"1", "true", "yes", "on", "enabled", "live"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in BOOL_TRUE


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          strategy_id TEXT NOT NULL DEFAULT '',
          candidate_id INTEGER NOT NULL DEFAULT 0,
          market_id TEXT NOT NULL DEFAULT '',
          outcome TEXT NOT NULL DEFAULT '',
          side TEXT NOT NULL DEFAULT '',
          price REAL NOT NULL DEFAULT 0,
          size REAL NOT NULL DEFAULT 0,
          order_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'queued',
          notes TEXT NOT NULL DEFAULT '',
          route_id INTEGER NOT NULL DEFAULT 0,
          token_id TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL DEFAULT 'paper',
          notional REAL NOT NULL DEFAULT 0,
          response_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )

    # Backfill for older DBs.
    expected_columns = {
        "side": "TEXT NOT NULL DEFAULT ''",
        "route_id": "INTEGER NOT NULL DEFAULT 0",
        "token_id": "TEXT NOT NULL DEFAULT ''",
        "mode": "TEXT NOT NULL DEFAULT 'paper'",
        "notional": "REAL NOT NULL DEFAULT 0",
        "response_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    if _table_exists(conn, "polymarket_orders"):
        for col, spec in expected_columns.items():
            if not _column_exists(conn, "polymarket_orders", col):
                conn.execute(f"ALTER TABLE polymarket_orders ADD COLUMN {col} {spec}")
        # Normalize legacy status labels so dashboard semantics stay truthful.
        conn.execute(
            """
            UPDATE polymarket_orders
            SET status='submitted_paper',
                notes=CASE
                  WHEN notes LIKE '%paper%' THEN notes
                  ELSE 'legacy migrated: ' || notes
                END
            WHERE mode='paper' AND status='submitted'
            """
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_controls (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )

    defaults = {
        "enable_polymarket_auto": "0",
        "allow_polymarket_live": "0",
        "polymarket_max_notional_usd": "10",
        "polymarket_max_daily_exposure": "20",
        "polymarket_min_edge_pct": "5.0",
        "polymarket_min_confidence_pct": "60",
        "polymarket_fee_gate_enabled": "1",
        "polymarket_taker_fee_pct": "3.15",
        "polymarket_fee_buffer_pct": "0.50",
        "polymarket_copy_enabled": "1",
        "polymarket_arb_enabled": "1",
        "polymarket_alpha_enabled": "1",
        "polymarket_copy_max_notional_usd": "5",
        "polymarket_arb_max_notional_usd": "5",
        "polymarket_alpha_max_notional_usd": "5",
        "polymarket_manual_approval": "1",
        "polymarket_approval_threshold": "10",
        "polymarket_approval_count": "0",
        "polymarket_cycle_limit": "8",
        "polymarket_strict_funding_check": "0",
        "polymarket_edge_unit_mode": "auto",
        "threshold_override_unlocked": "0",
    }
    cur = conn.cursor()
    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO execution_controls (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now_iso()),
        )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_orders_candidate ON polymarket_orders(candidate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_orders_created ON polymarket_orders(created_at)")
    conn.commit()


def _load_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    return apply_training_mode({str(k): str(v) for k, v in cur.fetchall()})


def _load_runtime_env() -> Dict[str, str]:
    out = {
        "POLY_API_KEY": os.environ.get("POLY_API_KEY", ""),
        "POLY_API_SECRET": os.environ.get("POLY_API_SECRET", ""),
        "POLY_API_PASSPHRASE": os.environ.get("POLY_API_PASSPHRASE", ""),
        "POLY_PRIVATE_KEY": os.environ.get("POLY_PRIVATE_KEY", ""),
        "POLY_FUNDER": os.environ.get("POLY_FUNDER", "") or os.environ.get("HL_WALLET_ADDRESS", ""),
        "POLY_CLOB_HOST": os.environ.get("POLY_CLOB_HOST", DEFAULT_HOST),
        "POLY_SIGNATURE_TYPE": os.environ.get("POLY_SIGNATURE_TYPE", "0"),
    }
    return out


def _live_ready(env: Dict[str, str]) -> Tuple[bool, str]:
    if not CLOB_AVAILABLE:
        return False, "py-clob-client unavailable"
    required = ["POLY_API_KEY", "POLY_API_SECRET", "POLY_API_PASSPHRASE", "POLY_PRIVATE_KEY", "POLY_FUNDER"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        return False, f"missing credentials: {','.join(missing)}"
    return True, "ok"


def _cli_available() -> bool:
    probe = subprocess.run(["bash", "-lc", "command -v polymarket || command -v polymarket-cli || true"], capture_output=True, text=True)
    return bool((probe.stdout or "").strip())


def _live_ready_cli(env: Dict[str, str]) -> Tuple[bool, str]:
    if not _cli_available():
        return False, "polymarket CLI binary unavailable"
    if not str(env.get("POLY_PRIVATE_KEY", "") or "").strip():
        return False, "missing POLY_PRIVATE_KEY for CLI signing"
    return True, "ok"


def _normalize_live_wallet(env: Dict[str, str]) -> Tuple[Dict[str, str], str]:
    """
    Keep live signer and funder coherent:
    - if POLY_FUNDER unset, use signer address
    - if set but mismatched, force signer address (cannot sign for a different EOA)
    """
    out = dict(env)
    if not ETH_ACCOUNT_AVAILABLE:
        return out, ""
    pk = str(out.get("POLY_PRIVATE_KEY", "") or "").strip()
    if not pk:
        return out, ""
    try:
        signer = str(Account.from_key(pk).address)
    except Exception as exc:
        return out, f"wallet normalization skipped: invalid POLY_PRIVATE_KEY ({exc})"
    current = str(out.get("POLY_FUNDER", "") or "").strip()
    if not current:
        out["POLY_FUNDER"] = signer
        return out, f"POLY_FUNDER auto-set to signer {signer}"
    if current.lower() != signer.lower():
        return out, f"POLY_FUNDER ({current}) differs from signer ({signer}); verify proxy/API-wallet setup"
    return out, ""


def _make_client(env: Dict[str, str]) -> ClobClient:
    creds = ApiCreds(
        api_key=env["POLY_API_KEY"],
        api_secret=env["POLY_API_SECRET"],
        api_passphrase=env["POLY_API_PASSPHRASE"],
    )
    sig_type = 0
    try:
        sig_type = int(str(env.get("POLY_SIGNATURE_TYPE", "0") or "0").strip())
    except Exception:
        sig_type = 0
    if sig_type not in {0, 1, 2}:
        sig_type = 0
    return ClobClient(
        host=env.get("POLY_CLOB_HOST") or DEFAULT_HOST,
        key=env["POLY_PRIVATE_KEY"],
        chain_id=137,
        creds=creds,
        # Signature types: EOA=0, POLY_PROXY=1, GNOSIS_SAFE=2
        signature_type=sig_type,
        funder=env["POLY_FUNDER"],
    )


def _already_logged(conn: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM polymarket_orders WHERE candidate_id=? AND status=? LIMIT 1",
        (int(candidate_id), str(status)),
    )
    return cur.fetchone() is not None


def _insert_order_event(
    conn: sqlite3.Connection,
    candidate: Dict[str, Any],
    *,
    mode: str,
    status: str,
    notes: str,
    notional: float,
    token_id: str = "",
    side: str = "BUY",
    price: float = 0.0,
    size: float = 0.0,
    order_id: str = "",
    response: Optional[Dict[str, Any]] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO polymarket_orders
        (created_at, strategy_id, candidate_id, market_id, outcome, side, token_id, mode,
         notional, price, size, order_id, status, notes, response_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            str(candidate.get("strategy_id") or ""),
            int(candidate.get("id") or 0),
            str(candidate.get("market_id") or ""),
            str(candidate.get("outcome") or ""),
            str(side or "BUY"),
            str(token_id or ""),
            str(mode),
            float(notional or 0.0),
            float(price or 0.0),
            float(size or 0.0),
            str(order_id or ""),
            str(status),
            str(notes or ""),
            json.dumps(response or {}, separators=(",", ":")),
        ),
    )


def _candidate_token_and_price(conn: sqlite3.Connection, candidate: Dict[str, Any]) -> Tuple[str, float, str]:
    if not _table_exists(conn, "polymarket_markets"):
        return "", 0.0, "polymarket_markets missing"

    cur = conn.cursor()
    cur.execute(
        """
        SELECT clob_token_ids_json, outcome_prices_json
        FROM polymarket_markets
        WHERE market_id=?
        LIMIT 1
        """,
        (str(candidate.get("market_id") or ""),),
    )
    row = cur.fetchone()
    if not row:
        return "", 0.0, "market metadata missing"

    token_ids: List[str] = []
    prices: List[float] = []
    try:
        parsed = json.loads(row[0] or "[]")
        if isinstance(parsed, list):
            token_ids = [str(x) for x in parsed]
    except Exception:
        token_ids = []

    try:
        parsed_prices = json.loads(row[1] or "[]")
        if isinstance(parsed_prices, list):
            prices = [float(x) for x in parsed_prices]
    except Exception:
        prices = []

    outcome = str(candidate.get("outcome") or "").strip().lower()
    idx = 0 if outcome in {"yes", "y", "true", "1"} else 1

    token_id = token_ids[idx] if len(token_ids) > idx else ""
    base_price = prices[idx] if len(prices) > idx else float(candidate.get("implied_prob") or 0.5)

    if not token_id:
        return "", 0.0, "token_id unavailable"

    base_price = max(0.01, min(0.99, float(base_price or 0.5)))
    return token_id, base_price, "ok"


def _resolve_limit_price(client: ClobClient, token_id: str, fallback: float) -> float:
    try:
        book = client.get_order_book(token_id)
        asks = getattr(book, "asks", None) or []
        if asks:
            top = asks[0]
            p = float(getattr(top, "price", fallback))
            return max(0.01, min(0.99, p))
    except Exception:
        pass
    return max(0.01, min(0.99, float(fallback or 0.5)))


def _map_live_status(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return "submitted_live"
    if "fill" in s or s in {"matched", "executed", "complete", "completed"}:
        return "filled_live"
    if "cancel" in s:
        return "cancelled_live"
    if "reject" in s or "fail" in s:
        return "submission_failed"
    if "open" in s:
        return "open_live"
    if "part" in s:
        return "partially_filled_live"
    return "submitted_live"


def _daily_exposure(conn: sqlite3.Connection, mode: str) -> float:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(notional), 0)
        FROM polymarket_orders
        WHERE date(created_at)=date('now')
          AND mode=?
          AND status IN (
            'submitted_paper','filled_paper',
            'submitted_live','accepted_live','open_live','partially_filled_live','filled_live',
            'submitted'
          )
        """,
        (str(mode),),
    )
    return float((cur.fetchone() or [0.0])[0] or 0.0)


def _fetch_candidates(conn: sqlite3.Connection, limit: int) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "polymarket_candidates"):
        return []
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, strategy_id, market_id, outcome, implied_prob, model_prob,
               edge, confidence, source_tag, rationale, question, status
        FROM polymarket_candidates
        WHERE status IN ('new','approved','awaiting_approval')
        ORDER BY CASE WHEN status='approved' THEN 0 ELSE 1 END ASC,
                 ABS(edge) DESC,
                 datetime(COALESCE(created_at,'1970-01-01')) DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def _mark_candidate(conn: sqlite3.Connection, candidate_id: int, status: str) -> None:
    if not _table_exists(conn, "polymarket_candidates"):
        return
    conn.execute(
        "UPDATE polymarket_candidates SET status=? WHERE id=?",
        (str(status), int(candidate_id)),
    )


def _sync_live_orders(conn: sqlite3.Connection, client: Optional[ClobClient]) -> int:
    if client is None or not _table_exists(conn, "polymarket_orders"):
        return 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, order_id, status
        FROM polymarket_orders
        WHERE mode='live'
          AND order_id<>''
          AND status IN ('submitted_live','accepted_live','open_live','partially_filled_live','submitted')
        ORDER BY id DESC
        LIMIT 50
        """
    )

    updated = 0
    for oid, order_id, status in cur.fetchall():
        try:
            payload = client.get_order(str(order_id))
        except Exception:
            continue

        raw = ""
        if isinstance(payload, dict):
            raw = str(payload.get("status") or payload.get("orderStatus") or payload.get("state") or "")
        mapped = _map_live_status(raw)
        if mapped != status:
            conn.execute(
                "UPDATE polymarket_orders SET status=?, response_json=?, notes=? WHERE id=?",
                (
                    mapped,
                    json.dumps(payload if isinstance(payload, dict) else {"raw": str(payload)}),
                    f"synced at {now_iso()}",
                    int(oid),
                ),
            )
            updated += 1
    return updated


def _live_funding_status(client: Optional[ClobClient]) -> Tuple[bool, str]:
    if client is None:
        return False, "live client unavailable"
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=0)
        snap = client.get_balance_allowance(params)
        bal = float((snap or {}).get("balance") or 0.0)
        allowances = (snap or {}).get("allowances") or {}
        max_allow = 0.0
        if isinstance(allowances, dict):
            for v in allowances.values():
                try:
                    max_allow = max(max_allow, float(v or 0.0))
                except Exception:
                    continue
        if bal <= 0:
            return False, f"insufficient collateral balance ({bal:.6f})"
        if max_allow <= 0:
            return False, f"collateral allowance is zero (balance={bal:.6f})"
        return True, "ok"
    except Exception as exc:
        return False, f"funding check failed: {exc}"


def _live_funding_status_cli(env: Dict[str, str]) -> Tuple[bool, str]:
    sig = str(env.get("POLY_SIGNATURE_TYPE", "0") or "0").strip().lower()
    sig_flag = "eoa"
    if sig in {"1", "proxy", "poly_proxy"}:
        sig_flag = "proxy"
    elif sig in {"2", "gnosis-safe", "gnosis_safe", "safe"}:
        sig_flag = "gnosis-safe"
    cmd = [
        "polymarket",
        "-o",
        "json",
        "--signature-type",
        sig_flag,
        "clob",
        "balance",
        "--asset-type",
        "collateral",
    ]
    run_env = os.environ.copy()
    run_env["POLYMARKET_PRIVATE_KEY"] = str(env.get("POLY_PRIVATE_KEY", "") or "")
    # Keep account deterministic for funded wallet routing.
    if sig_flag != "eoa" and str(env.get("POLY_FUNDER", "") or "").strip():
        run_env["POLYMARKET_FUNDER"] = str(env.get("POLY_FUNDER", "") or "")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=run_env)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
        return False, f"cli balance check failed: {err[:220]}"
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        return False, "cli balance check returned non-json output"
    bal = 0.0
    for key in ("balance", "available", "value"):
        try:
            bal = float(payload.get(key) or 0.0)
        except Exception:
            continue
        if bal > 0:
            break
    if bal <= 0:
        return False, "cli collateral balance appears zero"
    return True, f"ok balance={bal:.4f}"


def _strategy_allowed(controls: Dict[str, str], strategy: str) -> bool:
    key = {
        "POLY_COPY": "polymarket_copy_enabled",
        "POLY_ARB": "polymarket_arb_enabled",
        "POLY_ALPHA": "polymarket_alpha_enabled",
    }.get(str(strategy).upper(), "")
    if not key:
        return True
    return _as_bool(controls.get(key, "1"), default=True)


def _strategy_notional_cap(controls: Dict[str, str], strategy: str, fallback: float) -> float:
    key = {
        "POLY_COPY": "polymarket_copy_max_notional_usd",
        "POLY_ARB": "polymarket_arb_max_notional_usd",
        "POLY_ALPHA": "polymarket_alpha_max_notional_usd",
    }.get(str(strategy).upper(), "")
    if not key:
        return fallback
    return _as_float(controls.get(key), fallback)


def _normalized_edge_pct(
    controls: Dict[str, str],
    candidate: Dict[str, Any],
) -> float:
    """
    Normalize edge to percentage points for threshold comparisons.
    Supports:
    - pct (already percent, e.g. 2.5)
    - fraction (0.025 => 2.5%)
    - ratio (1.025 => 2.5%; 18.17 => 1717%)
    """
    raw = _as_float(candidate.get("edge"), 0.0)
    mode = str(controls.get("polymarket_edge_unit_mode", "auto") or "auto").strip().lower()
    implied = _as_float(candidate.get("implied_prob"), 0.0)
    model = _as_float(candidate.get("model_prob"), 0.0)
    delta_pct = (model - implied) * 100.0

    if mode == "pct":
        return raw
    if mode == "fraction":
        return raw * 100.0
    if mode == "ratio":
        return (raw - 1.0) * 100.0

    # auto mode
    if abs(raw) <= 1.0:
        return raw * 100.0
    if 0.0 <= implied <= 1.0 and 0.0 <= model <= 1.0:
        pct_dist = abs(raw - delta_pct)
        ratio_to_pct = (raw - 1.0) * 100.0
        ratio_dist = abs(ratio_to_pct - delta_pct)
        if ratio_dist + 0.25 < pct_dist:
            return ratio_to_pct
    return raw


def _evaluate_candidate(
    conn: sqlite3.Connection,
    controls: Dict[str, str],
    candidate: Dict[str, Any],
    mode: str,
) -> Tuple[bool, float, str, str]:
    strategy = str(candidate.get("strategy_id") or "")
    edge_pct = _normalized_edge_pct(controls, candidate)
    confidence_raw = _as_float(candidate.get("confidence"), 0.0)
    confidence_pct = confidence_raw * 100.0 if confidence_raw <= 1.0 else confidence_raw
    cid = int(candidate.get("id") or 0)

    if not _strategy_allowed(controls, strategy):
        return False, 0.0, "blocked_control", f"strategy disabled: {strategy}"

    min_edge = _as_float(controls.get("polymarket_min_edge_pct"), 5.0)
    q = str(candidate.get("question") or "").lower()
    fee_gate = _as_bool(controls.get("polymarket_fee_gate_enabled"), default=True)
    taker_fee = _as_float(controls.get("polymarket_taker_fee_pct"), 3.15)
    fee_buf = _as_float(controls.get("polymarket_fee_buffer_pct"), 0.50)
    fee_market = ("5 minute" in q or "5-minute" in q) and any(k in q for k in ("btc", "bitcoin", "sol", "eth", "ethereum", "up or down"))
    effective_min = min_edge
    if fee_gate and fee_market:
        effective_min = max(min_edge, taker_fee + fee_buf)
    if edge_pct < effective_min:
        return False, 0.0, "blocked_control", f"edge below threshold ({edge_pct:.2f}% < {effective_min:.2f}%)"

    min_conf = _as_float(controls.get("polymarket_min_confidence_pct"), 60.0)
    if confidence_pct < min_conf:
        return False, 0.0, "blocked_control", f"confidence below threshold ({confidence_pct:.2f} < {min_conf:.2f})"

    manual = _as_bool(controls.get("polymarket_manual_approval"), default=True)
    approval_threshold = _as_int(controls.get("polymarket_approval_threshold"), 10)
    approval_count = _as_int(controls.get("polymarket_approval_count"), 0)

    if manual:
        # First N requires approval; if threshold <= 0 then always require approval.
        require_approval = (approval_threshold <= 0) or (approval_count < approval_threshold)
        if require_approval and str(candidate.get("status") or "") != "approved":
            return False, 0.0, "awaiting_approval", "manual approval required"

    global_cap = _as_float(controls.get("polymarket_max_notional_usd"), 10.0)
    strat_cap = _strategy_notional_cap(controls, strategy, global_cap)
    notional = max(0.0, min(global_cap, strat_cap))
    if notional <= 0:
        return False, 0.0, "blocked_control", "notional cap resolved to zero"

    daily_cap = _as_float(controls.get("polymarket_max_daily_exposure"), 20.0)
    used_today = _daily_exposure(conn, mode)
    if used_today + notional > daily_cap:
        return False, notional, "blocked_control", f"daily cap exceeded ({used_today + notional:.2f} > {daily_cap:.2f})"

    if mode == "live":
        live_enabled = _as_bool(controls.get("allow_polymarket_live"), default=False)
        if not live_enabled:
            return False, notional, "blocked_control", "live execution disabled by control"

    return True, notional, "approved", "ready"


def _candidate_status(conn: sqlite3.Connection, candidate_id: int) -> str:
    if not _table_exists(conn, "polymarket_candidates"):
        return ""
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(status,'') FROM polymarket_candidates WHERE id=? LIMIT 1", (int(candidate_id),))
    row = cur.fetchone()
    return str(row[0] if row else "")


def _submit_live_order(
    client: ClobClient,
    token_id: str,
    notional: float,
    price_hint: float,
) -> Tuple[str, float, float, str, Dict[str, Any], str]:
    limit_price = _resolve_limit_price(client, token_id, fallback=price_hint)
    size = round(float(notional) / max(limit_price, 0.01), 6)

    order_args = OrderArgs(
        token_id=str(token_id),
        price=float(limit_price),
        size=float(size),
        side=BUY,
    )
    signed = client.create_order(order_args)
    resp = client.post_order(signed, OrderType.GTC)
    payload = resp if isinstance(resp, dict) else {"raw": str(resp)}
    order_id = str(payload.get("orderID") or payload.get("id") or "")
    raw_status = str(payload.get("status") or payload.get("orderStatus") or "submitted")
    status = _map_live_status(raw_status)
    return order_id, limit_price, size, status, payload, raw_status


def _submit_live_order_cli(
    env: Dict[str, str],
    token_id: str,
    notional: float,
) -> Tuple[str, float, float, str, Dict[str, Any], str]:
    sig = str(env.get("POLY_SIGNATURE_TYPE", "0") or "0").strip().lower()
    sig_flag = "eoa"
    if sig in {"1", "proxy", "poly_proxy"}:
        sig_flag = "proxy"
    elif sig in {"2", "gnosis-safe", "gnosis_safe", "safe"}:
        sig_flag = "gnosis-safe"
    cmd = [
        "polymarket",
        "-o",
        "json",
        "--signature-type",
        sig_flag,
        "clob",
        "market-order",
        "--token",
        str(token_id),
        "--side",
        "buy",
        "--amount",
        str(round(float(notional), 6)),
    ]
    run_env = os.environ.copy()
    run_env["POLYMARKET_PRIVATE_KEY"] = str(env.get("POLY_PRIVATE_KEY", "") or "")
    if sig_flag != "eoa" and str(env.get("POLY_FUNDER", "") or "").strip():
        run_env["POLYMARKET_FUNDER"] = str(env.get("POLY_FUNDER", "") or "")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=run_env)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
        raise RuntimeError(f"polymarket cli market-order failed: {err[:260]}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception as exc:
        raise RuntimeError(f"polymarket cli returned non-json payload: {exc}")
    order_id = str(payload.get("orderID") or payload.get("id") or payload.get("order_id") or "")
    raw_status = str(payload.get("status") or payload.get("orderStatus") or payload.get("state") or "submitted")
    status = _map_live_status(raw_status)
    # CLI market orders don't return deterministic price/size schema across versions.
    px = _as_float(payload.get("price"), 0.0)
    sz = _as_float(payload.get("size"), 0.0)
    return order_id, px, sz, status, payload, raw_status


def run() -> int:
    conn = _connect()
    try:
        ensure_tables(conn)
        controls = _load_controls(conn)
        env, wallet_fix_note = _normalize_live_wallet(_load_runtime_env())

        allow_auto = _as_bool(controls.get("enable_polymarket_auto"), default=False)
        master_enabled = _as_bool(controls.get("agent_master_enabled"), default=False)
        if not master_enabled:
            conn.commit()
            print("POLYMARKET_EXECUTOR mode=paper auto=disabled note='agent_master_enabled=0'")
            return 0
        want_live = _as_bool(controls.get("allow_polymarket_live"), default=False)
        backend = str(controls.get("polymarket_exec_backend", "pyclob") or "pyclob").strip().lower()
        if backend not in {"pyclob", "cli"}:
            backend = "pyclob"

        live_ok = False
        live_msg = "paper mode"
        client: Optional[ClobClient] = None
        if backend == "cli":
            live_ok, live_msg = _live_ready_cli(env)
            mode = "live" if (want_live and live_ok) else "paper"
            live_funds_ok, live_funds_reason = _live_funding_status_cli(env) if mode == "live" else (False, "paper mode")
        else:
            live_ok, live_msg = _live_ready(env)
            mode = "live" if (want_live and live_ok) else "paper"
            client = _make_client(env) if mode == "live" else None
            live_funds_ok, live_funds_reason = _live_funding_status(client) if mode == "live" else (False, "paper mode")
        strict_funding = _as_bool(controls.get("polymarket_strict_funding_check", "0"), default=False)

        # Keep truth in sync for previously-submitted live orders.
        synced = _sync_live_orders(conn, client)

        if not allow_auto:
            conn.commit()
            print(
                "POLYMARKET_EXECUTOR "
                f"mode={mode} auto=disabled synced={synced} note='auto execution disabled by control'"
            )
            return 0

        if want_live and not live_ok:
            print(f"POLYMARKET_EXECUTOR backend={backend} live_fallback reason='{live_msg}'")
        if wallet_fix_note:
            print(f"POLYMARKET_EXECUTOR wallet_note='{wallet_fix_note}'")

        cycle_limit = _as_int(controls.get("polymarket_cycle_limit"), 8)
        candidates = _fetch_candidates(conn, max(1, cycle_limit))

        stats = {
            "mode": mode,
            "candidates": len(candidates),
            "executed": 0,
            "blocked": 0,
            "failed": 0,
            "awaiting_approval": 0,
            "synced": synced,
        }

        for c in candidates:
            cid = int(c.get("id") or 0)
            ok, notional, decision_status, reason = _evaluate_candidate(conn, controls, c, mode)
            current_status = _candidate_status(conn, cid)

            if not ok:
                if decision_status == "awaiting_approval":
                    # Preserve manual review lifecycle but do not force-reset approved/submitted states.
                    if current_status in {"", "new", "awaiting_approval"}:
                        _mark_candidate(conn, cid, "awaiting_approval")
                    stats["awaiting_approval"] += 1
                else:
                    # Do not auto-overwrite candidate lifecycle to blocked on every cycle.
                    # Keep status stable unless submission is actually attempted.
                    stats["blocked"] += 1

                if not _already_logged(conn, cid, decision_status):
                    _insert_order_event(
                        conn,
                        c,
                        mode=mode,
                        status=decision_status,
                        notes=reason,
                        notional=notional,
                    )
                continue

            if mode == "live" and not live_funds_ok:
                if strict_funding:
                    stats["blocked"] += 1
                    if not _already_logged(conn, cid, "blocked_control"):
                        _insert_order_event(
                            conn,
                            c,
                            mode="live",
                            status="blocked_control",
                            notes=f"strict funding gate: {live_funds_reason}",
                            notional=0.0,
                        )
                    continue
                else:
                    if not _already_logged(conn, cid, "funding_warn"):
                        _insert_order_event(
                            conn,
                            c,
                            mode="live",
                            status="funding_warn",
                            notes=f"non-strict funding check warning: {live_funds_reason}",
                            notional=0.0,
                        )

            token_id, fallback_price, token_reason = _candidate_token_and_price(conn, c)
            if not token_id:
                _mark_candidate(conn, cid, "submission_failed")
                stats["failed"] += 1
                if not _already_logged(conn, cid, "submission_failed"):
                    _insert_order_event(
                        conn,
                        c,
                        mode=mode,
                        status="submission_failed",
                        notes=token_reason,
                        notional=notional,
                    )
                continue

            if mode == "paper":
                px = max(0.01, min(0.99, float(fallback_price or 0.5)))
                size = round(float(notional) / px, 6)
                order_id = f"poly-paper-{cid}-{int(time.time())}"
                _insert_order_event(
                    conn,
                    c,
                    mode="paper",
                    status="submitted_paper",
                    notes="paper simulation only (no real money)",
                    notional=notional,
                    token_id=token_id,
                    side="BUY",
                    price=px,
                    size=size,
                    order_id=order_id,
                    response={"paper": True, "candidate_id": cid},
                )
                _mark_candidate(conn, cid, "submitted_paper")
                stats["executed"] += 1
                continue

            try:
                if backend == "cli":
                    order_id, px, size, status, payload, raw_status = _submit_live_order_cli(
                        env=env,
                        token_id=token_id,
                        notional=notional,
                    )
                else:
                    assert client is not None
                    order_id, px, size, status, payload, raw_status = _submit_live_order(
                        client=client,
                        token_id=token_id,
                        notional=notional,
                        price_hint=fallback_price,
                    )
                _insert_order_event(
                    conn,
                    c,
                    mode="live",
                    status=status,
                    notes=f"live post_order status={raw_status}",
                    notional=notional,
                    token_id=token_id,
                    side="BUY",
                    price=px,
                    size=size,
                    order_id=order_id,
                    response=payload,
                )
                _mark_candidate(conn, cid, status)
                stats["executed"] += 1

                # First-N manual approvals consumed only on successful live submissions.
                if _as_bool(controls.get("polymarket_manual_approval"), default=True):
                    current = _as_int(controls.get("polymarket_approval_count"), 0)
                    controls["polymarket_approval_count"] = str(current + 1)
                    conn.execute(
                        "UPDATE execution_controls SET value=?, updated_at=? WHERE key='polymarket_approval_count'",
                        (str(current + 1), now_iso()),
                    )

            except Exception as exc:
                _insert_order_event(
                    conn,
                    c,
                    mode="live",
                    status="submission_failed",
                    notes=f"live submit error: {exc}",
                    notional=notional,
                    token_id=token_id,
                )
                _mark_candidate(conn, cid, "submission_failed")
                stats["failed"] += 1

        conn.commit()
        print(
            "POLYMARKET_EXECUTOR "
            f"mode={stats['mode']} candidates={stats['candidates']} executed={stats['executed']} "
            f"awaiting_approval={stats['awaiting_approval']} blocked={stats['blocked']} failed={stats['failed']} synced={stats['synced']}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(run())
