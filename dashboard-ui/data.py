import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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


def _normalize_x_handle(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = re.split(r"[?#\s]", raw, maxsplit=1)[0].strip()
    if re.match(r"^(?:www\.)?(?:x\.com|twitter\.com)/", raw, flags=re.IGNORECASE):
        raw = "https://" + raw.lstrip("/")
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower().replace("www.", "")
    candidate = raw
    if host:
        if host in {"x.com", "twitter.com"}:
            candidate = parsed.path.strip("/").split("/", 1)[0]
        else:
            candidate = parsed.path.strip("/").split("/", 1)[0] or parsed.netloc
    candidate = candidate.strip().lstrip("@")
    candidate = re.sub(r"[^A-Za-z0-9_]", "", candidate)
    return candidate.lower()


def _extract_x_handle(payload: Dict[str, Any]) -> str:
    data = payload or {}
    # Accept nested payload wrappers from differing clients.
    if isinstance(data.get("payload"), dict):
        data = data.get("payload") or data
    elif isinstance(data.get("data"), dict):
        data = data.get("data") or data
    for key in ("handle", "x_handle", "src_handle", "source_handle", "username", "screen_name", "profile_url", "url"):
        normalized = _normalize_x_handle(data.get(key))
        if normalized:
            return normalized
    return ""


def _normalize_ticker(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    raw = re.sub(r"[^A-Z0-9._-]", "", raw)
    return raw[:24]


def _parse_json_list(payload_value: Any, *, lower: bool = False, max_items: int = 20) -> List[str]:
    data = payload_value
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                data = json.loads(text)
            except Exception:
                data = []
        else:
            data = [x.strip() for x in text.split(",")]
    if not isinstance(data, list):
        return []
    out: List[str] = []
    for item in data:
        val = str(item or "").strip()
        if not val:
            continue
        out.append(val.lower() if lower else val)
        if len(out) >= int(max_items):
            break
    return out


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


def get_learning_monitor() -> Dict[str, Any]:
    base = {
        "learning_health": get_learning_health(lookback_days=7),
        "outcomes": {
            "realized_total": 0,
            "operational_total": 0,
            "unknown_total": 0,
            "realized_24h": 0,
            "operational_24h": 0,
            "last_resolved_at": "",
            "last_resolved_age_min": None,
        },
        "horizons": {
            "rows_total": 0,
            "by_horizon": [],
        },
        "trades": {
            "open_total": 0,
            "closed_total": 0,
            "closed_with_route": 0,
        },
        "readiness": {
            "state": "",
            "reasons": "",
            "apply_live_updates": "0",
        },
        "reconciler": {
            "last_status": "",
            "last_attempt_utc": "",
            "last_success_utc": "",
        },
    }
    if not DB_PATH.exists():
        return base

    conn = _connect()
    try:
        cur = conn.cursor()
        if _table_exists(conn, "route_outcomes"):
            cur.execute(
                """
                SELECT
                  SUM(CASE WHEN COALESCE(outcome_type,'realized')='realized' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(outcome_type,'realized')='operational' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(outcome_type,'realized') NOT IN ('realized','operational') THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(outcome_type,'realized')='realized' AND datetime(COALESCE(resolved_at,'1970-01-01')) >= datetime('now','-24 hour') THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(outcome_type,'realized')='operational' AND datetime(COALESCE(resolved_at,'1970-01-01')) >= datetime('now','-24 hour') THEN 1 ELSE 0 END),
                  MAX(resolved_at)
                FROM route_outcomes
                """
            )
            row = cur.fetchone() or (0, 0, 0, 0, 0, "")
            last_resolved = str(row[5] or "")
            base["outcomes"] = {
                "realized_total": int(row[0] or 0),
                "operational_total": int(row[1] or 0),
                "unknown_total": int(row[2] or 0),
                "realized_24h": int(row[3] or 0),
                "operational_24h": int(row[4] or 0),
                "last_resolved_at": last_resolved,
                "last_resolved_age_min": _age_minutes(last_resolved),
            }

        if _table_exists(conn, "route_outcomes_horizons"):
            cur.execute(
                """
                SELECT horizon_hours, COUNT(*) AS n, AVG(pnl_percent) AS avg_pnl_pct
                FROM route_outcomes_horizons
                GROUP BY horizon_hours
                ORDER BY horizon_hours ASC
                """
            )
            by_h = []
            total = 0
            for h, n, avg_pct in cur.fetchall():
                ni = int(n or 0)
                total += ni
                by_h.append(
                    {
                        "horizon_hours": int(h or 0),
                        "count": ni,
                        "avg_pnl_pct": round(float(avg_pct or 0.0), 4),
                    }
                )
            base["horizons"] = {"rows_total": total, "by_horizon": by_h}

        if _table_exists(conn, "trades"):
            cur.execute(
                """
                SELECT
                  SUM(CASE WHEN COALESCE(status,'')='open' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(status,'')='closed' THEN 1 ELSE 0 END),
                  SUM(CASE WHEN COALESCE(status,'')='closed' AND COALESCE(route_id,0)>0 THEN 1 ELSE 0 END)
                FROM trades
                """
            )
            row = cur.fetchone() or (0, 0, 0)
            base["trades"] = {
                "open_total": int(row[0] or 0),
                "closed_total": int(row[1] or 0),
                "closed_with_route": int(row[2] or 0),
            }

        if _table_exists(conn, "execution_controls"):
            cur.execute(
                """
                SELECT key, value
                FROM execution_controls
                WHERE key IN (
                  'runtime:grpo_readiness_state',
                  'runtime:grpo_readiness_reasons',
                  'grpo_apply_weight_updates',
                  'runtime:realized_reconciler_last_status',
                  'runtime:realized_reconciler_last_attempt_utc',
                  'runtime:realized_reconciler_last_success_utc'
                )
                """
            )
            kv = {str(k): str(v) for k, v in cur.fetchall()}
            base["readiness"] = {
                "state": kv.get("runtime:grpo_readiness_state", ""),
                "reasons": kv.get("runtime:grpo_readiness_reasons", ""),
                "apply_live_updates": kv.get("grpo_apply_weight_updates", "0"),
            }
            base["reconciler"] = {
                "last_status": kv.get("runtime:realized_reconciler_last_status", ""),
                "last_attempt_utc": kv.get("runtime:realized_reconciler_last_attempt_utc", ""),
                "last_success_utc": kv.get("runtime:realized_reconciler_last_success_utc", ""),
            }
        return base
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
        hl_auto = controls.get("enable_hyperliquid_test_auto", "0") == "1"
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
        checks.append({"name": "Hyperliquid Auto", "state": "good" if hl_auto else "warn", "detail": "enabled" if hl_auto else "disabled"})
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

        pos_age = None
        open_hl_positions = 0
        if _table_exists(conn, "position_awareness_snapshots"):
            pos_age = _age_minutes(_latest_value(conn, "position_awareness_snapshots", "created_at"))
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(DISTINCT symbol)
                FROM position_awareness_snapshots
                WHERE venue='hyperliquid'
                  AND datetime(COALESCE(created_at, '1970-01-01')) >= datetime('now', '-90 minutes')
                """
            )
            row = cur.fetchone()
            open_hl_positions = int((row[0] if row and row[0] is not None else 0) or 0)
        checks.append(
            {
                "name": "Position Snapshot Freshness",
                "state": "good" if (pos_age is not None and pos_age <= 90) else ("warn" if not hl_auto else "bad"),
                "detail": f"{pos_age} min ago" if pos_age is not None else "no snapshot data",
            }
        )
        checks.append(
            {
                "name": "Open HL Positions Seen",
                "state": "good" if open_hl_positions > 0 else "warn",
                "detail": f"{open_hl_positions} position(s) in last 90m",
            }
        )

        manage_age = None
        if _table_exists(conn, "trade_intents"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT created_at
                FROM trade_intents
                WHERE COALESCE(status,'') LIKE 'manage_%'
                ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC
                LIMIT 1
                """
            )
            r = cur.fetchone()
            manage_age = _age_minutes(r[0]) if r and r[0] else None
        manage_state = "good"
        manage_detail = "no open positions require active manage intents"
        if open_hl_positions > 0:
            if manage_age is None:
                manage_state = "bad"
                manage_detail = "no manage intents generated for current open positions"
            elif manage_age > 180:
                manage_state = "warn"
                manage_detail = f"last manage intent {manage_age} min ago (stale)"
            else:
                manage_detail = f"last manage intent {manage_age} min ago"
        checks.append({"name": "Open Position Plan", "state": manage_state, "detail": manage_detail})

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
        if hl_auto and pos_age is None:
            blockers.append("hyperliquid position snapshots missing; open-position awareness is blind")
        elif hl_auto and pos_age is not None and pos_age > 180:
            warnings.append("hyperliquid position snapshots are stale (>180 min)")
        if open_hl_positions > 0 and manage_age is None:
            blockers.append("open Hyperliquid positions detected but no management plan intents were generated")
        elif open_hl_positions > 0 and manage_age is not None and manage_age > 180:
            warnings.append("open Hyperliquid positions exist but management intents are stale")

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
        "sync_broker": "cd /Users/Shared/curtis/trader-curtis && (python3.11 ./sync_alpaca_order_status.py || python3 ./sync_alpaca_order_status.py)",
        "refresh_learning": "cd /Users/Shared/curtis/trader-curtis && ./scripts/run_realized_reconciler.sh && ./source_ranker.py",
        "run_realized_reconciler": "cd /Users/Shared/curtis/trader-curtis && ./scripts/run_realized_reconciler.sh",
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


def apply_position_protection(payload: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str((payload or {}).get("symbol") or "").strip().upper()
    mode = str((payload or {}).get("mode") or "stop").strip().lower()
    requested_stop = float((payload or {}).get("stop_price") or 0.0)
    qty_pct = float((payload or {}).get("qty_pct") or 100.0)
    trailing_gap_pct = float((payload or {}).get("trailing_gap_pct") or 0.0)
    dry_run = str((payload or {}).get("dry_run") or "0").strip().lower() in {"1", "true", "yes", "on"}
    cancel_existing = str((payload or {}).get("cancel_existing") or "1").strip().lower() in {"1", "true", "yes", "on"}

    if not symbol:
        return {"ok": False, "error": "symbol is required"}
    if mode not in {"stop", "trailing"}:
        return {"ok": False, "error": "mode must be stop or trailing"}
    qty_pct = max(0.1, min(100.0, qty_pct))

    env = _load_env()
    wallet = str(env.get("HL_WALLET_ADDRESS", "") or "").strip()
    if not wallet:
        return {"ok": False, "error": "HL_WALLET_ADDRESS missing"}

    api_url = str(env.get("HL_API_URL", "") or "").strip().rstrip("/")
    if not api_url:
        api_url = "https://api.hyperliquid-testnet.xyz" if str(env.get("HL_USE_TESTNET", "0")).strip().lower() in {"1", "true", "yes", "on"} else "https://api.hyperliquid.xyz"
    info_url = str(env.get("HL_INFO_URL", "") or "").strip().rstrip("/") or f"{api_url}/info"
    network = "testnet" if "testnet" in api_url else "mainnet"

    controls = {x["key"]: x["value"] for x in get_risk_controls()}
    hl_live_allowed = str(controls.get("allow_hyperliquid_live", "0")) == "1"
    if network != "testnet" and not hl_live_allowed:
        return {"ok": False, "error": "allow_hyperliquid_live=0; refusing mainnet stop order"}

    # Pull live position state directly from HL.
    try:
        req = urllib.request.Request(
            info_url,
            data=json.dumps({"type": "clearinghouseState", "user": wallet}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            state = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"hyperliquid state read failed: {exc}"}

    position: Dict[str, Any] = {}
    for item in (state.get("assetPositions") or []):
        if not isinstance(item, dict):
            continue
        pos = item.get("position", {}) if isinstance(item.get("position"), dict) else {}
        coin = str(pos.get("coin") or "").strip().upper()
        if coin != symbol:
            continue
        szi = float(pos.get("szi") or 0.0)
        if abs(szi) <= 1e-10:
            continue
        entry_price = float(pos.get("entryPx") or 0.0)
        position_value = float(pos.get("positionValue") or 0.0)
        mark_price = 0.0
        if abs(position_value) > 0 and abs(szi) > 0:
            mark_price = abs(position_value) / abs(szi)
        if mark_price <= 0:
            mark_price = float(pos.get("markPx") or pos.get("markPrice") or 0.0)
        position = {
            "symbol": coin,
            "side": "long" if szi > 0 else "short",
            "szi": float(szi),
            "qty_abs": abs(float(szi)),
            "entry_price": entry_price,
            "mark_price": mark_price,
            "unrealized_pnl": float(pos.get("unrealizedPnl") or 0.0),
        }
        break

    if not position:
        return {"ok": False, "error": f"no open HL position found for {symbol}"}

    qty_abs = float(position["qty_abs"])
    qty_to_protect = qty_abs * (qty_pct / 100.0)
    if qty_to_protect <= 0:
        return {"ok": False, "error": "computed qty_to_protect <= 0"}

    stop_price = float(requested_stop or 0.0)
    if mode == "trailing":
        gap = trailing_gap_pct
        if gap <= 0:
            gap = float(controls.get("position_trailing_stop_gap_pct", "2.5") or 2.5)
        mark = float(position.get("mark_price") or 0.0)
        if mark <= 0:
            return {"ok": False, "error": "mark price unavailable for trailing stop"}
        if position["side"] == "long":
            stop_price = mark * (1.0 - gap / 100.0)
        else:
            stop_price = mark * (1.0 + gap / 100.0)
    elif stop_price <= 0:
        sl_pct = float(controls.get("position_stop_loss_pct", "5") or 5.0)
        anchor = float(position.get("entry_price") or 0.0) or float(position.get("mark_price") or 0.0)
        if anchor <= 0:
            return {"ok": False, "error": "entry/mark unavailable for stop fallback"}
        if position["side"] == "long":
            stop_price = anchor * (1.0 - abs(sl_pct) / 100.0)
        else:
            stop_price = anchor * (1.0 + abs(sl_pct) / 100.0)

    if stop_price <= 0:
        return {"ok": False, "error": "computed stop_price <= 0"}

    exit_side = "sell" if position["side"] == "long" else "buy"
    response = {
        "ok": True,
        "dry_run": dry_run,
        "network": network,
        "symbol": symbol,
        "position_side": position["side"],
        "exit_side": exit_side,
        "qty_abs": round(qty_abs, 8),
        "qty_to_protect": round(float(qty_to_protect), 8),
        "qty_pct": round(float(qty_pct), 4),
        "entry_price": round(float(position.get("entry_price") or 0.0), 8),
        "mark_price": round(float(position.get("mark_price") or 0.0), 8),
        "stop_price": round(float(stop_price), 8),
        "mode": mode,
        "cancel_existing": bool(cancel_existing),
    }
    if dry_run:
        return response

    helper = BASE_DIR / "scripts" / "apply_hl_protection.py"
    if not helper.exists():
        return {**response, "ok": False, "error": "helper script missing: scripts/apply_hl_protection.py"}
    py = "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python"
    if not Path(py).exists():
        py = sys.executable or "python3"
    cmd = [
        py,
        str(helper),
        "--symbol",
        symbol,
        "--side",
        exit_side,
        "--qty",
        str(float(qty_to_protect)),
        "--stop-price",
        str(float(stop_price)),
        "--cancel-existing",
        "1" if cancel_existing else "0",
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=45,
            cwd=str(BASE_DIR),
        )
    except Exception as exc:
        return {**response, "ok": False, "error": f"stop helper launch failed: {exc}"}

    raw = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parsed: Dict[str, Any] = {}
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {"ok": False, "message": "invalid helper json", "details": {"stdout": raw[:800], "stderr": err[:800]}}

    ok = bool(parsed.get("ok"))
    msg = str(parsed.get("message") or ("submitted stop order" if ok else "stop helper failed"))
    details = parsed.get("details") if isinstance(parsed.get("details"), dict) else {"stdout": raw[:800], "stderr": err[:800]}
    if not ok and err:
        details["stderr"] = err[:1200]
    return {
        **response,
        "ok": bool(ok),
        "message": msg,
        "details": details if isinstance(details, dict) else {"raw": str(details)},
    }


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
        "polymarket": {
            "ok": False,
            "wallet": "",
            "filled_live_count": 0,
            "net_exposure_usd": 0.0,
            "positions": [],
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
                lev = 1.0
                lev_raw = pos.get("leverage")
                if isinstance(lev_raw, dict):
                    lev = float(lev_raw.get("value") or 1.0)
                elif lev_raw is not None:
                    lev = float(lev_raw or 1.0)
                positions.append(
                    {
                        "coin": pos.get("coin", ""),
                        "szi": pos.get("szi", ""),
                        "entry_price": float(pos.get("entryPx") or 0.0),
                        "mark_price": float(pos.get("markPx") or pos.get("markPrice") or 0.0),
                        "position_value": float(pos.get("positionValue") or 0.0),
                        "unrealized_pnl": float(pos.get("unrealizedPnl") or 0.0),
                        "unrealized_pnl_pct": float(pos.get("returnOnEquity") or 0.0) * 100.0,
                        "leverage": lev,
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

    # Polymarket live position view from filled live orders.
    try:
        conn = _connect()
        try:
            controls = {x["key"]: x["value"] for x in get_risk_controls()}
            live_enabled = str(controls.get("allow_polymarket_live", "0")).strip().lower() in {"1", "true", "yes", "on", "enabled", "live"}
            snapshot["polymarket"]["wallet"] = str(env.get("POLY_FUNDER", "") or "")
            if _table_exists(conn, "polymarket_orders"):
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT market_id,
                           outcome,
                           MAX(created_at) AS last_at,
                           SUM(CASE
                                 WHEN lower(COALESCE(side,''))='sell' THEN -1.0*COALESCE(notional,0)
                                 ELSE COALESCE(notional,0)
                               END) AS net_notional,
                           COUNT(*) AS trades
                    FROM polymarket_orders
                    WHERE lower(COALESCE(mode,''))='live'
                      AND lower(COALESCE(status,''))='filled_live'
                    GROUP BY market_id, outcome
                    HAVING ABS(COALESCE(net_notional,0)) > 0.000001
                    ORDER BY last_at DESC
                    LIMIT 100
                    """
                )
                rows = []
                total_abs = 0.0
                for market_id, outcome, last_at, net_notional, trades in cur.fetchall():
                    net_v = float(net_notional or 0.0)
                    total_abs += abs(net_v)
                    rows.append(
                        {
                            "market_id": str(market_id or ""),
                            "outcome": str(outcome or ""),
                            "net_notional": round(net_v, 6),
                            "trades": int(trades or 0),
                            "last_at": str(last_at or ""),
                        }
                    )
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM polymarket_orders
                    WHERE lower(COALESCE(mode,''))='live'
                      AND lower(COALESCE(status,''))='filled_live'
                    """
                )
                filled_count = int((cur.fetchone() or [0])[0] or 0)
                snapshot["polymarket"]["filled_live_count"] = filled_count
                snapshot["polymarket"]["net_exposure_usd"] = round(total_abs, 6)
                snapshot["polymarket"]["positions"] = rows
                snapshot["polymarket"]["ok"] = bool(live_enabled or filled_count > 0 or rows)
            else:
                snapshot["polymarket"]["error"] = "polymarket_orders table missing"
        finally:
            conn.close()
    except Exception as exc:
        snapshot["polymarket"]["error"] = str(exc)

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
                  COALESCE(el.reason,'') AS learning_reason,
                  (
                    SELECT COALESCE(tc.rationale,'')
                    FROM trade_candidates tc
                    WHERE UPPER(COALESCE(tc.ticker,''))=UPPER(COALESCE(eo.ticker,''))
                    ORDER BY datetime(COALESCE(tc.generated_at,'1970-01-01')) DESC
                    LIMIT 1
                  ) AS candidate_rationale,
                  (
                    SELECT COALESCE(tc.input_breakdown_json,'[]')
                    FROM trade_candidates tc
                    WHERE UPPER(COALESCE(tc.ticker,''))=UPPER(COALESCE(eo.ticker,''))
                    ORDER BY datetime(COALESCE(tc.generated_at,'1970-01-01')) DESC
                    LIMIT 1
                  ) AS candidate_inputs
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
                  '' AS learning_reason,
                  (
                    SELECT COALESCE(tc.rationale,'')
                    FROM trade_candidates tc
                    WHERE UPPER(COALESCE(tc.ticker,''))=UPPER(COALESCE(eo.ticker,''))
                    ORDER BY datetime(COALESCE(tc.generated_at,'1970-01-01')) DESC
                    LIMIT 1
                  ) AS candidate_rationale,
                  (
                    SELECT COALESCE(tc.input_breakdown_json,'[]')
                    FROM trade_candidates tc
                    WHERE UPPER(COALESCE(tc.ticker,''))=UPPER(COALESCE(eo.ticker,''))
                    ORDER BY datetime(COALESCE(tc.generated_at,'1970-01-01')) DESC
                    LIMIT 1
                  ) AS candidate_inputs
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
                  '' AS learning_reason,
                  (
                    SELECT COALESCE(tc.rationale,'')
                    FROM trade_candidates tc
                    WHERE UPPER(COALESCE(tc.ticker,''))=UPPER(COALESCE(execution_orders.ticker,''))
                    ORDER BY datetime(COALESCE(tc.generated_at,'1970-01-01')) DESC
                    LIMIT 1
                  ) AS candidate_rationale,
                  (
                    SELECT COALESCE(tc.input_breakdown_json,'[]')
                    FROM trade_candidates tc
                    WHERE UPPER(COALESCE(tc.ticker,''))=UPPER(COALESCE(execution_orders.ticker,''))
                    ORDER BY datetime(COALESCE(tc.generated_at,'1970-01-01')) DESC
                    LIMIT 1
                  ) AS candidate_inputs
                FROM execution_orders
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_pnl_breakdown(limit: int = 120) -> Dict[str, Any]:
    base = {
        "closed_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "top_winners": [],
        "top_losers": [],
        "recent_closed": [],
    }
    if not DB_PATH.exists():
        return base
    conn = _connect()
    try:
        if not _table_exists(conn, "trades"):
            return base
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              COALESCE(t.trade_id,'') AS trade_id,
              UPPER(COALESCE(t.ticker,'')) AS ticker,
              COALESCE(t.exit_date, t.created_at, '') AS closed_at,
              COALESCE(t.pnl, 0) AS pnl,
              COALESCE(t.pnl_percent, 0) AS pnl_percent,
              COALESCE(t.shares, 0) AS shares,
              COALESCE(t.route_id, 0) AS route_id,
              COALESCE(sr.source_tag, '') AS source_tag,
              COALESCE(sr.score, 0) AS route_score,
              COALESCE(sr.reason, '') AS route_reason
            FROM trades t
            LEFT JOIN signal_routes sr ON sr.id = t.route_id
            WHERE lower(COALESCE(t.status,''))='closed'
            ORDER BY datetime(COALESCE(t.exit_date, t.created_at, '1970-01-01')) DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        if not rows:
            return base

        wins = 0
        losses = 0
        total_pnl = 0.0
        for row in rows:
            pnl = float(row.get("pnl") or 0.0)
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
        closed_count = len(rows)
        avg_pnl = total_pnl / closed_count if closed_count else 0.0
        win_rate = (wins / closed_count) * 100.0 if closed_count else 0.0

        by_pnl_desc = sorted(rows, key=lambda x: float(x.get("pnl") or 0.0), reverse=True)
        top_winners = [r for r in by_pnl_desc if float(r.get("pnl") or 0.0) > 0][:8]
        top_losers = [r for r in sorted(rows, key=lambda x: float(x.get("pnl") or 0.0)) if float(r.get("pnl") or 0.0) < 0][:8]

        return {
            "closed_count": int(closed_count),
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(float(win_rate), 2),
            "total_pnl": round(float(total_pnl), 4),
            "avg_pnl": round(float(avg_pnl), 4),
            "top_winners": top_winners,
            "top_losers": top_losers,
            "recent_closed": rows[:30],
        }
    finally:
        conn.close()


def _input_friendly_name(key: str) -> str:
    k = str(key or "").strip().lower()
    if k == "family:liquidity":
        return "Liquidity setup quality"
    if k == "family:pipeline":
        return "Strategy score"
    if k == "family:pattern":
        return "Pattern confidence"
    if k == "family:social":
        return "Social sentiment"
    if k == "family:external":
        return "External signal confidence"
    if k == "family:copy":
        return "Copy/call signal strength"
    if k.startswith("strategy:"):
        return "Strategy-specific weight"
    if k.startswith("source:"):
        return "Source feed weight"
    if k.startswith("pipeline:"):
        return "Pipeline family weight"
    if k.startswith("x:"):
        return "Tracked X handle weight"
    return str(key or "").replace("_", " ")


def _input_friendly_help(key: str) -> str:
    k = str(key or "").strip().lower()
    if k == "family:liquidity":
        return "This favors setups with cleaner entry/stop/target structure. It helps entry timing."
    if k == "family:pipeline":
        return "This favors your strategy engine score. Higher means strategy score drives decisions more."
    if k == "family:pattern":
        return "This favors chart pattern reliability (breakouts, reversals, traps)."
    if k == "family:social":
        return "This favors social sentiment inputs."
    if k == "family:external":
        return "This favors news/event/external data signals."
    if k == "family:copy":
        return "This favors copy-trade style signals from tracked sources."
    if k.startswith("strategy:"):
        return "This is a strategy-specific override for one strategy profile."
    if k.startswith("source:"):
        return "This is a source-specific override for one feed."
    if k.startswith("pipeline:"):
        return "This is a pipeline-level override."
    if k.startswith("x:"):
        return "This controls influence from one tracked X handle."
    return "This input contributes to trade scoring."


def _ensure_trade_feedback_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_feedback_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          identifier TEXT NOT NULL,
          route_id INTEGER NOT NULL DEFAULT 0,
          trade_id TEXT NOT NULL DEFAULT '',
          ticker TEXT NOT NULL DEFAULT '',
          feedback_action TEXT NOT NULL DEFAULT '',
          rating REAL NOT NULL DEFAULT 0.0,
          notes TEXT NOT NULL DEFAULT '',
          apply_now INTEGER NOT NULL DEFAULT 0,
          applied INTEGER NOT NULL DEFAULT 0,
          applied_at TEXT NOT NULL DEFAULT '',
          snapshot_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_feedback_input_votes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          review_id INTEGER NOT NULL,
          input_key TEXT NOT NULL,
          input_value REAL NOT NULL DEFAULT 0.0,
          input_weight REAL NOT NULL DEFAULT 1.0,
          suggested_multiplier REAL NOT NULL DEFAULT 1.0,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_feedback_reviews_applied ON trade_feedback_reviews(applied, apply_now)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_feedback_votes_review ON trade_feedback_input_votes(review_id)")
    conn.commit()


def _parse_input_breakdown_json(raw: str) -> List[Dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        arr = json.loads(text)
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        try:
            value = float(item.get("value", 0.0) or 0.0)
        except Exception:
            value = 0.0
        try:
            weight = float(item.get("weight", 1.0) or 1.0)
        except Exception:
            weight = 1.0
        out.append(
            {
                "key": key,
                "name": _input_friendly_name(key),
                "help": _input_friendly_help(key),
                "value": round(value, 6),
                "weight": round(weight, 6),
            }
        )
    out.sort(key=lambda x: float(x.get("value") or 0.0), reverse=True)
    return out


def _simple_trade_explanation(
    ticker: str,
    direction: str,
    outcome_label: str,
    score: float,
    top_inputs: List[Dict[str, Any]],
    route_reason: str,
) -> str:
    inputs = [str(x.get("name") or x.get("key") or "input") for x in top_inputs[:3]]
    input_text = ", ".join(inputs) if inputs else "no strong inputs were recorded"
    d = str(direction or "unknown").upper()
    return (
        f"We took a {d} idea on {ticker or 'this ticker'} because the system score was {score:.1f} and "
        f"the strongest signals were {input_text}. "
        f"Result: {outcome_label}. "
        f"In plain terms, the model saw enough green lights at the time, then the market moved {'with' if outcome_label == 'WIN' else 'against' if outcome_label == 'LOSS' else 'sideways to'} the setup."
        + (f" Main gate reason was: {route_reason[:180]}." if route_reason else "")
    )


def get_trade_explain(identifier: str) -> Dict[str, Any]:
    ident = str(identifier or "").strip()
    if not ident:
        return {"ok": False, "error": "identifier required"}
    if ident.lower().startswith("route_"):
        tail = ident.split("_", 1)[1].strip()
        if tail.isdigit():
            ident = tail
    if not DB_PATH.exists():
        return {"ok": False, "error": "database missing"}
    conn = _connect()
    try:
        cur = conn.cursor()
        is_num = ident.isdigit()
        route_id = 0
        trade: Dict[str, Any] = {}

        if _table_exists(conn, "trades"):
            if is_num:
                cur.execute(
                    """
                    SELECT trade_id, COALESCE(route_id,0), UPPER(COALESCE(ticker,'')), COALESCE(status,''), COALESCE(pnl,0), COALESCE(pnl_percent,0),
                           COALESCE(entry_date,''), COALESCE(exit_date,''), COALESCE(shares,0), COALESCE(entry_price,0), COALESCE(exit_price,0)
                    FROM trades
                    WHERE COALESCE(route_id,0)=?
                    ORDER BY datetime(COALESCE(exit_date, created_at, '1970-01-01')) DESC
                    LIMIT 1
                    """,
                    (int(ident),),
                )
            else:
                cur.execute(
                    """
                    SELECT trade_id, COALESCE(route_id,0), UPPER(COALESCE(ticker,'')), COALESCE(status,''), COALESCE(pnl,0), COALESCE(pnl_percent,0),
                           COALESCE(entry_date,''), COALESCE(exit_date,''), COALESCE(shares,0), COALESCE(entry_price,0), COALESCE(exit_price,0)
                    FROM trades
                    WHERE COALESCE(trade_id,'')=?
                    ORDER BY datetime(COALESCE(exit_date, created_at, '1970-01-01')) DESC
                    LIMIT 1
                    """,
                    (ident,),
                )
            row = cur.fetchone()
            if row:
                trade = {
                    "trade_id": str(row[0] or ""),
                    "route_id": int(row[1] or 0),
                    "ticker": str(row[2] or ""),
                    "status": str(row[3] or ""),
                    "pnl": float(row[4] or 0.0),
                    "pnl_percent": float(row[5] or 0.0),
                    "entry_date": str(row[6] or ""),
                    "exit_date": str(row[7] or ""),
                    "shares": float(row[8] or 0.0),
                    "entry_price": float(row[9] or 0.0),
                    "exit_price": float(row[10] or 0.0),
                }
                route_id = int(trade.get("route_id") or 0)

        if not trade and _table_exists(conn, "execution_orders") and is_num:
            cur.execute(
                """
                SELECT COALESCE(route_id,0), UPPER(COALESCE(ticker,'')), COALESCE(direction,''), COALESCE(order_status,''), COALESCE(notional,0), COALESCE(created_at,'')
                FROM execution_orders
                WHERE id=? OR COALESCE(route_id,0)=?
                ORDER BY datetime(COALESCE(created_at,'1970-01-01')) DESC
                LIMIT 1
                """,
                (int(ident), int(ident)),
            )
            row = cur.fetchone()
            if row:
                route_id = int(row[0] or 0)
                trade = {
                    "trade_id": f"execution:{ident}",
                    "route_id": route_id,
                    "ticker": str(row[1] or ""),
                    "status": str(row[3] or ""),
                    "pnl": 0.0,
                    "pnl_percent": 0.0,
                    "entry_date": str(row[5] or ""),
                    "exit_date": "",
                    "shares": 0.0,
                    "entry_price": 0.0,
                    "exit_price": 0.0,
                }

        if not trade and is_num and _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT id, UPPER(COALESCE(ticker,'')), COALESCE(direction,''), COALESCE(score,0), COALESCE(status,''), COALESCE(routed_at,'')
                FROM signal_routes
                WHERE id=?
                LIMIT 1
                """,
                (int(ident),),
            )
            row = cur.fetchone()
            if row:
                route_id = int(row[0] or 0)
                trade = {
                    "trade_id": f"route_{route_id}",
                    "route_id": route_id,
                    "ticker": str(row[1] or ""),
                    "status": str(row[4] or ""),
                    "pnl": 0.0,
                    "pnl_percent": 0.0,
                    "entry_date": str(row[5] or ""),
                    "exit_date": "",
                    "shares": 0.0,
                    "entry_price": 0.0,
                    "exit_price": 0.0,
                }

        if not trade:
            return {"ok": False, "error": f"trade not found for identifier {ident}"}

        route = {
            "id": 0,
            "ticker": trade.get("ticker", ""),
            "direction": "",
            "score": 0.0,
            "source_tag": "",
            "decision": "",
            "status": "",
            "preferred_venue": "",
            "reason": "",
            "routed_at": "",
        }
        if route_id > 0 and _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT id, UPPER(COALESCE(ticker,'')), COALESCE(direction,''), COALESCE(score,0), COALESCE(source_tag,''), COALESCE(decision,''),
                       COALESCE(status,''), COALESCE(preferred_venue,''), COALESCE(reason,''), COALESCE(routed_at,'')
                FROM signal_routes
                WHERE id=?
                LIMIT 1
                """,
                (route_id,),
            )
            row = cur.fetchone()
            if row:
                route = {
                    "id": int(row[0] or 0),
                    "ticker": str(row[1] or ""),
                    "direction": str(row[2] or ""),
                    "score": float(row[3] or 0.0),
                    "source_tag": str(row[4] or ""),
                    "decision": str(row[5] or ""),
                    "status": str(row[6] or ""),
                    "preferred_venue": str(row[7] or ""),
                    "reason": str(row[8] or ""),
                    "routed_at": str(row[9] or ""),
                }

        outcome = {
            "outcome_type": "",
            "resolution": "",
            "pnl": float(trade.get("pnl") or 0.0),
            "pnl_percent": float(trade.get("pnl_percent") or 0.0),
            "resolved_at": str(trade.get("exit_date") or ""),
        }
        if route_id > 0 and _table_exists(conn, "route_outcomes"):
            cur.execute(
                """
                SELECT COALESCE(outcome_type,''), COALESCE(resolution,''), COALESCE(pnl,0), COALESCE(pnl_percent,0), COALESCE(resolved_at,'')
                FROM route_outcomes
                WHERE route_id=?
                ORDER BY datetime(COALESCE(resolved_at,'1970-01-01')) DESC
                LIMIT 1
                """,
                (route_id,),
            )
            row = cur.fetchone()
            if row:
                outcome = {
                    "outcome_type": str(row[0] or ""),
                    "resolution": str(row[1] or ""),
                    "pnl": float(row[2] or 0.0),
                    "pnl_percent": float(row[3] or 0.0),
                    "resolved_at": str(row[4] or ""),
                }

        candidate = {"rationale": "", "input_breakdown": [], "generated_at": "", "score": 0.0,
                     "evidence_items": [], "pipeline_breakdown": [],
                     "sentiment_score": None, "pattern_type": "", "pattern_score": None,
                     "external_confidence": None, "confirmations": 0}
        if _table_exists(conn, "trade_candidates"):
            ticker = str(trade.get("ticker") or "")
            route_ts = str(route.get("routed_at") or "")
            if ticker:
                if route_ts:
                    cur.execute(
                        """
                        SELECT COALESCE(rationale,''), COALESCE(input_breakdown_json,'[]'),
                               COALESCE(generated_at,''), COALESCE(score,0),
                               COALESCE(evidence_json,'[]'), COALESCE(source_tag,''),
                               COALESCE(sentiment_score,0), COALESCE(pattern_type,''),
                               COALESCE(pattern_score,0), COALESCE(external_confidence,0),
                               COALESCE(confirmations,0)
                        FROM trade_candidates
                        WHERE UPPER(COALESCE(ticker,''))=?
                        ORDER BY ABS(julianday(COALESCE(generated_at,'1970-01-01')) - julianday(?)) ASC
                        LIMIT 1
                        """,
                        (ticker.upper(), route_ts),
                    )
                else:
                    cur.execute(
                        """
                        SELECT COALESCE(rationale,''), COALESCE(input_breakdown_json,'[]'),
                               COALESCE(generated_at,''), COALESCE(score,0),
                               COALESCE(evidence_json,'[]'), COALESCE(source_tag,''),
                               COALESCE(sentiment_score,0), COALESCE(pattern_type,''),
                               COALESCE(pattern_score,0), COALESCE(external_confidence,0),
                               COALESCE(confirmations,0)
                        FROM trade_candidates
                        WHERE UPPER(COALESCE(ticker,''))=?
                        ORDER BY datetime(COALESCE(generated_at,'1970-01-01')) DESC
                        LIMIT 1
                        """,
                        (ticker.upper(),),
                    )
                row = cur.fetchone()
                if row:
                    import json as _json
                    try:
                        ev_raw = _json.loads(row[4] or "[]")
                        evidence_items = ev_raw if isinstance(ev_raw, list) else []
                    except Exception:
                        evidence_items = []

                    candidate = {
                        "rationale": str(row[0] or ""),
                        "input_breakdown": _parse_input_breakdown_json(str(row[1] or "[]")),
                        "generated_at": str(row[2] or ""),
                        "score": float(row[3] or 0.0),
                        "evidence_items": evidence_items,
                        "pipeline_breakdown": [],
                        "sentiment_score": float(row[6] or 0.0),
                        "pattern_type": str(row[7] or ""),
                        "pattern_score": float(row[8] or 0.0),
                        "external_confidence": float(row[9] or 0.0),
                        "confirmations": int(row[10] or 0),
                    }

                    # Resolve pipeline sub-signals from evidence_json
                    # Handles both "pipeline:C_EVENT" (old) and "event_alpha:C_EVENT" (new promoted family)
                    if evidence_items and _table_exists(conn, "pipeline_signals"):
                        pipeline_ids = [
                            e.split(":", 1)[1] for e in evidence_items
                            if isinstance(e, str) and (e.startswith("pipeline:") or e.startswith("event_alpha:"))
                        ]
                        pipe_breakdown = []
                        for pid in pipeline_ids:
                            q_ts = str(route.get("routed_at") or row[2] or "")
                            if q_ts:
                                cur.execute(
                                    """
                                    SELECT pipeline_id, COALESCE(score,0), COALESCE(confidence,0),
                                           COALESCE(rationale,''), COALESCE(source_refs,''),
                                           COALESCE(direction,''), COALESCE(generated_at,'')
                                    FROM pipeline_signals
                                    WHERE UPPER(pipeline_id)=UPPER(?) AND UPPER(asset)=UPPER(?)
                                    ORDER BY ABS(julianday(generated_at) - julianday(?)) ASC
                                    LIMIT 1
                                    """,
                                    (pid, ticker, q_ts),
                                )
                            else:
                                cur.execute(
                                    """
                                    SELECT pipeline_id, COALESCE(score,0), COALESCE(confidence,0),
                                           COALESCE(rationale,''), COALESCE(source_refs,''),
                                           COALESCE(direction,''), COALESCE(generated_at,'')
                                    FROM pipeline_signals
                                    WHERE UPPER(pipeline_id)=UPPER(?) AND UPPER(asset)=UPPER(?)
                                    ORDER BY datetime(generated_at) DESC
                                    LIMIT 1
                                    """,
                                    (pid, ticker),
                                )
                            ps = cur.fetchone()
                            if ps:
                                pipe_breakdown.append({
                                    "pipeline_id": str(ps[0] or ""),
                                    "score": float(ps[1] or 0.0),
                                    "confidence": float(ps[2] or 0.0),
                                    "rationale": str(ps[3] or ""),
                                    "source": str(ps[4] or ""),
                                    "direction": str(ps[5] or ""),
                                    "generated_at": str(ps[6] or ""),
                                })
                        candidate["pipeline_breakdown"] = pipe_breakdown

        pnl = float(outcome.get("pnl") if outcome.get("pnl") is not None else trade.get("pnl", 0.0))
        if pnl > 0:
            outcome_label = "WIN"
        elif pnl < 0:
            outcome_label = "LOSS"
        else:
            outcome_label = "FLAT"

        simple = _simple_trade_explanation(
            ticker=str(trade.get("ticker") or ""),
            direction=str(route.get("direction") or ""),
            outcome_label=outcome_label,
            score=float(route.get("score") or candidate.get("score") or 0.0),
            top_inputs=candidate.get("input_breakdown") or [],
            route_reason=str(route.get("reason") or ""),
        )

        # Phase 6: Enhanced trade explain — 4 additional query blocks
        ticker = str(trade.get("ticker") or "")
        routed_at = str(route.get("routed_at") or "")

        # 1. Kelly verdict at trade time
        kelly = None
        if route_id > 0 and _table_exists(conn, "kelly_signals") and ticker:
            q_ts = routed_at or str(trade.get("entry_date") or "")
            if q_ts:
                cur.execute(
                    """
                    SELECT verdict, kelly_fraction, win_prob, payout_ratio, ev_percent, sample_size, verdict_reason
                    FROM kelly_signals
                    WHERE UPPER(ticker)=UPPER(?) AND direction=COALESCE(?,direction)
                    ORDER BY ABS(julianday(COALESCE(computed_at,'1970-01-01')) - julianday(?)) ASC
                    LIMIT 1
                    """,
                    (ticker, str(route.get("direction") or ""), q_ts),
                )
                krow = cur.fetchone()
                if krow:
                    kelly = {
                        "verdict": str(krow[0] or ""),
                        "fraction": round(float(krow[1] or 0.0), 4),
                        "win_prob": round(float(krow[2] or 0.0), 4),
                        "payout_ratio": round(float(krow[3] or 0.0), 4),
                        "ev_percent": round(float(krow[4] or 0.0), 2),
                        "sample_size": int(krow[5] or 0),
                        "verdict_reason": str(krow[6] or ""),
                    }

        # 2. Premium gate checklist (from evidence_json)
        premium_gate = None
        evidence_items = candidate.get("evidence_items") or []
        kelly_hit = any("pipeline:KYLE_WILLIAMS" in str(e) for e in evidence_items)
        liq_hit = any("liquidity_map:" in str(e) for e in evidence_items)
        mom_hit = any("momentum:" in str(e) for e in evidence_items)
        pg_entries = [e for e in evidence_items if isinstance(e, str) and e.startswith("premium_gate:")]
        pg_blocked = any("blocked" in str(e) for e in pg_entries)
        premium_gate = {
            "kelly_hit": kelly_hit,
            "liquidity_hit": liq_hit,
            "momentum_hit": mom_hit,
            "hits": sum([kelly_hit, liq_hit, mom_hit]),
            "passed": not pg_blocked,
            "gate_entries": pg_entries,
        }

        # 3. Position protection history (trade_intents)
        position_intents = []
        if _table_exists(conn, "trade_intents") and ticker:
            q_ts = routed_at or str(trade.get("entry_date") or "")
            if q_ts:
                cur.execute(
                    """
                    SELECT id, created_at, venue, symbol, side, qty, notional, status, details
                    FROM trade_intents
                    WHERE UPPER(symbol) = UPPER(?)
                      AND datetime(created_at) >= datetime(?, '-1 day')
                      AND datetime(created_at) <= datetime(?, '+7 days')
                    ORDER BY datetime(created_at) ASC
                    LIMIT 20
                    """,
                    (ticker, q_ts, q_ts),
                )
                for irow in cur.fetchall():
                    position_intents.append({
                        "id": int(irow[0] or 0),
                        "created_at": str(irow[1] or ""),
                        "venue": str(irow[2] or ""),
                        "symbol": str(irow[3] or ""),
                        "side": str(irow[4] or ""),
                        "qty": float(irow[5] or 0),
                        "notional": float(irow[6] or 0),
                        "status": str(irow[7] or ""),
                        "details": str(irow[8] or ""),
                    })

        # 4. Source stats at trade time
        source_stats = None
        source_tag = str(route.get("source_tag") or "")
        if source_tag and _table_exists(conn, "source_learning_stats"):
            cur.execute(
                """
                SELECT win_rate, sample_size, avg_pnl_percent
                FROM source_learning_stats
                WHERE source_tag = ?
                LIMIT 1
                """,
                (source_tag,),
            )
            srow = cur.fetchone()
            if srow:
                source_stats = {
                    "win_rate": round(float(srow[0] or 0.0), 1),
                    "sample_size": int(srow[1] or 0),
                    "avg_pnl_percent": round(float(srow[2] or 0.0), 2),
                }

        return {
            "ok": True,
            "identifier": ident,
            "trade": trade,
            "route": route,
            "outcome": outcome,
            "candidate": candidate,
            "simple_explanation": simple,
            "kelly": kelly,
            "premium_gate": premium_gate,
            "position_intents": position_intents,
            "source_stats": source_stats,
        }
    finally:
        conn.close()


def _apply_feedback_multipliers(
    conn: sqlite3.Connection,
    input_rows: List[Dict[str, Any]],
    multiplier: float,
    apply_column: str = "manual_weight",
) -> Dict[str, Any]:
    _ensure_input_source_controls(conn)
    cur = conn.cursor()
    updates = []
    for row in input_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        cur.execute("SELECT COALESCE(manual_weight,1.0), COALESCE(auto_weight,1.0), COALESCE(enabled,1), COALESCE(source_label,''), COALESCE(source_class,'') FROM input_source_controls WHERE source_key=? LIMIT 1", (key,))
        existing = cur.fetchone()
        if existing:
            manual_w = float(existing[0] or 1.0)
            auto_w = float(existing[1] or 1.0)
            enabled = int(existing[2] or 1)
            label = str(existing[3] or _input_friendly_name(key))
            klass = str(existing[4] or "feedback")
        else:
            manual_w = 1.0
            auto_w = 1.0
            enabled = 1
            label = _input_friendly_name(key)
            klass = "feedback"
            cur.execute(
                """
                INSERT OR IGNORE INTO input_source_controls
                (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, 1.0, 1.0, '')
                """,
                (key, label, klass, enabled),
            )

        if apply_column == "auto_weight":
            new_auto = max(0.1, min(5.0, auto_w * float(multiplier)))
            cur.execute(
                "UPDATE input_source_controls SET updated_at=datetime('now'), auto_weight=? WHERE source_key=?",
                (float(new_auto), key),
            )
            updates.append({"key": key, "from": auto_w, "to": new_auto, "column": "auto_weight"})
        else:
            new_manual = max(0.0, min(5.0, manual_w * float(multiplier)))
            cur.execute(
                "UPDATE input_source_controls SET updated_at=datetime('now'), manual_weight=? WHERE source_key=?",
                (float(new_manual), key),
            )
            updates.append({"key": key, "from": manual_w, "to": new_manual, "column": "manual_weight"})
    conn.commit()
    return {"updated": len(updates), "rows": updates}


def submit_trade_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    identifier = str((payload or {}).get("identifier") or "").strip()
    if not identifier:
        return {"ok": False, "error": "identifier required"}
    action = str((payload or {}).get("feedback_action") or "").strip().lower()
    if action not in {"boost", "downrank", "neutral"}:
        return {"ok": False, "error": "feedback_action must be boost, downrank, or neutral"}
    apply_now = bool((payload or {}).get("apply_now", False))
    notes = str((payload or {}).get("notes") or "").strip()
    rating = float((payload or {}).get("rating", 0.0) or 0.0)

    explain = get_trade_explain(identifier)
    if not explain.get("ok"):
        return {"ok": False, "error": explain.get("error", "trade not found")}

    if action == "boost":
        suggested_multiplier = 2.0
    elif action == "downrank":
        suggested_multiplier = 0.5
    else:
        suggested_multiplier = 1.0

    if not DB_PATH.exists():
        return {"ok": False, "error": "database missing"}
    selected_keys_raw: List[str] = []
    if isinstance((payload or {}).get("selected_input_keys"), list):
        selected_keys_raw = [str(x or "").strip().lower() for x in ((payload or {}).get("selected_input_keys") or []) if str(x or "").strip()]
    elif (payload or {}).get("selected_input_key"):
        selected_keys_raw = [str((payload or {}).get("selected_input_key") or "").strip().lower()]
    selected_keys = [k for k in selected_keys_raw if k]

    conn = _connect()
    try:
        _ensure_trade_feedback_tables(conn)
        trade = explain.get("trade") or {}
        route = explain.get("route") or {}
        candidate = explain.get("candidate") or {}
        candidate_inputs = (candidate.get("input_breakdown") or [])[:8]
        top_inputs = candidate_inputs[:5]
        if selected_keys:
            selected_rows: List[Dict[str, Any]] = []
            by_key = {str(x.get("key") or "").strip().lower(): x for x in candidate_inputs}
            for sk in selected_keys:
                row = by_key.get(sk)
                if row:
                    selected_rows.append(row)
                else:
                    selected_rows.append(
                        {
                            "key": sk,
                            "name": _input_friendly_name(sk),
                            "help": _input_friendly_help(sk),
                            "value": 0.0,
                            "weight": 1.0,
                        }
                    )
            top_inputs = selected_rows[:5]
        snapshot = {
            "trade": trade,
            "route": route,
            "outcome": explain.get("outcome") or {},
            "candidate_rationale": candidate.get("rationale", ""),
            "top_inputs": top_inputs,
            "simple_explanation": explain.get("simple_explanation", ""),
        }

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO trade_feedback_reviews
            (created_at, identifier, route_id, trade_id, ticker, feedback_action, rating, notes, apply_now, applied, applied_at, snapshot_json)
            VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?)
            """,
            (
                identifier,
                int(route.get("id") or trade.get("route_id") or 0),
                str(trade.get("trade_id") or ""),
                str(trade.get("ticker") or route.get("ticker") or ""),
                action,
                float(rating),
                notes,
                1 if apply_now else 0,
                json.dumps(snapshot, separators=(",", ":"), ensure_ascii=True),
            ),
        )
        review_id = int(cur.lastrowid or 0)
        for inp in top_inputs:
            cur.execute(
                """
                INSERT INTO trade_feedback_input_votes
                (review_id, input_key, input_value, input_weight, suggested_multiplier, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    review_id,
                    str(inp.get("key") or ""),
                    float(inp.get("value") or 0.0),
                    float(inp.get("weight") or 1.0),
                    float(suggested_multiplier),
                ),
            )
        conn.commit()

        applied = {"updated": 0, "rows": []}
        if apply_now and top_inputs:
            applied = _apply_feedback_multipliers(conn, top_inputs, suggested_multiplier, apply_column="manual_weight")
            cur.execute(
                "UPDATE trade_feedback_reviews SET applied=1, applied_at=datetime('now') WHERE id=?",
                (review_id,),
            )
            conn.commit()

        return {
            "ok": True,
            "review_id": review_id,
            "identifier": identifier,
            "feedback_action": action,
            "apply_now": apply_now,
            "selected_input_keys": selected_keys,
            "suggested_multiplier": suggested_multiplier,
            "top_inputs": top_inputs,
            "applied": applied,
        }
    finally:
        conn.close()


def apply_weekly_trade_feedback(max_reviews: int = 300) -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"ok": False, "error": "database missing"}
    conn = _connect()
    try:
        _ensure_trade_feedback_tables(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, v.input_key, v.suggested_multiplier
            FROM trade_feedback_reviews r
            JOIN trade_feedback_input_votes v ON v.review_id = r.id
            WHERE COALESCE(r.apply_now,0)=0
              AND COALESCE(r.applied,0)=0
            ORDER BY r.id ASC
            LIMIT ?
            """,
            (int(max_reviews),),
        )
        rows = cur.fetchall()
        if not rows:
            return {"ok": True, "applied_reviews": 0, "updated_inputs": 0, "rows": []}

        by_key: Dict[str, List[float]] = {}
        review_ids = set()
        for rid, input_key, mult in rows:
            review_ids.add(int(rid or 0))
            k = str(input_key or "").strip()
            if not k:
                continue
            by_key.setdefault(k, []).append(float(mult or 1.0))

        input_rows: List[Dict[str, Any]] = []
        for k, vals in by_key.items():
            if not vals:
                continue
            avg_mult = sum(vals) / len(vals)
            input_rows.append({"key": k, "value": 0.0, "weight": 1.0, "mult": avg_mult})

        _ensure_input_source_controls(conn)
        updates = []
        for r in input_rows:
            k = str(r.get("key") or "")
            mult = float(r.get("mult") or 1.0)
            cur.execute("SELECT COALESCE(auto_weight,1.0) FROM input_source_controls WHERE source_key=? LIMIT 1", (k,))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    INSERT INTO input_source_controls
                    (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                    VALUES (datetime('now'), datetime('now'), ?, ?, 'feedback', 1, 1.0, 1.0, 'weekly human feedback lane')
                    """,
                    (k, _input_friendly_name(k)),
                )
                auto_w = 1.0
            else:
                auto_w = float(row[0] or 1.0)
            new_auto = max(0.1, min(5.0, auto_w * mult))
            cur.execute(
                "UPDATE input_source_controls SET updated_at=datetime('now'), auto_weight=? WHERE source_key=?",
                (float(new_auto), k),
            )
            updates.append({"key": k, "from": auto_w, "to": new_auto, "column": "auto_weight"})

        if review_ids:
            q_marks = ",".join(["?"] * len(review_ids))
            cur.execute(
                f"UPDATE trade_feedback_reviews SET applied=1, applied_at=datetime('now') WHERE id IN ({q_marks})",
                tuple(sorted(review_ids)),
            )
        conn.commit()
        return {
            "ok": True,
            "applied_reviews": len(review_ids),
            "updated_inputs": len(updates),
            "rows": updates,
        }
    finally:
        conn.close()


def set_execution_controls(updates: Dict[str, Any]) -> Dict[str, Any]:
    threshold_keys = {
        "min_candidate_score",
        "alpaca_min_route_score",
        "hyperliquid_min_route_score",
        "consensus_min_confirmations",
        "consensus_min_ratio",
        "consensus_min_score",
        "polymarket_min_edge_pct",
        "polymarket_min_confidence_pct",
        "training_min_candidate_score",
        "training_consensus_min_confirmations",
        "training_consensus_min_ratio",
        "training_consensus_min_score",
        "training_alpaca_min_route_score",
        "training_hyperliquid_min_route_score",
        "training_polymarket_min_confidence_pct",
        "promote_min_paper_trades",
        "promote_min_win_rate",
        "promote_min_sharpe",
        "promote_max_drawdown",
    }
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
        "polymarket_exec_backend",
        "polymarket_strict_funding_check",
        "polymarket_edge_unit_mode",
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
        "position_stop_loss_pct",
        "position_trail_start_pct",
        "position_trailing_stop_gap_pct",
        "position_take_profit_partial_pct",
        "position_take_profit_major_pct",
        "position_take_profit_partial_usd",
        "position_take_profit_major_usd",
        "position_manage_intent_cooldown_hours",
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
        "kaggle_min_hours_between_runs",
        "kaggle_daily_download_limit",
        "kaggle_max_files_per_run",
        "kaggle_max_rows_per_file",
        "threshold_override_unlocked",
        # Premium Confirmation Gate
        "premium_gate_stocks_min",
        "premium_gate_crypto_min",
        "premium_gate_kw_stocks",
        "premium_gate_kw_crypto",
        "premium_gate_liq_stocks",
        "premium_gate_liq_crypto",
        "premium_gate_mom_stocks",
        "premium_gate_mom_crypto",
        # X consensus
        "x_consensus_min_hits",
        # Venue promotion controls
        "auto_promote_enabled",
        "promote_min_paper_trades",
        "promote_min_win_rate",
        "promote_min_sharpe",
        "promote_max_drawdown",
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
        cur.execute("SELECT key, value FROM execution_controls")
        existing_controls = {str(k): str(v) for k, v in cur.fetchall()}
        lock_open = str(existing_controls.get("threshold_override_unlocked", "0")).strip() == "1"
        requested_unlock = str((updates or {}).get("threshold_override_unlocked", "")).strip() == "1"
        can_change_thresholds = lock_open or requested_unlock
        changed = 0
        blocked_locked: List[str] = []
        for key, value in (updates or {}).items():
            if key not in allowed:
                continue
            if key in threshold_keys and not can_change_thresholds:
                blocked_locked.append(str(key))
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
        out = {"updated": changed, "controls": get_risk_controls()}
        if blocked_locked:
            out["blocked_locked"] = sorted(blocked_locked)
            out["lock_key"] = "threshold_override_unlocked"
        return out
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


CORE_SIGNAL_DEFS: List[Dict[str, str]] = [
    {
        "key": "liquidity",
        "label": "Liquidity",
        "description": "Entry/exit structure quality for timing and risk placement.",
    },
    {
        "key": "pattern",
        "label": "Pattern",
        "description": "Chart pattern quality (breakout, reversal, fakeout structure).",
    },
    {
        "key": "social",
        "label": "Social",
        "description": "Social sentiment signal pressure across monitored social feeds.",
    },
    {
        "key": "external",
        "label": "External",
        "description": "News/event-driven context including free feeds and breakthrough events.",
    },
    {
        "key": "copy",
        "label": "Copy",
        "description": "Copy/call style idea flow from tracked discretionary sources.",
    },
    {
        "key": "strategy",
        "label": "Strategy Engine",
        "description": "Core strategy model score used for the final route decision.",
    },
    {
        "key": "x_sources",
        "label": "X Sources",
        "description": "Tracked X handles as one signal family with drilldown details.",
    },
    {
        "key": "kelly",
        "label": "Kelly Sizing",
        "description": "Position sizing guide per candidate. Kelly% = (p×b−(1−p))/b. Quarter Kelly applied. Shows portfolio budget used.",
    },
    {
        "key": "kyle_williams",
        "label": "Kyle Williams Setup",
        "description": "First-red-day short and extension setups. Fires when a momentum leader extends above VWAP for 2+ green days then shows first reversal candle. Signals scored by ext_vs_vwap and prior green day count.",
    },
    {
        "key": "momentum",
        "label": "Momentum Rank",
        "description": "Is this ticker in the top 100 momentum leaders (Qullamaggie-style)? Stocks: Finviz screener — small-cap+, above 50-day SMA, up 10%+ last quarter, sorted by 52-week performance. Crypto: CoinGecko top 10 by 30-day price change. Rank 1 = strongest leader.",
    },
    {
        "key": "event_alpha",
        "label": "Event Alpha (Macro/Geo)",
        "description": "Macro and geopolitical regime signals — tariff shock, geopolitical escalation, rate surprises. Fires on BTC and SPY. Unique: no other family covers macro regime risk. Scores average 73+.",
    },
]

CORE_FAMILY_KEYS: Dict[str, str] = {
    "liquidity": "family:liquidity",
    "pattern": "family:pattern",
    "social": "family:social",
    "external": "family:external",
    "copy": "family:copy",
    "strategy": "family:pipeline",
    "kelly": "family:kelly",
    "kyle_williams": "family:kyle_williams",
    "momentum": "family:momentum",
    "event_alpha": "family:event_alpha",
}


def _map_input_key_to_core(key: Any, tracked_handles: Optional[set[str]] = None) -> str:
    k = str(key or "").strip().lower()
    if not k:
        return ""
    if any(x in k for x in ("venue", "hyperliquid", "alpaca", "execution")):
        return ""
    if k.startswith("x:"):
        return "x_sources"
    if k.startswith("strategy:") or k.startswith("pipeline:") or k.startswith("family:pipeline"):
        return "strategy"
    if k.startswith("family:liquidity") or ":family:liquidity" in k:
        return "liquidity"
    if k.startswith("family:pattern") or ":family:pattern" in k:
        return "pattern"
    if k.startswith("family:social") or ":family:social" in k or k.startswith("social:"):
        return "social"
    if k.startswith("family:external") or ":family:external" in k:
        return "external"
    if k.startswith("family:copy") or ":family:copy" in k:
        return "copy"
    if k.startswith("kelly:") or k.startswith("family:kelly"):
        return "kelly"
    if k.startswith("family:kyle_williams") or k.startswith("kyle_williams:"):
        return "kyle_williams"
    if k.startswith("family:momentum") or k.startswith("momentum:"):
        return "momentum"
    if k.startswith("family:event_alpha") or k.startswith("event_alpha:"):
        return "event_alpha"
    if k.startswith("source:"):
        tail = k.split("source:", 1)[1].strip()
        if tracked_handles and tail in tracked_handles:
            return "x_sources"
        if tail in {"internal", "unspecified"} or tail.startswith("manual-"):
            return "strategy"
        if any(x in tail for x in ("freefeed", "finviz", "event", "breakthrough", "policy", "news")):
            return "external"
        return "copy"
    return ""


def _map_source_tag_to_core(source_tag: Any, tracked_handles: set[str]) -> str:
    tag = str(source_tag or "").strip().lower()
    if not tag:
        return ""
    if tag in tracked_handles:
        return "x_sources"
    if tag.startswith("x:"):
        tail = tag.split("x:", 1)[1].strip().lstrip("@")
        if tail and tail in tracked_handles:
            return "x_sources"
    if tag.startswith(("freefeed:", "finviz:", "news:")):
        return "external"
    if any(x in tag for x in ("event", "breakthrough", "policy")):
        return "external"
    if "copy" in tag:
        return "copy"
    if "social" in tag:
        return "social"
    if "pattern" in tag:
        return "pattern"
    if "liquidity" in tag:
        return "liquidity"
    return "strategy"


def _source_tag_to_input_key(source_tag: Any, tracked_handles: set[str]) -> str:
    tag = str(source_tag or "").strip().lower()
    if not tag:
        return ""
    if tag in tracked_handles:
        return f"x:{tag}"
    if tag.startswith("x:"):
        tail = tag.split("x:", 1)[1].strip().lstrip("@")
        if tail:
            return f"x:{tail}"
    return f"source:{tag}"


def _candidate_token_to_input_key(token: Any, tracked_handles: set[str]) -> str:
    raw = str(token or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("@"):
        raw = raw.lstrip("@")
    if raw in tracked_handles:
        return f"x:{raw}"
    if raw.startswith(("family:", "source:", "strategy:", "pipeline:", "x:")):
        return raw
    if re.match(r"^[a-z0-9._:-]{2,96}$", raw):
        return f"source:{raw}"
    return ""


def get_core_signal_overview(lookback_hours: int = 72, limit: int = 1200) -> Dict[str, Any]:
    lookback = max(1, min(336, int(lookback_hours or 72)))
    scan_limit = max(100, min(5000, int(limit or 1200)))
    signal_rows: Dict[str, Dict[str, Any]] = {}
    for row in CORE_SIGNAL_DEFS:
        signal_rows[row["key"]] = {
            "key": row["key"],
            "label": row["label"],
            "description": row["description"],
            "enabled": 0,
            "manual_weight": 1.0,
            "auto_weight": 1.0,
            "effective_weight": 1.0,
            "sub_inputs_total": 0,
            "sub_inputs_enabled": 0,
            "recent_hits": 0,
            "last_seen_utc": "",
            "sub_inputs": [],
        }

    base_out = {
        "ok": True,
        "lookback_hours": lookback,
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "signals": [signal_rows[x["key"]] for x in CORE_SIGNAL_DEFS],
        "x_sources": [],
    }
    if not DB_PATH.exists():
        return base_out

    conn = _connect()
    try:
        cur = conn.cursor()
        tracked_handles: set[str] = set()
        x_sources: List[Dict[str, Any]] = []
        x_meta_by_key: Dict[str, Dict[str, Any]] = {}
        controls: Dict[str, Dict[str, Any]] = {}
        source_learning: Dict[str, Dict[str, Any]] = {}
        strategy_learning: Dict[str, Dict[str, Any]] = {}

        if _table_exists(conn, "input_source_controls"):
            cur.execute(
                """
                SELECT LOWER(COALESCE(source_key,'')),
                       COALESCE(source_label,''),
                       COALESCE(source_class,''),
                       COALESCE(enabled,1),
                       COALESCE(manual_weight,1.0),
                       COALESCE(auto_weight,1.0),
                       ROUND(COALESCE(manual_weight,1.0) * COALESCE(auto_weight,1.0), 6),
                       COALESCE(notes,'')
                FROM input_source_controls
                """
            )
            for source_key, source_label, source_class, enabled, manual_w, auto_w, effective_w, notes in cur.fetchall():
                sk = str(source_key or "").strip().lower()
                if not sk:
                    continue
                controls[sk] = {
                    "source_key": sk,
                    "source_label": str(source_label or ""),
                    "source_class": str(source_class or ""),
                    "enabled": int(enabled or 0),
                    "manual_weight": float(manual_w or 1.0),
                    "auto_weight": float(auto_w or 1.0),
                    "effective_weight": float(effective_w or 1.0),
                    "notes": str(notes or ""),
                }

        if _table_exists(conn, "tracked_x_sources"):
            has_x_api = _column_exists(conn, "tracked_x_sources", "x_api_enabled")
            has_weight = _column_exists(conn, "tracked_x_sources", "source_weight")
            x_api_expr = "COALESCE(x_api_enabled,1)" if has_x_api else "1"
            source_weight_expr = "COALESCE(source_weight,1.0)" if has_weight else "1.0"
            cur.execute(
                """
                SELECT COALESCE(handle,''), COALESCE(active,1), """
                + x_api_expr
                + """, COALESCE(role_copy,1), COALESCE(role_alpha,1), """
                + source_weight_expr
                + """
                FROM tracked_x_sources
                ORDER BY updated_at DESC
                """
            )
            for handle, active, x_api, role_copy, role_alpha, source_weight in cur.fetchall():
                h = _normalize_x_handle(handle)
                if not h:
                    continue
                tracked_handles.add(h)
                x_key = f"x:{h}"
                ctl = controls.get(x_key, {})
                manual_w = float(ctl.get("manual_weight", float(source_weight or 1.0)))
                auto_w = float(ctl.get("auto_weight", 1.0))
                effective_w = float(ctl.get("effective_weight", manual_w * auto_w))
                enabled = int(active or 0) == 1 and int(x_api or 0) == 1 and int(ctl.get("enabled", 1)) == 1
                x_sources.append(
                    {
                        "source_key": x_key,
                        "source_label": str(ctl.get("source_label") or f"X @{h}"),
                        "source_class": str(ctl.get("source_class") or "x_account"),
                        "notes": str(ctl.get("notes") or ""),
                        "handle": h,
                        "active": 1 if enabled else 0,
                        "role_copy": int(role_copy or 0),
                        "role_alpha": int(role_alpha or 0),
                        "source_weight": round(float(source_weight or 1.0), 4),
                        "manual_weight": round(manual_w, 4),
                        "auto_weight": round(auto_w, 4),
                        "effective_weight": round(effective_w, 4),
                        "recent_hits": 0,
                        "last_seen_utc": "",
                        "sample_size": 0,
                        "win_rate": 0.0,
                        "avg_pnl_percent": 0.0,
                    }
                )
                x_meta_by_key[x_key] = {"role_copy": int(role_copy or 0), "role_alpha": int(role_alpha or 0)}
                if x_key not in controls:
                    controls[x_key] = {
                        "source_key": x_key,
                        "source_label": f"X @{h}",
                        "source_class": "x_account",
                        "enabled": 1 if enabled else 0,
                        "manual_weight": float(manual_w),
                        "auto_weight": float(auto_w),
                        "effective_weight": float(effective_w),
                        "notes": "",
                    }

        if _table_exists(conn, "source_learning_stats"):
            cur.execute(
                """
                SELECT LOWER(COALESCE(source_tag,'')),
                       COALESCE(sample_size,0),
                       COALESCE(win_rate,0.0),
                       COALESCE(avg_pnl_percent,0.0)
                FROM source_learning_stats
                """
            )
            for source_tag, sample_size, win_rate, avg_pnl_percent in cur.fetchall():
                st = str(source_tag or "").strip().lower()
                if not st:
                    continue
                source_learning[st] = {
                    "sample_size": int(sample_size or 0),
                    "win_rate": float(win_rate or 0.0),
                    "avg_pnl_percent": float(avg_pnl_percent or 0.0),
                }

        if _table_exists(conn, "strategy_learning_stats"):
            cur.execute(
                """
                SELECT UPPER(COALESCE(strategy_tag,'')),
                       COALESCE(sample_size,0),
                       COALESCE(win_rate,0.0),
                       COALESCE(avg_pnl_percent,0.0)
                FROM strategy_learning_stats
                """
            )
            for strategy_tag, sample_size, win_rate, avg_pnl_percent in cur.fetchall():
                st = str(strategy_tag or "").strip().upper()
                if not st:
                    continue
                strategy_learning[st] = {
                    "sample_size": int(sample_size or 0),
                    "win_rate": float(win_rate or 0.0),
                    "avg_pnl_percent": float(avg_pnl_percent or 0.0),
                }

        route_hits: Dict[str, int] = {}
        route_last_seen: Dict[str, str] = {}
        input_hits: Dict[str, int] = {}
        input_last_seen: Dict[str, str] = {}
        if _table_exists(conn, "signal_routes"):
            cur.execute(
                """
                SELECT LOWER(COALESCE(source_tag,'')), COALESCE(routed_at,'')
                FROM signal_routes
                WHERE datetime(COALESCE(routed_at, '1970-01-01')) >= datetime('now', ?)
                ORDER BY datetime(COALESCE(routed_at, '1970-01-01')) DESC
                LIMIT ?
                """,
                (f"-{lookback} hour", scan_limit),
            )
            for source_tag, routed_at in cur.fetchall():
                core = _map_source_tag_to_core(source_tag, tracked_handles)
                if not core:
                    continue
                route_hits[core] = int(route_hits.get(core, 0) or 0) + 1
                ts = str(routed_at or "")
                if ts and (not route_last_seen.get(core) or ts > route_last_seen.get(core, "")):
                    route_last_seen[core] = ts
                input_key = _source_tag_to_input_key(source_tag, tracked_handles)
                if input_key:
                    input_hits[input_key] = int(input_hits.get(input_key, 0) or 0) + 1
                    if ts and (not input_last_seen.get(input_key) or ts > input_last_seen.get(input_key, "")):
                        input_last_seen[input_key] = ts

        candidate_hits: Dict[str, int] = {}
        candidate_last_seen: Dict[str, str] = {}
        if _table_exists(conn, "trade_candidates"):
            cur.execute(
                """
                SELECT COALESCE(generated_at,''), COALESCE(input_breakdown_json,'[]'), COALESCE(evidence_json,'[]')
                FROM trade_candidates
                WHERE datetime(COALESCE(generated_at, '1970-01-01')) >= datetime('now', ?)
                ORDER BY datetime(COALESCE(generated_at, '1970-01-01')) DESC
                LIMIT ?
                """,
                (f"-{lookback} hour", scan_limit),
            )
            for generated_at, input_breakdown_raw, evidence_raw in cur.fetchall():
                ts = str(generated_at or "")
                keys: List[str] = []
                for item in _parse_input_breakdown_json(str(input_breakdown_raw or "[]")):
                    kk = str(item.get("key") or "").strip()
                    if kk:
                        keys.append(kk)
                try:
                    evidence = json.loads(str(evidence_raw or "[]"))
                    if isinstance(evidence, list):
                        for ev in evidence:
                            evs = str(ev or "").strip()
                            if evs:
                                keys.append(evs)
                except Exception:
                    pass
                for k in keys:
                    input_key = _candidate_token_to_input_key(k, tracked_handles)
                    if not input_key:
                        continue
                    core = _map_input_key_to_core(input_key, tracked_handles=tracked_handles)
                    if not core:
                        continue
                    candidate_hits[core] = int(candidate_hits.get(core, 0) or 0) + 1
                    if ts and (not candidate_last_seen.get(core) or ts > candidate_last_seen.get(core, "")):
                        candidate_last_seen[core] = ts
                    input_hits[input_key] = int(input_hits.get(input_key, 0) or 0) + 1
                    if ts and (not input_last_seen.get(input_key) or ts > input_last_seen.get(input_key, "")):
                        input_last_seen[input_key] = ts

        for key, row in signal_rows.items():
            family_key = CORE_FAMILY_KEYS.get(key, "")
            row["family_source_key"] = family_key  # expose to dashboard for save
            if family_key:
                family = controls.get(family_key, {})
                if family:
                    row["enabled"] = int(family.get("enabled", 1))
                    row["manual_weight"] = round(float(family.get("manual_weight", 1.0)), 4)
                    row["auto_weight"] = round(float(family.get("auto_weight", 1.0)), 4)
                    row["effective_weight"] = round(float(family.get("effective_weight", 1.0)), 4)
                else:
                    row["enabled"] = 1

            row["recent_hits"] = int(route_hits.get(key, 0) or 0) + int(candidate_hits.get(key, 0) or 0)
            row["last_seen_utc"] = route_last_seen.get(key, "") or candidate_last_seen.get(key, "")

        sub_inputs_by_core: Dict[str, List[Dict[str, Any]]] = {k: [] for k in signal_rows.keys()}
        for sk, ctl in controls.items():
            core = _map_input_key_to_core(sk, tracked_handles=tracked_handles)
            if not core:
                continue
            sample_size = 0
            win_rate = 0.0
            avg_pnl_pct = 0.0
            role_copy = 0
            role_alpha = 0
            strategy_tag = ""
            if sk.startswith("source:"):
                tag = sk.split("source:", 1)[1].strip()
                stats = source_learning.get(tag, {})
                sample_size = int(stats.get("sample_size", 0))
                win_rate = float(stats.get("win_rate", 0.0))
                avg_pnl_pct = float(stats.get("avg_pnl_percent", 0.0))
            elif sk.startswith("x:"):
                tag = sk.split("x:", 1)[1].strip()
                stats = source_learning.get(tag, {})
                sample_size = int(stats.get("sample_size", 0))
                win_rate = float(stats.get("win_rate", 0.0))
                avg_pnl_pct = float(stats.get("avg_pnl_percent", 0.0))
                roles = x_meta_by_key.get(sk, {})
                role_copy = int(roles.get("role_copy", 0))
                role_alpha = int(roles.get("role_alpha", 0))
            elif sk.startswith("strategy:"):
                m = re.match(r"^strategy:([^:]+)", sk)
                strategy_tag = str((m.group(1) if m else "") or "").upper()
                stats = strategy_learning.get(strategy_tag, {})
                sample_size = int(stats.get("sample_size", 0))
                win_rate = float(stats.get("win_rate", 0.0))
                avg_pnl_pct = float(stats.get("avg_pnl_percent", 0.0))
            elif sk.startswith("pipeline:"):
                strategy_tag = sk.split("pipeline:", 1)[1].strip().upper()
                stats = strategy_learning.get(strategy_tag, {})
                sample_size = int(stats.get("sample_size", 0))
                win_rate = float(stats.get("win_rate", 0.0))
                avg_pnl_pct = float(stats.get("avg_pnl_percent", 0.0))

            sub_inputs_by_core[core].append(
                {
                    "source_key": sk,
                    "source_label": str(ctl.get("source_label") or _input_friendly_name(sk)),
                    "source_class": str(ctl.get("source_class") or ""),
                    "help": _input_friendly_help(sk),
                    "enabled": int(ctl.get("enabled", 1)),
                    "manual_weight": round(float(ctl.get("manual_weight", 1.0)), 4),
                    "auto_weight": round(float(ctl.get("auto_weight", 1.0)), 4),
                    "effective_weight": round(float(ctl.get("effective_weight", 1.0)), 4),
                    "recent_hits": int(input_hits.get(sk, 0) or 0),
                    "last_seen_utc": input_last_seen.get(sk, ""),
                    "sample_size": sample_size,
                    "win_rate": round(win_rate, 2),
                    "avg_pnl_percent": round(avg_pnl_pct, 4),
                    "score_pct": round(win_rate, 2) if sample_size > 0 else 0.0,
                    "strategy_tag": strategy_tag,
                    "role_copy": role_copy,
                    "role_alpha": role_alpha,
                    "notes": str(ctl.get("notes") or ""),
                }
            )

        for key, row in signal_rows.items():
            subs = sorted(
                sub_inputs_by_core.get(key, []),
                key=lambda x: (int(x.get("recent_hits", 0) or 0), float(x.get("effective_weight", 1.0) or 1.0)),
                reverse=True,
            )
            row["sub_inputs"] = subs[:200]
            row["sub_inputs_total"] = len(subs)
            row["sub_inputs_enabled"] = len([x for x in subs if int(x.get("enabled", 0)) == 1])

        x_by_handle = {str(x.get("handle") or ""): x for x in x_sources}
        for handle, payload in x_by_handle.items():
            key = f"x:{handle}"
            payload["recent_hits"] = int(input_hits.get(key, 0) or 0)
            payload["last_seen_utc"] = input_last_seen.get(key, "")
            stats = source_learning.get(handle, {})
            payload["sample_size"] = int(stats.get("sample_size", 0))
            payload["win_rate"] = round(float(stats.get("win_rate", 0.0)), 2)
            payload["avg_pnl_percent"] = round(float(stats.get("avg_pnl_percent", 0.0)), 4)

        x_sorted = sorted(
            x_by_handle.values(),
            key=lambda x: (int(x.get("recent_hits", 0)), float(x.get("effective_weight", 1.0))),
            reverse=True,
        )

        x_active = [x for x in x_sorted if int(x.get("active", 0)) == 1]
        x_row = signal_rows["x_sources"]
        x_row["enabled"] = 1 if x_active else 0
        x_row["sub_inputs_total"] = len(x_sorted)
        x_row["sub_inputs_enabled"] = len(x_active)
        if x_active:
            x_row["manual_weight"] = round(sum(float(x.get("manual_weight", 1.0)) for x in x_active) / len(x_active), 4)
            x_row["auto_weight"] = round(sum(float(x.get("auto_weight", 1.0)) for x in x_active) / len(x_active), 4)
            x_row["effective_weight"] = round(sum(float(x.get("effective_weight", 1.0)) for x in x_active) / len(x_active), 4)
        else:
            x_row["manual_weight"] = 1.0
            x_row["auto_weight"] = 1.0
            x_row["effective_weight"] = 1.0
        x_row["recent_hits"] = int(route_hits.get("x_sources", 0) or 0) + int(candidate_hits.get("x_sources", 0) or 0)
        x_row["last_seen_utc"] = route_last_seen.get("x_sources", "") or candidate_last_seen.get("x_sources", "")

        # ── Kelly signal family ──────────────────────────────────────────────
        kelly_row = signal_rows["kelly"]
        if _table_exists(conn, "kelly_signals"):
            cur.execute(
                """
                SELECT ticker, direction, source_tag, win_prob, avg_win_pct, avg_loss_pct,
                       payout_ratio, kelly_fraction, frac_kelly, ev_percent,
                       sample_size, verdict, verdict_reason, computed_at
                FROM kelly_signals
                WHERE computed_at = (SELECT MAX(computed_at) FROM kelly_signals)
                ORDER BY
                  CASE verdict WHEN 'pass' THEN 0 WHEN 'warmup' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END,
                  frac_kelly DESC
                """
            )
            kelly_rows = cur.fetchall()
            kelly_sub: List[Dict[str, Any]] = []
            passes = 0
            for (kticker, kdir, ksrc, wp, aw, al, b, kf, fk, ev,
                 ksamp, kverdict, kreason, kts) in kelly_rows:
                is_pass = kverdict in ("pass", "warmup")
                if is_pass:
                    passes += 1
                label = f"{kticker} {str(kdir or '').upper()} [{kverdict}]"
                src_key = f"kelly:{str(kticker or '').lower()}:{str(kdir or '').lower()}"
                kelly_sub.append({
                    "source_key": src_key,
                    "source_label": label,
                    "source_class": "kelly",
                    "enabled": 1 if is_pass else 0,
                    # repurpose weight fields for Kelly metrics
                    "manual_weight": round(float(kf or 0.0), 4),     # full Kelly%
                    "auto_weight": round(float(b or 0.0), 4),         # payout ratio b
                    "effective_weight": round(float(fk or 0.0), 4),   # ¼Kelly%
                    "notes": (
                        f"p={round(float(wp or 0)*100,1)}% "
                        f"b={round(float(b or 0),2)} "
                        f"EV={round(float(ev or 0),2)}% "
                        f"src={ksrc} {kreason}"
                    ),
                    "recent_hits": int(ksamp or 0),
                    "last_seen_utc": str(kts or ""),
                    "score_pct": round(float(ev or 0.0), 2),   # EV% as score
                    "win_rate": round(float(wp or 0.0) * 100, 1),  # win prob %
                })

            kelly_row["sub_inputs"] = kelly_sub
            kelly_row["sub_inputs_total"] = len(kelly_sub)
            kelly_row["sub_inputs_enabled"] = passes
            # enabled comes from input_source_controls (family:kelly) — don't override it
            if kelly_sub:
                kelly_row["recent_hits"] = len(kelly_sub)
                kelly_row["last_seen_utc"] = kelly_sub[0].get("last_seen_utc", "")
                # effective_weight stays as manual_weight * auto_weight from family controls — don't override

        return {
            "ok": True,
            "lookback_hours": lookback,
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "signals": [signal_rows[x["key"]] for x in CORE_SIGNAL_DEFS],
            "x_sources": x_sorted[:200],
        }
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


def get_position_management_intents(limit: int = 120) -> List[Dict[str, Any]]:
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
            WHERE COALESCE(status,'') LIKE 'manage_%'
            ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        for row in rows:
            action = str(row.get("status") or "").replace("manage_", "").replace("_", " ").strip()
            row["action"] = action or "manage"
            row["confidence"] = 0.0
            row["pnl_pct"] = 0.0
            row["upnl_usd"] = 0.0
            row["reason"] = ""
            row["suggested_stop_price"] = 0.0
            row["leverage"] = 1.0
            try:
                d = json.loads(str(row.get("details") or "{}"))
                if isinstance(d, dict):
                    row["confidence"] = round(float(d.get("confidence", 0.0) or 0.0), 4)
                    row["pnl_pct"] = round(float(d.get("pnl_pct", 0.0) or 0.0), 4)
                    row["upnl_usd"] = round(float(d.get("upnl_usd", 0.0) or 0.0), 4)
                    row["reason"] = str(d.get("reason") or "")
                    row["suggested_stop_price"] = round(float(d.get("suggested_stop_price", 0.0) or 0.0), 6)
                    row["leverage"] = round(float(d.get("leverage", 1.0) or 1.0), 4)
            except Exception:
                pass
        return rows
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
        has_kol = _column_exists(conn, "tracked_x_sources", "kol_category")
        x_api_expr = "x_api_enabled" if has_x_api else "1 AS x_api_enabled"
        weight_expr = "source_weight" if has_weight else "1.0 AS source_weight"
        kol_expr = "kol_category" if has_kol else "'stocks' AS kol_category"
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, updated_at, handle, role_copy, role_alpha, active, """ + x_api_expr + """, """ + weight_expr + """, notes, """ + kol_expr + """
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
    handle = _extract_x_handle(payload or {})
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
    kol_category = str((payload or {}).get("kol_category") or "stocks").strip()
    if kol_category not in ("stocks", "crypto", "polymarket", "mixed"):
        kol_category = "stocks"

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
              notes TEXT NOT NULL DEFAULT '',
              kol_category TEXT NOT NULL DEFAULT 'stocks'
            )
            """
        )
        if not _column_exists(conn, "tracked_x_sources", "x_api_enabled"):
            conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN x_api_enabled INTEGER NOT NULL DEFAULT 1")
        if not _column_exists(conn, "tracked_x_sources", "source_weight"):
            conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN source_weight REAL NOT NULL DEFAULT 1.0")
        if not _column_exists(conn, "tracked_x_sources", "kol_category"):
            conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN kol_category TEXT NOT NULL DEFAULT 'stocks'")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT handle
            FROM tracked_x_sources
            WHERE lower(COALESCE(handle,'')) = ?
            LIMIT 1
            """,
            (handle,),
        )
        existing = cur.fetchone()
        if existing and str(existing[0] or "").strip() and str(existing[0]).strip() != handle:
            conn.execute(
                """
                UPDATE tracked_x_sources
                SET
                  updated_at=datetime('now'),
                  handle=?,
                  role_copy=?,
                  role_alpha=?,
                  active=?,
                  x_api_enabled=?,
                  source_weight=?,
                  notes=?,
                  kol_category=?
                WHERE handle=?
                """,
                (handle, role_copy, role_alpha, active, x_api_enabled, float(source_weight), notes, kol_category, str(existing[0])),
            )
            conn.commit()
            return {"ok": True, "handle": handle, "sources": get_tracked_sources()}
        conn.execute(
            """
            INSERT INTO tracked_x_sources (created_at, updated_at, handle, role_copy, role_alpha, active, x_api_enabled, source_weight, notes, kol_category)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
              updated_at=datetime('now'),
              role_copy=excluded.role_copy,
              role_alpha=excluded.role_alpha,
              active=excluded.active,
              x_api_enabled=excluded.x_api_enabled,
              source_weight=excluded.source_weight,
              notes=excluded.notes,
              kol_category=excluded.kol_category
            """,
            (handle, role_copy, role_alpha, active, x_api_enabled, float(source_weight), notes, kol_category),
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
        ("family:kyle_williams", "Kyle Williams Setup", "family"),
        ("family:momentum", "Momentum Rank", "family"),
        ("family:event_alpha", "Event Alpha (Macro/Geo)", "family"),
    ]
    cur = conn.cursor()
    if _table_exists(conn, "tracked_x_sources"):
        cur.execute("SELECT handle FROM tracked_x_sources")
        for (h,) in cur.fetchall():
            hh = _normalize_x_handle(h)
            if hh:
                keys.append((f"x:{hh}", f"X @{hh}", "x_account"))
    if _table_exists(conn, "source_learning_stats"):
        cur.execute("SELECT DISTINCT source_tag FROM source_learning_stats")
        for (s,) in cur.fetchall():
            tag = str(s or "").strip()
            if tag:
                keys.append((f"source:{tag.lower()}", f"Source {tag}", "source_tag"))
    # Strategies promoted to own families, removed as redundant, or generic placeholders
    _excluded_pipeline_tags = {"CHART_LIQUIDITY", "KYLE_WILLIAMS", "B_LONGTERM", "E_BREAKTHROUGH", "C_EVENT", "UNSPECIFIED", ""}
    if _table_exists(conn, "strategy_learning_stats"):
        cur.execute("SELECT DISTINCT strategy_tag FROM strategy_learning_stats")
        for (s,) in cur.fetchall():
            tag = str(s or "").strip()
            if tag and tag.upper() not in _excluded_pipeline_tags:
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


def _ensure_ticker_trade_profiles(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ticker_trade_profiles (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          ticker TEXT NOT NULL UNIQUE,
          active INTEGER NOT NULL DEFAULT 1,
          preferred_venue TEXT NOT NULL DEFAULT '',
          allowed_venues_json TEXT NOT NULL DEFAULT '["stocks","crypto","prediction"]',
          required_inputs_json TEXT NOT NULL DEFAULT '[]',
          min_score REAL NOT NULL DEFAULT 0.0,
          notional_override REAL NOT NULL DEFAULT 0.0,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_trade_profiles_active ON ticker_trade_profiles(active)")
    conn.commit()


def get_ticker_trade_profiles(limit: int = 200) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        _ensure_ticker_trade_profiles(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, updated_at, ticker, active, preferred_venue,
                   allowed_venues_json, required_inputs_json, min_score, notional_override, notes
            FROM ticker_trade_profiles
            ORDER BY updated_at DESC, ticker ASC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())
        for row in rows:
            row["allowed_venues"] = _parse_json_list(row.get("allowed_venues_json"), lower=True)
            row["required_inputs"] = _parse_json_list(row.get("required_inputs_json"), lower=True)
        return rows
    finally:
        conn.close()


def upsert_ticker_trade_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    ticker = _normalize_ticker((payload or {}).get("ticker"))
    if not ticker:
        return {"ok": False, "error": "ticker required"}

    active = 1 if bool((payload or {}).get("active", True)) else 0
    preferred_venue = str((payload or {}).get("preferred_venue") or "").strip().lower()
    if preferred_venue not in {"", "stocks", "crypto", "prediction"}:
        return {"ok": False, "error": "preferred_venue must be stocks, crypto, prediction, or empty"}

    allowed_venues = [
        x
        for x in _parse_json_list((payload or {}).get("allowed_venues", (payload or {}).get("allowed_venues_json", [])), lower=True)
        if x in {"stocks", "crypto", "prediction"}
    ]
    if not allowed_venues:
        allowed_venues = ["stocks", "crypto", "prediction"]
    if preferred_venue and preferred_venue not in allowed_venues:
        allowed_venues.append(preferred_venue)

    required_inputs = _parse_json_list(
        (payload or {}).get("required_inputs", (payload or {}).get("required_inputs_json", [])),
        lower=True,
        max_items=30,
    )
    required_inputs = [x for x in required_inputs if x]

    min_score = float((payload or {}).get("min_score", 0.0) or 0.0)
    min_score = max(0.0, min(100.0, min_score))
    notional_override = float((payload or {}).get("notional_override", 0.0) or 0.0)
    notional_override = max(0.0, min(1000000.0, notional_override))
    notes = str((payload or {}).get("notes") or "").strip()

    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        _ensure_ticker_trade_profiles(conn)
        conn.execute(
            """
            INSERT INTO ticker_trade_profiles
            (created_at, updated_at, ticker, active, preferred_venue, allowed_venues_json, required_inputs_json, min_score, notional_override, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
              updated_at=datetime('now'),
              active=excluded.active,
              preferred_venue=excluded.preferred_venue,
              allowed_venues_json=excluded.allowed_venues_json,
              required_inputs_json=excluded.required_inputs_json,
              min_score=excluded.min_score,
              notional_override=excluded.notional_override,
              notes=excluded.notes
            """,
            (
                ticker,
                int(active),
                preferred_venue,
                json.dumps(sorted(set(allowed_venues)), separators=(",", ":"), ensure_ascii=True),
                json.dumps(required_inputs, separators=(",", ":"), ensure_ascii=True),
                float(min_score),
                float(notional_override),
                notes,
            ),
        )
        conn.commit()
        return {"ok": True, "ticker": ticker}
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


def get_source_horizon_ratings(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Source performance broken down by time horizon: 1d, 7d, 14d, 30d.
    Used in the dashboard to show which inputs are best for scalps vs long-term.
    Includes both taken trades and counterfactual wins from non-taken routes.
    """
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "source_horizon_learning_stats"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              source_tag,
              horizon_hours,
              wins,
              losses,
              pushes,
              round(win_rate, 1) AS win_rate,
              sample_size
            FROM source_horizon_learning_stats
            WHERE horizon_hours IN (24, 168, 336, 720)
              AND sample_size > 0
            ORDER BY source_tag, horizon_hours
            """,
        )
        # Pivot to one row per source with horizon columns
        source_map: Dict[str, Dict] = {}
        horizon_labels = {24: "1d", 168: "7d", 336: "14d", 720: "30d"}
        for tag, h_hours, wins, losses, pushes, win_rate, sample in cur.fetchall():
            t = str(tag or "").strip()
            if not t:
                continue
            if t not in source_map:
                source_map[t] = {"source": t, "total_sample": 0}
            label = horizon_labels.get(int(h_hours), f"{h_hours}h")
            source_map[t][f"{label}_wins"] = int(wins or 0)
            source_map[t][f"{label}_losses"] = int(losses or 0)
            source_map[t][f"{label}_win_rate"] = float(win_rate or 0.0)
            source_map[t][f"{label}_sample"] = int(sample or 0)
            source_map[t]["total_sample"] = max(
                int(source_map[t].get("total_sample", 0)),
                int(sample or 0),
            )
        rows = sorted(source_map.values(), key=lambda x: int(x.get("total_sample", 0)), reverse=True)
        return rows[:limit]
    finally:
        conn.close()


def get_counterfactual_wins(limit: int = 200, horizon_hours: int = 24) -> Dict[str, Any]:
    """
    Non-traded signals that would have been winners.
    These are routes the pipeline flagged but the agent didn't take (threshold blocked).
    Also includes taken trades that were wins for comparison.

    Returns rows + aggregate stats per source.
    User can upvote (confirm win) or downvote (false positive) each entry.
    Upvoted wins boost that source's auto_weight in input_source_controls.
    """
    if not DB_PATH.exists():
        return {"rows": [], "stats": {}}
    conn = _connect()
    try:
        if not _table_exists(conn, "route_outcomes_horizons"):
            return {"rows": [], "stats": {}}

        cur = conn.cursor()

        # Ensure feedback table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS counterfactual_feedback (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              route_id INTEGER NOT NULL,
              horizon_hours INTEGER NOT NULL,
              feedback TEXT NOT NULL DEFAULT 'pending',
              feedback_at TEXT,
              notes TEXT NOT NULL DEFAULT '',
              UNIQUE(route_id, horizon_hours)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cf_feedback_route ON counterfactual_feedback(route_id, horizon_hours)"
        )
        conn.commit()

        cur.execute(
            """
            SELECT
              h.route_id,
              h.ticker,
              h.source_tag,
              h.venue,
              h.direction,
              h.decision,
              h.pnl_percent,
              h.horizon_hours,
              h.routed_at,
              h.evaluated_at,
              h.resolution,
              h.outcome_type,
              h.entry_price,
              h.eval_price,
              COALESCE(rf.route_score, 0.0) AS route_score,
              COALESCE(rf.strategy_tag, '') AS strategy_tag,
              COALESCE(cf.feedback, 'pending') AS user_feedback,
              COALESCE(cf.notes, '') AS feedback_notes
            FROM route_outcomes_horizons h
            LEFT JOIN route_feedback_features rf ON rf.route_id = h.route_id
            LEFT JOIN counterfactual_feedback cf ON cf.route_id = h.route_id AND cf.horizon_hours = h.horizon_hours
            WHERE h.resolution = 'win'
              AND h.horizon_hours = ?
              AND COALESCE(h.pnl_percent, 0) > 0
            ORDER BY h.pnl_percent DESC
            LIMIT ?
            """,
            (int(horizon_hours), limit),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())

        # Stats by source
        stats_by_source: Dict[str, Dict] = {}
        for r in rows:
            src = str(r.get("source_tag") or "unknown")
            taken = str(r.get("decision") or "").lower() == "approved"
            if src not in stats_by_source:
                stats_by_source[src] = {
                    "source": src,
                    "total_wins": 0,
                    "taken_wins": 0,
                    "not_taken_wins": 0,
                    "upvoted": 0,
                    "downvoted": 0,
                    "avg_pnl_pct": 0.0,
                    "_pnl_sum": 0.0,
                }
            stats_by_source[src]["total_wins"] += 1
            if taken:
                stats_by_source[src]["taken_wins"] += 1
            else:
                stats_by_source[src]["not_taken_wins"] += 1
            fb = str(r.get("user_feedback") or "pending")
            if fb == "upvote":
                stats_by_source[src]["upvoted"] += 1
            elif fb == "downvote":
                stats_by_source[src]["downvoted"] += 1
            stats_by_source[src]["_pnl_sum"] += float(r.get("pnl_percent") or 0.0)

        for s in stats_by_source.values():
            n = s["total_wins"]
            s["avg_pnl_pct"] = round(s["_pnl_sum"] / n, 2) if n > 0 else 0.0
            del s["_pnl_sum"]

        stats_list = sorted(stats_by_source.values(), key=lambda x: x["total_wins"], reverse=True)
        return {
            "rows": rows,
            "stats": stats_list,
            "horizon_hours": horizon_hours,
            "total": len(rows),
        }
    finally:
        conn.close()


def submit_counterfactual_feedback(route_id: int, horizon_hours: int, feedback: str, notes: str = "") -> Dict[str, Any]:
    """
    Record user upvote/downvote on a counterfactual win.

    feedback: 'upvote' | 'downvote' | 'pending'

    Upvotes are treated as confirmed wins and will boost the source's auto_weight
    the next time reweight_input_sources.py runs.
    Downvotes flag the signal as a false positive — reduces source weight.
    """
    if feedback not in {"upvote", "downvote", "pending"}:
        return {"ok": False, "error": "feedback must be upvote, downvote, or pending"}
    if not DB_PATH.exists():
        return {"ok": False, "error": "db not found"}
    conn = _connect()
    try:
        from datetime import datetime, timezone

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS counterfactual_feedback (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              route_id INTEGER NOT NULL,
              horizon_hours INTEGER NOT NULL,
              feedback TEXT NOT NULL DEFAULT 'pending',
              feedback_at TEXT,
              notes TEXT NOT NULL DEFAULT '',
              UNIQUE(route_id, horizon_hours)
            )
            """
        )
        ts = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO counterfactual_feedback(route_id, horizon_hours, feedback, feedback_at, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(route_id, horizon_hours) DO UPDATE SET
              feedback=excluded.feedback,
              feedback_at=excluded.feedback_at,
              notes=excluded.notes
            """,
            (int(route_id), int(horizon_hours), feedback, ts, str(notes or "")),
        )
        conn.commit()

        # Immediately adjust auto_weight for the source if upvote/downvote
        source_tag = ""
        if _table_exists(conn, "route_outcomes_horizons"):
            cur = conn.cursor()
            cur.execute(
                "SELECT source_tag FROM route_outcomes_horizons WHERE route_id=? AND horizon_hours=? LIMIT 1",
                (int(route_id), int(horizon_hours)),
            )
            row = cur.fetchone()
            if row:
                source_tag = str(row[0] or "").strip()

        if source_tag and feedback in {"upvote", "downvote"} and _table_exists(conn, "input_source_controls"):
            key = f"source:{source_tag.lower()}"
            cur = conn.cursor()
            cur.execute(
                "SELECT auto_weight FROM input_source_controls WHERE source_key=? LIMIT 1",
                (key,),
            )
            existing = cur.fetchone()
            current_w = float(existing[0] if existing else 1.0)
            nudge = 0.05 if feedback == "upvote" else -0.05
            new_w = round(max(0.4, min(2.0, current_w + nudge)), 6)
            conn.execute(
                """
                INSERT INTO input_source_controls
                (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
                VALUES (datetime('now'), datetime('now'), ?, ?, 'source_tag', 1, 1.0, ?, '')
                ON CONFLICT(source_key) DO UPDATE SET
                  updated_at=datetime('now'),
                  auto_weight=excluded.auto_weight
                """,
                (key, f"Source {source_tag}", new_w),
            )
            conn.commit()

        return {
            "ok": True,
            "route_id": route_id,
            "horizon_hours": horizon_hours,
            "feedback": feedback,
            "source_tag": source_tag,
        }
    finally:
        conn.close()


def get_kelly_signals(limit: int = 50) -> Dict[str, Any]:
    """
    Latest Kelly scores for all trade candidates.

    Returns:
      rows          — per-candidate Kelly breakdown
      portfolio     — budget summary (used/remaining/max)
      summary       — counts by verdict
    """
    if not DB_PATH.exists():
        return {"rows": [], "portfolio": {}, "summary": {}}
    conn = _connect()
    try:
        if not _table_exists(conn, "kelly_signals"):
            return {"rows": [], "portfolio": {}, "summary": {}}

        cur = conn.cursor()
        # Latest batch: all rows from the most recent computed_at
        cur.execute(
            """
            SELECT
              ticker, direction, source_tag, horizon_hours,
              win_prob, avg_win_pct, avg_loss_pct,
              payout_ratio, kelly_fraction, frac_kelly,
              convexity_score, ev_percent, sample_size,
              verdict, verdict_reason, computed_at
            FROM kelly_signals
            WHERE computed_at = (SELECT MAX(computed_at) FROM kelly_signals)
            ORDER BY
              CASE verdict WHEN 'pass' THEN 0 WHEN 'warmup' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END,
              ev_percent DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = _rows_to_dicts(cur, cur.fetchall())

        # Portfolio budget from pipeline_runtime_state
        portfolio: Dict[str, Any] = {}
        if _table_exists(conn, "pipeline_runtime_state"):
            cur.execute(
                "SELECT key, value FROM pipeline_runtime_state WHERE key LIKE 'kelly_%'",
            )
            for key, val in cur.fetchall():
                k = key.replace("kelly_", "", 1)
                try:
                    portfolio[k] = float(val)
                except (ValueError, TypeError):
                    portfolio[k] = val

        # Verdict summary
        summary: Dict[str, int] = {}
        for r in rows:
            v = str(r.get("verdict") or "unknown")
            summary[v] = summary.get(v, 0) + 1

        return {"rows": rows, "portfolio": portfolio, "summary": summary}
    finally:
        conn.close()


def get_exchange_pnl_summary() -> Dict[str, Any]:
    """
    Per-exchange P&L summary with agent action attribution.

    Returns:
      exchanges: dict of venue -> { realized_pnl, unrealized_pnl, trades_won, trades_lost,
                                    win_rate, closed_trades, open_positions }
      agent_actions: recent intents that were acted on (stops placed, alerts sent, entries)
      closed_trades: recent closed trades with closed_by attribution
    """
    if not DB_PATH.exists():
        return {"exchanges": {}, "agent_actions": [], "closed_trades": []}

    conn = _connect()
    try:
        cur = conn.cursor()

        # ── 1. Alpaca realized P&L from trades table ──────────────────────────
        alpaca_realized = {"total_pnl": 0.0, "wins": 0, "losses": 0, "trades": []}
        if _table_exists(conn, "trades"):
            cur.execute("""
                SELECT ticker, entry_side, entry_price, exit_price,
                       pnl, pnl_percent, status, entry_date, last_sync, broker_order_id, route_id, trade_id
                FROM trades
                WHERE status = 'closed' AND pnl IS NOT NULL
                ORDER BY last_sync DESC
                LIMIT 100
            """)
            for row in cur.fetchall():
                ticker, side, entry_px, exit_px, pnl, pnl_pct, status, entry_date, last_sync, broker_id, route_id, trade_id = row
                alpaca_realized["total_pnl"] += float(pnl or 0)
                if (pnl or 0) > 0:
                    alpaca_realized["wins"] += 1
                else:
                    alpaca_realized["losses"] += 1
                # Build a clean lookup ID: prefer route_id, fall back to trade_id
                lookup_id = f"route_{route_id}" if route_id else str(trade_id or "")
                alpaca_realized["trades"].append({
                    "ticker": ticker, "side": side,
                    "entry_price": entry_px, "exit_price": exit_px,
                    "pnl": round(float(pnl or 0), 4),
                    "pnl_percent": round(float(pnl_pct or 0), 2),
                    "closed_at": str(last_sync or entry_date or ""),
                    "route_id": route_id,
                    "trade_id": str(trade_id or ""),
                    "lookup_id": lookup_id,
                })

        # ── 2. Live positions from position_awareness_snapshots ───────────────
        live_positions: Dict[str, List[Dict]] = {}
        if _table_exists(conn, "position_awareness_snapshots"):
            cur.execute("""
                SELECT venue, symbol, side, qty, entry_price, mark_price,
                       unrealized_pnl_usd, unrealized_pnl_pct, notional_usd, action, created_at
                FROM position_awareness_snapshots
                WHERE created_at = (SELECT MAX(created_at) FROM position_awareness_snapshots)
                ORDER BY ABS(unrealized_pnl_usd) DESC
            """)
            for row in cur.fetchall():
                venue, sym, side, qty, entry_px, mark_px, upnl_usd, upnl_pct, notional, action, ts = row
                venue = str(venue or "unknown").lower()
                if venue not in live_positions:
                    live_positions[venue] = []
                live_positions[venue].append({
                    "symbol": sym, "side": side, "qty": qty,
                    "entry_price": entry_px, "mark_price": mark_px,
                    "unrealized_pnl_usd": round(float(upnl_usd or 0), 2),
                    "unrealized_pnl_pct": round(float(upnl_pct or 0), 2),
                    "notional_usd": round(float(notional or 0), 2),
                    "action": action, "snapshot_at": str(ts or ""),
                })

        # ── 3. Agent actions from trade_intents ───────────────────────────────
        agent_actions = []
        if _table_exists(conn, "trade_intents"):
            cur.execute("""
                SELECT id, created_at, venue, symbol, side, qty, notional, status, details
                FROM trade_intents
                WHERE status IN (
                    'submitted','submitted_stop','alert_sent',
                    'manage_trail_stop_tighten','manage_reduce_or_exit',
                    'manage_take_profit_major','manage_take_profit_partial',
                    'held_signal_veto'
                )
                ORDER BY created_at DESC
                LIMIT 40
            """)
            for row in cur.fetchall():
                intent_id, ts, venue, symbol, side, qty, notional, status, details_raw = row
                details = {}
                try:
                    details = json.loads(details_raw or "{}")
                except Exception:
                    pass

                # Determine human-readable action type
                if status == "submitted_stop":
                    action_type = "stop_placed"
                    stop_px = details.get("trigger_stop_price") or details.get("trigger_px")
                    description = f"Stop placed @ ${stop_px:.2f}" if stop_px else "Stop order placed"
                elif status == "alert_sent":
                    action_type = "take_profit_alert"
                    pnl_pct = details.get("pnl_pct") or details.get("unrealized_pnl_pct")
                    description = f"Take profit alert — PnL {pnl_pct:.1f}%" if pnl_pct else "Take profit alert sent"
                elif status == "submitted":
                    action_type = "order_filled"
                    filled = (details.get("live_order_result") or {}).get("response", {}).get("data", {}).get("statuses", [{}])[0]
                    avg_px = (filled.get("filled") or {}).get("avgPx")
                    network = details.get("network", "")
                    description = f"Filled @ ${avg_px} ({network})" if avg_px else f"Order submitted ({network})"
                elif status == "manage_trail_stop_tighten":
                    action_type = "reassess_tighten"
                    net = details.get("net_score", "?")
                    description = f"Reassess: tighten stop (net={net})"
                elif status == "manage_reduce_or_exit":
                    action_type = "reassess_exit"
                    description = "Reassess: exit signal"
                elif status == "manage_take_profit_major":
                    action_type = "reassess_take_profit"
                    description = "Reassess: take profit (all 3 bullish)"
                elif status == "held_signal_veto":
                    action_type = "veto_hold"
                    description = "Stop suppressed — bullish liquidity veto"
                else:
                    action_type = status
                    description = status

                agent_actions.append({
                    "intent_id": intent_id,
                    "symbol": symbol, "side": side,
                    "venue": str(venue or ""),
                    "status": status,
                    "action_type": action_type,
                    "description": description,
                    "network": details.get("network", ""),
                    "acted_at": str(ts or ""),
                })

        # ── 4. Build per-exchange summary ─────────────────────────────────────
        exchanges: Dict[str, Any] = {}

        # Alpaca
        n = len(alpaca_realized["trades"])
        wins = alpaca_realized["wins"]
        exchanges["alpaca"] = {
            "label": "Alpaca (Stocks)",
            "realized_pnl": round(alpaca_realized["total_pnl"], 2),
            "unrealized_pnl": 0.0,
            "trades_closed": n,
            "wins": wins,
            "losses": alpaca_realized["losses"],
            "win_rate": round(wins / n * 100, 1) if n else 0.0,
            "open_positions": 0,  # Alpaca open tracked in trades table
        }

        # Hyperliquid
        hl_positions = live_positions.get("hyperliquid", [])
        hl_unrealized = sum(p["unrealized_pnl_usd"] for p in hl_positions)
        # Count agent stop + entry actions on HL
        hl_actions = [a for a in agent_actions if "hyperliquid" in str(a.get("venue", "")).lower()
                      or a.get("network") == "testnet"]
        exchanges["hyperliquid"] = {
            "label": "Hyperliquid (Crypto)",
            "realized_pnl": 0.0,  # HL realized not tracked in trades table yet
            "unrealized_pnl": round(hl_unrealized, 2),
            "trades_closed": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "open_positions": len(hl_positions),
            "open_details": hl_positions,
            "agent_actions_count": len(hl_actions),
        }

        return {
            "ok": True,
            "exchanges": exchanges,
            "agent_actions": agent_actions,
            "closed_trades": alpaca_realized["trades"],
            "live_positions": live_positions,
        }
    finally:
        conn.close()


# ── Alpaca / Hyperliquid venue-specific queries ────────────────────────────


def get_alpaca_orders(limit: int = 120) -> List[Dict[str, Any]]:
    """Execution orders filtered to stocks/Alpaca venue with fill data."""
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "execution_orders"):
            return []
        cur = conn.cursor()
        has_fill = _table_exists(conn, "alpaca_fill_sync")
        if has_fill:
            cur.execute(
                """
                SELECT eo.created_at, eo.route_id, eo.ticker, eo.direction, eo.mode,
                       eo.notional, eo.order_status, eo.broker_order_id, eo.notes,
                       afs.filled_qty, afs.filled_price, afs.filled_at
                FROM execution_orders eo
                LEFT JOIN alpaca_fill_sync afs ON eo.broker_order_id = afs.order_id
                ORDER BY eo.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT created_at, route_id, ticker, direction, mode,
                       notional, order_status, broker_order_id, notes,
                       NULL AS filled_qty, NULL AS filled_price, NULL AS filled_at
                FROM execution_orders
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def get_hyperliquid_intents(limit: int = 120) -> List[Dict[str, Any]]:
    """Trade intents filtered to venue='hyperliquid'."""
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "trade_intents"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, venue, symbol, side, qty, notional, status, details
            FROM trade_intents
            WHERE LOWER(COALESCE(venue, '')) = 'hyperliquid'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    finally:
        conn.close()


def submit_alpaca_quick_trade(
    symbol: str, side: str, notional: float
) -> Dict[str, Any]:
    """Submit a manual Alpaca market order via REST API."""
    env = _load_env()
    api_key = env.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY", "")
    base_url = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not api_key or not secret:
        return {"ok": False, "error": "missing Alpaca credentials"}

    symbol = str(symbol).strip().upper()
    side = str(side).strip().lower()
    if side not in ("buy", "sell", "close"):
        return {"ok": False, "error": f"invalid side: {side}"}

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }

    if side == "close":
        try:
            req = urllib.request.Request(
                f"{base_url}/v2/positions/{symbol}",
                headers=headers,
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            order_id = result.get("id", "")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"Alpaca API {exc.code}: {body}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    else:
        if notional <= 0:
            return {"ok": False, "error": "notional must be positive"}
        order_body = json.dumps({
            "symbol": symbol,
            "notional": str(round(notional, 2)),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"{base_url}/v2/orders",
                data=order_body,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            order_id = result.get("id", "")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"Alpaca API {exc.code}: {body}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Record in execution_orders + trade_intents
    conn = _connect()
    try:
        if _table_exists(conn, "execution_orders"):
            conn.execute(
                """
                INSERT INTO execution_orders
                (created_at, route_id, ticker, direction, mode, notional, order_status, broker_order_id, notes)
                VALUES (datetime('now'), 0, ?, ?, 'manual', ?, 'submitted', ?, 'quick-trade-ui')
                """,
                (symbol, side, notional, order_id),
            )
        if _table_exists(conn, "trade_intents"):
            conn.execute(
                """
                INSERT INTO trade_intents
                (created_at, venue, symbol, side, qty, notional, status, details)
                VALUES (datetime('now'), 'alpaca', ?, ?, 0, ?, 'submitted', ?)
                """,
                (symbol, side, notional, json.dumps({"order_id": order_id, "source": "quick-trade-ui"})),
            )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "order_id": order_id}


def submit_hyperliquid_quick_trade(
    symbol: str, side: str, notional: float
) -> Dict[str, Any]:
    """Submit a manual Hyperliquid market order via execution_adapters."""
    symbol = str(symbol).strip().upper()
    side = str(side).strip().lower()
    if side not in ("buy", "sell"):
        return {"ok": False, "error": f"invalid side: {side}"}
    if notional <= 0:
        return {"ok": False, "error": "notional must be positive"}

    # Import execution adapter from parent directory
    adapter_path = str(BASE_DIR)
    if adapter_path not in sys.path:
        sys.path.insert(0, adapter_path)
    try:
        from execution_adapters import hyperliquid_submit_notional_live
    except ImportError as exc:
        return {"ok": False, "error": f"cannot import execution_adapters: {exc}"}

    try:
        result = hyperliquid_submit_notional_live(symbol, side, notional)
        ok = result.get("ok", False) if isinstance(result, dict) else False
        intent_id = result.get("intent_id", "") if isinstance(result, dict) else ""
        error = result.get("error", "") if isinstance(result, dict) else ""
        return {"ok": ok, "intent_id": intent_id, "error": error}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_system_intelligence() -> Dict[str, Any]:
    """Rolling Sharpe + win rate, quant gate effectiveness, and source P&L contribution."""
    from statistics import pstdev

    result: Dict[str, Any] = {"rolling": [], "gate_effectiveness": {}, "source_contribution": []}
    if not DB_PATH.exists():
        return result

    conn = _connect()
    try:
        # --- Rolling Sharpe & Win Rate ---
        if _table_exists(conn, "route_outcomes"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT resolved_at, pnl_percent
                FROM route_outcomes
                WHERE pnl_percent IS NOT NULL
                ORDER BY datetime(COALESCE(resolved_at, '1970-01-01')) ASC
                """
            )
            all_outcomes = cur.fetchall()
            window = 30
            step = 5
            rolling: List[Dict[str, Any]] = []
            for i in range(window, len(all_outcomes) + 1, step):
                chunk = all_outcomes[i - window:i]
                pnls = [float(r[1] or 0.0) for r in chunk]
                wins = sum(1 for p in pnls if p > 0)
                win_rate = round(100.0 * wins / len(pnls), 1)
                mean_pnl = sum(pnls) / len(pnls)
                std_pnl = pstdev(pnls) if len(pnls) > 1 else 0.0
                sharpe = round(mean_pnl / std_pnl, 3) if std_pnl > 1e-9 else 0.0
                ts = str(chunk[-1][0] or "")
                rolling.append({"ts": ts, "sharpe": sharpe, "win_rate": win_rate, "idx": i})
            result["rolling"] = rolling

        # --- Gate Effectiveness ---
        if _table_exists(conn, "quant_validations") and _table_exists(conn, "route_outcomes"):
            cur = conn.cursor()
            for passed_val, label in [(1, "passed"), (0, "rejected")]:
                cur.execute(
                    """
                    SELECT
                      COUNT(*) AS n,
                      AVG(CASE WHEN o.pnl_percent > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate,
                      AVG(o.pnl_percent) AS avg_pnl_pct
                    FROM (
                      SELECT DISTINCT UPPER(ticker) AS tk, source_tag AS st
                      FROM quant_validations
                      WHERE passed = ?
                    ) qv
                    JOIN route_outcomes o
                      ON UPPER(o.ticker) = qv.tk AND o.source_tag = qv.st
                    WHERE o.pnl_percent IS NOT NULL
                    """,
                    (passed_val,),
                )
                row = cur.fetchone()
                n = int(row[0] or 0) if row else 0
                wr = round(float(row[1] or 0.0), 1) if row and n > 0 else 0.0
                avg = round(float(row[2] or 0.0), 2) if row and n > 0 else 0.0
                result["gate_effectiveness"][label] = {"n": n, "win_rate": wr, "avg_pnl_pct": avg}

        # --- Source P&L Contribution ---
        if _table_exists(conn, "route_outcomes"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT source_tag, SUM(pnl_percent) AS total, COUNT(*) AS n
                FROM route_outcomes
                WHERE pnl_percent IS NOT NULL
                GROUP BY source_tag
                ORDER BY SUM(pnl_percent) DESC
                """
            )
            result["source_contribution"] = [
                {"source_tag": str(r[0] or ""), "total_pnl_pct": round(float(r[1] or 0.0), 2), "n": int(r[2] or 0)}
                for r in cur.fetchall()
            ]
    finally:
        conn.close()

    return result


# ---------------------------------------------------------------------------
# Source Decay Detection + Dampening
# ---------------------------------------------------------------------------


def _ensure_weight_change_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weight_change_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          changed_at TEXT NOT NULL,
          source_key TEXT NOT NULL,
          old_auto_weight REAL NOT NULL,
          new_auto_weight REAL NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          sample_size INTEGER NOT NULL DEFAULT 0,
          win_rate REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def _log_decay_change(
    conn: sqlite3.Connection,
    source_key: str,
    old_w: float,
    new_w: float,
    reason: str,
    sample_size: int,
    win_rate: float,
) -> None:
    if abs(old_w - new_w) < 0.0001:
        return
    conn.execute(
        """
        INSERT INTO weight_change_log
        (changed_at, source_key, old_auto_weight, new_auto_weight, reason, sample_size, win_rate)
        VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)
        """,
        (source_key, old_w, new_w, reason, sample_size, round(win_rate, 2)),
    )


def get_source_decay_status(
    window_days: int = 14, min_lifetime_trades: int = 10
) -> Dict[str, Any]:
    """Compare recent vs lifetime per-source performance and flag decay."""
    import math

    conn = _connect()
    try:
        if not _table_exists(conn, "route_outcomes"):
            return {"ok": True, "window_days": window_days, "sources": [], "summary": {"healthy": 0, "decaying": 0, "improving": 0}}

        cur = conn.cursor()

        # Q1 — lifetime stats per source
        cur.execute(
            """
            SELECT source_tag,
                   COUNT(*) AS n,
                   AVG(CASE WHEN pnl_percent > 0 THEN 1.0 ELSE 0.0 END) * 100 AS wr,
                   AVG(pnl_percent) AS avg_pnl
            FROM route_outcomes
            WHERE pnl_percent IS NOT NULL
            GROUP BY source_tag
            HAVING COUNT(*) >= ?
            """,
            (min_lifetime_trades,),
        )
        lifetime = {}
        for row in cur.fetchall():
            tag = str(row[0] or "")
            lifetime[tag] = {
                "n": int(row[1] or 0),
                "win_rate": round(float(row[2] or 0.0), 2),
                "avg_pnl": round(float(row[3] or 0.0), 4),
            }

        # Q2 — recent window stats
        cur.execute(
            """
            SELECT source_tag,
                   COUNT(*) AS n,
                   AVG(CASE WHEN pnl_percent > 0 THEN 1.0 ELSE 0.0 END) * 100 AS wr,
                   AVG(pnl_percent) AS avg_pnl
            FROM route_outcomes
            WHERE pnl_percent IS NOT NULL
              AND datetime(resolved_at) >= datetime('now', ? || ' days')
            GROUP BY source_tag
            """,
            (str(-window_days),),
        )
        recent = {}
        for row in cur.fetchall():
            tag = str(row[0] or "")
            recent[tag] = {
                "n": int(row[1] or 0),
                "win_rate": round(float(row[2] or 0.0), 2),
                "avg_pnl": round(float(row[3] or 0.0), 4),
            }

        # auto_weight lookup
        has_isc = _table_exists(conn, "input_source_controls")

        sources_out = []
        counts = {"healthy": 0, "decaying": 0, "improving": 0}

        for tag, lt in sorted(lifetime.items(), key=lambda x: x[1]["win_rate"]):
            rc = recent.get(tag, {"n": 0, "win_rate": 0.0, "avg_pnl": 0.0})

            # Q3 — EMA series from ordered pnl values
            cur.execute(
                """
                SELECT pnl_percent FROM route_outcomes
                WHERE source_tag = ? AND pnl_percent IS NOT NULL
                ORDER BY datetime(COALESCE(resolved_at, '1970-01-01')) ASC
                """,
                (tag,),
            )
            pnl_rows = [float(r[0]) for r in cur.fetchall()]
            alpha = 2.0 / (14.0 + 1.0)
            ema_series = []
            ema = 50.0
            for val in pnl_rows:
                win_val = 100.0 if val > 0 else 0.0
                ema = alpha * win_val + (1.0 - alpha) * ema
                ema_series.append(round(ema, 2))

            # Decay signal: Bernoulli σ
            lt_p = lt["win_rate"] / 100.0
            sigma = math.sqrt(max(lt_p * (1.0 - lt_p), 0.0001)) * 100.0
            if rc["n"] >= 5:
                if rc["win_rate"] < lt["win_rate"] - sigma:
                    decay_signal = "decaying"
                elif rc["win_rate"] > lt["win_rate"] + sigma:
                    decay_signal = "improving"
                else:
                    decay_signal = "stable"
            else:
                decay_signal = "stable"

            severity = round(max(0.0, lt["win_rate"] - rc["win_rate"]) / max(sigma, 1.0), 2) if rc["n"] >= 5 else 0.0

            # auto_weight
            auto_weight = 1.0
            if has_isc:
                cur.execute(
                    "SELECT auto_weight FROM input_source_controls WHERE source_key = ? LIMIT 1",
                    ("source:" + tag.lower(),),
                )
                aw_row = cur.fetchone()
                if aw_row:
                    auto_weight = round(float(aw_row[0] or 1.0), 4)

            # Suggested action
            if decay_signal == "decaying":
                suggested = "dampen"
            elif decay_signal == "improving" and auto_weight < 0.95:
                suggested = "boost"
            else:
                suggested = "hold"

            if decay_signal == "decaying":
                counts["decaying"] += 1
            elif decay_signal == "improving":
                counts["improving"] += 1
            else:
                counts["healthy"] += 1

            sources_out.append({
                "source_tag": tag,
                "lifetime_n": lt["n"],
                "lifetime_win_rate": lt["win_rate"],
                "lifetime_avg_pnl_pct": lt["avg_pnl"],
                "recent_n": rc["n"],
                "recent_win_rate": rc["win_rate"],
                "recent_avg_pnl_pct": rc["avg_pnl"],
                "ema_series": ema_series,
                "decay_signal": decay_signal,
                "severity": severity,
                "current_auto_weight": auto_weight,
                "suggested_action": suggested,
            })

        return {
            "ok": True,
            "window_days": window_days,
            "sources": sources_out,
            "summary": counts,
        }
    finally:
        conn.close()


def apply_source_dampening(source_tag: str, action: str) -> Dict[str, Any]:
    """Apply dampen/restore/disable to a source's auto_weight."""
    if action not in ("dampen", "restore", "disable"):
        return {"ok": False, "error": f"unknown action: {action}"}
    if not source_tag:
        return {"ok": False, "error": "missing source_tag"}

    source_key = "source:" + source_tag.lower()
    conn = _connect()
    try:
        _ensure_weight_change_log_table(conn)

        # Ensure row exists
        conn.execute(
            """
            INSERT OR IGNORE INTO input_source_controls
            (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, '', 1, 1.0, 1.0, '')
            """,
            (source_key, source_tag),
        )

        cur = conn.cursor()
        cur.execute(
            "SELECT auto_weight, enabled FROM input_source_controls WHERE source_key = ?",
            (source_key,),
        )
        row = cur.fetchone()
        old_weight = float(row[0]) if row else 1.0
        old_enabled = int(row[1]) if row else 1

        new_weight = old_weight
        new_enabled = old_enabled
        reason = ""

        if action == "dampen":
            new_weight = 0.0
            reason = "dashboard_decay_dampening"
        elif action == "restore":
            new_weight = 1.0
            reason = "dashboard_decay_restore"
        elif action == "disable":
            new_enabled = 0
            reason = "dashboard_decay_disable"

        conn.execute(
            """
            UPDATE input_source_controls
            SET auto_weight = ?, enabled = ?, updated_at = datetime('now')
            WHERE source_key = ?
            """,
            (new_weight, new_enabled, source_key),
        )

        _log_decay_change(conn, source_key, old_weight, new_weight, reason, 0, 0.0)
        conn.commit()

        return {
            "ok": True,
            "source_key": source_key,
            "action": action,
            "old_auto_weight": round(old_weight, 4),
            "new_auto_weight": round(new_weight, 4),
        }
    finally:
        conn.close()


def auto_dampen_decaying_sources() -> Dict[str, Any]:
    """Auto-zero any source flagged as decaying. Controlled by auto_decay_enabled."""
    conn = _connect()
    try:
        enabled = True
        if _table_exists(conn, "execution_controls"):
            cur = conn.cursor()
            cur.execute("SELECT value FROM execution_controls WHERE key='auto_decay_enabled' LIMIT 1")
            row = cur.fetchone()
            if row and str(row[0]) == "0":
                enabled = False
        if not enabled:
            return {"auto_decay_enabled": False, "checked": 0, "zeroed": []}

        decay = get_source_decay_status()
        sources = decay.get("sources") or []
        zeroed: List[str] = []
        for s in sources:
            if s.get("decay_signal") == "decaying":
                tag = s.get("source_tag", "")
                if tag:
                    apply_source_dampening(tag, "dampen")
                    zeroed.append(tag)
        return {"auto_decay_enabled": True, "checked": len(sources), "zeroed": zeroed}
    finally:
        conn.close()


def get_fresh_whale_discoveries(limit: int = 50) -> Dict[str, Any]:
    """Return recent fresh whale discoveries with summary stats."""
    if not DB_PATH.exists():
        return {"ok": False, "discoveries": [], "summary": {"total_discovered": 0, "total_auto_tracked": 0}}
    conn = _connect()
    try:
        if not _table_exists(conn, "fresh_whale_discoveries"):
            return {"ok": True, "discoveries": [], "summary": {"total_discovered": 0, "total_auto_tracked": 0}}
        cur = conn.cursor()
        cur.execute(
            """
            SELECT discovered_at, wallet_address, handle, join_date, account_age_days,
                   market_slug, condition_id, trade_size_usdc, side, outcome, auto_tracked, notes
            FROM fresh_whale_discoveries
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        cols = [c[0] for c in cur.description]
        discoveries = [dict(zip(cols, row)) for row in cur.fetchall()]

        cur.execute("SELECT COUNT(*) FROM fresh_whale_discoveries")
        total = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM fresh_whale_discoveries WHERE auto_tracked=1")
        tracked = int(cur.fetchone()[0] or 0)

        return {
            "ok": True,
            "discoveries": discoveries,
            "summary": {"total_discovered": total, "total_auto_tracked": tracked},
        }
    finally:
        conn.close()


def get_market_regime_status() -> Dict[str, Any]:
    """Read latest market regime state for all asset classes."""
    if not DB_PATH.exists():
        return {"ok": False, "regimes": []}
    conn = _connect()
    try:
        if not _table_exists(conn, "market_regime_state"):
            return {"ok": True, "regimes": []}
        cur = conn.cursor()
        regimes: List[Dict[str, Any]] = []
        for ac in ("stocks", "crypto"):
            cur.execute(
                """
                SELECT fetched_at, symbol, ema_fast, ema_slow, hl2_current, trend, cloud_width_pct
                FROM market_regime_state
                WHERE asset_class = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ac,),
            )
            row = cur.fetchone()
            if row:
                regimes.append({
                    "asset_class": ac,
                    "fetched_at": str(row[0]),
                    "symbol": str(row[1]),
                    "ema_fast": float(row[2]),
                    "ema_slow": float(row[3]),
                    "hl2_current": float(row[4]),
                    "trend": str(row[5]),
                    "cloud_width_pct": float(row[6]),
                })
        return {"ok": True, "regimes": regimes}
    finally:
        conn.close()


def get_x_consensus_status() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"consensus_signals": [], "discovery_candidates": [], "settings": {"x_consensus_min_hits": 3}}
    conn = _connect()
    try:
        consensus_signals: List[Dict[str, Any]] = []
        if _table_exists(conn, "x_consensus_signals"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ticker, direction, source_count, sources, avg_confidence,
                       weighted_confidence, created_at
                FROM x_consensus_signals
                WHERE status = 'active'
                ORDER BY source_count DESC, created_at DESC
                LIMIT 100
                """
            )
            consensus_signals = _rows_to_dicts(cur, cur.fetchall())

        discovery_candidates: List[Dict[str, Any]] = []
        if _table_exists(conn, "x_discovery_candidates"):
            cur = conn.cursor()
            cur.execute(
                """
                SELECT handle, display_name, followers, description, sample_call,
                       discovery_source, status, discovered_at,
                       COALESCE(kol_category, 'stocks') AS kol_category
                FROM x_discovery_candidates
                ORDER BY CASE status WHEN 'new' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                         discovered_at DESC
                LIMIT 200
                """
            )
            discovery_candidates = _rows_to_dicts(cur, cur.fetchall())

        min_hits = 3
        if _table_exists(conn, "execution_controls"):
            cur = conn.cursor()
            cur.execute("SELECT value FROM execution_controls WHERE key='x_consensus_min_hits' LIMIT 1")
            row = cur.fetchone()
            if row and row[0]:
                min_hits = int(float(row[0]))

        return {
            "consensus_signals": consensus_signals,
            "discovery_candidates": discovery_candidates,
            "settings": {"x_consensus_min_hits": min_hits},
        }
    finally:
        conn.close()


def approve_x_discovery(handle: str) -> Dict[str, Any]:
    handle = str(handle or "").strip().lower().lstrip("@")
    if not handle:
        return {"ok": False, "error": "handle required"}
    if not DB_PATH.exists():
        return {"ok": False, "error": "database not found"}
    conn = _connect()
    try:
        if not _table_exists(conn, "x_discovery_candidates"):
            return {"ok": False, "error": "no discovery candidates table"}

        conn.execute(
            "UPDATE x_discovery_candidates SET status='approved' WHERE lower(handle)=?",
            (handle,),
        )

        # Read kol_category from discovery candidate
        kol_category = "stocks"
        if _column_exists(conn, "x_discovery_candidates", "kol_category"):
            cur = conn.cursor()
            cur.execute(
                "SELECT kol_category FROM x_discovery_candidates WHERE lower(handle)=? LIMIT 1",
                (handle,),
            )
            row = cur.fetchone()
            if row and row[0]:
                kol_category = str(row[0])

        # Auto-insert into tracked_x_sources
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
              notes TEXT NOT NULL DEFAULT '',
              kol_category TEXT NOT NULL DEFAULT 'stocks'
            )
            """
        )
        if not _column_exists(conn, "tracked_x_sources", "kol_category"):
            conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN kol_category TEXT NOT NULL DEFAULT 'stocks'")
        conn.execute(
            """
            INSERT INTO tracked_x_sources
            (created_at, updated_at, handle, role_copy, role_alpha, active, x_api_enabled, source_weight, notes, kol_category)
            VALUES (datetime('now'), datetime('now'), ?, 0, 1, 1, 1, 1.0, 'auto-approved from discovery', ?)
            ON CONFLICT(handle) DO UPDATE SET
              active=1, x_api_enabled=1, updated_at=datetime('now'),
              kol_category=excluded.kol_category
            """,
            (handle, kol_category),
        )
        conn.commit()
        return {"ok": True, "handle": handle, "action": "approved", "kol_category": kol_category}
    finally:
        conn.close()


def reject_x_discovery(handle: str) -> Dict[str, Any]:
    handle = str(handle or "").strip().lower().lstrip("@")
    if not handle:
        return {"ok": False, "error": "handle required"}
    if not DB_PATH.exists():
        return {"ok": False, "error": "database not found"}
    conn = _connect()
    try:
        if not _table_exists(conn, "x_discovery_candidates"):
            return {"ok": False, "error": "no discovery candidates table"}
        conn.execute(
            "UPDATE x_discovery_candidates SET status='rejected' WHERE lower(handle)=?",
            (handle,),
        )
        conn.commit()
        return {"ok": True, "handle": handle, "action": "rejected"}
    finally:
        conn.close()


def get_health_pulse() -> Dict[str, Any]:
    """Aggregate ~15 indicators from existing data functions into a health pulse."""
    indicators: List[Dict[str, Any]] = []

    # ── Fetch upstream data (reuse existing endpoints, zero new SQL) ──
    summary = get_summary()
    perf = get_performance_curve()
    intel = get_system_intelligence()
    rdns = get_signal_readiness()
    guard = get_trade_claim_guard()
    overview = get_master_overview()
    learning = get_learning_health()
    monitor = get_learning_monitor()
    decay = get_source_decay_status()
    consensus = get_x_consensus_status()

    from data_scorecard import get_signal_scorecard as _scorecard
    scorecard = _scorecard()

    # ── Helper ──
    def _ind(
        ind_id: str,
        label: str,
        value: Any,
        display: str,
        status: str,
        delta: str,
        sparkline: List[float],
        tooltip: str,
        thresholds: str,
        category: str,
    ) -> Dict[str, Any]:
        return {
            "id": ind_id,
            "label": label,
            "value": value,
            "display": display,
            "status": status,
            "delta": delta,
            "sparkline": sparkline,
            "tooltip": tooltip,
            "thresholds": thresholds,
            "category": category,
        }

    # ── 1. Rolling Sharpe ──
    rolling = intel.get("rolling") or []
    sharpe_vals = [float(r.get("sharpe") or 0) for r in rolling if r.get("sharpe") is not None]
    sharpe = sharpe_vals[-1] if sharpe_vals else 0.0
    sharpe_prev = sharpe_vals[-2] if len(sharpe_vals) >= 2 else sharpe
    sharpe_delta = sharpe - sharpe_prev
    sharpe_status = "green" if sharpe > 1.0 else ("yellow" if sharpe >= 0.5 else "red")
    indicators.append(_ind(
        "sharpe", "Rolling Sharpe", round(sharpe, 2), f"{sharpe:.2f}",
        sharpe_status,
        f"{'+' if sharpe_delta >= 0 else ''}{sharpe_delta:.2f}",
        sharpe_vals[-20:],
        "How much reward you're getting for the risk you take. Imagine two lemonade stands — "
        "both make $10/day, but one has wild swings ($0 some days, $20 others). Sharpe measures "
        "which stand is more reliable. Above 1.0 = solid, above 2.0 = excellent, below 0.5 = too "
        "risky for the return. Fed by: route_outcomes \u2192 30-trade rolling window \u2192 sharpe ratio.",
        "green >1.0 \u00b7 yellow 0.5\u20131.0 \u00b7 red <0.5",
        "performance",
    ))

    # ── 2. Win Rate (30-trade rolling) ──
    wr_vals = [float(r.get("win_rate") or 0) for r in rolling if r.get("win_rate") is not None]
    wr = wr_vals[-1] if wr_vals else float(summary.get("win_rate") or 0)
    wr_prev = wr_vals[-2] if len(wr_vals) >= 2 else wr
    wr_delta = wr - wr_prev
    wr_status = "green" if wr > 55 else ("yellow" if wr >= 45 else "red")
    indicators.append(_ind(
        "win_rate", "Win Rate (30-trade)", round(wr, 1), f"{wr:.1f}%",
        wr_status,
        f"{'+' if wr_delta >= 0 else ''}{wr_delta:.1f}%",
        wr_vals[-20:],
        "Of your last 30 closed trades, what percentage were winners. Think of it like a batting "
        "average \u2014 above 55% means you're hitting more than you're missing. Below 45% means "
        "the system is struggling. Fed by: route_outcomes \u2192 30-trade rolling window \u2192 win/loss count.",
        "green >55% \u00b7 yellow 45\u201355% \u00b7 red <45%",
        "performance",
    ))

    # ── 3. Max Drawdown ──
    max_dd = float(perf.get("max_drawdown") or 0)
    dd_pct = abs(max_dd)
    dd_status = "green" if dd_pct < 10 else ("yellow" if dd_pct <= 20 else "red")
    by_trade = perf.get("by_trade") or []
    dd_series: List[float] = []
    peak = 0.0
    for pt in by_trade:
        cum = float(pt.get("cumulative_pnl") or pt.get("cum_pnl") or 0)
        if cum > peak:
            peak = cum
        dd_series.append(peak - cum)
    indicators.append(_ind(
        "max_drawdown", "Max Drawdown", round(dd_pct, 1), f"{dd_pct:.1f}%",
        dd_status, "", dd_series[-20:] if dd_series else [],
        "The biggest peak-to-trough drop in your account. If you had $1000 and it dropped to $900, "
        "that's a 10% drawdown. Smaller is better \u2014 under 10% = disciplined risk, over 20% = "
        "painful losses piling up. Fed by: route_outcomes \u2192 cumulative P&L curve \u2192 peak-to-trough.",
        "green <10% \u00b7 yellow 10\u201320% \u00b7 red >20%",
        "performance",
    ))

    # ── 4. Total P&L ──
    total_pnl = float(summary.get("total_pnl") or 0)
    pnl_status = "green" if total_pnl > 0 else ("yellow" if total_pnl == 0 else "red")
    pnl_display = f"${total_pnl:+,.2f}" if abs(total_pnl) < 100000 else f"${total_pnl:+,.0f}"
    indicators.append(_ind(
        "total_pnl", "Total P&L", round(total_pnl, 2), pnl_display,
        pnl_status, "", [],
        "Your total profit or loss across all closed trades. Green = making money, red = losing "
        "money. This is the bottom line \u2014 everything else is about improving this number. "
        "Fed by: route_outcomes (realized) or trades table \u2192 sum of P&L.",
        "green >$0 \u00b7 red <$0",
        "performance",
    ))

    # ── 5. Source Health ──
    decay_summary = decay.get("summary") or {}
    n_decaying = int(decay_summary.get("decaying") or 0)
    n_healthy = int(decay_summary.get("healthy") or 0)
    n_improving = int(decay_summary.get("improving") or 0)
    src_status = "green" if n_decaying == 0 else ("yellow" if n_decaying <= 2 else "red")
    indicators.append(_ind(
        "source_health", "Source Health", n_decaying,
        f"{n_healthy}ok {n_decaying}decay {n_improving}up",
        src_status, "", [],
        "How your signal sources (X accounts, pipelines) are performing recently vs their lifetime "
        "average. 'Decaying' means a source that used to win is now losing \u2014 like a baseball "
        "player in a slump. 0 decaying = healthy ecosystem, 3+ = multiple sources going bad at once. "
        "Fed by: route_outcomes \u2192 per-source EMA decay detection \u2192 14d vs lifetime comparison.",
        "green 0 decaying \u00b7 yellow 1\u20132 \u00b7 red 3+",
        "signal_quality",
    ))

    # ── 6. Quant Gate Edge ──
    gate = intel.get("gate_effectiveness") or {}
    passed = gate.get("passed") or {}
    rejected = gate.get("rejected") or {}
    passed_wr = float(passed.get("win_rate") or 0)
    rejected_wr = float(rejected.get("win_rate") or 0)
    gate_delta_val = passed_wr - rejected_wr
    gate_status = "green" if gate_delta_val > 5 else ("yellow" if gate_delta_val >= 0 else "red")
    indicators.append(_ind(
        "gate_delta", "Quant Gate Edge", round(gate_delta_val, 1), f"{gate_delta_val:+.1f}%",
        gate_status, "", [],
        "The quant gate is a filter that blocks low-quality trades before they execute. This shows "
        "whether the gate is helping: positive = trades it approved win more than those it rejected "
        "(good!). Negative = the gate is blocking good trades (bad \u2014 it's hurting you). "
        "Fed by: route_outcomes \u2192 comparing win rates of passed vs rejected candidates.",
        "green >5% \u00b7 yellow 0\u20135% \u00b7 red <0%",
        "signal_quality",
    ))

    # ── 7. Source Grades ──
    sources_sc = scorecard.get("sources") or []
    grade_counts: Dict[str, int] = {"green": 0, "yellow": 0, "red": 0}
    for s in sources_sc:
        g = str(s.get("grade") or "").lower()
        if g in grade_counts:
            grade_counts[g] += 1
    total_graded = sum(grade_counts.values())
    green_pct = (grade_counts["green"] / total_graded * 100) if total_graded else 0
    red_pct = (grade_counts["red"] / total_graded * 100) if total_graded else 0
    grades_status = "green" if green_pct >= 60 else ("red" if red_pct >= 50 else "yellow")
    indicators.append(_ind(
        "source_grades", "Source Grades", grade_counts,
        f"{grade_counts['green']}G {grade_counts['yellow']}Y {grade_counts['red']}R",
        grades_status, "", [],
        "A summary of how your signal sources grade out. Each source gets green (>55% win rate), "
        "yellow (45\u201355%), or red (<45%). Mostly green = your sources are strong. Mostly red = "
        "time to prune bad sources or find new ones. Fed by: signal_scorecard \u2192 per-source grade.",
        "green mostly green \u00b7 yellow mixed \u00b7 red mostly red",
        "signal_quality",
    ))

    # ── 8. Missed Winners (7d) ──
    missed = overview.get("missed") or {}
    missed_wins = int(missed.get("not_taken_wins") or 0)
    missed_status = "green" if missed_wins <= 2 else ("yellow" if missed_wins <= 5 else "red")
    indicators.append(_ind(
        "missed_winners", "Missed Winners (7d)", missed_wins, str(missed_wins),
        missed_status, "", [],
        "Trades the system identified but didn't take that turned out to be winners. A few misses "
        "are normal (risk limits, timing). But 6+ means the system is being too cautious or filters "
        "are blocking profitable opportunities. Fed by: route_outcomes \u2192 not-taken routes resolved "
        "as wins in the last 7 days.",
        "green 0\u20132 \u00b7 yellow 3\u20135 \u00b7 red 6+",
        "signal_quality",
    ))

    # ── 9. System Readiness ──
    readiness_score = int(rdns.get("score") or 0)
    rdns_status = "green" if readiness_score > 80 else ("yellow" if readiness_score >= 50 else "red")
    indicators.append(_ind(
        "readiness", "System Readiness", readiness_score, f"{readiness_score}/100",
        rdns_status, "", [],
        "An overall score of whether all pipeline components are working. Checks: do you have "
        "candidates flowing in, routes being created, quant validations passing, signals arriving? "
        "Above 80 = everything humming. Below 50 = something major is broken or stale. "
        "Fed by: signal_readiness \u2192 weighted checklist of pipeline components.",
        "green >80 \u00b7 yellow 50\u201380 \u00b7 red <50",
        "pipeline",
    ))

    # ── 10. Trade Ready ──
    trade_ready = bool(guard.get("trade_ready"))
    tr_status = "green" if trade_ready else "red"
    indicators.append(_ind(
        "trade_ready", "Trade Ready", trade_ready, "YES" if trade_ready else "NO",
        tr_status, "", [],
        "Can the system actually execute trades right now? Checks: is trading enabled, are exchange "
        "adapters connected, is Python runtime healthy, are signing keys valid (for Polymarket). "
        "If NO, nothing will trade until the blocker is fixed. "
        "Fed by: trade_claim_guard \u2192 all execution prerequisites checked.",
        "green yes \u00b7 red no",
        "pipeline",
    ))

    # ── 11. Learning Coverage ──
    coverage = float(learning.get("coverage_pct") or learning.get("tracked_coverage_pct") or 0)
    cov_status = "green" if coverage > 70 else ("yellow" if coverage >= 40 else "red")
    indicators.append(_ind(
        "learning_coverage", "Learning Coverage", round(coverage, 1), f"{coverage:.0f}%",
        cov_status, "", [],
        "What percentage of your signal routes have tracked outcomes (win/loss resolution). "
        "High coverage means the system is learning from most of its decisions. Low coverage means "
        "many trades go untracked \u2014 the system can't learn from what it doesn't measure. "
        "Fed by: learning_health \u2192 tracked_routes / eligible_routes.",
        "green >70% \u00b7 yellow 40\u201370% \u00b7 red <40%",
        "pipeline",
    ))

    # ── 12. Last Learning Update ──
    outcomes = monitor.get("outcomes") or {}
    age_min = outcomes.get("last_resolved_age_min")
    if age_min is not None:
        age_val = float(age_min)
        age_display = f"{int(age_val)}m" if age_val < 60 else f"{age_val / 60:.1f}h"
        age_status = "green" if age_val < 60 else ("yellow" if age_val <= 360 else "red")
    else:
        age_val = None
        age_display = "\u2014"
        age_status = "yellow"
    indicators.append(_ind(
        "learning_age", "Last Learning Update", age_val, age_display,
        age_status, "", [],
        "How long ago the system last resolved a trade outcome (marked a route as win or loss). "
        "Under 60 minutes = outcomes are flowing fresh. Over 6 hours = learning pipeline may be "
        "stalled, and the system is flying blind on recent performance. "
        "Fed by: learning_monitor \u2192 most recent resolved_at timestamp \u2192 age in minutes.",
        "green <60m \u00b7 yellow 60\u2013360m \u00b7 red >6h",
        "pipeline",
    ))

    # ── 13. Queued Trades ──
    queued = int(guard.get("approved_queued_routes") or 0)
    queued_status = "green" if queued >= 1 else "yellow"
    indicators.append(_ind(
        "queued_routes", "Queued Trades", queued, str(queued),
        queued_status, "", [],
        "How many trade routes are approved and waiting to execute. 1+ means the pipeline has "
        "actionable ideas ready to go. 0 means nothing is queued \u2014 either the market is quiet, "
        "filters are too strict, or the pipeline isn't generating candidates. "
        "Fed by: trade_claim_guard \u2192 approved_queued_routes count.",
        "green 1+ \u00b7 yellow 0",
        "execution",
    ))

    # ── 14. Trades Made (24h) ──
    venue_24h = overview.get("venue_24h") or {}
    trades_24h = 0
    for venue_data in venue_24h.values():
        if isinstance(venue_data, dict):
            trades_24h += int(venue_data.get("filled") or 0)
    indicators.append(_ind(
        "trades_24h", "Trades Made (24h)", trades_24h, str(trades_24h),
        "info", "", [],
        "Total trades that actually filled across all venues (Alpaca, Hyperliquid, Polymarket) "
        "in the last 24 hours. This is informational \u2014 not good or bad, just activity level. "
        "Zero trades could mean safe mode, no signals, or market hours. "
        "Fed by: master_overview \u2192 per-venue 24h fill counts.",
        "info only",
        "execution",
    ))

    # ── 15. X Consensus Active ──
    consensus_signals = consensus.get("consensus_signals") or []
    n_consensus = len(consensus_signals)
    consensus_status = "green" if n_consensus >= 1 else "yellow"
    indicators.append(_ind(
        "x_consensus", "X Consensus Active", n_consensus, str(n_consensus),
        consensus_status, "", [],
        "How many consensus signals are active \u2014 meaning 3+ X accounts agree on the same "
        "ticker and direction. Consensus adds conviction to a trade idea. 1+ active = the "
        "crowd sees something. 0 = no strong multi-source agreement right now. "
        "Fed by: x_consensus_signals \u2192 active signals where source_count >= min_hits.",
        "green 1+ \u00b7 yellow 0",
        "execution",
    ))

    # ── 16. Stocks Regime ──
    regime_data = get_market_regime_status()
    regime_map = {r["asset_class"]: r for r in (regime_data.get("regimes") or [])}
    stocks_r = regime_map.get("stocks")
    stocks_trend = stocks_r["trend"] if stocks_r else "unknown"
    stocks_regime_status = "green" if stocks_trend == "bullish" else ("red" if stocks_trend == "bearish" else "yellow")
    stocks_display = stocks_trend.upper() if stocks_r else "NO DATA"
    indicators.append(_ind(
        "stocks_regime", "Stocks Regime", stocks_trend, stocks_display,
        stocks_regime_status, "", [],
        "Ripster 34/50 EMA cloud on SPY hl2. Bullish = EMA34 above EMA50 (green cloud), "
        "bearish = EMA34 below EMA50 (red cloud). When bearish, the regime filter blocks "
        "stock longs in the signal router. Two indicators, zero confusion. "
        "Fed by: market_regime_state \u2192 SPY trend.",
        "green bullish \u00b7 red bearish",
        "regime",
    ))

    # ── 17. Crypto Regime ──
    crypto_r = regime_map.get("crypto")
    crypto_trend = crypto_r["trend"] if crypto_r else "unknown"
    crypto_regime_status = "green" if crypto_trend == "bullish" else ("red" if crypto_trend == "bearish" else "yellow")
    crypto_display = crypto_trend.upper() if crypto_r else "NO DATA"
    indicators.append(_ind(
        "crypto_regime", "Crypto Regime", crypto_trend, crypto_display,
        crypto_regime_status, "", [],
        "Ripster 34/50 EMA cloud on BTC-USD hl2. Bullish = EMA34 above EMA50 (green cloud), "
        "bearish = EMA34 below EMA50 (red cloud). When bearish, the regime filter blocks "
        "crypto longs in the signal router. Clouds not green = no trade. "
        "Fed by: market_regime_state \u2192 BTC-USD trend.",
        "green bullish \u00b7 red bearish",
        "regime",
    ))

    # ── 18. Fresh Whales (24h) ──
    fw_count_24h = 0
    try:
        fw_conn = _connect()
        if _table_exists(fw_conn, "fresh_whale_discoveries"):
            fw_cur = fw_conn.cursor()
            fw_cur.execute(
                """
                SELECT COUNT(*) FROM fresh_whale_discoveries
                WHERE auto_tracked=1
                  AND datetime(discovered_at) >= datetime('now', '-24 hours')
                """
            )
            fw_count_24h = int(fw_cur.fetchone()[0] or 0)
        fw_conn.close()
    except Exception:
        pass
    fw_status = "green" if fw_count_24h >= 1 else "yellow"
    indicators.append(_ind(
        "fresh_whales", "Fresh Whales (24h)", fw_count_24h, str(fw_count_24h),
        fw_status, "", [],
        "New Polymarket accounts (under 7 days old) caught placing large bets ($50k+) in the "
        "last 24 hours and auto-added for copy trading. Fresh whales are high-signal because "
        "insiders often create new accounts before placing informed bets. 1+ = discovery working, "
        "0 = no new whales found (normal on quiet days). "
        "Fed by: scan_fresh_whales \u2192 CLOB trade scan \u2192 profile age check \u2192 auto-track.",
        "green 1+ \u00b7 yellow 0",
        "execution",
    ))

    return {"indicators": indicators}


# ── Cross-platform arb opportunities (brain_arb_opportunities) ──────────────
def get_arb_opportunities(limit: int = 100) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = _connect()
    try:
        if not _table_exists(conn, "brain_arb_opportunities"):
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, detected_at, poly_condition_id, kalshi_ticker, title,
                   similarity, poly_price, kalshi_price, spread, spread_after_fees,
                   direction, poly_size_usd, kalshi_size_usd, action,
                   poly_order_id, kalshi_order_id, notes
            FROM brain_arb_opportunities
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return _rows_to_dicts(cur, cur.fetchall())
    except Exception:
        return []
    finally:
        conn.close()


def get_arb_overview() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {}
    conn = _connect()
    try:
        if not _table_exists(conn, "brain_arb_opportunities"):
            return {"total_scanned": 0, "executed": 0, "partial": 0, "avg_spread": 0}
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_scanned,
                SUM(CASE WHEN action='executed' THEN 1 ELSE 0 END) AS executed,
                SUM(CASE WHEN action='partial' THEN 1 ELSE 0 END) AS partial,
                AVG(CASE WHEN spread_after_fees > 0 THEN spread_after_fees ELSE NULL END) AS avg_spread,
                SUM(CASE WHEN action='executed' THEN poly_size_usd + kalshi_size_usd ELSE 0 END) AS total_notional
            FROM brain_arb_opportunities
            WHERE datetime(detected_at) >= datetime('now', '-7 days')
            """
        )
        row = cur.fetchone()
        # Fetch arb controls
        arb_enabled = "1"
        min_spread = "5.0"
        max_leg = "25"
        if _table_exists(conn, "execution_controls"):
            for key in ("tb_arb_enabled", "tb_arb_min_spread_pct", "tb_arb_max_per_leg"):
                c = conn.execute(
                    "SELECT value FROM execution_controls WHERE key=?", (key,)
                )
                r = c.fetchone()
                if r:
                    if key == "tb_arb_enabled":
                        arb_enabled = r[0]
                    elif key == "tb_arb_min_spread_pct":
                        min_spread = r[0]
                    elif key == "tb_arb_max_per_leg":
                        max_leg = r[0]
        return {
            "total_scanned": int(row[0] or 0),
            "executed": int(row[1] or 0),
            "partial": int(row[2] or 0),
            "avg_spread": round(float(row[3] or 0), 4),
            "total_notional": round(float(row[4] or 0), 2),
            "arb_enabled": arb_enabled == "1",
            "min_spread_pct": float(min_spread),
            "max_per_leg": float(max_leg),
        }
    except Exception:
        return {}
    finally:
        conn.close()
