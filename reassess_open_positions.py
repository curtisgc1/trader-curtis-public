#!/usr/bin/env python3
"""
Reassess open positions using 2-of-3 signal scoring.

For each open position, scores 3 independent signals:
  1. Liquidity — chart_liquidity_signals (TTL: 6h configurable)
  2. Pipeline  — pipeline_signals (respects stored ttl_minutes)
  3. Kelly EV  — kelly_signals verdict + ev_percent (latest batch)

Signal alignment (relative to position side):
  +1 = bullish for the position  (long signal on a buy, or short signal on a sell)
   0 = neutral / no fresh data
  -1 = bearish for the position  (short signal on a buy, or long signal on a sell)

Net score → action:
  >= +2  → manage_hold (no new intent, but log it) or manage_take_profit_major if also
            1 signal hit take-profit threshold
   0/+1  → no action (within noise floor, keep existing stops)
  -2     → manage_trail_stop_tighten
  -3     → manage_reduce_or_exit  (all 3 bearish — aggressive exit)

Cooldown: position_manage_intent_cooldown_hours (default 6h).
  Won't write a new manage_* intent for the same symbol within cooldown window.

Writes to:
  trade_intents          — manage_* rows for bearish verdicts
  pipeline_runtime_state — reassess_summary key with last run stats
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

DEFAULT_LIQUIDITY_TTL_HOURS = 6
DEFAULT_COOLDOWN_HOURS = 6

# Score thresholds
TIGHTEN_THRESHOLD = -2   # >= 2 bearish signals → tighten stop
EXIT_THRESHOLD = -3      # all 3 bearish → aggressive exit
HOLD_THRESHOLD = 2       # >= 2 bullish → hold / consider take profit


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def _get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute(
        "SELECT value FROM execution_controls WHERE key=?", (key,)
    ).fetchone()
    return row["value"] if row else default


def _get_open_positions(conn: sqlite3.Connection) -> List[Dict]:
    """Return distinct open positions by ticker+entry_side."""
    rows = conn.execute(
        """
        SELECT ticker, entry_side,
               MIN(entry_price) AS entry_price,
               COUNT(*) AS lot_count
        FROM trades
        WHERE status = 'open'
          AND ticker IS NOT NULL
          AND entry_side IS NOT NULL
        GROUP BY ticker, entry_side
        ORDER BY ticker
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _score_liquidity(conn: sqlite3.Connection, ticker: str, position_side: str, ttl_hours: int) -> Tuple[int, str]:
    """
    Score the latest chart_liquidity_signals for ticker within TTL.
    Returns (score, reason) where score is -1, 0, or +1.
    """
    cutoff = (now_utc() - timedelta(hours=ttl_hours)).isoformat()
    row = conn.execute(
        """
        SELECT direction, score, confidence
        FROM chart_liquidity_signals
        WHERE ticker = ? AND created_at >= ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (ticker, cutoff),
    ).fetchone()

    if not row:
        return 0, "no_data"

    direction = row["direction"]  # 'long', 'short', 'neutral'
    score = row["score"]
    confidence = row["confidence"]

    if direction == "neutral":
        return 0, f"neutral(score={score:.0f})"

    # Bullish for a buy if direction == 'long'; bullish for a sell if direction == 'short'
    aligned = (
        (position_side == "buy" and direction == "long")
        or (position_side == "sell" and direction == "short")
    )
    signal_score = +1 if aligned else -1
    label = "bullish" if aligned else "bearish"
    return signal_score, f"{label}(dir={direction},score={score:.0f},conf={confidence:.2f})"


def _score_pipeline(conn: sqlite3.Connection, ticker: str, position_side: str) -> Tuple[int, str]:
    """
    Score the freshest non-expired pipeline_signals for ticker.
    Respects stored ttl_minutes to avoid acting on stale signals.
    Returns (score, reason).
    """
    now = now_utc()
    rows = conn.execute(
        """
        SELECT direction, score, ttl_minutes, generated_at
        FROM pipeline_signals
        WHERE asset = ?
        ORDER BY generated_at DESC
        LIMIT 10
        """,
        (ticker,),
    ).fetchall()

    for row in rows:
        generated_at = datetime.fromisoformat(row["generated_at"].replace("Z", "+00:00"))
        ttl_minutes = row["ttl_minutes"] or 180
        expires_at = generated_at + timedelta(minutes=ttl_minutes)
        if now > expires_at:
            continue  # expired — try next

        direction = row["direction"]
        score = row["score"]

        if direction in ("neutral", None, ""):
            return 0, f"neutral(score={score:.0f})"

        aligned = (
            (position_side == "buy" and direction == "long")
            or (position_side == "sell" and direction == "short")
        )
        signal_score = +1 if aligned else -1
        label = "bullish" if aligned else "bearish"
        age_min = int((now - generated_at).total_seconds() / 60)
        return signal_score, f"{label}(dir={direction},score={score:.0f},age={age_min}m)"

    return 0, "no_fresh_data"


def _score_kelly(conn: sqlite3.Connection, ticker: str, position_side: str) -> Tuple[int, str]:
    """
    Score kelly_signals for ticker+direction matching position side.
    Uses the latest computed_at batch only.
    Returns (score, reason).
    """
    # Map position side to kelly direction
    kelly_direction = "long" if position_side == "buy" else "short"

    latest_batch = conn.execute(
        "SELECT MAX(computed_at) AS max_ts FROM kelly_signals"
    ).fetchone()
    if not latest_batch or not latest_batch["max_ts"]:
        return 0, "no_kelly_data"

    row = conn.execute(
        """
        SELECT verdict, ev_percent, kelly_fraction, frac_kelly
        FROM kelly_signals
        WHERE ticker = ?
          AND direction = ?
          AND computed_at = ?
        LIMIT 1
        """,
        (ticker, kelly_direction, latest_batch["max_ts"]),
    ).fetchone()

    if not row:
        return 0, "not_in_kelly_batch"

    verdict = row["verdict"]
    ev_pct = row["ev_percent"] or 0.0

    if verdict in ("pass",) and ev_pct > 0:
        return +1, f"bullish(verdict={verdict},ev={ev_pct:.1f}%)"
    elif verdict in ("skip",) or ev_pct < 0:
        return -1, f"bearish(verdict={verdict},ev={ev_pct:.1f}%)"
    else:
        # warmup, warn, budget_exceeded — insufficient confidence
        return 0, f"neutral(verdict={verdict},ev={ev_pct:.1f}%)"


def _check_cooldown(conn: sqlite3.Connection, ticker: str, cooldown_hours: int) -> bool:
    """Returns True if position is in cooldown (intent written recently)."""
    cutoff = (now_utc() - timedelta(hours=cooldown_hours)).isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM trade_intents
        WHERE symbol = ?
          AND status LIKE 'manage_%'
          AND created_at >= ?
        """,
        (ticker, cutoff),
    ).fetchone()
    return (row["cnt"] or 0) > 0


def _write_intent(conn: sqlite3.Connection, ticker: str, entry_side: str, status: str, details: Dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO trade_intents (created_at, venue, symbol, side, qty, notional, status, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            "reassess",
            ticker,
            entry_side,
            None,
            None,
            status,
            json.dumps(details),
        ),
    )
    conn.commit()
    return cur.lastrowid


def _update_runtime_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_runtime_state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, now_iso()),
    )
    conn.commit()


def _log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


def reassess_all() -> Dict:
    conn = _connect()

    master_enabled = _get_control(conn, "agent_master_enabled", "0")
    if master_enabled != "1":
        _log("reassess=skipped reason=agent_master_disabled")
        return {"skipped": True}

    cooldown_hours = int(_get_control(conn, "position_manage_intent_cooldown_hours", str(DEFAULT_COOLDOWN_HOURS)))
    liquidity_ttl = DEFAULT_LIQUIDITY_TTL_HOURS

    positions = _get_open_positions(conn)
    _log(f"reassess=start open_positions={len(positions)} cooldown_hours={cooldown_hours}")

    stats = {
        "assessed": 0,
        "hold": 0,
        "tighten": 0,
        "exit": 0,
        "skipped_cooldown": 0,
        "no_data": 0,
        "intents_written": [],
    }

    for pos in positions:
        ticker = pos["ticker"]
        entry_side = pos["entry_side"]  # 'buy' or 'sell'

        # Cooldown check
        if _check_cooldown(conn, ticker, cooldown_hours):
            _log(f"ticker={ticker} side={entry_side} reassess=skipped reason=cooldown")
            stats["skipped_cooldown"] += 1
            continue

        stats["assessed"] += 1

        # Score the 3 signals
        liq_score, liq_reason = _score_liquidity(conn, ticker, entry_side, liquidity_ttl)
        pipe_score, pipe_reason = _score_pipeline(conn, ticker, entry_side)
        kelly_score, kelly_reason = _score_kelly(conn, ticker, entry_side)

        net = liq_score + pipe_score + kelly_score
        signals_detail = {
            "liquidity": {"score": liq_score, "reason": liq_reason},
            "pipeline": {"score": pipe_score, "reason": pipe_reason},
            "kelly": {"score": kelly_score, "reason": kelly_reason},
            "net": net,
        }

        _log(
            f"ticker={ticker} side={entry_side} "
            f"liq={liq_score}({liq_reason}) "
            f"pipe={pipe_score}({pipe_reason}) "
            f"kelly={kelly_score}({kelly_reason}) "
            f"net={net}"
        )

        if net <= EXIT_THRESHOLD:
            # All 3 bearish — aggressive exit
            intent_id = _write_intent(conn, ticker, entry_side, "manage_reduce_or_exit", {
                "reason": "reassess_3of3_bearish",
                "net_score": net,
                "signals": signals_detail,
            })
            _log(f"ticker={ticker} action=manage_reduce_or_exit intent_id={intent_id}")
            stats["exit"] += 1
            stats["intents_written"].append({"ticker": ticker, "action": "exit", "net": net})

        elif net <= TIGHTEN_THRESHOLD:
            # 2-of-3 bearish — tighten trailing stop
            intent_id = _write_intent(conn, ticker, entry_side, "manage_trail_stop_tighten", {
                "reason": "reassess_2of3_bearish",
                "net_score": net,
                "signals": signals_detail,
            })
            _log(f"ticker={ticker} action=manage_trail_stop_tighten intent_id={intent_id}")
            stats["tighten"] += 1
            stats["intents_written"].append({"ticker": ticker, "action": "tighten", "net": net})

        elif net >= HOLD_THRESHOLD:
            # 2-of-3 bullish — hold or consider take profit
            # Write manage_take_profit_major if all 3 bullish (net == +3); else manage_hold
            if net == 3:
                intent_id = _write_intent(conn, ticker, entry_side, "manage_take_profit_major", {
                    "reason": "reassess_3of3_bullish",
                    "net_score": net,
                    "signals": signals_detail,
                })
                _log(f"ticker={ticker} action=manage_take_profit_major intent_id={intent_id}")
                stats["intents_written"].append({"ticker": ticker, "action": "take_profit_major", "net": net})
            else:
                # 2-of-3 bullish — hold, no stop change needed
                _log(f"ticker={ticker} action=hold net={net} (2of3_bullish — no intent written)")
            stats["hold"] += 1

        else:
            # net is -1, 0, or +1 — noise floor, no action
            _log(f"ticker={ticker} action=no_action net={net} (within noise floor)")
            stats["no_data"] += 1

    # Persist summary
    summary = {
        "run_at": now_iso(),
        "open_positions": len(positions),
        **{k: v for k, v in stats.items() if k != "intents_written"},
        "intents_written": len(stats["intents_written"]),
        "actions": stats["intents_written"],
    }
    _update_runtime_state(conn, "reassess_summary", json.dumps(summary))

    _log(
        f"reassess=done assessed={stats['assessed']} "
        f"hold={stats['hold']} tighten={stats['tighten']} exit={stats['exit']} "
        f"skipped_cooldown={stats['skipped_cooldown']}"
    )

    conn.close()
    return summary


if __name__ == "__main__":
    reassess_all()
