#!/usr/bin/env python3
"""
Automated paper-to-live venue promotion.

Checks per-venue source performance against configurable thresholds
and auto-promotes venues from paper to live when criteria are met.

Safety:
  - Only promotes paper -> live, never demotes
  - Requires auto_promote_enabled=1 in execution_controls (default off)
  - 7-day cooldown after last promotion per venue
  - Audit trail in venue_promotion_log table
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import pstdev
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

DEFAULT_PROMOTE_THRESHOLDS = {
    "promote_min_paper_trades": 20,
    "promote_min_win_rate": 50.0,
    "promote_min_sharpe": 1.0,
    "promote_max_drawdown": 25.0,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH), timeout=10)


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS venue_promotion_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          promoted_at TEXT NOT NULL,
          venue TEXT NOT NULL,
          old_mode TEXT NOT NULL,
          new_mode TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          sharpe REAL NOT NULL,
          max_drawdown REAL NOT NULL
        )
        """
    )
    conn.commit()


def _get_control(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    cur = conn.cursor()
    cur.execute(
        "SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,)
    )
    row = cur.fetchone()
    return str(row[0]) if row else default


def _get_thresholds(conn: sqlite3.Connection) -> Dict[str, float]:
    result = {}
    for key, default_val in DEFAULT_PROMOTE_THRESHOLDS.items():
        raw = _get_control(conn, key, str(default_val))
        try:
            result[key] = float(raw)
        except (ValueError, TypeError):
            result[key] = default_val
    return result


def _venue_for_ticker(ticker: str) -> str:
    crypto = {
        "BTC", "ETH", "SOL", "DOGE", "LTC", "XRP", "ADA",
        "AVAX", "DOT", "LINK", "MATIC", "BNB",
    }
    upper = str(ticker).upper().replace("/USD", "").replace("-USD", "")
    return "crypto" if upper in crypto else "stocks"


def _max_drawdown_pct(series: List[float]) -> float:
    if not series:
        return 0.0
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for x in reversed(series):
        cumulative += float(x)
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_dd = max(max_dd, drawdown)
    return round(max_dd, 4)


def _compute_venue_stats(
    conn: sqlite3.Connection, venue: str, lookback_days: int = 30
) -> Optional[Dict]:
    cur = conn.cursor()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).isoformat()

    cur.execute(
        """
        SELECT ticker, pnl_percent, resolution
        FROM route_outcomes
        WHERE resolved_at >= ?
        """,
        (cutoff,),
    )
    rows = cur.fetchall()

    venue_pnls: List[float] = []
    wins = 0
    losses = 0
    for ticker, pnl_pct, resolution in rows:
        if _venue_for_ticker(str(ticker)) != venue:
            continue
        venue_pnls.append(float(pnl_pct or 0.0))
        if resolution == "win":
            wins += 1
        elif resolution == "loss":
            losses += 1

    n = len(venue_pnls)
    if n == 0:
        return None

    win_rate = round((wins / n) * 100.0, 4)
    avg_pnl = sum(venue_pnls) / n
    vol = pstdev(venue_pnls) if n > 1 else 0.0
    sharpe = round(avg_pnl / vol, 4) if vol > 0 else 0.0
    max_dd = _max_drawdown_pct(venue_pnls)

    return {
        "sample_size": n,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
    }


def _last_promotion_at(conn: sqlite3.Connection, venue: str) -> Optional[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT promoted_at FROM venue_promotion_log WHERE venue=? ORDER BY promoted_at DESC LIMIT 1",
        (venue,),
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


def _within_cooldown(last_promoted: Optional[str], cooldown_days: int = 7) -> bool:
    if not last_promoted:
        return False
    try:
        last_dt = datetime.fromisoformat(last_promoted)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_dt < timedelta(days=cooldown_days)
    except (ValueError, TypeError):
        return True


def run_promotion() -> None:
    if not DB_PATH.exists():
        print("DB not found, skipping venue promotion")
        return

    conn = _connect()
    try:
        _ensure_tables(conn)

        enabled = _get_control(conn, "auto_promote_enabled", "0")
        if str(enabled).strip() != "1":
            print("auto_promote_enabled not set — skipping venue promotion")
            return

        thresholds = _get_thresholds(conn)

        cur = conn.cursor()
        cur.execute(
            "SELECT venue, mode FROM venue_matrix WHERE enabled=1 ORDER BY venue"
        )
        venues = cur.fetchall()

        promoted_count = 0
        for venue, mode in venues:
            if str(mode).lower() != "paper":
                continue

            if _within_cooldown(_last_promotion_at(conn, venue)):
                print(f"  {venue}: cooldown active, skipping")
                continue

            stats = _compute_venue_stats(conn, venue)
            if stats is None:
                print(f"  {venue}: no recent trades, skipping")
                continue

            reasons: List[str] = []
            if stats["sample_size"] < thresholds["promote_min_paper_trades"]:
                reasons.append(
                    f"trades={stats['sample_size']}<{int(thresholds['promote_min_paper_trades'])}"
                )
            if stats["win_rate"] < thresholds["promote_min_win_rate"]:
                reasons.append(
                    f"win_rate={stats['win_rate']:.1f}<{thresholds['promote_min_win_rate']}"
                )
            if stats["sharpe"] < thresholds["promote_min_sharpe"]:
                reasons.append(
                    f"sharpe={stats['sharpe']:.2f}<{thresholds['promote_min_sharpe']}"
                )
            if stats["max_drawdown"] > thresholds["promote_max_drawdown"]:
                reasons.append(
                    f"drawdown={stats['max_drawdown']:.1f}>{thresholds['promote_max_drawdown']}"
                )

            if reasons:
                print(f"  {venue}: not eligible — {'; '.join(reasons)}")
                continue

            cur.execute(
                "UPDATE venue_matrix SET mode='live', updated_at=datetime('now') WHERE venue=?",
                (venue,),
            )
            cur.execute(
                """
                INSERT INTO venue_promotion_log
                (promoted_at, venue, old_mode, new_mode, sample_size, win_rate, sharpe, max_drawdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    venue,
                    "paper",
                    "live",
                    stats["sample_size"],
                    stats["win_rate"],
                    stats["sharpe"],
                    stats["max_drawdown"],
                ),
            )
            conn.commit()
            promoted_count += 1
            print(
                f"  {venue}: PROMOTED paper -> live "
                f"(n={stats['sample_size']}, wr={stats['win_rate']:.1f}%, "
                f"sharpe={stats['sharpe']:.2f}, dd={stats['max_drawdown']:.1f}%)"
            )

        if promoted_count == 0:
            print("No venues promoted this cycle")
        else:
            print(f"Promoted {promoted_count} venue(s)")
    finally:
        conn.close()


if __name__ == "__main__":
    run_promotion()
