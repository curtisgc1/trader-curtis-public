import json
import os
import re
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "trades.db"
BOOKMARKS_PATH = BASE_DIR / "docs" / "x-bookmarks.json"
LOG_DIR = BASE_DIR / "dashboard-ui" / "logs"
ENV_PATH = BASE_DIR / ".env"

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


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def _rows_to_dicts(cur: sqlite3.Cursor, rows: List[tuple]) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def _load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return {k: v for k, v in os.environ.items()}
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


def _hl_runtime_network() -> str:
    env = _load_env()
    api = str(env.get("HL_API_URL", "")).strip().lower()
    use_testnet = str(env.get("HL_USE_TESTNET", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if "testnet" in api or use_testnet:
        return "testnet"
    return "mainnet"


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
        cur = conn.cursor()
        if _table_exists(conn, "institutional_patterns"):
            cur.execute(
                "SELECT * FROM institutional_patterns ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            if rows:
                return _rows_to_dicts(cur, rows)

        # Fallback: use chart liquidity signals when institutional_patterns has no rows.
        if _table_exists(conn, "chart_liquidity_signals"):
            cur.execute(
                """
                SELECT
                  created_at AS timestamp,
                  ticker,
                  pattern AS pattern_name,
                  direction,
                  confidence,
                  score,
                  'chart_liquidity' AS source
                FROM chart_liquidity_signals
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return _rows_to_dicts(cur, cur.fetchall())
        return []
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

    total_pnl = round(sum([(t.get("pnl", 0) or 0) for t in trades]), 4) if total else 0.0
    summary_source = "trades"
    realized_total = 0
    realized_wins = 0
    realized_losses = 0
    operational_losses = 0

    # Fallback: when closed-trade PnL isn't populated yet, derive health metrics from route outcomes.
    if (wins + losses == 0) and DB_PATH.exists():
        conn = _connect()
        try:
            if _table_exists(conn, "route_outcomes"):
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT
                      SUM(CASE WHEN COALESCE(outcome_type,'realized')='realized' THEN 1 ELSE 0 END) AS realized_n,
                      SUM(CASE WHEN COALESCE(outcome_type,'realized')='realized' AND resolution='win' THEN 1 ELSE 0 END) AS realized_wins,
                      SUM(CASE WHEN COALESCE(outcome_type,'realized')='realized' AND resolution='loss' THEN 1 ELSE 0 END) AS realized_losses,
                      SUM(CASE WHEN COALESCE(outcome_type,'realized')='realized' THEN COALESCE(pnl,0) ELSE 0 END) AS realized_pnl,
                      SUM(CASE WHEN COALESCE(outcome_type,'realized')='operational' AND resolution='loss' THEN 1 ELSE 0 END) AS operational_losses
                    FROM route_outcomes
                    """
                )
                row = cur.fetchone() or (0, 0, 0, 0.0, 0)
                realized_total = int(row[0] or 0)
                realized_wins = int(row[1] or 0)
                realized_losses = int(row[2] or 0)
                realized_pnl = float(row[3] or 0.0)
                operational_losses = int(row[4] or 0)

                if realized_total > 0:
                    wins = realized_wins
                    losses = realized_losses
                    total = realized_total
                    win_rate = round((wins / total) * 100.0, 2) if total else 0.0
                    total_pnl = round(realized_pnl, 4)
                    avg_pnl = round((realized_pnl / total), 4) if total else 0.0
                    summary_source = "route_outcomes_realized"
                elif operational_losses > 0:
                    cur.execute(
                        """
                        SELECT COALESCE(SUM(COALESCE(pnl,0)),0)
                        FROM route_outcomes
                        WHERE COALESCE(outcome_type,'realized')='operational'
                        """
                    )
                    op_pnl_row = cur.fetchone()
                    op_total_pnl = float(op_pnl_row[0] or 0.0) if op_pnl_row else 0.0
                    wins = 0
                    losses = operational_losses
                    total = operational_losses
                    win_rate = 0.0
                    total_pnl = round(op_total_pnl, 4)
                    avg_pnl = round((op_total_pnl / total), 4) if total else 0.0
                    summary_source = "route_outcomes_operational"
        finally:
            conn.close()

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl,
        "summary_source": summary_source,
        "realized_routes": realized_total,
        "operational_losses": operational_losses,
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
        hl_network = _hl_runtime_network()

        checks.append({"name": "Alpaca Auto", "state": "good" if alpaca_auto else "warn", "detail": "enabled" if alpaca_auto else "disabled"})
        checks.append({"name": "HL Auto", "state": "good" if hl_auto else "warn", "detail": f"enabled (${hl_notional:g})" if hl_auto else "disabled"})
        checks.append({"name": "HL Live", "state": "good" if hl_live else "warn", "detail": "enabled" if hl_live else "disabled"})
        checks.append(
            {
                "name": "HL Network",
                "state": "good" if hl_network == "testnet" else "warn",
                "detail": hl_network,
            }
        )

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

        checks.append({"name": "Candidates (6h)", "state": "good" if cands > 0 else "bad", "detail": str(cands), "critical": True})
        checks.append({"name": "Routes (6h)", "state": "good" if routes > 0 else "bad", "detail": str(routes), "critical": True})
        checks.append({"name": "Quant Validations (6h)", "state": "good" if quant > 0 else "warn", "detail": str(quant), "critical": False})
        checks.append({"name": "Pipeline Signals (6h)", "state": "good" if pipes > 0 else "warn", "detail": str(pipes), "critical": False})
        checks.append({"name": "Polymarket Candidates (6h)", "state": "good" if poly > 0 else "warn", "detail": str(poly), "critical": False})

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
                "critical": False,
            }
        )
        checks.append(
            {
                "name": "Learning Resolved (7d)",
                "state": "good" if resolved_pct >= 60 else ("warn" if resolved_pct >= 15 else "bad"),
                "detail": f"{resolved_pct}%",
                "critical": False,
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
                "critical": False,
            }
        )

        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        live_off = controls.get("allow_live_trading", "0") == "0"
        paper_off = controls.get("enable_alpaca_paper_auto", "0") == "0"
        hl_off = controls.get("enable_hyperliquid_test_auto", "0") == "0"
        poly_off = controls.get("enable_polymarket_auto", "0") == "0"
        safe_mode = live_off and paper_off and hl_off and poly_off
        checks.append({"name": "Safe Mode", "state": "good" if safe_mode else "warn", "detail": "on" if safe_mode else "off", "critical": False})

        if cands == 0:
            blockers.append("no fresh trade candidates in last 6h")
        if routes == 0:
            blockers.append("no fresh routed signals in last 6h")

        bad_critical = len([c for c in checks if c["state"] == "bad" and c.get("critical", False)])
        bad_noncritical = len([c for c in checks if c["state"] == "bad" and not c.get("critical", False)])
        warn = len([c for c in checks if c["state"] == "warn"])
        score = max(0, 100 - bad_critical * 25 - bad_noncritical * 12 - warn * 8)
        if blockers or bad_critical > 0:
            state = "bad"
        elif bad_noncritical > 0 or warn > 0:
            state = "warn"
        else:
            state = "good"

        return {"state": state, "score": score, "checks": checks, "blockers": blockers}
    finally:
        conn.close()


def _keychain_secret_present(service: str, account: str = "curtiscorum") -> bool:
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0 and bool((proc.stdout or "").strip())


def _run_tooling_context_check() -> Dict[str, Any]:
    script = BASE_DIR / "scripts" / "check_tooling_context.sh"
    if not script.exists():
        return {"state": "bad", "detail": "missing"}
    if not os.access(script, os.X_OK):
        return {"state": "bad", "detail": "not executable"}
    try:
        proc = subprocess.run(
            [str(script)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except Exception as exc:
        return {"state": "bad", "detail": f"error: {exc.__class__.__name__}"}
    out = (proc.stdout or "").strip().splitlines()
    marker = ""
    for line in out:
        if line.startswith("tooling_context="):
            marker = line.split("=", 1)[1].strip()
    if proc.returncode == 0 and marker == "good":
        return {"state": "good", "detail": "good"}
    if proc.returncode == 1 or marker == "warn":
        return {"state": "warn", "detail": "warn"}
    return {"state": "bad", "detail": marker or f"exit={proc.returncode}"}


def get_agent_awareness() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []
    warnings: List[str] = []
    if not DB_PATH.exists():
        return {"overall": "bad", "summary": "database missing", "checks": [], "blockers": ["trades.db missing"], "warnings": []}

    env = _load_env()
    conn = _connect()
    try:
        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        poly_auto = controls.get("enable_polymarket_auto", "0") == "1"
        poly_live = controls.get("allow_polymarket_live", "0") == "1"
        x_influence_enabled = controls.get("x_influence_enabled", "1") == "1"

        api_env_ok = all(bool(str(env.get(k, "")).strip()) for k in ("POLY_API_KEY", "POLY_API_SECRET", "POLY_API_PASSPHRASE"))
        api_keychain_ok = all(
            _keychain_secret_present(k)
            for k in (
                "trader-curtis-POLY_API_KEY",
                "trader-curtis-POLY_API_SECRET",
                "trader-curtis-POLY_API_PASSPHRASE",
            )
        )
        api_ok = api_env_ok or api_keychain_ok

        signing_env_ok = bool(str(env.get("POLY_PRIVATE_KEY", "")).strip())
        signing_keychain_ok = _keychain_secret_present("trader-curtis-POLY_PRIVATE_KEY")
        signing_ok = signing_env_ok or signing_keychain_ok

        poly_wallet = ""
        if _table_exists(conn, "wallet_config"):
            cur = conn.cursor()
            cur.execute("SELECT value FROM wallet_config WHERE key='poly_wallet_address' LIMIT 1")
            row = cur.fetchone()
            poly_wallet = str(row[0]) if row and row[0] else ""

        checks.append({"name": "Polymarket Auto", "state": "good" if poly_auto else "warn", "detail": "enabled" if poly_auto else "disabled"})
        checks.append({"name": "Polymarket Live", "state": "good", "detail": "enabled" if poly_live else "disabled"})
        checks.append({"name": "Polymarket Wallet", "state": "good" if poly_wallet else "warn", "detail": poly_wallet or "not configured"})
        checks.append({"name": "Polymarket API Credentials", "state": "good" if api_ok else "bad", "detail": "available" if api_ok else "missing (env/keychain)"})
        checks.append(
            {
                "name": "Polymarket Signing Key",
                "state": "good" if signing_ok else ("bad" if poly_live else "warn"),
                "detail": "available" if signing_ok else "missing (required for live)",
            }
        )

        m_age = _age_minutes(_latest_value(conn, "polymarket_markets", "fetched_at"))
        c_age = _age_minutes(_latest_value(conn, "polymarket_candidates", "created_at"))
        o_age = _age_minutes(_latest_value(conn, "polymarket_orders", "created_at"))
        checks.append({"name": "Polymarket Market Freshness", "state": "good" if (m_age is not None and m_age <= 1440) else "warn", "detail": f"{m_age} min ago" if m_age is not None else "no data"})
        checks.append({"name": "Polymarket Candidate Freshness", "state": "good" if (c_age is not None and c_age <= 360) else "warn", "detail": f"{c_age} min ago" if c_age is not None else "no data"})
        checks.append({"name": "Polymarket Order Activity", "state": "good" if (o_age is not None and o_age <= 1440) else "warn", "detail": f"{o_age} min ago" if o_age is not None else "no orders yet"})
        xai_ok = bool(str(env.get("XAI_API_KEY", "")).strip())
        checks.append({"name": "X Input Influence", "state": "good" if x_influence_enabled else "warn", "detail": "enabled" if x_influence_enabled else "disabled"})
        checks.append({"name": "X API Key (xAI)", "state": "good" if xai_ok else ("warn" if not x_influence_enabled else "bad"), "detail": "available" if xai_ok else "missing XAI_API_KEY"})
        checks.append(
            {
                "name": "Tooling Playbook",
                "state": "good" if (BASE_DIR / "docs" / "TOOLING-RUNTIME-PLAYBOOK.md").exists() else "bad",
                "detail": "available" if (BASE_DIR / "docs" / "TOOLING-RUNTIME-PLAYBOOK.md").exists() else "missing",
            }
        )
        tooling_check = _run_tooling_context_check()
        checks.append(
            {
                "name": "Tooling Context Check",
                "state": tooling_check["state"],
                "detail": tooling_check["detail"],
            }
        )

        if not api_ok:
            blockers.append("Polymarket API credentials are not available from env/keychain")
        if poly_live and not signing_ok:
            blockers.append("Polymarket live enabled but no POLY_PRIVATE_KEY; worker will fall back to paper")
        if poly_auto and not poly_wallet:
            warnings.append("Polymarket auto is enabled but wallet address is not visible in wallet_config")
        if x_influence_enabled and not xai_ok:
            blockers.append("X influence enabled but XAI_API_KEY missing")
        if tooling_check["state"] == "bad":
            blockers.append("Tooling context check failed; agent may not be grounded on runtime tools")
        elif tooling_check["state"] == "warn":
            warnings.append("Tooling context check returned warnings; verify missing components")

        bad = len([c for c in checks if c["state"] == "bad"])
        warn = len([c for c in checks if c["state"] == "warn"])
        if blockers or bad > 0:
            overall = "bad"
        elif warnings or warn > 0:
            overall = "warn"
        else:
            overall = "good"

        effective_mode = "live" if (poly_live and signing_ok and api_ok) else "paper"
        summary = f"polymarket {effective_mode} mode"
        return {
            "overall": overall,
            "summary": summary,
            "effective_mode": effective_mode,
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
        }
    finally:
        conn.close()


def get_trade_claim_guard() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    if not DB_PATH.exists():
        return {
            "state": "bad",
            "trade_ready": False,
            "summary": "database missing",
            "checks": [],
            "blockers": ["trades.db missing"],
            "warnings": [],
            "approved_queued_routes": 0,
        }

    env = _load_env()
    conn = _connect()
    try:
        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        master = controls.get("agent_master_enabled", "0") == "1"
        live = controls.get("allow_live_trading", "0") == "1"
        alpaca_auto = controls.get("enable_alpaca_paper_auto", "0") == "1"
        hl_test_auto = controls.get("enable_hyperliquid_test_auto", "0") == "1"
        hl_live = controls.get("allow_hyperliquid_live", "0") == "1"
        poly_auto = controls.get("enable_polymarket_auto", "0") == "1"
        poly_live = controls.get("allow_polymarket_live", "0") == "1"

        any_adapter = alpaca_auto or hl_test_auto or poly_auto
        checks.append({"name": "Master Enabled", "state": "good" if master else "bad", "detail": "on" if master else "off"})
        checks.append({"name": "Execution Adapter", "state": "good" if any_adapter else "bad", "detail": "enabled" if any_adapter else "none enabled"})
        checks.append({"name": "Trading Mode", "state": "good", "detail": "live" if live else "paper/test"})
        checks.append(
            {
                "name": "Adapters Detail",
                "state": "good",
                "detail": f"alpaca={int(alpaca_auto)} hl_test={int(hl_test_auto)} hl_live={int(hl_live)} poly={int(poly_auto)}",
            }
        )

        py_ok = bool(shutil.which("python3") or shutil.which("python"))
        checks.append({"name": "Python Runtime", "state": "good" if py_ok else "bad", "detail": "available" if py_ok else "missing"})

        cur = conn.cursor()
        approved_queued = 0
        if _table_exists(conn, "signal_routes"):
            cur.execute("SELECT COUNT(*) FROM signal_routes WHERE decision='approved' AND status='queued'")
            approved_queued = int((cur.fetchone() or [0])[0] or 0)
        checks.append(
            {
                "name": "Approved Queued Routes",
                "state": "good" if approved_queued > 0 else "warn",
                "detail": str(approved_queued),
            }
        )

        if not master:
            blockers.append("agent_master_enabled=0 (execution worker paused)")
        if not any_adapter:
            blockers.append("no execution adapter enabled")
        if not py_ok:
            blockers.append("python runtime missing")
        if approved_queued == 0:
            warnings.append("no approved queued routes")

        # Polymarket live signing must be present if live mode is enabled.
        if poly_auto and poly_live:
            signing_env_ok = bool(str(env.get("POLY_PRIVATE_KEY", "")).strip())
            signing_keychain_ok = _keychain_secret_present("trader-curtis-POLY_PRIVATE_KEY")
            signing_ok = signing_env_ok or signing_keychain_ok
            checks.append(
                {
                    "name": "Polymarket Signing Key",
                    "state": "good" if signing_ok else "bad",
                    "detail": "available" if signing_ok else "missing",
                }
            )
            if not signing_ok:
                blockers.append("polymarket live enabled but signing key missing")

        if blockers:
            state = "bad"
            ready = False
        elif warnings:
            state = "warn"
            ready = False
        else:
            state = "good"
            ready = True

        return {
            "state": state,
            "trade_ready": ready,
            "summary": "ready to claim trade readiness" if ready else "not ready for trade-readiness claim",
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "approved_queued_routes": approved_queued,
        }
    finally:
        conn.close()


def get_performance_curve(limit: int = 500) -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "source": "none",
            "count": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "unit": "usd",
            "by_time": [],
            "by_trade": [],
        }

    conn = _connect()
    try:
        rows: List[Dict[str, Any]] = []
        source = "none"
        cur = conn.cursor()

        if _table_exists(conn, "route_outcomes"):
            cur.execute(
                """
                SELECT
                  CAST(route_id AS TEXT) AS rid,
                  resolved_at AS ts,
                  pnl,
                  pnl_percent
                FROM route_outcomes
                WHERE pnl IS NOT NULL OR pnl_percent IS NOT NULL
                ORDER BY datetime(COALESCE(resolved_at, '1970-01-01')) ASC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = _rows_to_dicts(cur, cur.fetchall())
            if rows:
                source = "route_outcomes"

        if not rows and _table_exists(conn, "trades"):
            cur.execute(
                """
                SELECT
                  COALESCE(trade_id, '') AS rid,
                  created_at AS ts,
                  pnl
                FROM trades
                WHERE pnl IS NOT NULL
                ORDER BY datetime(COALESCE(created_at, '1970-01-01')) ASC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = _rows_to_dicts(cur, cur.fetchall())
            if rows:
                source = "trades"

        if not rows:
            return {
                "source": source,
                "count": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
                "unit": "usd",
                "by_time": [],
                "by_trade": [],
            }

        # Use PnL percent as fallback when USD pnl is unavailable/flat.
        use_pct = False
        if source == "route_outcomes":
            non_zero_usd = 0
            non_zero_pct = 0
            for r in rows:
                usd = float(r.get("pnl") or 0.0)
                pct = float(r.get("pnl_percent") or 0.0)
                if abs(usd) > 1e-9:
                    non_zero_usd += 1
                if abs(pct) > 1e-9:
                    non_zero_pct += 1
            use_pct = non_zero_usd == 0 and non_zero_pct > 0

        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        wins = 0
        losses = 0
        by_time: List[Dict[str, Any]] = []
        by_trade: List[Dict[str, Any]] = []

        for i, r in enumerate(rows, 1):
            pnl = float((r.get("pnl_percent") if use_pct else r.get("pnl")) or 0.0)
            ts = str(r.get("ts") or "")
            rid = str(r.get("rid") or "")
            cumulative += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            max_drawdown = max(max_drawdown, drawdown)

            point = {
                "trade": i,
                "timestamp": ts,
                "id": rid,
                "pnl": round(pnl, 4),
                "cum_pnl": round(cumulative, 4),
                "drawdown": round(drawdown, 4),
            }
            by_time.append(
                {
                    "x": ts,
                    "y": point["cum_pnl"],
                    "pnl": point["pnl"],
                    "trade": i,
                    "drawdown": point["drawdown"],
                }
            )
            by_trade.append(
                {
                    "x": i,
                    "y": point["cum_pnl"],
                    "pnl": point["pnl"],
                    "timestamp": ts,
                    "drawdown": point["drawdown"],
                }
            )

        return {
            "source": source,
            "count": len(rows),
            "wins": wins,
            "losses": losses,
            "total_pnl": round(cumulative, 4),
            "max_drawdown": round(max_drawdown, 4),
            "unit": "pct" if use_pct else "usd",
            "by_time": by_time,
            "by_trade": by_trade,
        }
    finally:
        conn.close()


def run_system_action(action: str) -> Dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "actions.log"
    commands = {
        "run_scan": "cd /Users/Shared/curtis/trader-curtis && ./run-all-scans.sh",
        "run_poly_align": "cd /Users/Shared/curtis/trader-curtis && python3.11 ./align_high_signal_polymarket.py",
        "run_cycle": "cd /Users/Shared/curtis/trader-curtis && ./scripts/trader_cycle_locked.sh dashboard_manual",
        "run_polymarket_exec": "cd /Users/Shared/curtis/trader-curtis && ./scripts/with_polymarket_keychain.sh python3.11 ./execution_polymarket.py",
        "run_polymarket_mm": "cd /Users/Shared/curtis/trader-curtis && python3.11 ./polymarket_mm_engine.py",
        "run_poly_wallet_ingest": "cd /Users/Shared/curtis/trader-curtis && python3.11 ./ingest_polymarket_wallet_activity.py && python3.11 ./score_polymarket_wallets.py",
        "sync_broker": "cd /Users/Shared/curtis/trader-curtis && ./sync_alpaca_order_status.py",
        "refresh_learning": "cd /Users/Shared/curtis/trader-curtis && ./update_learning_feedback.py && ./source_ranker.py",
        "run_auto_tune": "cd /Users/Shared/curtis/trader-curtis && ./auto_tune_controls.py",
        "validate_signals": "cd /Users/Shared/curtis/trader-curtis && ./scripts/run_signal_validation.sh",
        "check_awareness": "cd /Users/Shared/curtis/trader-curtis && ./scripts/check_agent_awareness.sh",
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


def _ensure_venue_matrix(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS venue_matrix (
          venue TEXT PRIMARY KEY,
          enabled INTEGER NOT NULL DEFAULT 1,
          min_score REAL NOT NULL DEFAULT 60,
          max_notional REAL NOT NULL DEFAULT 100,
          mode TEXT NOT NULL DEFAULT 'paper',
          updated_at TEXT NOT NULL
        )
        """
    )
    cur = conn.cursor()
    controls: Dict[str, Any] = {}
    if _table_exists(conn, "execution_controls"):
        cur.execute("SELECT key, value FROM execution_controls")
        controls = {str(k): str(v) for k, v in cur.fetchall()}
    rows = [
        (
            "stocks",
            1 if controls.get("enable_alpaca_paper_auto", "1") == "1" else 0,
            float(controls.get("alpaca_min_route_score", "60") or 60.0),
            float(controls.get("max_signal_notional_usd", "150") or 150.0),
            "paper",
        ),
        (
            "crypto",
            1 if controls.get("enable_hyperliquid_test_auto", "1") == "1" else 0,
            float(controls.get("hyperliquid_min_route_score", "60") or 60.0),
            float(controls.get("hyperliquid_test_notional_usd", "10") or 10.0),
            "paper",
        ),
        (
            "prediction",
            1 if controls.get("enable_polymarket_auto", "0") == "1" else 0,
            float(controls.get("polymarket_min_confidence_pct", "60") or 60.0),
            float(controls.get("polymarket_max_notional_usd", "10") or 10.0),
            "paper",
        ),
    ]
    for venue, enabled, min_score, max_notional, mode in rows:
        cur.execute(
            """
            INSERT OR IGNORE INTO venue_matrix(venue, enabled, min_score, max_notional, mode, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (venue, int(enabled), float(min_score), float(max_notional), mode),
        )
    conn.commit()


def get_venue_matrix() -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        _ensure_venue_matrix(conn)
        cur = conn.cursor()
        cur.execute("SELECT venue, enabled, min_score, max_notional, mode, updated_at FROM venue_matrix ORDER BY venue")
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def set_venue_matrix(updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    allowed_venues = {"stocks", "crypto", "prediction"}
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        _ensure_venue_matrix(conn)
        changed = 0
        cur = conn.cursor()
        for row in (updates or []):
            venue = str((row or {}).get("venue", "")).strip().lower()
            if venue not in allowed_venues:
                continue
            enabled = 1 if str((row or {}).get("enabled", "1")).strip().lower() in {"1", "true", "yes", "on"} else 0
            min_score = float((row or {}).get("min_score", 60.0) or 60.0)
            max_notional = float((row or {}).get("max_notional", 100.0) or 100.0)
            mode = str((row or {}).get("mode", "paper") or "paper").strip().lower()
            if mode not in {"paper", "live"}:
                mode = "paper"
            cur.execute(
                """
                UPDATE venue_matrix
                SET enabled=?, min_score=?, max_notional=?, mode=?, updated_at=datetime('now')
                WHERE venue=?
                """,
                (int(enabled), float(min_score), float(max_notional), mode, venue),
            )
            changed += int(cur.rowcount or 0)
        conn.commit()
        return {"updated": changed, "venues": get_venue_matrix()}
    finally:
        conn.close()


def get_venue_readiness() -> Dict[str, Any]:
    matrix = get_venue_matrix()
    controls = {x.get("key"): x.get("value") for x in get_risk_controls()}
    snapshot = get_portfolio_snapshot()
    by_venue: Dict[str, Any] = {}
    rows_by_name = {str(x.get("venue")): x for x in matrix}
    for venue in ("stocks", "crypto", "prediction"):
        row = rows_by_name.get(venue, {})
        enabled = int(row.get("enabled", 0) or 0) == 1
        min_score = float(row.get("min_score", 60) or 60)
        max_notional = float(row.get("max_notional", 0) or 0)
        checks: List[Dict[str, Any]] = []
        if venue == "stocks":
            auto = controls.get("enable_alpaca_paper_auto", "0") == "1"
            ok = bool(snapshot.get("alpaca", {}).get("ok"))
            checks.append({"name": "adapter", "state": "good" if auto else "bad", "detail": "alpaca_auto"})
            checks.append({"name": "account", "state": "good" if ok else "warn", "detail": snapshot.get("alpaca", {}).get("error", "")})
        elif venue == "crypto":
            auto = controls.get("enable_hyperliquid_test_auto", "0") == "1"
            ok = bool(snapshot.get("hyperliquid", {}).get("ok"))
            checks.append({"name": "adapter", "state": "good" if auto else "bad", "detail": "hl_auto"})
            checks.append({"name": "account", "state": "good" if ok else "warn", "detail": snapshot.get("hyperliquid", {}).get("error", "")})
        else:
            auto = controls.get("enable_polymarket_auto", "0") == "1"
            live = controls.get("allow_polymarket_live", "0") == "1"
            checks.append({"name": "adapter", "state": "good" if auto else "bad", "detail": "polymarket_auto"})
            checks.append({"name": "mode", "state": "warn" if live else "good", "detail": "live" if live else "paper"})
        states = [c.get("state") for c in checks]
        state = "good" if enabled and "bad" not in states else ("warn" if enabled else "bad")
        by_venue[venue] = {
            "state": state,
            "enabled": enabled,
            "min_score": min_score,
            "max_notional": max_notional,
            "checks": checks,
        }
    overall = "good"
    if any(v.get("state") == "bad" for v in by_venue.values()):
        overall = "bad"
    elif any(v.get("state") == "warn" for v in by_venue.values()):
        overall = "warn"
    return {"overall": overall, "venues": by_venue}


def get_wallet_config() -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "wallet_config"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT key, value, source, updated_at
            FROM wallet_config
            ORDER BY key ASC
            """
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        if rows and _table_exists(conn, "trade_candidates"):
            cur2 = conn.cursor()
            for r in rows:
                t = str(r.get("ticker") or "").strip().upper()
                if not t:
                    r["candidate_rationale"] = ""
                    r["candidate_inputs"] = "[]"
                    continue
                cur2.execute(
                    """
                    SELECT COALESCE(rationale,''), COALESCE(input_breakdown_json,'[]')
                    FROM trade_candidates
                    WHERE UPPER(COALESCE(ticker,''))=?
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """,
                    (t,),
                )
                x = cur2.fetchone()
                r["candidate_rationale"] = str(x[0]) if x else ""
                r["candidate_inputs"] = str(x[1]) if x else "[]"
        return rows
    finally:
        conn.close()


def get_portfolio_snapshot() -> Dict[str, Any]:
    env = _load_env()
    snapshot: Dict[str, Any] = {
        "alpaca": {
            "ok": False,
            "equity": 0.0,
            "cash": 0.0,
            "buying_power": 0.0,
            "positions": [],
            "error": "",
        },
        "hyperliquid": {
            "ok": False,
            "network": _hl_runtime_network(),
            "wallet": env.get("HL_WALLET_ADDRESS", ""),
            "account_value": 0.0,
            "withdrawable": 0.0,
            "positions": [],
            "perp_account_value": 0.0,
            "perp_withdrawable": 0.0,
            "spot_total_usdc": 0.0,
            "spot_balances": [],
            "spot_available_after_maintenance": [],
            "error": "",
        },
    }

    # Alpaca account + open positions.
    api_key = env.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY", "")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if api_key and secret:
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
        }
        try:
            req_acc = urllib.request.Request(f"{base_url}/v2/account", headers=headers, method="GET")
            with urllib.request.urlopen(req_acc, timeout=12) as resp:
                acc = json.loads(resp.read().decode("utf-8"))
            snapshot["alpaca"]["equity"] = float(acc.get("equity") or 0.0)
            snapshot["alpaca"]["cash"] = float(acc.get("cash") or 0.0)
            snapshot["alpaca"]["buying_power"] = float(acc.get("buying_power") or 0.0)

            req_pos = urllib.request.Request(f"{base_url}/v2/positions", headers=headers, method="GET")
            with urllib.request.urlopen(req_pos, timeout=12) as resp:
                pos = json.loads(resp.read().decode("utf-8"))
            rows = []
            if isinstance(pos, list):
                for p in pos:
                    rows.append(
                        {
                            "symbol": p.get("symbol", ""),
                            "qty": p.get("qty", ""),
                            "side": p.get("side", ""),
                            "market_value": float(p.get("market_value") or 0.0),
                            "unrealized_pl": float(p.get("unrealized_pl") or 0.0),
                            "unrealized_plpc": float(p.get("unrealized_plpc") or 0.0),
                        }
                    )
            snapshot["alpaca"]["positions"] = rows
            snapshot["alpaca"]["ok"] = True
        except Exception as exc:
            snapshot["alpaca"]["error"] = str(exc)
    else:
        snapshot["alpaca"]["error"] = "missing credentials"

    # Hyperliquid account state (if wallet configured).
    hl_wallet = str(env.get("HL_WALLET_ADDRESS", "") or "").strip()
    hl_api = str(env.get("HL_API_URL", "") or "").strip().rstrip("/")
    if not hl_api:
        hl_api = "https://api.hyperliquid-testnet.xyz" if snapshot["hyperliquid"]["network"] == "testnet" else "https://api.hyperliquid.xyz"
    hl_info = str(env.get("HL_INFO_URL", "") or "").strip()
    if not hl_info:
        hl_info = f"{hl_api}/info"

    if hl_wallet:
        try:
            # Perps state: account margin, withdrawable, perp positions.
            perp_payload = {"type": "clearinghouseState", "user": hl_wallet}
            perp_req = urllib.request.Request(
                hl_info,
                data=json.dumps(perp_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(perp_req, timeout=12) as resp:
                perp_state = json.loads(resp.read().decode("utf-8"))
            ms = perp_state.get("marginSummary", {}) if isinstance(perp_state, dict) else {}
            perp_account_value = float(ms.get("accountValue") or 0.0)
            perp_withdrawable = float(perp_state.get("withdrawable") or 0.0)
            snapshot["hyperliquid"]["account_value"] = perp_account_value
            snapshot["hyperliquid"]["withdrawable"] = perp_withdrawable
            snapshot["hyperliquid"]["perp_account_value"] = perp_account_value
            snapshot["hyperliquid"]["perp_withdrawable"] = perp_withdrawable
            positions = []
            for item in (perp_state.get("assetPositions") or []):
                if not isinstance(item, dict):
                    continue
                pos = item.get("position", {}) if isinstance(item.get("position"), dict) else {}
                positions.append(
                    {
                        "coin": pos.get("coin", ""),
                        "szi": pos.get("szi", ""),
                        "position_value": float(pos.get("positionValue") or 0.0),
                        "unrealized_pnl": float(pos.get("unrealizedPnl") or 0.0),
                    }
                )
            snapshot["hyperliquid"]["positions"] = positions

            # Spot state: token balances; this is separate from perp margin.
            spot_payload = {"type": "spotClearinghouseState", "user": hl_wallet}
            spot_req = urllib.request.Request(
                hl_info,
                data=json.dumps(spot_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(spot_req, timeout=12) as resp:
                spot_state = json.loads(resp.read().decode("utf-8"))
            balances = spot_state.get("balances") if isinstance(spot_state, dict) else []
            token_after_maint = spot_state.get("tokenToAvailableAfterMaintenance") if isinstance(spot_state, dict) else []

            spot_balances = []
            spot_total_usdc = 0.0
            if isinstance(balances, list):
                for b in balances:
                    if not isinstance(b, dict):
                        continue
                    coin = str(b.get("coin") or "")
                    total = float(b.get("total") or 0.0)
                    hold = float(b.get("hold") or 0.0)
                    entry_ntl = float(b.get("entryNtl") or 0.0)
                    spot_balances.append(
                        {
                            "coin": coin,
                            "total": total,
                            "hold": hold,
                            "entry_ntl": entry_ntl,
                        }
                    )
                    if coin.upper() in {"USDC", "USD"}:
                        spot_total_usdc += total
            snapshot["hyperliquid"]["spot_balances"] = spot_balances
            snapshot["hyperliquid"]["spot_total_usdc"] = round(spot_total_usdc, 6)
            if isinstance(token_after_maint, list):
                snapshot["hyperliquid"]["spot_available_after_maintenance"] = token_after_maint
            snapshot["hyperliquid"]["ok"] = True
        except Exception as exc:
            snapshot["hyperliquid"]["error"] = str(exc)
    else:
        snapshot["hyperliquid"]["error"] = "wallet not configured"

    return snapshot


def get_recent_trade_decisions(limit: int = 20) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "execution_orders"):
            return []
        cur = conn.cursor()
        has_routes = _table_exists(conn, "signal_routes")
        has_learning = _table_exists(conn, "execution_learning")
        if has_routes and has_learning:
            cur.execute(
                """
                SELECT
                  eo.created_at,
                  eo.route_id,
                  eo.ticker,
                  eo.direction,
                  eo.mode,
                  eo.notional,
                  eo.order_status,
                  eo.notes,
                  COALESCE(sr.source_tag,'') AS source_tag,
                  COALESCE(sr.score,0) AS score,
                  COALESCE(sr.reason,'') AS route_reason,
                  COALESCE(el.reason,'') AS learning_reason
                FROM execution_orders eo
                LEFT JOIN signal_routes sr ON sr.id = eo.route_id
                LEFT JOIN execution_learning el ON el.route_id = eo.route_id
                ORDER BY eo.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        elif has_routes:
            cur.execute(
                """
                SELECT
                  eo.created_at,
                  eo.route_id,
                  eo.ticker,
                  eo.direction,
                  eo.mode,
                  eo.notional,
                  eo.order_status,
                  eo.notes,
                  COALESCE(sr.source_tag,'') AS source_tag,
                  COALESCE(sr.score,0) AS score,
                  COALESCE(sr.reason,'') AS route_reason,
                  '' AS learning_reason
                FROM execution_orders eo
                LEFT JOIN signal_routes sr ON sr.id = eo.route_id
                ORDER BY eo.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT
                  created_at,
                  route_id,
                  ticker,
                  direction,
                  mode,
                  notional,
                  order_status,
                  notes,
                  '' AS source_tag,
                  0 AS score,
                  '' AS route_reason,
                  '' AS learning_reason
                FROM execution_orders
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def set_execution_controls(updates: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "agent_master_enabled",
        "allow_live_trading",
        "allow_hyperliquid_live",
        "allow_equity_shorts",
        "enable_alpaca_paper_auto",
        "alpaca_min_route_score",
        "enable_hyperliquid_test_auto",
        "hyperliquid_min_route_score",
        "hyperliquid_test_notional_usd",
        "hyperliquid_test_leverage",
        "enable_polymarket_auto",
        "allow_polymarket_live",
        "polymarket_max_notional_usd",
        "polymarket_max_daily_exposure",
        "polymarket_min_edge_pct",
        "polymarket_min_confidence_pct",
        "polymarket_fee_gate_enabled",
        "polymarket_taker_fee_pct",
        "polymarket_fee_buffer_pct",
        "polymarket_manual_approval",
        "polymarket_approval_threshold",
        "polymarket_copy_enabled",
        "polymarket_arb_enabled",
        "polymarket_alpha_enabled",
        "polymarket_copy_max_notional_usd",
        "polymarket_arb_max_notional_usd",
        "polymarket_alpha_max_notional_usd",
        "consensus_enforce",
        "consensus_min_confirmations",
        "consensus_min_ratio",
        "consensus_min_score",
        "high_beta_only",
        "high_beta_min_beta",
        "weather_strict_station_required",
        "mm_enabled",
        "mm_risk_aversion",
        "mm_base_spread_bps",
        "mm_inventory_limit",
        "mm_toxicity_threshold",
        "mm_min_edge_bps",
        "quant_gate_enforce",
        "enable_allocator_causal",
        "allocator_regime_override",
        "allocator_min_source_samples",
        "allocator_block_posterior_floor",
        "allocator_max_scale_up",
        "allocator_max_scale_down",
        "auto_tuner_apply",
        "min_candidate_score",
        "max_open_positions",
        "max_daily_new_notional_usd",
        "max_signal_notional_usd",
        "auto_route_limit",
        "auto_route_notional",
        "x_influence_enabled",
        "input_auto_reweight_enabled",
        "input_weight_min_samples",
        "input_weight_floor",
        "input_weight_ceiling",
        "input_auto_disable_threshold",
        "missed_opportunity_resolver_enabled",
        "training_mode_enabled",
        "training_min_candidate_score",
        "training_consensus_min_confirmations",
        "training_consensus_min_ratio",
        "training_consensus_min_score",
        "training_alpaca_min_route_score",
        "training_hyperliquid_min_route_score",
        "training_polymarket_min_confidence_pct",
        "training_max_signal_notional_usd",
        "training_max_daily_new_notional_usd",
        "training_hyperliquid_test_notional_usd",
        "training_polymarket_max_notional_usd",
        "training_polymarket_max_daily_exposure",
        "grpo_alignment_enabled",
        "grpo_alignment_lookback_days",
        "grpo_alignment_min_samples",
        "grpo_alignment_weight_floor",
        "grpo_alignment_weight_ceiling",
        "grpo_apply_weight_updates",
        "grpo_llm_reasoner_enabled",
        "grpo_local_model",
        "kaggle_auto_pull_enabled",
        "kaggle_poly_dataset_slug",
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


def get_master_overview() -> Dict[str, Any]:
    summary = get_summary()
    controls_list = get_risk_controls()
    controls = {x.get("key"): x.get("value") for x in controls_list}

    alp_margin_capable = False
    alp_margin_multiplier = 1.0
    alp_margin_reason = "unavailable"
    try:
        env = _load_env()
        api_key = env.get("ALPACA_API_KEY", "")
        secret = env.get("ALPACA_SECRET_KEY", "")
        base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        if api_key and secret:
            req = urllib.request.Request(
                f"{base_url}/v2/account",
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret,
                    "Content-Type": "application/json",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            mm = float(data.get("multiplier") or 1.0)
            alp_margin_capable = mm > 1.0
            alp_margin_multiplier = mm
            alp_margin_reason = "ok"
        else:
            alp_margin_reason = "missing Alpaca credentials"
    except urllib.error.HTTPError as exc:
        alp_margin_reason = f"alpaca account http {exc.code}"
    except Exception as exc:
        alp_margin_reason = f"alpaca check error: {exc}"

    recent_exec = {"submitted": 0, "blocked": 0, "accepted": 0, "filled": 0}
    venue_24h = {
        "alpaca": {"events": 0, "submitted": 0, "filled": 0, "blocked": 0},
        "hyperliquid": {"events": 0, "submitted": 0, "filled": 0, "blocked": 0},
        "polymarket": {"events": 0, "submitted": 0, "filled": 0, "blocked": 0},
    }
    missed = {
        "lookback_days": 7,
        "not_taken_total": 0,
        "not_taken_resolved": 0,
        "not_taken_wins": 0,
        "not_taken_losses": 0,
        "not_taken_win_rate": 0.0,
        "not_taken_avg_pnl_pct": 0.0,
        "missed_winners_flagged": 0,
    }
    if DB_PATH.exists():
        conn = _connect()
        try:
            if _table_exists(conn, "execution_orders"):
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT lower(COALESCE(order_status,'')) AS s, COUNT(*)
                    FROM execution_orders
                    WHERE datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', '-24 hour')
                    GROUP BY s
                    """
                )
                for s, n in cur.fetchall():
                    if s in recent_exec:
                        recent_exec[s] = int(n or 0)
                has_venue_col = _column_exists(conn, "execution_orders", "venue")
                if has_venue_col:
                    cur.execute(
                        """
                        SELECT lower(COALESCE(venue,'')) AS v, lower(COALESCE(order_status,'')) AS s, COUNT(*)
                        FROM execution_orders
                        WHERE datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', '-24 hour')
                        GROUP BY v, s
                        """
                    )
                    iter_rows = cur.fetchall()
                else:
                    cur.execute(
                        """
                        SELECT lower(COALESCE(notes,'')) AS notes_v, lower(COALESCE(order_status,'')) AS s, COUNT(*)
                        FROM execution_orders
                        WHERE datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', '-24 hour')
                        GROUP BY notes_v, s
                        """
                    )
                    iter_rows = cur.fetchall()
                for v, s, n in iter_rows:
                    vv = str(v or "")
                    venue = "alpaca"
                    if "hyperliquid" in vv or "hl " in vv or " hl" in vv:
                        venue = "hyperliquid"
                    elif "alpaca" in vv:
                        venue = "alpaca"
                    venue_24h[venue]["events"] += int(n or 0)
                    if "fill" in str(s):
                        venue_24h[venue]["filled"] += int(n or 0)
                    elif "block" in str(s) or "reject" in str(s) or "fail" in str(s):
                        venue_24h[venue]["blocked"] += int(n or 0)
                    else:
                        venue_24h[venue]["submitted"] += int(n or 0)
            if _table_exists(conn, "polymarket_orders"):
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT lower(COALESCE(status,'')) AS s, COUNT(*)
                    FROM polymarket_orders
                    WHERE datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', '-24 hour')
                    GROUP BY s
                    """
                )
                for s, n in cur.fetchall():
                    venue_24h["polymarket"]["events"] += int(n or 0)
                    ss = str(s)
                    if "fill" in ss:
                        venue_24h["polymarket"]["filled"] += int(n or 0)
                    elif "block" in ss or "reject" in ss or "fail" in ss:
                        venue_24h["polymarket"]["blocked"] += int(n or 0)
                    else:
                        venue_24h["polymarket"]["submitted"] += int(n or 0)

            if _table_exists(conn, "signal_routes") and _table_exists(conn, "route_outcomes"):
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT
                      COUNT(*) AS not_taken_total,
                      SUM(CASE WHEN o.route_id IS NOT NULL THEN 1 ELSE 0 END) AS not_taken_resolved,
                      SUM(CASE WHEN o.route_id IS NOT NULL AND o.resolution='win' THEN 1 ELSE 0 END) AS not_taken_wins,
                      SUM(CASE WHEN o.route_id IS NOT NULL AND o.resolution='loss' THEN 1 ELSE 0 END) AS not_taken_losses,
                      AVG(CASE WHEN o.route_id IS NOT NULL THEN o.pnl_percent END) AS not_taken_avg_pnl_pct
                    FROM signal_routes r
                    LEFT JOIN route_outcomes o ON o.route_id = r.id
                    WHERE datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', '-7 day')
                      AND COALESCE(r.decision,'') <> 'approved'
                    """
                )
                row = cur.fetchone() or (0, 0, 0, 0, 0.0)
                missed["not_taken_total"] = int(row[0] or 0)
                missed["not_taken_resolved"] = int(row[1] or 0)
                missed["not_taken_wins"] = int(row[2] or 0)
                missed["not_taken_losses"] = int(row[3] or 0)
                missed["not_taken_avg_pnl_pct"] = round(float(row[4] or 0.0), 4)
                if missed["not_taken_resolved"] > 0:
                    missed["not_taken_win_rate"] = round((missed["not_taken_wins"] / missed["not_taken_resolved"]) * 100.0, 2)
                missed["missed_winners_flagged"] = missed["not_taken_wins"]
        finally:
            conn.close()

    wins = int(summary.get("wins") or 0)
    losses = int(summary.get("losses") or 0)
    total_closed = wins + losses
    win_rate = float(summary.get("win_rate") or 0.0)
    win_loss_ratio = round((wins / losses), 2) if losses > 0 else (float(wins) if wins > 0 else 0.0)

    return {
        "summary": {
            "total_trades": int(summary.get("total_trades") or 0),
            "open_trades": int(summary.get("open_trades") or 0),
            "wins": wins,
            "losses": losses,
            "total_closed": total_closed,
            "win_rate": win_rate,
            "win_loss_ratio": win_loss_ratio,
            "avg_pnl": float(summary.get("avg_pnl") or 0.0),
        },
        "controls": controls,
        "leverage": {
            "hl_test_leverage": float(controls.get("hyperliquid_test_leverage") or 1.0),
            "hl_live_enabled": controls.get("allow_hyperliquid_live", "0") == "1",
            "alpaca_margin_capable": alp_margin_capable,
            "alpaca_margin_multiplier": alp_margin_multiplier,
            "alpaca_margin_reason": alp_margin_reason,
        },
        "execution_24h": recent_exec,
        "venue_24h": venue_24h,
        "missed_opportunities": missed,
    }


def get_missed_opportunities(lookback_days: int = 7) -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "lookback_days": lookback_days,
            "not_taken_total": 0,
            "not_taken_resolved": 0,
            "not_taken_wins": 0,
            "not_taken_losses": 0,
            "not_taken_win_rate": 0.0,
            "not_taken_avg_pnl_pct": 0.0,
            "missed_winners_flagged": 0,
        }
    conn = _connect()
    try:
        if not _table_exists(conn, "signal_routes") or not _table_exists(conn, "route_outcomes"):
            return {
                "lookback_days": lookback_days,
                "not_taken_total": 0,
                "not_taken_resolved": 0,
                "not_taken_wins": 0,
                "not_taken_losses": 0,
                "not_taken_win_rate": 0.0,
                "not_taken_avg_pnl_pct": 0.0,
                "missed_winners_flagged": 0,
            }
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              COUNT(*) AS not_taken_total,
              SUM(CASE WHEN o.route_id IS NOT NULL THEN 1 ELSE 0 END) AS not_taken_resolved,
              SUM(CASE WHEN o.route_id IS NOT NULL AND o.resolution='win' THEN 1 ELSE 0 END) AS not_taken_wins,
              SUM(CASE WHEN o.route_id IS NOT NULL AND o.resolution='loss' THEN 1 ELSE 0 END) AS not_taken_losses,
              AVG(CASE WHEN o.route_id IS NOT NULL THEN o.pnl_percent END) AS not_taken_avg_pnl_pct
            FROM signal_routes r
            LEFT JOIN route_outcomes o ON o.route_id = r.id
            WHERE datetime(COALESCE(r.routed_at, '1970-01-01')) >= datetime('now', ?)
              AND COALESCE(r.decision,'') <> 'approved'
            """,
            (f"-{int(lookback_days)} day",),
        )
        row = cur.fetchone() or (0, 0, 0, 0, 0.0)
        out = {
            "lookback_days": lookback_days,
            "not_taken_total": int(row[0] or 0),
            "not_taken_resolved": int(row[1] or 0),
            "not_taken_wins": int(row[2] or 0),
            "not_taken_losses": int(row[3] or 0),
            "not_taken_avg_pnl_pct": round(float(row[4] or 0.0), 4),
            "not_taken_win_rate": 0.0,
            "missed_winners_flagged": int(row[2] or 0),
        }
        if out["not_taken_resolved"] > 0:
            out["not_taken_win_rate"] = round((out["not_taken_wins"] / out["not_taken_resolved"]) * 100.0, 2)
        return out
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
            SELECT routed_at, ticker, direction, score, source_tag, proposed_notional, mode, decision, reason, status,
                   COALESCE(preferred_venue,'') AS preferred_venue,
                   COALESCE(venue_scores_json,'{}') AS venue_scores_json,
                   COALESCE(venue_decisions_json,'{}') AS venue_decisions_json
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
        has_lev_used = _column_exists(conn, "execution_orders", "leverage_used")
        has_lev_cap = _column_exists(conn, "execution_orders", "leverage_capable")
        lev_used_expr = "COALESCE(leverage_used, 1.0)" if has_lev_used else "1.0"
        lev_cap_expr = "COALESCE(leverage_capable, 0)" if has_lev_cap else "0"
        cur.execute(
            f"""
            SELECT created_at, route_id, ticker, direction, mode, notional,
                   {lev_used_expr} AS leverage_used,
                   {lev_cap_expr} AS leverage_capable,
                   order_status, broker_order_id, notes
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
                       sentiment_score AS sentiment, pattern_type AS pattern, source_tag AS source,
                       COALESCE(confirmations,0) AS confirmations,
                       COALESCE(sources_total,0) AS sources_total,
                       COALESCE(consensus_ratio,0) AS consensus_ratio,
                       COALESCE(consensus_flag,0) AS consensus_flag,
                       COALESCE(evidence_json,'[]') AS evidence_json
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


def get_input_feature_stats(limit: int = 300, dimension: str = "") -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "input_feature_stats"):
            return []
        cur = conn.cursor()
        if dimension:
            cur.execute(
                """
                SELECT computed_at, outcome_type, dimension, dimension_value, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent
                FROM input_feature_stats
                WHERE dimension=?
                ORDER BY sample_size DESC, win_rate DESC
                LIMIT ?
                """,
                (dimension, limit),
            )
        else:
            cur.execute(
                """
                SELECT computed_at, outcome_type, dimension, dimension_value, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent
                FROM input_feature_stats
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
            FROM (
              SELECT *,
                     ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY id DESC) AS rn
              FROM chart_liquidity_signals
              WHERE COALESCE(pattern,'') <> 'insufficient_data'
            ) q
            WHERE q.rn = 1
            ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC
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


def get_breakthrough_events(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "breakthrough_events"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, source, modality, score, confidence, title, source_url, published_at, mapped_tickers_json
            FROM breakthrough_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        for r in rows:
            try:
                mapped = json.loads(r.get("mapped_tickers_json") or "[]")
                if isinstance(mapped, list):
                    r["mapped_tickers"] = ",".join([str(x) for x in mapped[:8]])
                else:
                    r["mapped_tickers"] = ""
            except Exception:
                r["mapped_tickers"] = ""
        return rows
    finally:
        conn.close()


def get_allocator_decisions(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "allocator_decisions"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, ticker, direction, source_tag, strategy_tag, regime,
                   base_score, adjusted_score, base_notional, adjusted_notional, factor, allowed, reason
            FROM allocator_decisions
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
            SELECT id, created_at, strategy_id, market_id, slug, question, outcome, implied_prob, model_prob, edge, confidence, source_tag, rationale, market_url, status
            FROM polymarket_candidates
            ORDER BY ABS(edge) DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_polymarket_aligned_setups(limit: int = 200, mode: str = "all") -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "polymarket_aligned_setups"):
            return []
        cur = conn.cursor()
        mode_norm = str(mode or "all").strip().lower()
        where = ""
        if mode_norm == "high_signal_low_interest":
            where = "WHERE class_tag='high_signal_low_interest'"
        elif mode_norm == "high_signal_direct":
            where = "WHERE class_tag='high_signal_direct'"
        elif mode_norm == "watchlist":
            where = "WHERE class_tag='watchlist'"
        cur.execute(
            f"""
            SELECT id, generated_at, ticker, direction, candidate_score, confirmations, sources_total, consensus_ratio,
                   source_tag, market_id, market_slug, question, market_url, liquidity, volume_24h,
                   implied_prob, match_score, alignment_confidence, signal_strength, source_quality,
                   resolution_clarity, crowding_penalty, fee_drag, alpha_score, class_tag, rationale, status
            FROM polymarket_aligned_setups
            {where}
            ORDER BY alpha_score DESC, alignment_confidence DESC, match_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_polymarket_orders(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "polymarket_orders"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, strategy_id, candidate_id, market_id, outcome, side, token_id, mode,
                   notional, price, size, order_id, status, notes, response_json
            FROM polymarket_orders
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        for row in rows:
            status = str(row.get("status") or "").lower()
            mode = str(row.get("mode") or "paper").lower()
            if status.startswith("submitted_live") or status.endswith("_live") or status in {"open_live", "partially_filled_live"}:
                row["money_type"] = "real"
            elif mode == "live":
                row["money_type"] = "real"
            else:
                row["money_type"] = "paper"

            if status.startswith("awaiting_approval"):
                row["stage"] = "approval"
            elif "block" in status:
                row["stage"] = "blocked"
            elif "fail" in status or "rejected" in status:
                row["stage"] = "failed"
            elif "fill" in status:
                row["stage"] = "filled"
            elif "submit" in status or "open" in status or "accept" in status:
                row["stage"] = "submitted"
            else:
                row["stage"] = "candidate"
        return rows
    finally:
        conn.close()


def get_polymarket_overview() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "mode": "paper",
            "live_enabled": False,
            "auto_enabled": False,
            "manual_approval": True,
            "approval_threshold": 10,
            "approval_count": 0,
            "daily_cap_usd": 20.0,
            "daily_used_usd": 0.0,
            "pending_approval": 0,
            "submitted_live": 0,
            "filled_live": 0,
            "submitted_paper": 0,
            "failed": 0,
            "blocked": 0,
        }

    conn = _connect()
    try:
        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        auto_enabled = controls.get("enable_polymarket_auto", "0") == "1"
        live_enabled = str(controls.get("allow_polymarket_live", "0")).strip().lower() in {"1", "true", "yes", "on", "enabled", "live"}
        manual_approval = controls.get("polymarket_manual_approval", "1") == "1"
        approval_threshold = int(float(controls.get("polymarket_approval_threshold", "10") or 10))
        approval_count = int(float(controls.get("polymarket_approval_count", "0") or 0))
        daily_cap = float(controls.get("polymarket_max_daily_exposure", "20") or 20)

        cur = conn.cursor()
        paper_used = 0.0
        live_used = 0.0
        if _table_exists(conn, "polymarket_orders"):
            for mode_name in ("paper", "live"):
                cur.execute(
                    """
                    SELECT COALESCE(SUM(notional), 0)
                    FROM polymarket_orders
                    WHERE date(created_at)=date('now')
                      AND lower(COALESCE(mode,''))=?
                      AND status IN (
                        'submitted_paper','filled_paper',
                        'submitted_live','accepted_live','open_live','partially_filled_live','filled_live',
                        'submitted'
                      )
                    """,
                    (mode_name,),
                )
                val = float((cur.fetchone() or [0.0])[0] or 0.0)
                if mode_name == "paper":
                    paper_used = val
                else:
                    live_used = val
        daily_used = live_used if live_enabled else paper_used

        def count_orders(where_clause: str) -> int:
            if not _table_exists(conn, "polymarket_orders"):
                return 0
            cur.execute(f"SELECT COUNT(*) FROM polymarket_orders WHERE {where_clause}")
            return int((cur.fetchone() or [0])[0] or 0)

        pending_approval = 0
        if _table_exists(conn, "polymarket_candidates"):
            cur.execute("SELECT COUNT(*) FROM polymarket_candidates WHERE status='awaiting_approval'")
            pending_approval = int((cur.fetchone() or [0])[0] or 0)

        return {
            "mode": "live" if live_enabled else "paper",
            "live_enabled": live_enabled,
            "auto_enabled": auto_enabled,
            "manual_approval": manual_approval,
            "approval_threshold": approval_threshold,
            "approval_count": approval_count,
            "daily_cap_usd": daily_cap,
            "daily_used_usd": round(daily_used, 4),
            "live_used_usd": round(live_used, 4),
            "paper_used_usd": round(paper_used, 4),
            "pending_approval": pending_approval,
            "submitted_live": count_orders("status IN ('submitted_live','accepted_live','open_live','partially_filled_live')"),
            "filled_live": count_orders("status='filled_live'"),
            "submitted_paper": count_orders("status='submitted_paper'"),
            "failed": count_orders("status IN ('submission_failed','rejected_live')"),
            "blocked": count_orders("status LIKE 'blocked%'"),
        }
    finally:
        conn.close()


def get_weather_market_probs(limit: int = 80) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "weather_market_probs"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, market_id, question, city, target_date, station_hint, source_hint, rounding_hint, model_count,
                   outcome_probs_json, best_outcome, best_prob, uncertainty, spread_c, market_url, status, notes
            FROM weather_market_probs
            ORDER BY best_prob DESC, model_count DESC, created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        for r in rows:
            try:
                probs = json.loads(r.get("outcome_probs_json") or "{}")
                if isinstance(probs, dict):
                    top = sorted(probs.items(), key=lambda x: float(x[1]), reverse=True)[:4]
                    r["top_probs"] = " | ".join([f"{k}:{round(float(v)*100,1)}%" for k, v in top])
                else:
                    r["top_probs"] = ""
            except Exception:
                r["top_probs"] = ""
        return rows
    finally:
        conn.close()


def get_polymarket_mm_snapshots(limit: int = 60, ready_only: bool = False) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "polymarket_mm_snapshots"):
            return []
        where = "WHERE COALESCE(execution_ready,0)=1" if ready_only else ""
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT created_at, ticker, direction, candidate_score, confirmations, sources_total, consensus_ratio,
                   market_id, market_question, market_url, match_score,
                   implied_prob, fair_prob, reservation_price, bid_price, ask_price,
                   spread_bps, edge_bps, inventory_qty, inventory_util_pct, toxicity,
                   source_accuracy, poly_exec_accuracy, state, execution_ready, rationale
            FROM polymarket_mm_snapshots
            {where}
            ORDER BY execution_ready DESC, edge_bps DESC, candidate_score DESC, created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_polymarket_mm_overview() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {
            "state": "offline",
            "mm_enabled": False,
            "ready_count": 0,
            "snapshot_count": 0,
            "avg_toxicity": 0.0,
            "avg_source_accuracy": 0.0,
            "poly_exec_accuracy_30d": 0.0,
            "poly_signal_accuracy_30d": 0.0,
            "avg_edge_bps": 0.0,
            "last_refresh": None,
        }
    conn = _connect()
    try:
        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        mm_enabled = str(controls.get("mm_enabled", "0")).strip().lower() in {"1", "true", "yes", "on"}
        tox_cut = float(controls.get("mm_toxicity_threshold", "0.72") or 0.72)
        if not _table_exists(conn, "polymarket_mm_snapshots"):
            return {
                "state": "offline",
                "mm_enabled": mm_enabled,
                "ready_count": 0,
                "snapshot_count": 0,
                "avg_toxicity": 0.0,
                "avg_source_accuracy": 0.0,
                "poly_exec_accuracy_30d": 0.0,
                "poly_signal_accuracy_30d": 0.0,
                "avg_edge_bps": 0.0,
                "last_refresh": None,
            }

        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              COUNT(*) AS n,
              SUM(COALESCE(execution_ready,0)) AS ready_n,
              AVG(COALESCE(toxicity,0)) AS avg_tox,
              AVG(COALESCE(source_accuracy,0)) AS avg_source_acc,
              AVG(COALESCE(poly_exec_accuracy,0)) AS avg_poly_exec_acc,
              AVG(COALESCE(edge_bps,0)) AS avg_edge_bps,
              MAX(created_at) AS last_refresh
            FROM polymarket_mm_snapshots
            """
        )
        row = cur.fetchone() or (0, 0, 0.0, 0.0, 0.0, 0.0, None)
        snapshot_n = int(row[0] or 0)
        ready_n = int(row[1] or 0)
        avg_tox = float(row[2] or 0.0)
        avg_source_acc = float(row[3] or 0.0)
        avg_poly_exec_acc = float(row[4] or 0.0)
        avg_edge = float(row[5] or 0.0)
        last_refresh = row[6]

        poly_signal_acc = 50.0
        if _table_exists(conn, "signal_routes") and _table_exists(conn, "route_outcomes"):
            cur.execute(
                """
                SELECT
                  SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' AND o.resolution='win' THEN 1 ELSE 0 END) AS wins,
                  SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' AND o.resolution IN ('win','loss') THEN 1 ELSE 0 END) AS total_n
                FROM route_outcomes o
                JOIN signal_routes r ON r.id=o.route_id
                WHERE datetime(COALESCE(r.routed_at,'1970-01-01')) >= datetime('now', '-30 day')
                  AND (UPPER(COALESCE(r.source_tag,'')) LIKE 'POLY%' OR UPPER(COALESCE(r.source_tag,'')) LIKE '%POLY%')
                """
            )
            wr = cur.fetchone() or (0, 0)
            wins = int(wr[0] or 0)
            total = int(wr[1] or 0)
            if total > 0:
                poly_signal_acc = (wins / total) * 100.0

        state = "good"
        if avg_tox >= tox_cut:
            state = "killswitch"
        elif avg_tox >= (tox_cut * 0.8):
            state = "caution"
        if not mm_enabled:
            state = "standby" if snapshot_n > 0 else "offline"

        return {
            "state": state,
            "mm_enabled": mm_enabled,
            "ready_count": ready_n,
            "snapshot_count": snapshot_n,
            "avg_toxicity": round(avg_tox, 4),
            "avg_source_accuracy": round(avg_source_acc, 2),
            "poly_exec_accuracy_30d": round(avg_poly_exec_acc, 2),
            "poly_signal_accuracy_30d": round(poly_signal_acc, 2),
            "avg_edge_bps": round(avg_edge, 2),
            "last_refresh": last_refresh,
        }
    finally:
        conn.close()


def approve_polymarket_candidates(ids: List[int]) -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"ok": False, "error": "database missing", "approved": 0}
    if not ids:
        return {"ok": False, "error": "no ids provided", "approved": 0}
    conn = _connect()
    try:
        if not _table_exists(conn, "polymarket_candidates"):
            return {"ok": False, "error": "polymarket_candidates missing", "approved": 0}
        cur = conn.cursor()
        approved = 0
        for cid in ids:
            try:
                cid_i = int(cid)
            except Exception:
                continue
            cur.execute("UPDATE polymarket_candidates SET status='approved' WHERE id=?", (cid_i,))
            approved += int(cur.rowcount or 0)
        conn.commit()
        return {"ok": True, "approved": approved}
    finally:
        conn.close()


def get_tracked_sources(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "tracked_x_sources"):
            return []
        has_x_api = _column_exists(conn, "tracked_x_sources", "x_api_enabled")
        has_weight = _column_exists(conn, "tracked_x_sources", "source_weight")
        x_api_expr = "x_api_enabled" if has_x_api else "1 AS x_api_enabled"
        weight_expr = "source_weight" if has_weight else "1.0 AS source_weight"
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, updated_at, handle, role_copy, role_alpha, active, """ + x_api_expr + """, """ + weight_expr + """, notes
            FROM tracked_x_sources
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def upsert_tracked_source(payload: Dict[str, Any]) -> Dict[str, Any]:
    handle = str((payload or {}).get("handle") or "").strip().lstrip("@")
    if not handle:
        return {"ok": False, "error": "handle required"}
    role_copy = 1 if bool((payload or {}).get("role_copy", True)) else 0
    role_alpha = 1 if bool((payload or {}).get("role_alpha", True)) else 0
    active = 1 if bool((payload or {}).get("active", True)) else 0
    x_api_enabled = 1 if bool((payload or {}).get("x_api_enabled", True)) else 0
    source_weight = float((payload or {}).get("source_weight", 1.0) or 1.0)
    if source_weight < 0.0:
        source_weight = 0.0
    if source_weight > 3.0:
        source_weight = 3.0
    notes = str((payload or {}).get("notes") or "").strip()

    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_x_sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              handle TEXT NOT NULL UNIQUE,
              role_copy INTEGER NOT NULL DEFAULT 1,
              role_alpha INTEGER NOT NULL DEFAULT 1,
              active INTEGER NOT NULL DEFAULT 1,
              x_api_enabled INTEGER NOT NULL DEFAULT 1,
              source_weight REAL NOT NULL DEFAULT 1.0,
              notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        if not _column_exists(conn, "tracked_x_sources", "x_api_enabled"):
            conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN x_api_enabled INTEGER NOT NULL DEFAULT 1")
        if not _column_exists(conn, "tracked_x_sources", "source_weight"):
            conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN source_weight REAL NOT NULL DEFAULT 1.0")
        conn.execute(
            """
            INSERT INTO tracked_x_sources (created_at, updated_at, handle, role_copy, role_alpha, active, x_api_enabled, source_weight, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
              updated_at=datetime('now'),
              role_copy=excluded.role_copy,
              role_alpha=excluded.role_alpha,
              active=excluded.active,
              x_api_enabled=excluded.x_api_enabled,
              source_weight=excluded.source_weight,
              notes=excluded.notes
            """,
            (handle, role_copy, role_alpha, active, x_api_enabled, float(source_weight), notes),
        )
        conn.commit()
        return {"ok": True, "handle": handle, "sources": get_tracked_sources()}
    finally:
        conn.close()


def _ensure_input_source_controls(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS input_source_controls (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          source_key TEXT NOT NULL UNIQUE,
          source_label TEXT NOT NULL DEFAULT '',
          source_class TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          manual_weight REAL NOT NULL DEFAULT 1.0,
          auto_weight REAL NOT NULL DEFAULT 1.0,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_input_source_controls_class ON input_source_controls(source_class)")
    conn.commit()


def _seed_input_sources_from_runtime(conn: sqlite3.Connection) -> None:
    _ensure_input_source_controls(conn)
    keys: List[tuple[str, str, str]] = [
        ("family:social", "Social Sentiment", "family"),
        ("family:pattern", "Pattern Quality", "family"),
        ("family:external", "External Signals", "family"),
        ("family:copy", "Copy Signals", "family"),
        ("family:pipeline", "Pipeline Signals", "family"),
        ("family:liquidity", "Liquidity Map", "family"),
    ]
    cur = conn.cursor()
    if _table_exists(conn, "tracked_x_sources"):
        cur.execute("SELECT handle FROM tracked_x_sources")
        for (h,) in cur.fetchall():
            hh = str(h or "").strip().lower()
            if hh:
                keys.append((f"x:{hh}", f"X @{hh}", "x_account"))
    if _table_exists(conn, "source_learning_stats"):
        cur.execute("SELECT DISTINCT source_tag FROM source_learning_stats")
        for (s,) in cur.fetchall():
            tag = str(s or "").strip()
            if tag:
                keys.append((f"source:{tag.lower()}", f"Source {tag}", "source_tag"))
    if _table_exists(conn, "strategy_learning_stats"):
        cur.execute("SELECT DISTINCT strategy_tag FROM strategy_learning_stats")
        for (s,) in cur.fetchall():
            tag = str(s or "").strip()
            if tag:
                keys.append((f"pipeline:{tag.upper()}", f"Pipeline {tag}", "pipeline"))
    seen = set()
    for key, label, klass in keys:
        if key in seen:
            continue
        seen.add(key)
        conn.execute(
            """
            INSERT INTO input_source_controls
            (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, 1, 1.0, 1.0, '')
            ON CONFLICT(source_key) DO UPDATE SET
              source_label=COALESCE(NULLIF(excluded.source_label,''), input_source_controls.source_label),
              source_class=COALESCE(NULLIF(excluded.source_class,''), input_source_controls.source_class),
              updated_at=input_source_controls.updated_at
            """,
            (key, label, klass),
        )
    conn.commit()


def get_input_source_controls(limit: int = 400) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "input_source_controls"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight,
                   ROUND(COALESCE(manual_weight,1.0) * COALESCE(auto_weight,1.0), 6) AS effective_weight,
                   notes
            FROM input_source_controls
            ORDER BY source_class ASC, source_key ASC
            LIMIT ?
            """,
            (int(limit),),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def upsert_input_source_control(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_key = str((payload or {}).get("source_key") or "").strip()
    if not source_key:
        return {"ok": False, "error": "source_key required"}
    source_label = str((payload or {}).get("source_label") or "").strip()
    source_class = str((payload or {}).get("source_class") or "").strip()
    enabled = 1 if bool((payload or {}).get("enabled", True)) else 0
    manual_weight = float((payload or {}).get("manual_weight", 1.0) or 1.0)
    auto_weight = float((payload or {}).get("auto_weight", 1.0) or 1.0)
    notes = str((payload or {}).get("notes") or "").strip()
    manual_weight = max(0.0, min(5.0, manual_weight))
    auto_weight = max(0.1, min(5.0, auto_weight))

    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        _ensure_input_source_controls(conn)
        conn.execute(
            """
            INSERT INTO input_source_controls
            (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
              updated_at=datetime('now'),
              source_label=excluded.source_label,
              source_class=excluded.source_class,
              enabled=excluded.enabled,
              manual_weight=excluded.manual_weight,
              auto_weight=excluded.auto_weight,
              notes=excluded.notes
            """,
            (source_key, source_label, source_class, int(enabled), float(manual_weight), float(auto_weight), notes),
        )
        conn.commit()
        return {"ok": True, "source_key": source_key}
    finally:
        conn.close()


def get_tracked_polymarket_wallets(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_polymarket_wallets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              handle TEXT NOT NULL UNIQUE,
              profile_url TEXT NOT NULL DEFAULT '',
              role_copy INTEGER NOT NULL DEFAULT 1,
              role_alpha INTEGER NOT NULL DEFAULT 1,
              active INTEGER NOT NULL DEFAULT 1,
              notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, updated_at, handle, profile_url, role_copy, role_alpha, active, notes
            FROM tracked_polymarket_wallets
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def upsert_tracked_polymarket_wallet(payload: Dict[str, Any]) -> Dict[str, Any]:
    handle = str((payload or {}).get("handle") or "").strip().lstrip("@")
    if not handle:
        return {"ok": False, "error": "handle required"}
    profile_url = str((payload or {}).get("profile_url") or "").strip()
    role_copy = 1 if bool((payload or {}).get("role_copy", True)) else 0
    role_alpha = 1 if bool((payload or {}).get("role_alpha", True)) else 0
    active = 1 if bool((payload or {}).get("active", True)) else 0
    notes = str((payload or {}).get("notes") or "").strip()

    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_polymarket_wallets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              handle TEXT NOT NULL UNIQUE,
              profile_url TEXT NOT NULL DEFAULT '',
              role_copy INTEGER NOT NULL DEFAULT 1,
              role_alpha INTEGER NOT NULL DEFAULT 1,
              active INTEGER NOT NULL DEFAULT 1,
              notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            INSERT INTO tracked_polymarket_wallets
            (created_at, updated_at, handle, profile_url, role_copy, role_alpha, active, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
              updated_at=datetime('now'),
              profile_url=excluded.profile_url,
              role_copy=excluded.role_copy,
              role_alpha=excluded.role_alpha,
              active=excluded.active,
              notes=excluded.notes
            """,
            (handle, profile_url, role_copy, role_alpha, active, notes),
        )
        conn.commit()
        return {"ok": True, "handle": handle, "wallets": get_tracked_polymarket_wallets()}
    finally:
        conn.close()


def get_polymarket_wallet_scores(limit: int = 100) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "tracked_polymarket_wallets"):
            return []

        cur = conn.cursor()
        wallets = get_tracked_polymarket_wallets(limit=limit)
        wallet_map = {str(w.get("handle") or "").strip().lower(): w for w in wallets}
        out: List[Dict[str, Any]] = []

        if _table_exists(conn, "polymarket_wallet_scores"):
            cur.execute(
                """
                SELECT s.handle, s.sample_size, s.wins, s.losses, s.win_rate, s.avg_pnl_pct, s.reliability_score
                FROM polymarket_wallet_scores s
                INNER JOIN (
                  SELECT handle, MAX(computed_at) AS latest
                  FROM polymarket_wallet_scores
                  GROUP BY handle
                ) t
                  ON t.handle = s.handle AND t.latest = s.computed_at
                ORDER BY s.reliability_score DESC, s.sample_size DESC
                LIMIT ?
                """,
                (limit,),
            )
            for h, sample_size, wins, losses, win_rate, avg_pnl_pct, reliability in cur.fetchall():
                wl = wallet_map.get(str(h or "").strip().lower(), {})
                out.append(
                    {
                        "handle": str(h or ""),
                        "profile_url": str(wl.get("profile_url") or ""),
                        "sample_size": int(sample_size or 0),
                        "wins": int(wins or 0),
                        "losses": int(losses or 0),
                        "win_rate": round(float(win_rate or 0.0), 2),
                        "avg_pnl_pct": round(float(avg_pnl_pct or 0.0), 2),
                        "reliability_score": round(float(reliability or 0.0), 2),
                        "active": int(wl.get("active") or 0),
                    }
                )
            if out:
                return out

        # Fallback to tracked wallets even if scoring table hasn't run yet.
        for w in wallets:
            out.append(
                {
                    "handle": str(w.get("handle") or ""),
                    "profile_url": str(w.get("profile_url") or ""),
                    "sample_size": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "avg_pnl_pct": 0.0,
                    "reliability_score": 0.0,
                    "active": int(w.get("active") or 0),
                }
            )
        return out[:limit]
    finally:
        conn.close()


def get_trust_panel() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"state": "bad", "reason": "database missing"}
    conn = _connect()
    try:
        controls = {x["key"]: x["value"] for x in get_risk_controls()}
        master = controls.get("agent_master_enabled", "0") == "1"
        consensus_enforce = controls.get("consensus_enforce", "1") == "1"
        cmin = int(float(controls.get("consensus_min_confirmations", "3") or 3))
        cratio = float(controls.get("consensus_min_ratio", "0.6") or 0.6)
        cscore = float(controls.get("consensus_min_score", "60") or 60)

        flagged = 0
        total = 0
        if _table_exists(conn, "trade_candidates"):
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM trade_candidates")
            total = int((cur.fetchone() or [0])[0] or 0)
            cur.execute("SELECT COUNT(*) FROM trade_candidates WHERE COALESCE(consensus_flag,0)=1")
            flagged = int((cur.fetchone() or [0])[0] or 0)

        top_sources = []
        if _table_exists(conn, "source_learning_stats"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT source_tag, sample_size, round(win_rate,2), round(avg_pnl_percent,2)
                FROM source_learning_stats
                ORDER BY sample_size DESC, win_rate DESC
                LIMIT 8
                """
            )
            top_sources = [
                {"source": r[0], "samples": int(r[1] or 0), "win_rate": float(r[2] or 0), "avg_pnl_pct": float(r[3] or 0)}
                for r in cur.fetchall()
            ]

        state = "good" if master and flagged > 0 else ("warn" if flagged > 0 else "bad")
        return {
            "state": state,
            "master_enabled": master,
            "consensus_enforce": consensus_enforce,
            "consensus_thresholds": {
                "min_confirmations": cmin,
                "min_ratio": cratio,
                "min_score": cscore,
            },
            "candidates_total": total,
            "candidates_flagged": flagged,
            "flagged_ratio": round((flagged / total), 4) if total else 0.0,
            "top_sources": top_sources,
        }
    finally:
        conn.close()


def get_consensus_candidates(limit: int = 100, flagged_only: bool = True) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "trade_candidates"):
            return []
        ratings = get_source_ratings(limit=500)
        rating_map: Dict[str, Dict[str, Any]] = {}
        for r in ratings:
            k = str(r.get("source") or "").strip().lower()
            if k:
                rating_map[k] = r
        # Backfill/merge with source_scores for sources not yet represented in source_learning_stats.
        if _table_exists(conn, "source_scores"):
            cur_scores = conn.cursor()
            cur_scores.execute(
                """
                SELECT source_tag, COALESCE(sample_size,0), COALESCE(approved_rate,0), COALESCE(reliability_score,0)
                FROM source_scores
                ORDER BY sample_size DESC
                LIMIT 800
                """
            )
            for source, signals_seen, approval_rate, reliability_score in cur_scores.fetchall():
                key = str(source or "").strip().lower()
                if not key:
                    continue
                existing = rating_map.get(key)
                incoming = {
                    "source": str(source or ""),
                    "sample_size": int(signals_seen or 0),
                    "win_rate": float(approval_rate or 0.0),
                    "avg_pnl_pct": float(reliability_score or 0.0),
                }
                if not existing or int(existing.get("sample_size") or 0) < incoming["sample_size"]:
                    rating_map[key] = incoming

        def _source_rating_for(tag: str) -> Dict[str, Any]:
            raw = str(tag or "").strip()
            key = raw.lower()
            candidates = [key]
            if key.startswith("liquidity_map:"):
                candidates.append("pipeline:chart_liquidity")
            if ":" in key:
                parts = key.split(":")
                if len(parts) >= 2:
                    candidates.append(f"{parts[0]}:{parts[1]}")
                candidates.append(parts[0])
            for cand in candidates:
                hit = rating_map.get(cand)
                if hit:
                    return {
                        "source": raw,
                        "matched_source": hit.get("source", ""),
                        "sample_size": int(hit.get("sample_size") or 0),
                        "win_rate": float(hit.get("win_rate") or 0.0),
                        "avg_pnl_pct": float(hit.get("avg_pnl_pct") or 0.0),
                    }
            return {
                "source": raw,
                "matched_source": "",
                "sample_size": 0,
                "win_rate": 0.0,
                "avg_pnl_pct": 0.0,
            }

        ticker_aliases: Dict[str, List[str]] = {
            "TSLA": ["tesla", "elon", "musk"],
            "AEM": ["agnico", "agnico eagle", "gold price"],
            "BTC": ["bitcoin", "btc", "crypto"],
            "ETH": ["ethereum", "eth", "crypto"],
            "NVDA": ["nvidia", "ai", "chips", "semiconductor"],
            "PLTR": ["palantir", "defense", "software"],
            "SPY": ["s&p", "sp500", "stocks", "equities"],
            "QQQ": ["nasdaq", "tech stocks", "nq"],
        }

        def _poly_matches(ticker: str, direction: str, max_rows: int = 3) -> List[Dict[str, Any]]:
            if not _table_exists(conn, "polymarket_markets"):
                return []
            t = str(ticker or "").strip().upper()
            if not t:
                return []
            tokens = [t.lower()] + ticker_aliases.get(t, [])
            tokens = [x for x in dict.fromkeys([str(x).strip().lower() for x in tokens if x])]
            if not tokens:
                return []
            cur_m = conn.cursor()
            cur_m.execute(
                """
                SELECT market_id, question, slug, market_url, liquidity, volume_24h
                FROM polymarket_markets
                WHERE active=1 AND closed=0
                ORDER BY liquidity DESC, volume_24h DESC
                LIMIT 700
                """
            )
            out: List[Dict[str, Any]] = []
            up_words = {"up", "rise", "higher", "above", "yes", "bull", "increase", "gain"}
            down_words = {"down", "fall", "lower", "below", "no", "bear", "decrease", "drop"}
            sports_noise = ("stanley cup", "nba finals", "world series", "super bowl", "champions league")
            for market_id, question, slug, market_url, liquidity, volume_24h in cur_m.fetchall():
                q = str(question or "").lower()
                s = str(slug or "").lower()
                score = 0
                question_hits = 0
                hits = []
                for tok in tokens:
                    if not tok:
                        continue
                    if len(tok) < 3 and tok not in {"btc", "eth", "spy", "qqq"}:
                        continue
                    # strict-ish token hit in question, relaxed hit in slug
                    if re.search(rf"(^|[^a-z0-9]){re.escape(tok)}([^a-z0-9]|$)", q):
                        score += 5
                        question_hits += 1
                        hits.append(tok)
                    elif re.search(rf"(^|[^a-z0-9]){re.escape(tok)}([^a-z0-9]|$)", s):
                        score += 2
                        hits.append(tok)
                if score <= 0:
                    continue
                if question_hits == 0:
                    # no direct semantic question match, avoid weak slug-only joins
                    continue
                if any(noise in q for noise in sports_noise) and str(ticker or "").upper() not in {"BTC", "ETH"}:
                    # prevent accidental joins like "gold" -> "Golden Knights"
                    continue
                if str(direction or "").lower() == "long" and any(w in q for w in up_words):
                    score += 1
                if str(direction or "").lower() == "short" and any(w in q for w in down_words):
                    score += 1
                out.append(
                    {
                        "market_id": str(market_id or ""),
                        "question": str(question or ""),
                        "market_url": str(market_url or ""),
                        "liquidity": round(float(liquidity or 0.0), 2),
                        "volume_24h": round(float(volume_24h or 0.0), 2),
                        "match_score": score,
                        "matched_terms": sorted(list(set(hits))),
                    }
                )
            out.sort(key=lambda x: (x["match_score"], x["liquidity"], x["volume_24h"]), reverse=True)
            return out[:max_rows]

        cur = conn.cursor()
        where = "WHERE COALESCE(consensus_flag,0)=1" if flagged_only else ""
        cur.execute(
            f"""
            SELECT generated_at, ticker, direction, score, source_tag,
                   COALESCE(confirmations,0) AS confirmations,
                   COALESCE(sources_total,0) AS sources_total,
                   COALESCE(consensus_ratio,0) AS consensus_ratio,
                   COALESCE(consensus_flag,0) AS consensus_flag,
                   COALESCE(evidence_json,'[]') AS evidence_json
            FROM trade_candidates
            {where}
            ORDER BY score DESC, consensus_ratio DESC, confirmations DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        for r in rows:
            try:
                ev = json.loads(r.get("evidence_json") or "[]")
                if isinstance(ev, list):
                    r["evidence"] = ", ".join([str(x) for x in ev[:6]])
                    evidence_list = [str(x) for x in ev[:10]]
                    r["evidence_list"] = evidence_list
                    ratings_list = [_source_rating_for(x) for x in evidence_list]
                    r["evidence_ratings"] = ratings_list
                    r["evidence_ratings_text"] = " | ".join(
                        [
                            f"{x['source']} ({x['win_rate']:.1f}%/{x['sample_size']})"
                            for x in ratings_list[:6]
                        ]
                    )
                else:
                    r["evidence"] = ""
                    r["evidence_list"] = []
                    r["evidence_ratings"] = []
                    r["evidence_ratings_text"] = ""
            except Exception:
                r["evidence"] = ""
                r["evidence_list"] = []
                r["evidence_ratings"] = []
                r["evidence_ratings_text"] = ""
            matches = _poly_matches(str(r.get("ticker") or ""), str(r.get("direction") or ""), max_rows=3)
            r["polymarket_matches"] = matches
            if matches:
                top = matches[0]
                r["polymarket_best"] = f"{top.get('question','')} (liq ${top.get('liquidity',0)})"
            else:
                r["polymarket_best"] = "No direct market match"
        return rows
    finally:
        conn.close()


def get_source_ratings(limit: int = 50) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        cur = conn.cursor()
        rows: List[Dict[str, Any]] = []
        if _table_exists(conn, "source_learning_stats"):
            cur.execute(
                """
                SELECT source_tag AS source,
                       sample_size,
                       wins,
                       losses,
                       round(win_rate,2) AS win_rate,
                       round(avg_pnl_percent,2) AS avg_pnl_pct
                FROM source_learning_stats
                ORDER BY sample_size DESC, win_rate DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows.extend(_rows_to_dicts(cur, cur.fetchall()))

        if _table_exists(conn, "source_scores"):
            if _column_exists(conn, "source_scores", "source_tag"):
                cur.execute(
                    """
                    SELECT source_tag AS source,
                           sample_size,
                           CAST(round((approved_rate * 100.0),2) AS REAL) AS wins,
                           CAST(round(((1.0 - approved_rate) * 100.0),2) AS REAL) AS losses,
                           CAST(round((approved_rate * 100.0),2) AS REAL) AS win_rate,
                           round(reliability_score,2) AS avg_pnl_pct
                    FROM source_scores
                    ORDER BY sample_size DESC, reliability_score DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cur.execute(
                    """
                    SELECT source AS source,
                           signals_seen AS sample_size,
                           approvals AS wins,
                           MAX(signals_seen - approvals, 0) AS losses,
                           round(approval_rate,2) AS win_rate,
                           round(reliability_score,2) AS avg_pnl_pct
                    FROM source_scores
                    ORDER BY signals_seen DESC, reliability_score DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            score_rows = _rows_to_dicts(cur, cur.fetchall())
            # merge by source if source_learning_stats was present
            if rows:
                have = {str(x.get("source") or "").lower() for x in rows}
                rows.extend([x for x in score_rows if str(x.get("source") or "").lower() not in have])
            else:
                rows = score_rows

        if _table_exists(conn, "polymarket_wallet_scores"):
            cur.execute(
                """
                SELECT
                  ('poly_wallet:' || handle) AS source,
                  sample_size,
                  wins,
                  losses,
                  round(win_rate,2) AS win_rate,
                  round(avg_pnl_pct,2) AS avg_pnl_pct
                FROM polymarket_wallet_scores
                ORDER BY reliability_score DESC, sample_size DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows.extend(_rows_to_dicts(cur, cur.fetchall()))

        rows.sort(key=lambda x: (int(x.get("sample_size") or 0), float(x.get("win_rate") or 0.0)), reverse=True)
        return rows[:limit]
    finally:
        conn.close()
