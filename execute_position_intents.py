#!/usr/bin/env python3
"""
Execute pending position management intents from trade_intents table.

Reads intents with manage_* status and acts:
  manage_trail_stop_tighten  → consult live signals first; if liquidity still bullish → HOLD,
                               else submit tightened reduce-only stop order
  manage_reduce_or_exit      → consult live signals; if strong bullish consensus → HOLD,
                               else submit reduce-only stop at aggressive price (near market)
  manage_take_profit_major   → iMessage alert to Curtis (requires manual confirm)
  manage_take_profit_partial → iMessage alert to Curtis (requires manual confirm)

Signal consultation (liquidity-first veto):
  Before executing a stop/trail, re-scores the open trade against current signals.
  If chart_liquidity_signals is bullish AND 1+ other input is bullish → suppress stop tighten.
  Reduce_or_exit (hard stop) only suppressed when 2+ bullish AND liquidity is primary.

Controls respected (from execution_controls table):
  agent_master_enabled             must be 1
  allow_hyperliquid_live           0 = testnet only, 1 = mainnet
  enable_hyperliquid_test_auto     must be 1 for testnet auto execution
  intent_signal_consult_enabled    1 = check live signals before stop (default: 1)
  intent_signal_consult_ttl_hours  max age of signals to consider (default: 4)

Marks each intent as:
  executing → submitted_stop | alert_sent | held_signal_veto | failed
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "trades.db"
IMSG_SCRIPT = Path("/Users/Shared/curtis/imsg-notify.sh")

ACTIONABLE_STATUSES = {
    "manage_trail_stop_tighten",
    "manage_reduce_or_exit",
    "manage_take_profit_partial",
    "manage_take_profit_major",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _load_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    return {str(k): str(v) for k, v in cur.fetchall()}


def _is_true(controls: Dict[str, str], key: str) -> bool:
    return str(controls.get(key, "0")).strip().lower() in {"1", "true", "yes", "on"}


def _load_pending_intents(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in ACTIONABLE_STATUSES)
    cur.execute(
        f"""
        SELECT id, venue, symbol, side, qty, notional, status, details
        FROM trade_intents
        WHERE status IN ({placeholders})
        ORDER BY id DESC
        LIMIT 30
        """,
        tuple(ACTIONABLE_STATUSES),
    )
    rows = []
    for row in cur.fetchall():
        intent_id, venue, symbol, side, qty, notional, status, details_raw = row
        try:
            details = json.loads(details_raw or "{}")
        except Exception:
            details = {}
        rows.append({
            "id": intent_id,
            "venue": venue,
            "symbol": str(symbol or "").upper().strip(),
            "side": str(side or "").lower().strip(),
            "qty": _as_float(qty),
            "notional": _as_float(notional),
            "status": str(status or ""),
            "details": details,
        })
    return rows


def _mark_intent(conn: sqlite3.Connection, intent_id: int, status: str, note: str = "") -> None:
    details_update = json.dumps({"executor_note": note, "executed_at": now_iso()}, ensure_ascii=True)
    conn.execute(
        """
        UPDATE trade_intents
        SET status = ?,
            details = json_patch(COALESCE(details, '{}'), ?)
        WHERE id = ?
        """,
        (status, details_update, intent_id),
    )
    conn.commit()


def _send_imessage(symbol: str, action: str, pnl_pct: float, upnl_usd: float, details: Dict) -> bool:
    if not IMSG_SCRIPT.exists():
        return False
    entry = _as_float(details.get("entry_price", 0))
    mark = _as_float(details.get("mark_price", 0))
    leverage = _as_float(details.get("leverage", 1), 1.0)
    msg = (
        f"TAKE PROFIT SIGNAL: {symbol} "
        f"pnl={pnl_pct:+.1f}% (${upnl_usd:+.0f}) "
        f"entry={entry:.4f} mark={mark:.4f} lev={leverage:.0f}x "
        f"action={action} — tap to approve close"
    )
    try:
        subprocess.run(
            [str(IMSG_SCRIPT), "TRADER", msg, "alert"],
            timeout=10,
            capture_output=True,
        )
        return True
    except Exception:
        return False


def _exit_side(position_side: str) -> str:
    """To close a long, we sell. To close a short, we buy."""
    return "sell" if position_side in {"long", "buy"} else "buy"


def _run_stop_protection(
    symbol: str,
    exit_side: str,
    qty: float,
    stop_price: float,
    cancel_existing: bool = True,
) -> Tuple[bool, str]:
    """Call apply_hl_protection.py subprocess — keeps execution isolated."""
    script = BASE_DIR / "scripts" / "apply_hl_protection.py"
    if not script.exists():
        return False, "apply_hl_protection.py not found"
    cmd = [
        sys.executable,
        str(script),
        "--symbol", symbol,
        "--side", exit_side,
        "--qty", str(qty),
        "--stop-price", str(stop_price),
        "--cancel-existing", "1" if cancel_existing else "0",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            try:
                data = json.loads(stdout)
                if data.get("ok"):
                    return True, stdout
                return False, data.get("message") or stdout or "stop returned ok=false with no message"
            except Exception:
                return True, stdout
        # Build detailed error message for debugging
        parts = []
        if stderr:
            parts.append(f"stderr={stderr[-500:]}")
        if stdout:
            parts.append(f"stdout={stdout[-500:]}")
        if not parts:
            parts.append(f"exit_code={result.returncode} (no output)")
        return False, "; ".join(parts)
    except subprocess.TimeoutExpired:
        return False, f"apply_hl_protection.py timed out (30s) for {symbol}"
    except Exception as exc:
        return False, f"subprocess error: {type(exc).__name__}: {exc}"


def _consult_live_signals(
    conn: sqlite3.Connection,
    symbol: str,
    position_side: str,
    ttl_hours: int = 4,
) -> Dict[str, Any]:
    """
    Re-score current signal state for an open position before executing a stop.
    Liquidity is the primary veto: if chart_liquidity_signals is bullish for a long,
    we may suppress the stop tighten to let the trade run.

    Returns:
      {
        "liquidity_bullish": bool,
        "liquidity_score": float,        # 0.0–1.0
        "liquidity_pattern": str,
        "pipeline_bullish": bool,
        "pipeline_score": float,
        "external_bullish": bool,
        "external_score": float,
        "bullish_count": int,            # how many inputs are currently bullish
        "veto_stop": bool,               # True = suppress stop, hold position
        "veto_reason": str,
      }
    """
    result: Dict[str, Any] = {
        "liquidity_bullish": False,
        "liquidity_score": 0.0,
        "liquidity_pattern": "",
        "pipeline_bullish": False,
        "pipeline_score": 0.0,
        "external_bullish": False,
        "external_score": 0.0,
        "bullish_count": 0,
        "veto_stop": False,
        "veto_reason": "no signal data",
    }
    sym = symbol.upper().strip()
    is_long = position_side.lower() in {"long", "buy"}
    ttl_cutoff = f"-{int(ttl_hours)} hour"
    cur = conn.cursor()

    # 1. Liquidity signals (primary veto input)
    cur.execute(
        """
        SELECT pattern, confidence, entry_hint, stop_hint, target_hint, created_at
        FROM chart_liquidity_signals
        WHERE upper(ticker) = ?
          AND datetime(COALESCE(created_at,'1970-01-01')) >= datetime('now', ?)
          AND COALESCE(pattern,'') NOT IN ('', 'insufficient_data')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (sym, ttl_cutoff),
    )
    liq_row = cur.fetchone()
    if liq_row:
        liq_pattern = str(liq_row[0] or "")
        liq_conf = _as_float(liq_row[1])
        # Bullish liquidity: high-confidence pattern with positive R:R
        liq_entry = _as_float(liq_row[2])
        liq_stop = _as_float(liq_row[3])
        liq_target = _as_float(liq_row[4])
        risk = abs(liq_entry - liq_stop)
        reward = abs(liq_target - liq_entry)
        liq_rr = round(reward / risk, 2) if risk > 0 else 0.0
        liq_bullish = (
            liq_conf >= 0.60
            and liq_rr >= 1.5
            and any(k in liq_pattern for k in ["liquidity_grab", "stop_hunt", "fakeout", "compression"])
        )
        result["liquidity_bullish"] = liq_bullish and is_long
        result["liquidity_score"] = liq_conf
        result["liquidity_pattern"] = liq_pattern

    # 2. Pipeline signals
    cur.execute(
        """
        SELECT score, direction
        FROM pipeline_signals
        WHERE upper(COALESCE(asset,'')) = ?
          AND status = 'new'
          AND datetime(COALESCE(generated_at,'1970-01-01')) >= datetime('now', ?)
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (sym, ttl_cutoff),
    )
    pipe_row = cur.fetchone()
    if pipe_row:
        pipe_score = _as_float(pipe_row[0], 50.0)
        pipe_dir = str(pipe_row[1] or "unknown").lower()
        pipe_bullish = pipe_score >= 65.0 and (pipe_dir in {"bullish", "long", "buy"} or pipe_dir == "unknown")
        result["pipeline_bullish"] = pipe_bullish and is_long
        result["pipeline_score"] = pipe_score / 100.0

    # 3. External signals
    cur.execute(
        """
        SELECT confidence, direction
        FROM external_signals
        WHERE upper(COALESCE(ticker,'')) = ?
          AND status IN ('new','active')
          AND datetime(COALESCE(created_at,'1970-01-01')) >= datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (sym, ttl_cutoff),
    )
    ext_row = cur.fetchone()
    if ext_row:
        ext_conf = _as_float(ext_row[0], 0.5)
        ext_dir = str(ext_row[1] or "unknown").lower()
        ext_bullish = ext_conf >= 0.65 and ext_dir in {"bullish", "long", "buy"}
        result["external_bullish"] = ext_bullish and is_long
        result["external_score"] = ext_conf

    bullish_count = sum([
        bool(result["liquidity_bullish"]),
        bool(result["pipeline_bullish"]),
        bool(result["external_bullish"]),
    ])
    result["bullish_count"] = bullish_count

    # Veto logic: suppress stop tighten if liquidity is still bullish + 1 other input agrees
    # Veto reduce_or_exit only if liquidity AND 2 other inputs strongly bullish (harder gate)
    if result["liquidity_bullish"] and bullish_count >= 2:
        result["veto_stop"] = True
        result["veto_reason"] = (
            f"liquidity bullish (pattern={result['liquidity_pattern']} conf={result['liquidity_score']:.2f}) "
            f"+ {bullish_count - 1} other input(s) agree — holding position"
        )
    else:
        parts = []
        if not result["liquidity_bullish"]:
            parts.append(f"liquidity not bullish (pattern={result['liquidity_pattern'] or 'none'} conf={result['liquidity_score']:.2f})")
        if bullish_count < 2:
            parts.append(f"only {bullish_count}/3 inputs bullish")
        result["veto_reason"] = "; ".join(parts) or "below veto threshold"

    return result


def process_intents(dry_run: bool = False) -> int:
    conn = _connect()
    try:
        controls = _load_controls(conn)
        intents = _load_pending_intents(conn)

        if not intents:
            print("INTENT_EXECUTOR: no pending manage intents")
            return 0

        # Gate checks
        agent_enabled = _is_true(controls, "agent_master_enabled")
        live_enabled = _is_true(controls, "allow_hyperliquid_live")
        test_auto = _is_true(controls, "enable_hyperliquid_test_auto")
        signal_consult = str(controls.get("intent_signal_consult_enabled", "1")).strip() != "0"
        consult_ttl = max(1, int(float(controls.get("intent_signal_consult_ttl_hours", "4") or 4)))

        if not agent_enabled:
            print(f"INTENT_EXECUTOR: agent_master_enabled=0 — skipping {len(intents)} intents")
            return 0

        # Require either live or test_auto to execute stop orders
        can_execute_stops = live_enabled or test_auto

        executed = 0
        alerted = 0
        held = 0
        skipped = 0

        for intent in intents:
            iid = intent["id"]
            symbol = intent["symbol"]
            status = intent["status"]
            qty = intent["qty"]
            position_side = intent["side"]
            details = intent["details"]

            suggested_stop = _as_float(details.get("suggested_stop_price", 0))
            pnl_pct = _as_float(details.get("pnl_pct", 0))
            upnl_usd = _as_float(details.get("upnl_usd", 0))
            mark_price = _as_float(details.get("mark_price", 0))
            exit_s = _exit_side(position_side)

            label = f"[{iid}] {symbol} {status} qty={qty} pnl={pnl_pct:+.1f}%"

            if status in {"manage_trail_stop_tighten", "manage_reduce_or_exit"}:
                if not can_execute_stops:
                    print(f"INTENT_EXECUTOR: {label} — stop execution disabled (live=0 test_auto=0), skip")
                    skipped += 1
                    continue

                if suggested_stop <= 0 and mark_price > 0:
                    # Fallback: 3% gap from mark for reduce_or_exit
                    gap = 0.03 if status == "manage_reduce_or_exit" else 0.025
                    suggested_stop = mark_price * (1.0 - gap) if position_side in {"long", "buy"} else mark_price * (1.0 + gap)

                if suggested_stop <= 0:
                    print(f"INTENT_EXECUTOR: {label} — no valid stop price, skip")
                    skipped += 1
                    continue

                if qty <= 0:
                    print(f"INTENT_EXECUTOR: {label} — qty=0, skip")
                    skipped += 1
                    continue

                # ── Signal Consultation (liquidity-first veto) ──────────────
                # For trail tightens: ask current signals if we should hold.
                # For hard exits (reduce_or_exit): signals can veto only when position is still positive PnL.
                if signal_consult:
                    sig = _consult_live_signals(conn, symbol, position_side, ttl_hours=consult_ttl)
                    veto_allowed = status == "manage_trail_stop_tighten" or (
                        status == "manage_reduce_or_exit" and pnl_pct > 0 and sig["bullish_count"] >= 2
                    )
                    if sig["veto_stop"] and veto_allowed:
                        print(
                            f"INTENT_EXECUTOR: {label} ⏸ HELD — {sig['veto_reason']}"
                        )
                        if not dry_run:
                            _mark_intent(conn, iid, "held_signal_veto", sig["veto_reason"][:200])
                        held += 1
                        continue
                    else:
                        print(
                            f"INTENT_EXECUTOR: {label} signal check: liq={sig['liquidity_bullish']} "
                            f"pipe={sig['pipeline_bullish']} ext={sig['external_bullish']} "
                            f"→ proceed ({sig['veto_reason']})"
                        )
                # ── End Signal Consultation ──────────────────────────────────

                print(f"INTENT_EXECUTOR: {label} → submit stop exit_side={exit_s} stop={suggested_stop:.4f}")
                if dry_run:
                    print(f"  DRY RUN: would call apply_hl_protection.py --symbol {symbol} --side {exit_s} --qty {qty} --stop-price {suggested_stop:.4f}")
                    executed += 1
                    continue

                _mark_intent(conn, iid, "executing", f"stop_price={suggested_stop:.6f}")
                ok, msg = _run_stop_protection(symbol, exit_s, qty, suggested_stop)
                if ok:
                    print(f"INTENT_EXECUTOR: {label} ✅ submitted stop")
                    _mark_intent(conn, iid, "submitted_stop", msg[:200])
                    executed += 1
                else:
                    print(f"INTENT_EXECUTOR: {label} ❌ stop failed: {msg}")
                    _mark_intent(conn, iid, "failed", msg[:200])

            elif status in {"manage_take_profit_partial", "manage_take_profit_major"}:
                # Take profit requires reduce-only close order — alert Curtis and require confirmation
                print(f"INTENT_EXECUTOR: {label} → iMessage alert (manual confirm required)")
                if not dry_run:
                    sent = _send_imessage(symbol, status, pnl_pct, upnl_usd, details)
                    new_status = "alert_sent" if sent else "alert_pending"
                    _mark_intent(conn, iid, new_status, f"sent={sent}")
                alerted += 1

        print(
            f"INTENT_EXECUTOR: done — "
            f"executed={executed} alerted={alerted} held={held} skipped={skipped} "
            f"total={len(intents)} dry_run={dry_run}"
        )
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Execute pending position management intents")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    args = parser.parse_args()
    raise SystemExit(process_intents(dry_run=args.dry_run))
