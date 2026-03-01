#!/usr/bin/env python3
"""
Quant validation gate for candidate routing.
Builds evidence-based checks before an order is queued.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from typing import Dict, List, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

DEFAULT_THRESHOLDS = {
    "min_sample_size": 3,
    "min_expected_value_pct": 0.0,
    "min_win_rate_pct": 45.0,
    "max_volatility_pct": 12.0,
    "max_drawdown_pct": 35.0,
    "max_corr_to_open_book": 0.85,
    "min_regime_score": 0.35,
    "min_sharpe_ratio": 0.5,
}
WARMUP_ALLOW_NO_SAMPLE = True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quant_validations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          validated_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          candidate_score REAL NOT NULL,
          sample_size INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL,
          expected_value_percent REAL NOT NULL,
          volatility_percent REAL NOT NULL,
          max_drawdown_percent REAL NOT NULL,
          corr_to_open_book REAL NOT NULL,
          regime_score REAL NOT NULL,
          passed INTEGER NOT NULL,
          reason TEXT NOT NULL
        )
        """
    )
    if not column_exists(conn, "quant_validations", "sharpe_ratio"):
        conn.execute("ALTER TABLE quant_validations ADD COLUMN sharpe_ratio REAL DEFAULT 0")
    conn.commit()


def _history_pnl_series(conn: sqlite3.Connection, ticker: str, source_tag: str, limit: int = 500) -> List[float]:
    if not table_exists(conn, "route_outcomes"):
        return []
    cur = conn.cursor()
    # Prefer same ticker history. Fall back to source_tag history.
    cur.execute(
        """
        SELECT pnl_percent
        FROM route_outcomes
        WHERE upper(COALESCE(ticker,'')) = upper(?)
        ORDER BY resolved_at DESC
        LIMIT ?
        """,
        (ticker, int(limit)),
    )
    rows = [float(r[0] or 0.0) for r in cur.fetchall()]
    if rows:
        return rows
    cur.execute(
        """
        SELECT pnl_percent
        FROM route_outcomes
        WHERE COALESCE(source_tag,'') = ?
        ORDER BY resolved_at DESC
        LIMIT ?
        """,
        (source_tag, int(limit)),
    )
    return [float(r[0] or 0.0) for r in cur.fetchall()]


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


def _corr_to_open_book(conn: sqlite3.Connection, ticker: str) -> float:
    if not table_exists(conn, "trades"):
        return 0.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM trades
        WHERE lower(COALESCE(status,'')) IN ('open','live')
        """
    )
    open_total = int((cur.fetchone() or [0])[0] or 0)
    if open_total <= 0:
        return 0.0
    cur.execute(
        """
        SELECT COUNT(*)
        FROM trades
        WHERE lower(COALESCE(status,'')) IN ('open','live')
          AND upper(COALESCE(ticker,'')) = upper(?)
        """,
        (ticker,),
    )
    same_ticker = int((cur.fetchone() or [0])[0] or 0)
    if same_ticker > 0:
        return 1.0
    # Conservative concentration proxy when any open positions exist.
    return min(0.8, round(0.25 + (open_total * 0.05), 4))


def _simulation_regime_boost(conn: sqlite3.Connection, ticker: str) -> float:
    """Boost regime_score when ensemble simulation shows edge > 10%."""
    if not table_exists(conn, "simulation_runs"):
        return 0.0
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT edge_pct FROM simulation_runs
               WHERE layer = 'ensemble' AND (contract = ? OR ticker = ?)
                 AND datetime(run_at) > datetime('now', '-24 hours')
               ORDER BY datetime(run_at) DESC LIMIT 1""",
            (ticker, ticker),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            edge = float(row[0])
            if edge > 10.0:
                return min(0.2, edge / 100.0)
    except Exception:
        pass
    return 0.0


def _regime_score(conn: sqlite3.Connection, ticker: str, direction: str) -> float:
    score = 0.5
    if not table_exists(conn, "event_alerts"):
        return max(0.0, min(1.0, round(score + _simulation_regime_boost(conn, ticker), 4)))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(proposed_asset,''), COALESCE(direction,''), COALESCE(priority,'')
        FROM event_alerts
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    for asset, evt_dir, priority in cur.fetchall():
        asset_u = str(asset).upper()
        if asset_u == str(ticker).upper():
            score += 0.15
            if str(evt_dir).lower() == str(direction).lower():
                score += 0.1
            if str(priority).lower() in {"high", "critical"}:
                score += 0.1
            break
    score += _simulation_regime_boost(conn, ticker)
    return max(0.0, min(1.0, round(score, 4)))


def evaluate_quant_candidate(
    conn: sqlite3.Connection,
    ticker: str,
    direction: str,
    source_tag: str,
    candidate_score: float,
) -> Tuple[bool, str, Dict]:
    ensure_tables(conn)
    series = _history_pnl_series(conn, ticker=ticker, source_tag=source_tag)
    n = len(series)
    wins = len([x for x in series if x > 0])
    losses = len([x for x in series if x < 0])
    pushes = n - wins - losses
    win_rate = round((wins / n) * 100.0, 4) if n else 0.0
    avg_pnl = round(sum(series) / n, 4) if n else 0.0
    avg_win = (sum(x for x in series if x > 0) / wins) if wins else 0.0
    avg_loss = (sum(x for x in series if x < 0) / losses) if losses else 0.0
    p_win = (wins / n) if n else 0.0
    p_loss = (losses / n) if n else 0.0
    ev = round((p_win * avg_win) + (p_loss * avg_loss), 4)
    vol = round(float(pstdev(series)) if n > 1 else 0.0, 4)
    sharpe = round(avg_pnl / vol, 4) if vol > 0 else 0.0
    max_dd = _max_drawdown_pct(series)
    corr_open_book = _corr_to_open_book(conn, ticker=ticker)
    regime = _regime_score(conn, ticker=ticker, direction=direction)

    reasons: List[str] = []
    th = DEFAULT_THRESHOLDS
    if n < th["min_sample_size"]:
        if WARMUP_ALLOW_NO_SAMPLE:
            reasons.append("warmup_low_sample")
        else:
            reasons.append(f"sample<{th['min_sample_size']}")
    if ev < th["min_expected_value_pct"]:
        reasons.append("ev<0")
    if n >= th["min_sample_size"] and win_rate < th["min_win_rate_pct"]:
        reasons.append(f"win_rate<{th['min_win_rate_pct']}")
    if vol > th["max_volatility_pct"]:
        reasons.append(f"vol>{th['max_volatility_pct']}")
    if max_dd > th["max_drawdown_pct"]:
        reasons.append(f"drawdown>{th['max_drawdown_pct']}")
    if n >= th["min_sample_size"] and sharpe < th["min_sharpe_ratio"]:
        reasons.append(f"sharpe<{th['min_sharpe_ratio']}")
    if corr_open_book > th["max_corr_to_open_book"]:
        reasons.append("corr_open_book_high")
    if regime < th["min_regime_score"]:
        reasons.append("regime_weak")

    hard_fail_reasons = [r for r in reasons if not r.startswith("warmup_")]
    passed = len(hard_fail_reasons) == 0
    reason = "quant pass" if passed and not reasons else ";".join(reasons)
    metrics = {
        "sample_size": n,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": win_rate,
        "avg_pnl_percent": avg_pnl,
        "expected_value_percent": ev,
        "volatility_percent": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown_percent": max_dd,
        "corr_to_open_book": corr_open_book,
        "regime_score": regime,
    }

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO quant_validations
        (
          validated_at, ticker, direction, source_tag, candidate_score, sample_size, win_rate,
          avg_pnl_percent, expected_value_percent, volatility_percent, sharpe_ratio,
          max_drawdown_percent, corr_to_open_book, regime_score, passed, reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            ticker,
            direction,
            source_tag,
            float(candidate_score),
            int(metrics["sample_size"]),
            float(metrics["win_rate"]),
            float(metrics["avg_pnl_percent"]),
            float(metrics["expected_value_percent"]),
            float(metrics["volatility_percent"]),
            float(metrics["sharpe_ratio"]),
            float(metrics["max_drawdown_percent"]),
            float(metrics["corr_to_open_book"]),
            float(metrics["regime_score"]),
            1 if passed else 0,
            reason[:200],
        ),
    )
    validation_id = int(cur.lastrowid)
    conn.commit()
    metrics["validation_id"] = validation_id
    return passed, reason, metrics
