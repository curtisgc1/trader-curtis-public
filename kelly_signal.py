#!/usr/bin/env python3
"""
Kelly Signal — position sizing and edge quality scorer.

Implements the framework from _dpg's guide:
  CONVEXITY × EDGE × RISK MANAGEMENT = Kelly-optimal bet sizing

For each active trade candidate, computes:
  p  = win probability  (from quant_validations / source_learning_stats)
  b  = payout ratio     (avg_win_pct / avg_loss_pct from route_outcomes_horizons)
  kelly_f  = (p*b - (1-p)) / b    — full Kelly fraction
  fkelly   = kelly_f * fraction   — fractional Kelly (quarter Kelly default)
  convexity = b                   — payout odds (>2 good, >5 excellent per _dpg)
  ev_pct   = p*avg_win - (1-p)*avg_loss — expected value per trade

Portfolio budget:
  Tracks sum of fractional Kelly across all open positions.
  Alerts when a new trade would push over the portfolio Kelly limit.

Writes to:
  kelly_signals         — per-candidate Kelly scores
  pipeline_runtime_state — portfolio budget summary
"""

import math
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

# Primary horizon for Kelly b calculation — 24h is the _dpg scalp horizon
PRIMARY_HORIZON_HOURS = 24
FALLBACK_HORIZON_HOURS = 6

# Defaults for when data is thin
DEFAULT_PAYOUT_RATIO = 1.5  # conservative: win 1.5x what you lose
GLOBAL_FLOOR_PAYOUT = 1.0   # if avg_win < avg_loss that's the minimum we'll use

# Default controls (overridden by execution_controls table)
DEFAULT_KELLY_FRACTION = 0.25       # quarter Kelly — dpg's "extra humility"
DEFAULT_MAX_PORTFOLIO_KELLY = 0.20  # 20% of capital across all open positions
DEFAULT_MIN_KELLY_TO_TRADE = 0.0    # any positive Kelly is worth considering
DEFAULT_MIN_PAYOUT_RATIO = 1.2      # at least 1.2:1 payout to qualify as convex-ish
DEFAULT_MIN_SAMPLE = 3              # minimum historical samples to trust p estimate


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _ctl(conn: sqlite3.Connection, key: str, default: float) -> float:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    if row and row[0]:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            pass
    return default


def _set_runtime(conn: sqlite3.Connection, key: str, value: str) -> None:
    if not _table_exists(conn, "pipeline_runtime_state"):
        return
    conn.execute(
        """
        INSERT INTO pipeline_runtime_state(key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value),
    )


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kelly_signals (
          id              INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at     TEXT NOT NULL,
          ticker          TEXT NOT NULL,
          direction       TEXT NOT NULL,
          source_tag      TEXT NOT NULL,
          horizon_hours   INTEGER NOT NULL,
          win_prob        REAL NOT NULL,
          avg_win_pct     REAL NOT NULL,
          avg_loss_pct    REAL NOT NULL,
          payout_ratio    REAL NOT NULL,
          kelly_fraction  REAL NOT NULL,
          frac_kelly      REAL NOT NULL,
          convexity_score REAL NOT NULL,
          ev_percent      REAL NOT NULL,
          sample_size     INTEGER NOT NULL,
          verdict         TEXT NOT NULL,
          verdict_reason  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kelly_ticker ON kelly_signals(ticker, direction, computed_at)"
    )
    conn.commit()


def _load_payout_map(conn: sqlite3.Connection) -> Dict[str, Dict[int, Tuple[float, float]]]:
    """
    Load avg win% and avg loss% per source_tag per horizon.
    Returns: {source_tag: {horizon_hours: (avg_win_pct, avg_loss_pct)}}
    """
    result: Dict[str, Dict[int, Tuple[float, float]]] = {}
    if not _table_exists(conn, "route_outcomes_horizons"):
        return result
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          source_tag,
          horizon_hours,
          AVG(CASE WHEN resolution='win' THEN pnl_percent END)         AS avg_win,
          AVG(CASE WHEN resolution='loss' THEN ABS(pnl_percent) END)   AS avg_loss,
          COUNT(CASE WHEN resolution='win' THEN 1 END)                 AS wins,
          COUNT(CASE WHEN resolution='loss' THEN 1 END)                AS losses
        FROM route_outcomes_horizons
        WHERE resolution IN ('win', 'loss')
          AND horizon_hours IN (?, ?)
        GROUP BY source_tag, horizon_hours
        HAVING (wins + losses) >= 1
        """,
        (PRIMARY_HORIZON_HOURS, FALLBACK_HORIZON_HOURS),
    )
    for tag, h_hours, avg_win, avg_loss, _wins, _losses in cur.fetchall():
        t = str(tag or "").strip()
        if not t:
            continue
        if t not in result:
            result[t] = {}
        w = float(avg_win or 0.0) if avg_win is not None else None
        l = float(avg_loss or 0.0) if avg_loss is not None else None
        if w is not None and l is not None and w > 0 and l > 0:
            result[t][int(h_hours)] = (w, l)

    # Global fallback (all sources combined)
    cur.execute(
        """
        SELECT
          horizon_hours,
          AVG(CASE WHEN resolution='win' THEN pnl_percent END)       AS avg_win,
          AVG(CASE WHEN resolution='loss' THEN ABS(pnl_percent) END) AS avg_loss
        FROM route_outcomes_horizons
        WHERE resolution IN ('win', 'loss')
          AND horizon_hours IN (?, ?)
        GROUP BY horizon_hours
        """,
        (PRIMARY_HORIZON_HOURS, FALLBACK_HORIZON_HOURS),
    )
    global_payout: Dict[int, Tuple[float, float]] = {}
    for h_hours, avg_win, avg_loss in cur.fetchall():
        w = float(avg_win or 0.0) if avg_win is not None else None
        l = float(avg_loss or 0.0) if avg_loss is not None else None
        if w is not None and l is not None and w > 0 and l > 0:
            global_payout[int(h_hours)] = (w, l)
    result["__global__"] = global_payout
    return result


def _decay_weighted_win_rate(
    outcomes: List[Tuple[str, float]],
    half_life: float,
) -> Tuple[float, int]:
    """Compute exponentially-decayed win rate from a list of (resolution, pnl_percent) tuples.

    Most recent outcomes are first. Each outcome's weight halves every `half_life` positions.
    Returns (win_rate_0_to_1, effective_sample_size).
    """
    if not outcomes:
        return 0.5, 0

    decay = math.log(2.0) / max(1.0, half_life)
    total_weight = 0.0
    win_weight = 0.0

    for i, (resolution, _pnl) in enumerate(outcomes):
        w = math.exp(-decay * i)
        total_weight += w
        if str(resolution or "").lower() == "win":
            win_weight += w

    if total_weight <= 0:
        return 0.5, 0

    rate = win_weight / total_weight
    # Effective sample size: sum of weights (accounts for decay discounting)
    eff_n = int(round(total_weight))
    return round(rate, 6), max(1, eff_n)


def _get_win_prob(
    conn: sqlite3.Connection,
    source_tag: str,
    ticker: str,
    direction: str,
    decay_half_life: float = 20.0,
) -> Tuple[float, int]:
    """
    Return (win_prob_0_to_1, sample_size) for a source/ticker/direction combo.

    When route_outcomes_horizons has enough data, uses exponential decay weighting
    so recent trades (last ~20) count 3x more than older ones. This makes Kelly
    respond faster after LoRA model swaps.

    Fallback chain: decay-weighted horizons → quant_validations → source_learning_stats → 50% prior
    """
    # Primary: decay-weighted win rate from route_outcomes_horizons (most granular)
    if _table_exists(conn, "route_outcomes_horizons"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT resolution, pnl_percent
            FROM route_outcomes_horizons
            WHERE source_tag = ?
              AND UPPER(COALESCE(ticker, '')) = UPPER(?)
              AND resolution IN ('win', 'loss')
              AND horizon_hours = ?
            ORDER BY evaluated_at DESC
            LIMIT 200
            """,
            (source_tag, ticker, PRIMARY_HORIZON_HOURS),
        )
        rows = [(str(r[0]), float(r[1] or 0.0)) for r in cur.fetchall()]
        if len(rows) >= 3:
            return _decay_weighted_win_rate(rows, decay_half_life)

        # Broaden: same source, any ticker, same direction
        cur.execute(
            """
            SELECT resolution, pnl_percent
            FROM route_outcomes_horizons
            WHERE source_tag = ?
              AND COALESCE(direction, '') = ?
              AND resolution IN ('win', 'loss')
              AND horizon_hours = ?
            ORDER BY evaluated_at DESC
            LIMIT 200
            """,
            (source_tag, direction, PRIMARY_HORIZON_HOURS),
        )
        rows = [(str(r[0]), float(r[1] or 0.0)) for r in cur.fetchall()]
        if len(rows) >= 3:
            return _decay_weighted_win_rate(rows, decay_half_life)

    # Fallback: quant_validations (snapshot win_rate, no decay)
    if _table_exists(conn, "quant_validations"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT win_rate, sample_size FROM quant_validations
            WHERE source_tag=? AND ticker=? AND direction=?
            ORDER BY validated_at DESC LIMIT 1
            """,
            (source_tag, ticker, direction),
        )
        row = cur.fetchone()
        if row and row[1] and int(row[1]) > 0:
            return float(row[0]) / 100.0, int(row[1])

        # Fallback: any ticker for this source + direction
        cur.execute(
            """
            SELECT AVG(win_rate), SUM(sample_size) FROM quant_validations
            WHERE source_tag=? AND direction=?
              AND sample_size >= 1
            """,
            (source_tag, direction),
        )
        row = cur.fetchone()
        if row and row[0] is not None and row[1] and float(row[1]) > 0:
            return float(row[0]) / 100.0, int(row[1])

    # Fallback: source_learning_stats (direction-agnostic)
    if _table_exists(conn, "source_learning_stats"):
        cur = conn.cursor()
        cur.execute(
            "SELECT win_rate, sample_size FROM source_learning_stats WHERE source_tag=? LIMIT 1",
            (source_tag,),
        )
        row = cur.fetchone()
        if row and row[1] and int(row[1]) > 0:
            return float(row[0]) / 100.0, int(row[1])

    # Fallback: simulation engine ensemble estimate (if fresh run exists)
    if _table_exists(conn, "simulation_runs"):
        cur = conn.cursor()
        cur.execute(
            """SELECT result, edge_pct
               FROM simulation_runs
               WHERE layer = 'ensemble' AND contract = ?
                 AND datetime(run_at) > datetime('now', '-24 hours')
               ORDER BY datetime(run_at) DESC LIMIT 1""",
            (ticker,),
        )
        row = cur.fetchone()
        if row and row[0]:
            try:
                import json as _json
                res = _json.loads(row[0])
                sim_prob = float(res.get("ensemble_prob", 0))
                sim_n = int(res.get("effective_n", 0))
                if 0.01 < sim_prob < 0.99 and sim_n > 0:
                    return sim_prob, sim_n
            except Exception:
                pass

    return 0.50, 0  # no data — use 50% as prior (coin flip)


def _get_payout(
    payout_map: Dict,
    source_tag: str,
    horizon_hours: int,
) -> Tuple[float, float, str]:
    """
    Return (avg_win_pct, avg_loss_pct, source_label).
    Tries source-specific → global → hardcoded default.
    """
    # Source-specific at primary horizon
    source_data = payout_map.get(source_tag, {})
    if horizon_hours in source_data:
        w, l = source_data[horizon_hours]
        return w, l, f"source/{horizon_hours}h"

    # Source-specific at fallback horizon
    fallback_h = FALLBACK_HORIZON_HOURS if horizon_hours != FALLBACK_HORIZON_HOURS else PRIMARY_HORIZON_HOURS
    if fallback_h in source_data:
        w, l = source_data[fallback_h]
        return w, l, f"source/{fallback_h}h"

    # Global at primary horizon
    global_data = payout_map.get("__global__", {})
    if horizon_hours in global_data:
        w, l = global_data[horizon_hours]
        return w, l, f"global/{horizon_hours}h"

    # Global at fallback
    if fallback_h in global_data:
        w, l = global_data[fallback_h]
        return w, l, f"global/{fallback_h}h"

    # Hardcoded conservative default
    return DEFAULT_PAYOUT_RATIO * 1.0, 1.0, "default"


def kelly_formula(p: float, b: float) -> float:
    """
    Full Kelly fraction: f* = (p*b - (1-p)) / b = p - (1-p)/b
    Returns the optimal fraction of capital to bet.
    Negative = negative EV, don't bet.
    """
    if b <= 0:
        return -1.0
    return (p * b - (1.0 - p)) / b


def convexity_label(b: float) -> str:
    """_dpg convexity labels — b is payout ratio (win/cost)."""
    if b >= 10.0:
        return "extreme"
    if b >= 5.0:
        return "high"
    if b >= 2.0:
        return "good"
    if b >= 1.2:
        return "moderate"
    if b >= 1.0:
        return "flat"
    return "concave"


def _portfolio_kelly_used(conn: sqlite3.Connection) -> float:
    """
    Sum of frac_kelly across recently computed kelly_signals for currently open positions.
    Uses exchange_trades (open status) joined with latest kelly_signals.
    """
    if not _table_exists(conn, "kelly_signals"):
        return 0.0
    if not _table_exists(conn, "exchange_trades"):
        return 0.0

    # Open positions: exchange_trades where status not in closed states
    cur = conn.cursor()
    cur.execute(
        """
        SELECT et.ticker, et.side
        FROM exchange_trades et
        WHERE et.status NOT IN ('closed', 'cancelled', 'rejected', 'filled_closed')
        GROUP BY et.ticker, et.side
        """
    )
    open_positions = [(r[0], r[1]) for r in cur.fetchall()]
    if not open_positions:
        return 0.0

    total_fkelly = 0.0
    for ticker, side in open_positions:
        direction = "long" if str(side or "").lower() in ("buy", "long") else "short"
        cur.execute(
            """
            SELECT frac_kelly FROM kelly_signals
            WHERE ticker=? AND direction=?
            ORDER BY computed_at DESC LIMIT 1
            """,
            (ticker, direction),
        )
        row = cur.fetchone()
        if row and row[0] and float(row[0]) > 0:
            total_fkelly += float(row[0])

    return round(total_fkelly, 6)


def main() -> int:
    if not DB_PATH.exists():
        print("KELLY_SIGNAL db_missing")
        return 1

    conn = _connect()
    try:
        ensure_table(conn)

        # Load controls
        kelly_fraction = _ctl(conn, "kelly_fraction", DEFAULT_KELLY_FRACTION)
        max_portfolio_kelly = _ctl(conn, "kelly_max_portfolio_frac", DEFAULT_MAX_PORTFOLIO_KELLY)
        min_kelly_to_trade = _ctl(conn, "kelly_min_to_trade", DEFAULT_MIN_KELLY_TO_TRADE)
        min_payout = _ctl(conn, "kelly_min_payout_ratio", DEFAULT_MIN_PAYOUT_RATIO)
        min_sample = int(_ctl(conn, "kelly_min_sample", DEFAULT_MIN_SAMPLE))
        decay_half_life = _ctl(conn, "kelly_decay_half_life", 20.0)

        # Load payout map
        payout_map = _load_payout_map(conn)

        # Portfolio budget
        portfolio_used = _portfolio_kelly_used(conn)
        portfolio_remaining = max(0.0, max_portfolio_kelly - portfolio_used)

        # Load active candidates
        if not _table_exists(conn, "trade_candidates"):
            print("KELLY_SIGNAL candidates_table_missing")
            return 0

        cur = conn.cursor()
        cur.execute(
            """
            SELECT ticker, direction, source_tag, score
            FROM trade_candidates
            WHERE generated_at = (SELECT MAX(generated_at) FROM trade_candidates)
            ORDER BY score DESC
            """,
        )
        candidates = cur.fetchall()

        computed = 0
        positive_ev = 0
        kelly_approved = 0

        for ticker, direction, source_tag, score in candidates:
            ticker = str(ticker or "").strip()
            direction = str(direction or "").strip().lower()
            source_tag = str(source_tag or "").strip()
            if not ticker or not direction or not source_tag:
                continue

            # Get p and b (with exponential decay weighting for model version responsiveness)
            p, sample_size = _get_win_prob(conn, source_tag, ticker, direction, decay_half_life=decay_half_life)
            avg_win, avg_loss, payout_source = _get_payout(payout_map, source_tag, PRIMARY_HORIZON_HOURS)
            b = avg_win / avg_loss if avg_loss > 0 else DEFAULT_PAYOUT_RATIO

            # Kelly formula
            kf = kelly_formula(p, b)
            fkelly = max(0.0, kf * kelly_fraction)

            # EV = p*avg_win - (1-p)*avg_loss
            ev_pct = p * avg_win - (1.0 - p) * avg_loss

            # Convexity
            convexity = b

            # Verdict logic (mirrors _dpg's rules)
            reasons = []
            verdict = "pass"

            if sample_size < min_sample:
                reasons.append(f"thin_data(n={sample_size})")
                verdict = "warmup"  # not enough data — use warmup allowance

            if kf <= 0:
                reasons.append(f"negative_ev(kelly={kf:.3f})")
                verdict = "skip"

            if b < min_payout:
                reasons.append(f"low_convexity(b={b:.2f}<{min_payout})")
                if verdict == "pass":
                    verdict = "warn"

            if fkelly > 0 and (portfolio_used + fkelly) > max_portfolio_kelly:
                reasons.append(f"portfolio_full(used={portfolio_used:.3f}+{fkelly:.3f}>{max_portfolio_kelly})")
                if verdict == "pass":
                    verdict = "budget_exceeded"

            if verdict == "pass" and kf > 0:
                kelly_approved += 1

            if ev_pct > 0:
                positive_ev += 1

            verdict_reason = "; ".join(reasons) if reasons else "ok"

            # Write to kelly_signals
            conn.execute(
                """
                INSERT INTO kelly_signals
                (computed_at, ticker, direction, source_tag, horizon_hours,
                 win_prob, avg_win_pct, avg_loss_pct, payout_ratio,
                 kelly_fraction, frac_kelly, convexity_score, ev_percent,
                 sample_size, verdict, verdict_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(), ticker, direction, source_tag, PRIMARY_HORIZON_HOURS,
                    round(p, 6), round(avg_win, 4), round(avg_loss, 4), round(b, 4),
                    round(kf, 6), round(fkelly, 6), round(convexity, 4), round(ev_pct, 4),
                    sample_size, verdict, verdict_reason,
                ),
            )
            computed += 1

        conn.commit()

        # Write portfolio state to runtime
        _set_runtime(conn, "kelly_portfolio_used", str(round(portfolio_used, 4)))
        _set_runtime(conn, "kelly_portfolio_remaining", str(round(portfolio_remaining, 4)))
        _set_runtime(conn, "kelly_portfolio_max", str(round(max_portfolio_kelly, 4)))
        _set_runtime(conn, "kelly_last_run_utc", now_iso())
        _set_runtime(conn, "kelly_candidates_scored", str(computed))
        conn.commit()

        print(
            f"KELLY_SIGNAL computed={computed} positive_ev={positive_ev} "
            f"kelly_approved={kelly_approved} "
            f"portfolio_used={portfolio_used:.3f} remaining={portfolio_remaining:.3f} "
            f"max={max_portfolio_kelly:.3f}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
