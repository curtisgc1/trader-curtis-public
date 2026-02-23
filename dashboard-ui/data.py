import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "trades.db"
BOOKMARKS_PATH = BASE_DIR / "docs" / "x-bookmarks.json"
LOG_DIR = BASE_DIR / "dashboard-ui" / "logs"

PATTERN_RELIABILITY = {
    "qml": 0.75,
    "institutional_reversal": 0.74,
    "flag_limit": 0.73,
    "liquidity_grab": 0.72,
    "supply_demand_flip": 0.70,
    "stop_hunt": 0.70,
    "fakeout": 0.68,
    "compression_expansion": 0.65,
}


def _connect():
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _rows_to_dicts(cur: sqlite3.Cursor, rows: List[tuple]) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # sqlite datetime('now') format
    if "T" not in s and " " in s:
        s = s.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _latest_value(conn: sqlite3.Connection, table: str, col: str) -> Optional[str]:
    if not _table_exists(conn, table):
        return None
    cur = conn.cursor()
    cur.execute(f"SELECT MAX({col}) FROM {table}")
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _age_minutes(ts: Optional[str]) -> Optional[float]:
    dt = _parse_ts(ts)
    if not dt:
        return None
    delta = datetime.now(timezone.utc) - dt
    return round(delta.total_seconds() / 60.0, 2)


def get_learning_health(lookback_days: int = 7) -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "lookback_days": lookback_days,
            "eligible_routes": 0,
            "tracked_routes": 0,
            "resolved_routes": 0,
            "realized_routes": 0,
            "operational_routes": 0,
            "unresolved_routes": 0,
            "tracked_unresolved_routes": 0,
            "tracked_coverage_pct": 0.0,
            "coverage_pct": 0.0,
            "realized_win_rate": 0.0,
            "realized_avg_pnl_pct": 0.0,
        }

    conn = _connect()
    try:
        if not _table_exists(conn, "signal_routes"):
            return {
                "lookback_days": lookback_days,
                "eligible_routes": 0,
                "tracked_routes": 0,
                "resolved_routes": 0,
                "realized_routes": 0,
                "operational_routes": 0,
                "unresolved_routes": 0,
                "tracked_unresolved_routes": 0,
                "tracked_coverage_pct": 0.0,
                "coverage_pct": 0.0,
                "realized_win_rate": 0.0,
                "realized_avg_pnl_pct": 0.0,
            }

        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM signal_routes
            WHERE decision='approved'
              AND datetime(COALESCE(routed_at, '1970-01-01')) >= datetime('now', ?)
            """,
            (f"-{int(lookback_days)} day",),
        )
        eligible = int((cur.fetchone() or [0])[0] or 0)

        if eligible == 0 or not _table_exists(conn, "route_outcomes"):
            return {
                "lookback_days": lookback_days,
                "eligible_routes": eligible,
                "tracked_routes": 0,
                "resolved_routes": 0,
                "realized_routes": 0,
                "operational_routes": 0,
                "unresolved_routes": eligible,
                "tracked_unresolved_routes": 0,
                "tracked_coverage_pct": 0.0,
                "coverage_pct": 0.0,
                "realized_win_rate": 0.0,
                "realized_avg_pnl_pct": 0.0,
            }

        tracked_routes = 0
        if _table_exists(conn, "route_trade_links"):
            cur.execute(
                """
                SELECT COUNT(*)
                FROM route_trade_links l
                JOIN signal_routes r ON r.id = l.route_id
                WHERE r.decision='approved'
                  AND datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', ?)
                """,
                (f"-{int(lookback_days)} day",),
            )
            tracked_routes = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
            SELECT
              COUNT(*) AS resolved_routes,
              SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' THEN 1 ELSE 0 END) AS realized_routes,
              SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='operational' THEN 1 ELSE 0 END) AS operational_routes,
              SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' AND o.resolution='win' THEN 1 ELSE 0 END) AS realized_wins,
              AVG(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' THEN o.pnl_percent END) AS realized_avg_pnl_pct
            FROM route_outcomes o
            JOIN signal_routes r ON r.id = o.route_id
            WHERE r.decision='approved'
              AND datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', ?)
            """,
            (f"-{int(lookback_days)} day",),
        )
        row = cur.fetchone() or (0, 0, 0, 0, 0.0)
        resolved_routes = int(row[0] or 0)
        realized_routes = int(row[1] or 0)
        operational_routes = int(row[2] or 0)
        realized_wins = int(row[3] or 0)
        realized_avg_pnl_pct = float(row[4] or 0.0)
        unresolved_routes = max(0, eligible - resolved_routes)
        coverage_pct = round((resolved_routes / eligible) * 100.0, 2) if eligible else 0.0
        tracked_coverage_pct = round((tracked_routes / eligible) * 100.0, 2) if eligible else 0.0
        tracked_unresolved_routes = max(0, tracked_routes - resolved_routes)
        realized_win_rate = round((realized_wins / realized_routes) * 100.0, 2) if realized_routes else 0.0

        return {
            "lookback_days": lookback_days,
            "eligible_routes": eligible,
            "tracked_routes": tracked_routes,
            "resolved_routes": resolved_routes,
            "realized_routes": realized_routes,
            "operational_routes": operational_routes,
            "unresolved_routes": unresolved_routes,
            "tracked_unresolved_routes": tracked_unresolved_routes,
            "tracked_coverage_pct": tracked_coverage_pct,
            "coverage_pct": coverage_pct,
            "realized_win_rate": realized_win_rate,
            "realized_avg_pnl_pct": round(realized_avg_pnl_pct, 4),
        }
    finally:
        conn.close()


def get_trades(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "trades"):
            return []
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def get_patterns(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "institutional_patterns"):
            return []
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM institutional_patterns ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def get_copy_trades(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "copy_trades"):
            return []
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM copy_trades ORDER BY call_timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def get_summary() -> Dict[str, Any]:
    trades = get_trades(limit=1000)
    total = len(trades)
    wins = len([t for t in trades if isinstance(t.get("pnl"), (int, float)) and t.get("pnl", 0) > 0])
    losses = len([t for t in trades if isinstance(t.get("pnl"), (int, float)) and t.get("pnl", 0) < 0])
    win_rate = round((wins / total) * 100, 2) if total else 0.0
    avg_pnl = 0.0
    if total:
        pnls = [t.get("pnl", 0) or 0 for t in trades]
        avg_pnl = round(sum(pnls) / max(len(pnls), 1), 2)

    open_trades = [t for t in trades if (t.get("status") or "").lower() in ("open", "live")]
    last_trade = trades[0] if trades else None

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "open_trades": len(open_trades),
        "last_trade": last_trade,
    }


def get_system_health() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "overall": "bad",
            "message": "trades.db missing",
            "checks": [],
        }

    conn = _connect()
    try:
        checks: List[Dict[str, Any]] = []

        pipeline_ts = _latest_value(conn, "pipeline_signals", "generated_at")
        route_ts = _latest_value(conn, "signal_routes", "routed_at")
        exec_ts = _latest_value(conn, "execution_orders", "created_at")

        pipeline_age = _age_minutes(pipeline_ts)
        route_age = _age_minutes(route_ts)
        exec_age = _age_minutes(exec_ts)

        def freshness_state(age: Optional[float]) -> str:
            if age is None:
                return "bad"
            if age <= 180:
                return "good"
            if age <= 360:
                return "warn"
            return "bad"

        checks.append({"name": "Pipeline Freshness", "state": freshness_state(pipeline_age), "detail": f"{pipeline_age} min ago" if pipeline_age is not None else "no data"})
        checks.append({"name": "Routing Freshness", "state": freshness_state(route_age), "detail": f"{route_age} min ago" if route_age is not None else "no data"})
        checks.append({"name": "Execution Freshness", "state": freshness_state(exec_age), "detail": f"{exec_age} min ago" if exec_age is not None else "no data"})

        learning = get_learning_health(lookback_days=7)
        coverage = float(learning.get("coverage_pct") or 0.0)
        tracked_coverage = float(learning.get("tracked_coverage_pct") or 0.0)
        eligible = int(learning.get("eligible_routes") or 0)
        if eligible == 0:
            learning_state = "warn"
        elif coverage >= 70:
            learning_state = "good"
        elif tracked_coverage >= 70:
            learning_state = "warn"
        elif coverage >= 40:
            learning_state = "warn"
        else:
            learning_state = "bad"
        checks.append(
            {
                "name": "Learning Coverage (7d)",
                "state": learning_state,
                "detail": f"resolved {coverage}% ({learning.get('resolved_routes', 0)}/{eligible}) | tracked {tracked_coverage}%",
            }
        )

        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        alpaca_auto = controls.get("enable_alpaca_paper_auto", "0") == "1"
        hl_auto = controls.get("enable_hyperliquid_test_auto", "0") == "1"
        hl_live = controls.get("allow_hyperliquid_live", "0") == "1"
        hl_notional = float(controls.get("hyperliquid_test_notional_usd", "0") or 0)

        checks.append({"name": "Alpaca Auto", "state": "good" if alpaca_auto else "warn", "detail": "enabled" if alpaca_auto else "disabled"})
        checks.append({"name": "HL Auto", "state": "good" if hl_auto else "warn", "detail": f"enabled (${hl_notional:g})" if hl_auto else "disabled"})
        checks.append({"name": "HL Live", "state": "good" if hl_live else "warn", "detail": "enabled" if hl_live else "disabled"})

        if hl_live and hl_notional < 10:
            checks.append({"name": "HL Min Notional", "state": "bad", "detail": "below ~$10 BTC minimum"})
        else:
            checks.append({"name": "HL Min Notional", "state": "good", "detail": "meets minimum"})

        scores = [c["state"] for c in checks]
        if "bad" in scores:
            overall = "bad"
        elif "warn" in scores:
            overall = "warn"
        else:
            overall = "good"
        return {"overall": overall, "message": f"{len(checks)} checks", "checks": checks}
    finally:
        conn.close()


def get_signal_readiness() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"state": "bad", "score": 0, "checks": [], "blockers": ["database missing"]}
    conn = _connect()
    try:
        checks: List[Dict[str, Any]] = []
        blockers: List[str] = []

        def recent_count(table: str, ts_col: str, hours: int = 6) -> int:
            if not _table_exists(conn, table):
                return 0
            cur = conn.cursor()
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE datetime(COALESCE({ts_col}, '1970-01-01')) >= datetime('now', ?)",
                (f"-{int(hours)} hour",),
            )
            return int((cur.fetchone() or [0])[0] or 0)

        cands = recent_count("trade_candidates", "generated_at", 6)
        routes = recent_count("signal_routes", "routed_at", 6)
        quant = recent_count("quant_validations", "validated_at", 6)
        poly = recent_count("polymarket_candidates", "created_at", 6)
        pipes = recent_count("pipeline_signals", "generated_at", 6)

        checks.append({"name": "Candidates (6h)", "state": "good" if cands > 0 else "bad", "detail": str(cands)})
        checks.append({"name": "Routes (6h)", "state": "good" if routes > 0 else "bad", "detail": str(routes)})
        checks.append({"name": "Quant Validations (6h)", "state": "good" if quant > 0 else "warn", "detail": str(quant)})
        checks.append({"name": "Pipeline Signals (6h)", "state": "good" if pipes > 0 else "warn", "detail": str(pipes)})
        checks.append({"name": "Polymarket Candidates (6h)", "state": "good" if poly > 0 else "warn", "detail": str(poly)})

        learning = get_learning_health(lookback_days=7)
        tracked_pct = float(learning.get("tracked_coverage_pct") or 0.0)
        resolved_pct = float(learning.get("coverage_pct") or 0.0)

        # Matured realized coverage: only routes older than 24h should be judged for realized outcomes.
        realized_matured_pct = 0.0
        matured_total = 0
        matured_realized = 0
        if _table_exists(conn, "signal_routes") and _table_exists(conn, "route_outcomes"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM signal_routes
                WHERE decision='approved'
                  AND datetime(COALESCE(routed_at, '1970-01-01')) <= datetime('now', '-24 hour')
                  AND datetime(COALESCE(routed_at, '1970-01-01')) >= datetime('now', '-7 day')
                """
            )
            matured_total = int((cur.fetchone() or [0])[0] or 0)
            if matured_total > 0:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM route_outcomes o
                    JOIN signal_routes r ON r.id = o.route_id
                    WHERE r.decision='approved'
                      AND datetime(COALESCE(r.routed_at, '1970-01-01')) <= datetime('now', '-24 hour')
                      AND datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', '-7 day')
                      AND COALESCE(o.outcome_type,'realized')='realized'
                    """
                )
                matured_realized = int((cur.fetchone() or [0])[0] or 0)
                realized_matured_pct = round((matured_realized / matured_total) * 100.0, 2)
        checks.append(
            {
                "name": "Learning Tracking (7d)",
                "state": "good" if tracked_pct >= 90 else ("warn" if tracked_pct >= 70 else "bad"),
                "detail": f"{tracked_pct}%",
            }
        )
        checks.append(
            {
                "name": "Learning Resolved (7d)",
                "state": "good" if resolved_pct >= 60 else ("warn" if resolved_pct >= 30 else "bad"),
                "detail": f"{resolved_pct}%",
            }
        )
        checks.append(
            {
                "name": "Realized Matured (7d, >24h)",
                "state": (
                    "warn"
                    if matured_total == 0
                    else ("good" if realized_matured_pct >= 50 else ("warn" if realized_matured_pct >= 20 else "bad"))
                ),
                "detail": (
                    "no matured routes"
                    if matured_total == 0
                    else f"{realized_matured_pct}% ({matured_realized}/{matured_total})"
                ),
            }
        )

        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        live_off = controls.get("allow_live_trading", "0") == "0"
        paper_off = controls.get("enable_alpaca_paper_auto", "0") == "0"
        hl_off = controls.get("enable_hyperliquid_test_auto", "0") == "0"
        poly_off = controls.get("enable_polymarket_auto", "0") == "0"
        safe_mode = live_off and paper_off and hl_off and poly_off
        checks.append({"name": "Safe Mode", "state": "good" if safe_mode else "warn", "detail": "on" if safe_mode else "off"})

        if cands == 0:
            blockers.append("no fresh trade candidates in last 6h")
        if routes == 0:
            blockers.append("no fresh routed signals in last 6h")

        bad = len([c for c in checks if c["state"] == "bad"])
        warn = len([c for c in checks if c["state"] == "warn"])
        score = max(0, 100 - bad * 25 - warn * 10)
        state = "good" if bad == 0 and warn <= 1 else ("warn" if bad == 0 else "bad")

        return {"state": state, "score": score, "checks": checks, "blockers": blockers}
    finally:
        conn.close()


def run_system_action(action: str) -> Dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "actions.log"
    commands = {
        "run_scan": "cd /Users/Shared/curtis/trader-curtis && ./run-all-scans.sh",
        "sync_broker": "cd /Users/Shared/curtis/trader-curtis && ./sync_alpaca_order_status.py",
        "refresh_learning": "cd /Users/Shared/curtis/trader-curtis && ./update_learning_feedback.py && ./source_ranker.py",
        "validate_signals": "cd /Users/Shared/curtis/trader-curtis && ./scripts/run_signal_validation.sh",
    }
    cmd = commands.get(action)
    if not cmd:
        return {"ok": False, "error": "unknown action"}

    with open(log_file, "a", encoding="utf-8") as lf:
        lf.write(f"\n[{datetime.now(timezone.utc).isoformat()}] action={action}\n")
        proc = subprocess.Popen(
            ["/bin/bash", "-lc", cmd],
            stdout=lf,
            stderr=lf,
        )
    return {"ok": True, "action": action, "pid": proc.pid}


def get_bookmarks() -> Dict[str, Any]:
    if not BOOKMARKS_PATH.exists():
        return {"status_urls": [], "external_urls": []}
    try:
        return json.loads(BOOKMARKS_PATH.read_text())
    except Exception:
        return {"status_urls": [], "external_urls": []}


def get_external_signals(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "external_signals"):
            return []
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM external_signals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def get_risk_controls() -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "execution_controls"):
            return []
        cur = conn.cursor()
        cur.execute("SELECT key, value, updated_at FROM execution_controls ORDER BY key")
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def set_execution_controls(updates: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "allow_live_trading",
        "allow_hyperliquid_live",
        "allow_equity_shorts",
        "enable_alpaca_paper_auto",
        "enable_hyperliquid_test_auto",
        "hyperliquid_test_notional_usd",
        "enable_polymarket_auto",
        "allow_polymarket_live",
        "polymarket_max_notional_usd",
        "polymarket_min_edge_pct",
        "min_candidate_score",
        "max_open_positions",
        "max_daily_new_notional_usd",
        "max_signal_notional_usd",
    }
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_controls (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        cur = conn.cursor()
        changed = 0
        for key, value in (updates or {}).items():
            if key not in allowed:
                continue
            cur.execute(
                """
                INSERT INTO execution_controls (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')
                """,
                (str(key), str(value)),
            )
            changed += 1
        conn.commit()
        return {"updated": changed, "controls": get_risk_controls()}
    finally:
        conn.close()


def get_signal_routes(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "signal_routes"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT routed_at, ticker, direction, score, source_tag, proposed_notional, mode, decision, reason, status
            FROM signal_routes
            ORDER BY routed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def get_bookmark_theses(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "bookmark_theses"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, source_handle, source_url, thesis_type, horizon, confidence, status
            FROM bookmark_theses
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_pipeline_signals(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "pipeline_signals"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT generated_at, pipeline_id, asset, direction, horizon, confidence, score, rationale
            FROM pipeline_signals
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_execution_orders(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "execution_orders"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, route_id, ticker, direction, mode, notional, order_status, broker_order_id, notes
            FROM execution_orders
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_source_scores(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "source_scores"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT computed_at, source_tag, sample_size, approved_rate, executed_rate, reliability_score
            FROM source_scores
            ORDER BY reliability_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_event_alerts(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "event_alerts"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, playbook_id, priority, source, proposed_asset, direction, confidence, status, alert_message
            FROM event_alerts
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_trade_candidates(limit: int = 50) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        cur = conn.cursor()
        if _table_exists(conn, "trade_candidates"):
            cur.execute(
                """
                SELECT generated_at AS updated_at, ticker, direction, score,
                       sentiment_score AS sentiment, pattern_type AS pattern, source_tag AS source
                FROM trade_candidates
                ORDER BY score DESC
                LIMIT ?
                """,
                (limit,),
            )
            return _rows_to_dicts(cur, cur.fetchall())

        latest_sent = {}
        if _table_exists(conn, "unified_social_sentiment"):
            cur.execute(
                """
                SELECT ticker, overall_score, timestamp
                FROM unified_social_sentiment
                ORDER BY timestamp DESC
                """
            )
            for ticker, score, ts in cur.fetchall():
                if ticker not in latest_sent:
                    latest_sent[ticker] = {"sentiment": score or 50, "sent_ts": ts}

        latest_pattern = {}
        if _table_exists(conn, "institutional_patterns"):
            cur.execute(
                """
                SELECT ticker, pattern_type, direction, timestamp
                FROM institutional_patterns
                ORDER BY timestamp DESC
                """
            )
            for ticker, ptype, direction, ts in cur.fetchall():
                if ticker not in latest_pattern:
                    latest_pattern[ticker] = {
                        "pattern_type": ptype,
                        "direction": direction,
                        "pattern_ts": ts,
                    }

        latest_external = {}
        if _table_exists(conn, "external_signals"):
            cur.execute(
                """
                SELECT ticker, source, direction, confidence, created_at
                FROM external_signals
                WHERE status IN ('new', 'active')
                ORDER BY created_at DESC
                """
            )
            for ticker, source, direction, confidence, ts in cur.fetchall():
                if ticker not in latest_external:
                    latest_external[ticker] = {
                        "source": source,
                        "ext_direction": direction,
                        "confidence": float(confidence or 0.5),
                        "ext_ts": ts,
                    }

        tickers = set(latest_sent.keys()) | set(latest_pattern.keys()) | set(latest_external.keys())
        candidates: List[Dict[str, Any]] = []
        for t in tickers:
            s = latest_sent.get(t, {})
            p = latest_pattern.get(t, {})
            e = latest_external.get(t, {})

            sentiment_component = float(s.get("sentiment", 50)) / 100.0
            pattern_component = float(PATTERN_RELIABILITY.get(p.get("pattern_type", ""), 0.5))
            external_component = float(e.get("confidence", 0.5))

            # Weighted score: sentiment 40%, pattern 40%, external source 20%
            score = round((0.4 * sentiment_component + 0.4 * pattern_component + 0.2 * external_component) * 100, 2)

            direction = p.get("direction") or e.get("ext_direction") or "unknown"
            candidates.append(
                {
                    "ticker": t,
                    "score": score,
                    "direction": direction,
                    "sentiment": s.get("sentiment", 50),
                    "pattern": p.get("pattern_type", "none"),
                    "source": e.get("source", "internal"),
                    "updated_at": s.get("sent_ts") or p.get("pattern_ts") or e.get("ext_ts"),
                }
            )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]
    finally:
        conn.close()


def get_trade_intents(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "trade_intents"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, venue, symbol, side, qty, notional, status, details
            FROM trade_intents
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_execution_learning(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "execution_learning"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, route_id, ticker, source_tag, mode, venue, decision, order_status, reason
            FROM execution_learning
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_source_learning_stats(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "source_learning_stats"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT computed_at, source_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent
            FROM source_learning_stats
            ORDER BY win_rate DESC, sample_size DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_strategy_learning_stats(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "strategy_learning_stats"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT computed_at, strategy_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent
            FROM strategy_learning_stats
            ORDER BY sample_size DESC, win_rate DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_memory_integrity(lookback_days: int = 30) -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "lookback_days": lookback_days,
            "approved_routes": 0,
            "linked_routes": 0,
            "resolved_routes": 0,
            "realized_routes": 0,
            "operational_routes": 0,
            "orphan_outcomes": 0,
            "coverage_pct": 0.0,
            "tracked_pct": 0.0,
            "consistency_state": "warn",
        }
    conn = _connect()
    try:
        cur = conn.cursor()

        approved_routes = 0
        if _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT COUNT(*)
                FROM signal_routes
                WHERE decision='approved'
                  AND datetime(COALESCE(routed_at, '1970-01-01')) >= datetime('now', ?)
                """,
                (f"-{int(lookback_days)} day",),
            )
            approved_routes = int((cur.fetchone() or [0])[0] or 0)

        linked_routes = 0
        if _table_exists(conn, "route_trade_links") and _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT COUNT(*)
                FROM route_trade_links l
                JOIN signal_routes r ON r.id = l.route_id
                WHERE r.decision='approved'
                  AND datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', ?)
                """,
                (f"-{int(lookback_days)} day",),
            )
            linked_routes = int((cur.fetchone() or [0])[0] or 0)

        resolved_routes = 0
        realized_routes = 0
        operational_routes = 0
        if _table_exists(conn, "route_outcomes") and _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT
                  COUNT(*),
                  SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='operational' THEN 1 ELSE 0 END)
                FROM route_outcomes o
                JOIN signal_routes r ON r.id = o.route_id
                WHERE r.decision='approved'
                  AND datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', ?)
                """,
                (f"-{int(lookback_days)} day",),
            )
            row = cur.fetchone() or (0, 0, 0)
            resolved_routes = int(row[0] or 0)
            realized_routes = int(row[1] or 0)
            operational_routes = int(row[2] or 0)

        orphan_outcomes = 0
        if _table_exists(conn, "route_outcomes") and _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT COUNT(*)
                FROM route_outcomes o
                LEFT JOIN signal_routes r ON r.id = o.route_id
                WHERE r.id IS NULL
                """
            )
            orphan_outcomes = int((cur.fetchone() or [0])[0] or 0)

        coverage_pct = round((resolved_routes / approved_routes) * 100.0, 2) if approved_routes else 0.0
        tracked_pct = round((linked_routes / approved_routes) * 100.0, 2) if approved_routes else 0.0

        consistency_state = "good"
        if orphan_outcomes > 0 or tracked_pct < 80:
            consistency_state = "warn"
        if approved_routes > 0 and coverage_pct < 50:
            consistency_state = "bad"

        return {
            "lookback_days": lookback_days,
            "approved_routes": approved_routes,
            "linked_routes": linked_routes,
            "resolved_routes": resolved_routes,
            "realized_routes": realized_routes,
            "operational_routes": operational_routes,
            "orphan_outcomes": orphan_outcomes,
            "coverage_pct": coverage_pct,
            "tracked_pct": tracked_pct,
            "consistency_state": consistency_state,
        }
    finally:
        conn.close()


def get_quant_validations(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "quant_validations"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT validated_at, ticker, direction, source_tag, candidate_score, sample_size,
                   win_rate, expected_value_percent, volatility_percent, max_drawdown_percent,
                   corr_to_open_book, regime_score, passed, reason
            FROM quant_validations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_chart_liquidity_signals(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "chart_liquidity_signals"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, ticker, timeframe, direction, pattern, confidence, score,
                   entry_hint, stop_hint, target_hint, liquidity_high, liquidity_low,
                   chart_url, source_ref, notes, status
            FROM chart_liquidity_signals
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_bookmark_alpha_ideas(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "bookmark_alpha_ideas"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, source_handle, source_url, strategy_tag, thesis_type, horizon, confidence, promoted_to_signal
            FROM bookmark_alpha_ideas
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_polymarket_markets(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "polymarket_markets"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT fetched_at, market_id, slug, question, liquidity, volume_24h, active, closed, market_url
            FROM polymarket_markets
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_polymarket_candidates(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "polymarket_candidates"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, strategy_id, market_id, slug, question, outcome, implied_prob, model_prob, edge, confidence, source_tag, rationale, market_url, status
            FROM polymarket_candidates
            ORDER BY ABS(edge) DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()
