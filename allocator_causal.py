#!/usr/bin/env python3
"""
Causal Alpha Allocator (CAA)

Adaptive sizing layer for routed candidates:
- Bayesian posterior over source + strategy outcomes
- Simple regime inference from recent outcomes/quant pass-rate
- Scale score/notional and optionally block persistent low-edge sources
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


@dataclass
class AllocationResult:
    allowed: bool
    adjusted_score: float
    adjusted_notional: float
    factor: float
    regime: str
    strategy_tag: str
    reason: str
    source_n: int
    strategy_n: int
    source_mean: float
    strategy_mean: float


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS allocator_decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          strategy_tag TEXT NOT NULL,
          regime TEXT NOT NULL,
          base_score REAL NOT NULL,
          adjusted_score REAL NOT NULL,
          base_notional REAL NOT NULL,
          adjusted_notional REAL NOT NULL,
          factor REAL NOT NULL,
          allowed INTEGER NOT NULL,
          reason TEXT NOT NULL,
          source_n INTEGER NOT NULL DEFAULT 0,
          strategy_n INTEGER NOT NULL DEFAULT 0,
          source_mean REAL NOT NULL DEFAULT 0.5,
          strategy_mean REAL NOT NULL DEFAULT 0.5
        )
        """
    )
    conn.commit()


def strategy_for(source_tag: str) -> str:
    src = str(source_tag or "").strip().upper()
    if not src:
        return "UNSPECIFIED"
    if src.startswith("POLY_"):
        return src.split(":", 1)[0]
    if src in {"A_SCALP", "B_LONGTERM", "C_EVENT", "D_BOOKMARKS", "E_BREAKTHROUGH"}:
        return src
    if "BREAKTHROUGH" in src:
        return "E_BREAKTHROUGH"
    return "UNSPECIFIED"


def _posterior_from_stats(wins: int, losses: int) -> float:
    # Beta(1,1) prior.
    return (wins + 1.0) / (wins + losses + 2.0)


def _lookup_source_stats(conn: sqlite3.Connection, source_tag: str) -> Tuple[int, int, int]:
    if _table_exists(conn, "source_learning_stats"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sample_size, wins, losses
            FROM source_learning_stats
            WHERE source_tag=?
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (source_tag,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    if _table_exists(conn, "route_outcomes"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN resolution='loss' THEN 1 ELSE 0 END)
            FROM route_outcomes
            WHERE source_tag=?
              AND datetime(COALESCE(resolved_at, '1970-01-01')) >= datetime('now', '-60 day')
            """,
            (source_tag,),
        )
        row = cur.fetchone() or (0, 0, 0)
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    return 0, 0, 0


def _lookup_strategy_stats(conn: sqlite3.Connection, strategy_tag: str) -> Tuple[int, int, int]:
    if _table_exists(conn, "strategy_learning_stats"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sample_size, wins, losses
            FROM strategy_learning_stats
            WHERE strategy_tag=?
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (strategy_tag,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    return 0, 0, 0


def infer_regime(conn: sqlite3.Connection) -> str:
    override = _control(conn, "allocator_regime_override", "auto").strip().lower()
    if override in {"risk_on", "risk_off", "neutral"}:
        return override

    win_rate = 50.0
    avg_pnl_pct = 0.0
    n = 0
    if _table_exists(conn, "route_outcomes"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END),
                   AVG(COALESCE(pnl_percent,0))
            FROM route_outcomes
            WHERE datetime(COALESCE(resolved_at, '1970-01-01')) >= datetime('now', '-14 day')
            """
        )
        row = cur.fetchone() or (0, 0, 0.0)
        n = int(row[0] or 0)
        wins = int(row[1] or 0)
        win_rate = (wins / n * 100.0) if n > 0 else 50.0
        avg_pnl_pct = float(row[2] or 0.0)

    quant_pass = 0.5
    if _table_exists(conn, "quant_validations"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT AVG(CASE WHEN passed=1 THEN 1.0 ELSE 0.0 END)
            FROM quant_validations
            WHERE datetime(COALESCE(validated_at, '1970-01-01')) >= datetime('now', '-24 hour')
            """
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            quant_pass = float(row[0])

    if (n >= 20 and (win_rate < 42.0 or avg_pnl_pct < -0.15)) or quant_pass < 0.35:
        return "risk_off"
    if (n >= 20 and (win_rate > 56.0 and avg_pnl_pct > 0.05)) and quant_pass > 0.60:
        return "risk_on"
    return "neutral"


def allocate_candidate(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    direction: str,
    source_tag: str,
    candidate_score: float,
    proposed_notional: float,
) -> AllocationResult:
    enabled = _control(conn, "enable_allocator_causal", "1") == "1"
    strategy_tag = strategy_for(source_tag)
    if not enabled:
        return AllocationResult(
            allowed=True,
            adjusted_score=float(candidate_score),
            adjusted_notional=float(proposed_notional),
            factor=1.0,
            regime="neutral",
            strategy_tag=strategy_tag,
            reason="allocator disabled",
            source_n=0,
            strategy_n=0,
            source_mean=0.5,
            strategy_mean=0.5,
        )

    regime = infer_regime(conn)
    regime_factor = {"risk_off": 0.72, "neutral": 1.0, "risk_on": 1.16}.get(regime, 1.0)

    src_n, src_w, src_l = _lookup_source_stats(conn, source_tag)
    strat_n, strat_w, strat_l = _lookup_strategy_stats(conn, strategy_tag)
    src_mean = _posterior_from_stats(src_w, src_l)
    strat_mean = _posterior_from_stats(strat_w, strat_l)

    src_conf = min(1.0, src_n / 20.0) if src_n > 0 else 0.0
    strat_conf = min(1.0, strat_n / 24.0) if strat_n > 0 else 0.0

    src_factor = 1.0 + ((src_mean - 0.5) * 0.70 * src_conf)
    strat_factor = 1.0 + ((strat_mean - 0.5) * 0.50 * strat_conf)

    novelty_factor = 1.0
    if strategy_tag == "E_BREAKTHROUGH":
        novelty_factor = 1.06
    elif strategy_tag == "B_LONGTERM":
        novelty_factor = 1.03

    factor = regime_factor * src_factor * strat_factor * novelty_factor
    max_up = float(_control(conn, "allocator_max_scale_up", "1.35") or 1.35)
    max_down = float(_control(conn, "allocator_max_scale_down", "0.60") or 0.60)
    if factor > max_up:
        factor = max_up
    if factor < max_down:
        factor = max_down

    block_floor = float(_control(conn, "allocator_block_posterior_floor", "0.35") or 0.35)
    min_samples = int(float(_control(conn, "allocator_min_source_samples", "12") or 12))
    allowed = True
    reason = f"regime={regime}; src_mean={src_mean:.3f}({src_n}); strat_mean={strat_mean:.3f}({strat_n}); factor={factor:.3f}"

    if src_n >= min_samples and src_mean < block_floor:
        allowed = False
        reason = f"allocator block: low source posterior {src_mean:.3f} on n={src_n} (<{block_floor:.2f})"

    adj_notional = float(proposed_notional) * factor
    max_signal = float(_control(conn, "max_signal_notional_usd", "150") or 150.0)
    if adj_notional > max_signal:
        adj_notional = max_signal
    if adj_notional < 1.0:
        adj_notional = 1.0

    score_boost = 1.0 + ((factor - 1.0) * 0.45)
    adj_score = max(0.0, min(100.0, float(candidate_score) * score_boost))

    return AllocationResult(
        allowed=allowed,
        adjusted_score=round(adj_score, 4),
        adjusted_notional=round(adj_notional, 4),
        factor=round(factor, 4),
        regime=regime,
        strategy_tag=strategy_tag,
        reason=reason,
        source_n=src_n,
        strategy_n=strat_n,
        source_mean=round(src_mean, 4),
        strategy_mean=round(strat_mean, 4),
    )


def log_allocator_decision(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    direction: str,
    source_tag: str,
    result: AllocationResult,
    base_score: float,
    base_notional: float,
) -> None:
    conn.execute(
        """
        INSERT INTO allocator_decisions
        (created_at, ticker, direction, source_tag, strategy_tag, regime,
         base_score, adjusted_score, base_notional, adjusted_notional, factor,
         allowed, reason, source_n, strategy_n, source_mean, strategy_mean)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            ticker,
            direction,
            source_tag or "",
            result.strategy_tag,
            result.regime,
            float(base_score),
            float(result.adjusted_score),
            float(base_notional),
            float(result.adjusted_notional),
            float(result.factor),
            1 if result.allowed else 0,
            result.reason[:240],
            int(result.source_n),
            int(result.strategy_n),
            float(result.source_mean),
            float(result.strategy_mean),
        ),
    )
    conn.commit()

