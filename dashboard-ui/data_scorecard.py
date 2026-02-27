"""
Signal scorecard queries for the dashboard.

Provides per-source win rates, direction accuracy, performance trends,
premium hit rates, and weight change history.
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "trades.db"


def _connect():
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    try:
        conn.execute("PRAGMA busy_timeout=20000")
    except Exception:
        pass
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _ctl(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def get_signal_scorecard(
    lookback_days: Optional[int] = None,
    min_samples: Optional[int] = None,
) -> Dict[str, Any]:
    """Per source_tag scorecard: win rate, direction accuracy, trends, premium hit rates."""
    conn = _connect()
    try:
        if lookback_days is None:
            lookback_days = int(float(_ctl(conn, "scorecard_lookback_days", "30") or 30))
        if min_samples is None:
            min_samples = int(float(_ctl(conn, "scorecard_min_samples", "5") or 5))

        green_threshold = float(_ctl(conn, "scorecard_green_threshold", "55") or 55)
        red_threshold = float(_ctl(conn, "scorecard_red_threshold", "45") or 45)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        sources: Dict[str, Dict[str, Any]] = {}
        cur = conn.cursor()

        # Source stats from route_outcomes (traded candidates)
        if _table_exists(conn, "route_outcomes"):
            cur.execute(
                """
                SELECT source_tag,
                       COUNT(*) AS n,
                       SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN resolution='loss' THEN 1 ELSE 0 END) AS losses,
                       AVG(pnl_percent) AS avg_pnl_pct
                FROM route_outcomes
                WHERE datetime(COALESCE(resolved_at, '1970-01-01')) >= datetime(?)
                GROUP BY source_tag
                """,
                (cutoff,),
            )
            for tag, n, wins, losses, avg_pnl in cur.fetchall():
                tag = str(tag or "").strip()
                if not tag:
                    continue
                n = int(n or 0)
                wins = int(wins or 0)
                sources[tag] = {
                    "source_tag": tag,
                    "sample_size": n,
                    "wins": wins,
                    "losses": int(losses or 0),
                    "win_rate": round((wins / n) * 100.0, 1) if n > 0 else 0.0,
                    "avg_pnl_pct": round(float(avg_pnl or 0.0), 2),
                    "data_source": "route_outcomes",
                }

        # Enrich with candidate_horizon_outcomes (all candidates, not just traded)
        if _table_exists(conn, "candidate_horizon_outcomes"):
            cur.execute(
                """
                SELECT candidate_source_tag,
                       COUNT(*) AS n,
                       SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN resolution='loss' THEN 1 ELSE 0 END) AS losses,
                       AVG(pnl_percent) AS avg_pnl_pct,
                       SUM(CASE WHEN candidate_direction IN ('long','buy','bullish') AND pnl_percent > 0 THEN 1
                                WHEN candidate_direction IN ('short','sell','bearish') AND pnl_percent < 0 THEN 1
                                ELSE 0 END) AS dir_correct,
                       COUNT(CASE WHEN candidate_direction NOT IN ('unknown','neutral','') THEN 1 END) AS dir_total
                FROM candidate_horizon_outcomes
                WHERE datetime(COALESCE(evaluated_at, '1970-01-01')) >= datetime(?)
                GROUP BY candidate_source_tag
                """,
                (cutoff,),
            )
            for tag, n, wins, losses, avg_pnl, dir_correct, dir_total in cur.fetchall():
                tag = str(tag or "").strip()
                if not tag:
                    continue
                n = int(n or 0)
                wins = int(wins or 0)
                entry = sources.get(tag, {
                    "source_tag": tag,
                    "sample_size": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "avg_pnl_pct": 0.0,
                    "data_source": "candidate_only",
                })
                entry["candidate_sample_size"] = n
                entry["candidate_wins"] = wins
                entry["candidate_win_rate"] = round((wins / n) * 100.0, 1) if n > 0 else 0.0
                entry["candidate_avg_pnl_pct"] = round(float(avg_pnl or 0.0), 2)
                dir_total = int(dir_total or 0)
                entry["direction_accuracy"] = round((int(dir_correct or 0) / dir_total) * 100.0, 1) if dir_total > 0 else 0.0
                sources[tag] = entry

            # 7-day trend
            cur.execute(
                """
                SELECT candidate_source_tag,
                       COUNT(*) AS n,
                       SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) AS wins
                FROM candidate_horizon_outcomes
                WHERE datetime(COALESCE(evaluated_at, '1970-01-01')) >= datetime(?)
                GROUP BY candidate_source_tag
                """,
                (cutoff_7d,),
            )
            for tag, n, wins in cur.fetchall():
                tag = str(tag or "").strip()
                if tag in sources:
                    n = int(n or 0)
                    sources[tag]["trend_7d_win_rate"] = round((int(wins or 0) / n) * 100.0, 1) if n > 0 else 0.0
                    sources[tag]["trend_7d_samples"] = n

        # Current weights from input_source_controls
        if _table_exists(conn, "input_source_controls"):
            cur.execute(
                """
                SELECT source_key, auto_weight, manual_weight
                FROM input_source_controls
                WHERE source_class = 'source_tag'
                """
            )
            weight_map: Dict[str, Dict[str, float]] = {}
            for key, auto_w, manual_w in cur.fetchall():
                # source_key is "source:tagname"
                tag = str(key or "").replace("source:", "").strip()
                weight_map[tag] = {
                    "auto_weight": round(float(auto_w or 1.0), 4),
                    "manual_weight": round(float(manual_w or 1.0), 4),
                }
            for tag, entry in sources.items():
                w = weight_map.get(tag.lower(), {})
                entry["auto_weight"] = w.get("auto_weight", 1.0)
                entry["manual_weight"] = w.get("manual_weight", 1.0)

        # Compute grade
        for entry in sources.values():
            wr = entry.get("candidate_win_rate", entry.get("win_rate", 0.0))
            total = entry.get("candidate_sample_size", entry.get("sample_size", 0))
            if total < min_samples:
                entry["grade"] = "insufficient_data"
            elif wr >= green_threshold:
                entry["grade"] = "green"
            elif wr <= red_threshold:
                entry["grade"] = "red"
            else:
                entry["grade"] = "yellow"

        result = sorted(sources.values(), key=lambda x: x.get("candidate_win_rate", x.get("win_rate", 0.0)), reverse=True)

        return {
            "ok": True,
            "sources": result,
            "config": {
                "lookback_days": lookback_days,
                "min_samples": min_samples,
                "green_threshold": green_threshold,
                "red_threshold": red_threshold,
            },
        }
    finally:
        conn.close()


def get_source_premium_breakdown(source_tag: str) -> Dict[str, Any]:
    """Per-source breakdown: what % of wins vs losses had each premium signal."""
    conn = _connect()
    try:
        if not _table_exists(conn, "candidate_horizon_outcomes"):
            return {"ok": True, "source_tag": source_tag, "breakdown": {}}

        cur = conn.cursor()
        # This would require evidence_json on candidates, which we don't store in candidate_horizon_outcomes
        # Return basic stats for now
        cur.execute(
            """
            SELECT horizon_hours,
                   COUNT(*) AS n,
                   SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN resolution='loss' THEN 1 ELSE 0 END) AS losses,
                   AVG(pnl_percent) AS avg_pnl
            FROM candidate_horizon_outcomes
            WHERE candidate_source_tag = ?
            GROUP BY horizon_hours
            ORDER BY horizon_hours
            """,
            (source_tag,),
        )
        horizons = []
        for h, n, wins, losses, avg_pnl in cur.fetchall():
            n = int(n or 0)
            horizons.append({
                "horizon_hours": int(h),
                "sample_size": n,
                "wins": int(wins or 0),
                "losses": int(losses or 0),
                "win_rate": round((int(wins or 0) / n) * 100.0, 1) if n > 0 else 0.0,
                "avg_pnl_pct": round(float(avg_pnl or 0.0), 2),
            })

        return {"ok": True, "source_tag": source_tag, "horizons": horizons}
    finally:
        conn.close()


def get_polymarket_scorecard() -> Dict[str, Any]:
    """Per-strategy Polymarket scorecard: win rate, edge analysis, wallet copy performance."""
    conn = _connect()
    try:
        strategies: List[Dict[str, Any]] = []
        cur = conn.cursor()

        all_strategies = [
            "POLY_ALPHA", "POLY_ARB", "POLY_COPY",
            "POLY_MOMENTUM", "POLY_ARB_MICRO", "POLY_OPTIONS_ARB",
        ]

        # Per-strategy win rate from polymarket_orders
        if _table_exists(conn, "polymarket_orders"):
            for strat in all_strategies:
                cur.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN status IN ('filled_live','filled_paper','submitted_paper') THEN 1 ELSE 0 END) AS fills,
                           SUM(CASE WHEN status IN ('submission_failed','cancelled_live') THEN 1 ELSE 0 END) AS fails,
                           AVG(notional) AS avg_notional,
                           SUM(notional) AS total_notional
                    FROM polymarket_orders
                    WHERE strategy_id=?
                      AND datetime(created_at) >= datetime('now', '-30 days')
                    """,
                    (strat,),
                )
                row = cur.fetchone()
                if not row or int(row[0] or 0) == 0:
                    continue
                total = int(row[0] or 0)
                fills = int(row[1] or 0)
                fails = int(row[2] or 0)
                strategies.append({
                    "strategy": strat,
                    "total_orders": total,
                    "fills": fills,
                    "fails": fails,
                    "fill_rate": round((fills / total) * 100.0, 1) if total > 0 else 0.0,
                    "avg_notional": round(float(row[3] or 0), 2),
                    "total_notional": round(float(row[4] or 0), 2),
                })

        # Active arb opportunities count
        active_arb = 0
        if _table_exists(conn, "polymarket_candidates"):
            cur.execute(
                """
                SELECT COUNT(*) FROM polymarket_candidates
                WHERE strategy_id IN ('POLY_ARB', 'POLY_ARB_MICRO')
                  AND status IN ('new', 'approved')
                """
            )
            active_arb = int((cur.fetchone() or [0])[0])

        # Wallet copy performance (per handle)
        wallet_perf: List[Dict[str, Any]] = []
        if _table_exists(conn, "polymarket_orders") and _table_exists(conn, "polymarket_candidates"):
            cur.execute(
                """
                SELECT c.source_tag,
                       COUNT(*) AS n,
                       SUM(CASE WHEN o.status IN ('filled_live','filled_paper','submitted_paper') THEN 1 ELSE 0 END) AS fills,
                       AVG(o.notional) AS avg_notional
                FROM polymarket_orders o
                JOIN polymarket_candidates c ON c.id = o.candidate_id
                WHERE c.strategy_id = 'POLY_COPY'
                  AND datetime(o.created_at) >= datetime('now', '-30 days')
                GROUP BY c.source_tag
                ORDER BY fills DESC
                LIMIT 20
                """
            )
            for tag, n, fills, avg_n in cur.fetchall():
                n = int(n or 0)
                wallet_perf.append({
                    "source_tag": str(tag or ""),
                    "total": n,
                    "fills": int(fills or 0),
                    "fill_rate": round((int(fills or 0) / n) * 100.0, 1) if n > 0 else 0.0,
                    "avg_notional": round(float(avg_n or 0), 2),
                })

        # Avg edge at entry
        avg_edge = 0.0
        if _table_exists(conn, "polymarket_candidates"):
            cur.execute(
                """
                SELECT AVG(ABS(edge))
                FROM polymarket_candidates
                WHERE datetime(created_at) >= datetime('now', '-7 days')
                  AND status NOT IN ('new', 'awaiting_approval')
                """
            )
            row = cur.fetchone()
            avg_edge = round(float((row or [0])[0] or 0), 2)

        return {
            "ok": True,
            "strategies": strategies,
            "active_arb_opportunities": active_arb,
            "wallet_copy_performance": wallet_perf,
            "avg_edge_at_entry": avg_edge,
        }
    finally:
        conn.close()


def get_weight_change_history(limit: int = 50) -> Dict[str, Any]:
    """Return recent weight change log entries."""
    conn = _connect()
    try:
        if not _table_exists(conn, "weight_change_log"):
            return {"ok": True, "changes": []}

        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, changed_at, source_key, old_auto_weight, new_auto_weight,
                   reason, sample_size, win_rate
            FROM weight_change_log
            ORDER BY datetime(changed_at) DESC
            LIMIT ?
            """,
            (limit,),
        )
        changes = []
        for row in cur.fetchall():
            changes.append({
                "id": int(row[0]),
                "changed_at": str(row[1] or ""),
                "source_key": str(row[2] or ""),
                "old_auto_weight": round(float(row[3] or 0.0), 4),
                "new_auto_weight": round(float(row[4] or 0.0), 4),
                "reason": str(row[5] or ""),
                "sample_size": int(row[6] or 0),
                "win_rate": round(float(row[7] or 0.0), 1),
            })

        return {"ok": True, "changes": changes}
    finally:
        conn.close()
