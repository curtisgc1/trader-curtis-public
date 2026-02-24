#!/usr/bin/env python3
"""
Build learning feedback from executed routes and realized trade outcomes.
This gives the agent a persistent mistakes/wins memory pipeline.
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Tuple
import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
ENV_PATH = Path(__file__).parent / ".env"
STRATEGY_TAGS = {"A_SCALP", "B_LONGTERM", "C_EVENT", "D_BOOKMARKS", "POLY_ALPHA", "POLY_COPY", "POLY_ARB"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS route_outcomes (
          route_id INTEGER PRIMARY KEY,
          ticker TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          outcome_type TEXT NOT NULL DEFAULT 'realized',
          resolution TEXT NOT NULL,
          pnl REAL NOT NULL,
          pnl_percent REAL NOT NULL,
          resolved_at TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_learning_stats (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at TEXT NOT NULL,
          source_tag TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          wins INTEGER NOT NULL,
          losses INTEGER NOT NULL,
          pushes INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_learning_stats (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at TEXT NOT NULL,
          strategy_tag TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          wins INTEGER NOT NULL,
          losses INTEGER NOT NULL,
          pushes INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS route_trade_links (
          route_id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          source_tag TEXT NOT NULL DEFAULT '',
          venue TEXT NOT NULL DEFAULT '',
          direction TEXT NOT NULL DEFAULT '',
          mode TEXT NOT NULL DEFAULT '',
          entry_side TEXT NOT NULL DEFAULT '',
          entry_order_id TEXT NOT NULL DEFAULT '',
          entry_status TEXT NOT NULL DEFAULT '',
          entry_fill_price REAL NOT NULL DEFAULT 0,
          entry_fill_qty REAL NOT NULL DEFAULT 0,
          entry_filled_at TEXT NOT NULL DEFAULT '',
          state TEXT NOT NULL DEFAULT 'pending',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS route_feedback_features (
          route_id INTEGER PRIMARY KEY,
          captured_at TEXT NOT NULL,
          routed_at TEXT NOT NULL DEFAULT '',
          ticker TEXT NOT NULL DEFAULT '',
          direction TEXT NOT NULL DEFAULT '',
          source_tag TEXT NOT NULL DEFAULT '',
          strategy_tag TEXT NOT NULL DEFAULT '',
          route_score REAL NOT NULL DEFAULT 0,
          route_decision TEXT NOT NULL DEFAULT '',
          route_status TEXT NOT NULL DEFAULT '',
          route_mode TEXT NOT NULL DEFAULT '',
          venue TEXT NOT NULL DEFAULT '',
          hour_utc INTEGER NOT NULL DEFAULT -1,
          dow_utc INTEGER NOT NULL DEFAULT -1,
          candidate_score_threshold REAL NOT NULL DEFAULT 0,
          consensus_min_confirmations INTEGER NOT NULL DEFAULT 0,
          consensus_min_ratio REAL NOT NULL DEFAULT 0,
          consensus_min_score REAL NOT NULL DEFAULT 0,
          alpaca_min_route_score REAL NOT NULL DEFAULT 0,
          hyperliquid_min_route_score REAL NOT NULL DEFAULT 0,
          polymarket_min_confidence_pct REAL NOT NULL DEFAULT 0,
          quant_validation_id INTEGER NOT NULL DEFAULT 0,
          quant_passed INTEGER NOT NULL DEFAULT -1,
          quant_sample_size INTEGER NOT NULL DEFAULT 0,
          quant_win_rate REAL NOT NULL DEFAULT 0,
          quant_ev REAL NOT NULL DEFAULT 0,
          allocator_factor REAL NOT NULL DEFAULT 1.0,
          allocator_regime TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS input_feature_stats (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          computed_at TEXT NOT NULL,
          outcome_type TEXT NOT NULL,
          dimension TEXT NOT NULL,
          dimension_value TEXT NOT NULL,
          sample_size INTEGER NOT NULL,
          wins INTEGER NOT NULL,
          losses INTEGER NOT NULL,
          pushes INTEGER NOT NULL,
          win_rate REAL NOT NULL,
          avg_pnl REAL NOT NULL,
          avg_pnl_percent REAL NOT NULL
        )
        """
    )
    if table_exists(conn, "route_outcomes") and not column_exists(conn, "route_outcomes", "outcome_type"):
        conn.execute("ALTER TABLE route_outcomes ADD COLUMN outcome_type TEXT NOT NULL DEFAULT 'realized'")
        conn.execute(
            """
            UPDATE route_outcomes
            SET outcome_type = CASE
              WHEN lower(COALESCE(notes,'')) LIKE 'operational_%' THEN 'operational'
              ELSE 'realized'
            END
            """
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_outcomes_source ON route_outcomes(source_tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_outcomes_type ON route_outcomes(outcome_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_links_state ON route_trade_links(state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_features_source ON route_feedback_features(source_tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_features_venue ON route_feedback_features(venue)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_route_features_hour ON route_feedback_features(hour_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_input_feature_dim ON input_feature_stats(dimension, dimension_value)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_input_feature_outcome ON input_feature_stats(outcome_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_learning_route ON execution_learning(route_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_route ON trades(route_id)")
    conn.commit()


def _operational_pnl_penalty(conn: sqlite3.Connection, route_id: int) -> float:
    """
    Derive a small synthetic USD penalty from proposed notional.
    Default: 25 bps of proposed notional, clipped to [-3.0, -0.5] USD.
    """
    notional = 50.0
    if table_exists(conn, "signal_routes"):
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(proposed_notional, 50.0) FROM signal_routes WHERE id=? LIMIT 1", (int(route_id),))
        row = cur.fetchone()
        if row and row[0] is not None:
            try:
                notional = float(row[0] or 50.0)
            except Exception:
                notional = 50.0
    raw = max(0.5, min(3.0, notional * 0.0025))
    return -round(raw, 4)


def backfill_operational_pnl(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "route_outcomes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT route_id
        FROM route_outcomes
        WHERE COALESCE(outcome_type,'realized')='operational'
          AND ABS(COALESCE(pnl, 0.0)) < 0.000001
        LIMIT 2000
        """
    )
    rows = cur.fetchall()
    updated = 0
    for (route_id,) in rows:
        penalty = _operational_pnl_penalty(conn, int(route_id))
        cur.execute(
            "UPDATE route_outcomes SET pnl=? WHERE route_id=?",
            (float(penalty), int(route_id)),
        )
        updated += int(cur.rowcount or 0)
    conn.commit()
    return updated


def backfill_route_links(conn: sqlite3.Connection, limit: int = 2000) -> int:
    if not table_exists(conn, "execution_orders") or not table_exists(conn, "route_trade_links"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT eo.route_id, eo.ticker, eo.direction, eo.mode, eo.order_status,
               COALESCE(eo.broker_order_id,''), COALESCE(eo.notes,''), COALESCE(sr.source_tag,'internal')
        FROM execution_orders eo
        LEFT JOIN route_trade_links l ON l.route_id = eo.route_id
        LEFT JOIN signal_routes sr ON sr.id = eo.route_id
        WHERE l.route_id IS NULL
        ORDER BY eo.id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    for route_id, ticker, direction, mode, order_status, broker_order_id, notes, source_tag in rows:
        status = str(order_status or "").lower()
        state = "pending"
        if status in {"rejected", "canceled", "expired", "stopped", "blocked", "failed"}:
            state = "failed"
        elif status in {"filled"}:
            state = "open"
        venue = "alpaca" if str(notes).lower().startswith("alpaca paper:") else (
            "hyperliquid" if "hyperliquid" in str(notes).lower() else "paper-sim"
        )
        side = "sell" if str(direction).lower() in {"short", "bearish", "sell"} else "buy"
        cur.execute(
            """
            INSERT OR REPLACE INTO route_trade_links
            (
              route_id, created_at, updated_at, ticker, source_tag, venue, direction, mode,
              entry_side, entry_order_id, entry_status, state, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(route_id),
                now_iso(),
                now_iso(),
                str(ticker or "").upper(),
                source_tag,
                venue,
                str(direction or ""),
                str(mode or ""),
                side,
                str(broker_order_id or ""),
                str(order_status or ""),
                state,
                str(notes or "")[:240],
            ),
        )
    conn.commit()
    return len(rows)


def strategy_for(source_tag: str) -> str:
    src = str(source_tag or "").strip().upper()
    if src in STRATEGY_TAGS:
        return src
    if src.startswith("POLY_"):
        return src
    return "UNSPECIFIED"


def _as_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return float(default)


def _as_int(v: object, default: int = 0) -> int:
    try:
        return int(float(v))  # type: ignore[arg-type]
    except Exception:
        return int(default)


def _parse_iso(ts: str) -> datetime:
    s = str(ts or "").strip()
    if not s:
        return datetime.now(timezone.utc)
    if "T" not in s and " " in s:
        s = s.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _score_bin(score: float) -> str:
    if score < 40:
        return "<40"
    if score < 50:
        return "40-49"
    if score < 60:
        return "50-59"
    if score < 70:
        return "60-69"
    if score < 80:
        return "70-79"
    return "80+"


def _ratio_bin(v: float) -> str:
    if v < 0.4:
        return "<0.4"
    if v < 0.6:
        return "0.4-0.59"
    if v < 0.8:
        return "0.6-0.79"
    return "0.8+"


def _ev_bin(v: float) -> str:
    if v < -1.0:
        return "<-1"
    if v < 0:
        return "-1-0"
    if v < 1.0:
        return "0-0.99"
    if v < 3.0:
        return "1-2.99"
    return "3+"


def load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _alpaca_latest_price(ticker: str, env: Dict[str, str]) -> float:
    api_key = str(env.get("ALPACA_API_KEY", "")).strip()
    secret = str(env.get("ALPACA_SECRET_KEY", "")).strip()
    if not api_key or not secret:
        return 0.0
    base = str(env.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")).strip().rstrip("/")
    url = f"{base}/v2/stocks/{ticker}/trades/latest"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code >= 400:
            return 0.0
        payload = res.json() if res.content else {}
        trade = payload.get("trade", {}) if isinstance(payload, dict) else {}
        px = float(trade.get("p") or 0.0)
        return px if px > 0 else 0.0
    except Exception:
        return 0.0


def _alpaca_price_at_time(ticker: str, ts_iso: str, env: Dict[str, str]) -> float:
    api_key = str(env.get("ALPACA_API_KEY", "")).strip()
    secret = str(env.get("ALPACA_SECRET_KEY", "")).strip()
    if not api_key or not secret:
        return 0.0
    base = str(env.get("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")).strip().rstrip("/")
    dt = _parse_iso(ts_iso).astimezone(timezone.utc)
    start = dt.isoformat().replace("+00:00", "Z")
    end = (dt + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    url = f"{base}/v2/stocks/{ticker}/bars?timeframe=1Min&start={start}&end={end}&limit=1&adjustment=raw&feed=iex&sort=asc"
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code >= 400:
            return 0.0
        payload = res.json() if res.content else {}
        bars = payload.get("bars", []) if isinstance(payload, dict) else []
        if bars:
            px = float((bars[0] or {}).get("c") or 0.0)
            if px > 0:
                return px
    except Exception:
        return 0.0
    return 0.0


def resolve_not_taken_opportunities(
    conn: sqlite3.Connection,
    min_age_hours: int = 6,
    max_age_hours: int = 72,
    max_candidates: int = 40,
    max_price_lookups: int = 120,
) -> int:
    """
    Resolve not-approved routes with hypothetical win/loss from routed-time price to current price.
    This flags missed winners for the learning loop.
    """
    if not table_exists(conn, "signal_routes"):
        return 0
    env = load_env()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.id, r.ticker, r.direction, COALESCE(r.source_tag,'internal'), COALESCE(r.routed_at,''), COALESCE(r.proposed_notional,50.0)
        FROM signal_routes r
        LEFT JOIN route_outcomes o ON o.route_id = r.id
        WHERE o.route_id IS NULL
          AND COALESCE(r.decision,'') <> 'approved'
        ORDER BY r.id DESC
        LIMIT 500
        """
    )
    rows = cur.fetchall()
    now = datetime.now(timezone.utc)
    inserted = 0
    latest_cache: Dict[str, float] = {}
    lookups = 0
    processed = 0
    for route_id, ticker, direction, source_tag, routed_at, proposed_notional in rows:
        if processed >= int(max_candidates) or lookups >= int(max_price_lookups):
            break
        dt = _parse_iso(str(routed_at or ""))
        age_h = (now - dt).total_seconds() / 3600.0
        if age_h < float(min_age_hours) or age_h > float(max_age_hours):
            continue
        tk = str(ticker or "").upper().strip()
        if not tk or not tk.isalpha():
            continue
        entry_px = _alpaca_price_at_time(tk, str(routed_at or ""), env)
        lookups += 1
        if tk in latest_cache:
            latest_px = latest_cache[tk]
        else:
            latest_px = _alpaca_latest_price(tk, env)
            latest_cache[tk] = latest_px
            lookups += 1
        if entry_px <= 0 or latest_px <= 0:
            continue

        side = str(direction or "long").lower()
        if side in {"short", "sell", "bearish"}:
            pnl_pct = ((entry_px - latest_px) / entry_px) * 100.0
        else:
            pnl_pct = ((latest_px - entry_px) / entry_px) * 100.0
        notional = float(proposed_notional or 50.0)
        pnl = notional * (pnl_pct / 100.0)
        if pnl > 0:
            resolution = "win"
        elif pnl < 0:
            resolution = "loss"
        else:
            resolution = "push"

        cur.execute(
            """
            INSERT OR REPLACE INTO route_outcomes
            (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(route_id),
                tk,
                str(source_tag or "internal"),
                "operational",
                resolution,
                round(float(pnl), 6),
                round(float(pnl_pct), 6),
                now_iso(),
                f"missed_not_taken_proxy age_h={age_h:.2f} entry={entry_px:.6f} latest={latest_px:.6f}",
            ),
        )
        inserted += 1
        processed += 1
    conn.commit()
    return inserted


def resolve_mark_to_market_outcomes(conn: sqlite3.Connection, max_age_hours: int = 72, min_age_hours: int = 4) -> int:
    """
    Aggressive fallback resolver:
    for older open routes without outcomes, stamp an operational win/loss using live mark price.
    This improves learning signal density when explicit close events lag.
    """
    if not table_exists(conn, "route_trade_links"):
        return 0
    env = load_env()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT l.route_id, l.ticker, COALESCE(r.source_tag,'internal'),
               COALESCE(l.entry_side,''), COALESCE(l.entry_fill_price,0), COALESCE(l.entry_fill_qty,0),
               COALESCE(r.routed_at,'')
        FROM route_trade_links l
        LEFT JOIN route_outcomes o ON o.route_id = l.route_id
        LEFT JOIN signal_routes r ON r.id = l.route_id
        WHERE o.route_id IS NULL
          AND lower(COALESCE(l.state,'')) IN ('open','pending')
          AND lower(COALESCE(l.entry_status,'')) IN ('filled','submitted','partially_filled')
        ORDER BY l.updated_at DESC
        LIMIT 500
        """
    )
    rows = cur.fetchall()
    inserted = 0
    now = datetime.now(timezone.utc)
    for route_id, ticker, source_tag, entry_side, entry_px, entry_qty, routed_at in rows:
        dt = _parse_iso(str(routed_at or ""))
        age_h = (now - dt).total_seconds() / 3600.0
        if age_h < float(min_age_hours) or age_h > float(max_age_hours):
            continue
        epx = float(entry_px or 0.0)
        qty = float(entry_qty or 0.0)
        if epx <= 0:
            continue
        mark = _alpaca_latest_price(str(ticker or "").upper(), env)
        if mark <= 0:
            continue
        side = str(entry_side or "buy").lower()
        if side == "sell":
            pnl = (epx - mark) * max(qty, 1.0)
            pnl_pct = ((epx - mark) / epx) * 100.0
        else:
            pnl = (mark - epx) * max(qty, 1.0)
            pnl_pct = ((mark - epx) / epx) * 100.0
        if pnl > 0:
            resolution = "win"
        elif pnl < 0:
            resolution = "loss"
        else:
            resolution = "push"
        cur.execute(
            """
            INSERT OR REPLACE INTO route_outcomes
            (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(route_id),
                str(ticker or "").upper(),
                str(source_tag or "internal"),
                "operational",
                resolution,
                round(float(pnl), 6),
                round(float(pnl_pct), 6),
                now_iso(),
                f"mark_to_market_proxy age_h={age_h:.2f} mark={mark:.6f} entry={epx:.6f}",
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def snapshot_route_features(conn: sqlite3.Connection, limit: int = 3000) -> int:
    if not table_exists(conn, "signal_routes") or not table_exists(conn, "route_feedback_features"):
        return 0
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    controls = {str(k): str(v) for k, v in cur.fetchall()}

    cur.execute(
        """
        SELECT r.id, r.routed_at, r.ticker, r.direction, COALESCE(r.score,0), COALESCE(r.source_tag,'internal'),
               COALESCE(r.decision,''), COALESCE(r.status,''), COALESCE(r.mode,''),
               COALESCE(r.validation_id,0), COALESCE(r.allocator_factor,1.0), COALESCE(r.allocator_regime,'')
        FROM signal_routes r
        LEFT JOIN route_feedback_features f ON f.route_id = r.id
        WHERE f.route_id IS NULL
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    inserted = 0
    for (
        route_id,
        routed_at,
        ticker,
        direction,
        route_score,
        source_tag,
        decision,
        status,
        mode,
        validation_id,
        allocator_factor,
        allocator_regime,
    ) in rows:
        dt = _parse_iso(str(routed_at or ""))
        hour_utc = int(dt.hour)
        dow_utc = int(dt.weekday())

        venue = ""
        if table_exists(conn, "route_trade_links"):
            cur.execute("SELECT COALESCE(venue,'') FROM route_trade_links WHERE route_id=? LIMIT 1", (int(route_id),))
            vr = cur.fetchone()
            venue = str(vr[0] or "") if vr else ""

        quant_passed = -1
        quant_sample_size = 0
        quant_win_rate = 0.0
        quant_ev = 0.0
        if int(validation_id or 0) > 0 and table_exists(conn, "quant_validations"):
            cur.execute(
                """
                SELECT COALESCE(passed,0), COALESCE(sample_size,0), COALESCE(win_rate,0), COALESCE(expected_value_percent,0)
                FROM quant_validations
                WHERE id=?
                LIMIT 1
                """,
                (int(validation_id),),
            )
            qrow = cur.fetchone()
            if qrow:
                quant_passed = int(qrow[0] or 0)
                quant_sample_size = int(qrow[1] or 0)
                quant_win_rate = float(qrow[2] or 0.0)
                quant_ev = float(qrow[3] or 0.0)

        cur.execute(
            """
            INSERT OR REPLACE INTO route_feedback_features
            (
              route_id, captured_at, routed_at, ticker, direction, source_tag, strategy_tag,
              route_score, route_decision, route_status, route_mode, venue,
              hour_utc, dow_utc,
              candidate_score_threshold, consensus_min_confirmations, consensus_min_ratio, consensus_min_score,
              alpaca_min_route_score, hyperliquid_min_route_score, polymarket_min_confidence_pct,
              quant_validation_id, quant_passed, quant_sample_size, quant_win_rate, quant_ev,
              allocator_factor, allocator_regime
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(route_id),
                now_iso(),
                str(routed_at or ""),
                str(ticker or "").upper(),
                str(direction or ""),
                str(source_tag or "internal"),
                strategy_for(str(source_tag or "")),
                float(route_score or 0.0),
                str(decision or ""),
                str(status or ""),
                str(mode or ""),
                str(venue or ""),
                hour_utc,
                dow_utc,
                _as_float(controls.get("min_candidate_score"), 60.0),
                _as_int(controls.get("consensus_min_confirmations"), 3),
                _as_float(controls.get("consensus_min_ratio"), 0.6),
                _as_float(controls.get("consensus_min_score"), 60.0),
                _as_float(controls.get("alpaca_min_route_score"), 60.0),
                _as_float(controls.get("hyperliquid_min_route_score"), 60.0),
                _as_float(controls.get("polymarket_min_confidence_pct"), 60.0),
                int(validation_id or 0),
                int(quant_passed),
                int(quant_sample_size),
                float(quant_win_rate),
                float(quant_ev),
                float(allocator_factor or 1.0),
                str(allocator_regime or ""),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def refresh_input_feature_stats(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "route_outcomes") or not table_exists(conn, "route_feedback_features"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.route_id, COALESCE(o.outcome_type,'realized'), COALESCE(o.resolution,'push'),
               COALESCE(o.pnl,0), COALESCE(o.pnl_percent,0),
               COALESCE(f.source_tag,'internal'), COALESCE(f.strategy_tag,'UNSPECIFIED'),
               COALESCE(f.venue,''), COALESCE(f.hour_utc,-1), COALESCE(f.route_score,0),
               COALESCE(f.candidate_score_threshold,0), COALESCE(f.consensus_min_ratio,0),
               COALESCE(f.consensus_min_score,0), COALESCE(f.alpaca_min_route_score,0),
               COALESCE(f.hyperliquid_min_route_score,0), COALESCE(f.polymarket_min_confidence_pct,0),
               COALESCE(f.quant_passed,-1), COALESCE(f.quant_ev,0)
        FROM route_outcomes o
        LEFT JOIN route_feedback_features f ON f.route_id = o.route_id
        """
    )
    rows = cur.fetchall()
    if not rows:
        cur.execute("DELETE FROM input_feature_stats")
        conn.commit()
        return 0

    agg: Dict[Tuple[str, str, str], Dict[str, float]] = {}

    def add_stat(outcome_type: str, dim: str, val: str, resolution: str, pnl: float, pnl_pct: float) -> None:
        key = (outcome_type, dim, val)
        bucket = agg.get(key, {"n": 0, "wins": 0, "losses": 0, "pushes": 0, "sum_pnl": 0.0, "sum_pnl_pct": 0.0})
        bucket["n"] += 1
        if resolution == "win":
            bucket["wins"] += 1
        elif resolution == "loss":
            bucket["losses"] += 1
        else:
            bucket["pushes"] += 1
        bucket["sum_pnl"] += pnl
        bucket["sum_pnl_pct"] += pnl_pct
        agg[key] = bucket

    for (
        _route_id,
        outcome_type,
        resolution,
        pnl,
        pnl_pct,
        source_tag,
        strategy_tag,
        venue,
        hour_utc,
        route_score,
        candidate_score_threshold,
        consensus_min_ratio,
        consensus_min_score,
        alpaca_min_route_score,
        hyperliquid_min_route_score,
        polymarket_min_confidence_pct,
        quant_passed,
        quant_ev,
    ) in rows:
        out_t = str(outcome_type or "realized")
        res = str(resolution or "push")
        p = float(pnl or 0.0)
        pp = float(pnl_pct or 0.0)
        hour_val = str(int(hour_utc)) if int(hour_utc) >= 0 else "unknown"
        quant_passed_val = str(int(quant_passed)) if int(quant_passed) in {0, 1} else "unknown"

        dims = {
            "source_tag": str(source_tag or "internal"),
            "strategy_tag": str(strategy_tag or "UNSPECIFIED"),
            "venue": str(venue or "unknown"),
            "hour_utc": hour_val,
            "route_score_bin": _score_bin(float(route_score or 0.0)),
            "candidate_score_threshold": f"{float(candidate_score_threshold or 0.0):.0f}",
            "alpaca_min_route_score": f"{float(alpaca_min_route_score or 0.0):.0f}",
            "hyperliquid_min_route_score": f"{float(hyperliquid_min_route_score or 0.0):.0f}",
            "polymarket_min_confidence_pct": f"{float(polymarket_min_confidence_pct or 0.0):.0f}",
            "consensus_min_score": f"{float(consensus_min_score or 0.0):.0f}",
            "consensus_min_ratio_bin": _ratio_bin(float(consensus_min_ratio or 0.0)),
            "quant_passed": quant_passed_val,
            "quant_ev_bin": _ev_bin(float(quant_ev or 0.0)),
        }
        for dim, val in dims.items():
            add_stat(out_t, dim, val, res, p, pp)

    cur.execute("DELETE FROM input_feature_stats")
    now = now_iso()
    rows_written = 0
    for (outcome_type, dim, val), b in sorted(agg.items()):
        n = int(b["n"] or 0)
        wins = int(b["wins"] or 0)
        losses = int(b["losses"] or 0)
        pushes = int(b["pushes"] or 0)
        win_rate = round((wins / n) * 100.0, 2) if n else 0.0
        avg_pnl = round((float(b["sum_pnl"]) / n), 6) if n else 0.0
        avg_pnl_pct = round((float(b["sum_pnl_pct"]) / n), 6) if n else 0.0
        cur.execute(
            """
            INSERT INTO input_feature_stats
            (computed_at, outcome_type, dimension, dimension_value, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, outcome_type, dim, val, n, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_pct),
        )
        rows_written += 1
    conn.commit()
    return rows_written


def clean_legacy_placeholder_outcomes(conn: sqlite3.Connection) -> int:
    """
    Remove old placeholder 'closed' outcomes that were inserted with zero PnL.
    These should be replaced by true realized PnL from trades when available.
    """
    if not table_exists(conn, "route_outcomes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM route_outcomes
        WHERE outcome_type='realized'
          AND ABS(COALESCE(pnl, 0)) < 0.000001
          AND ABS(COALESCE(pnl_percent, 0)) < 0.000001
          AND lower(COALESCE(notes,'')) LIKE 'route_link_closed:%'
        """
    )
    deleted = int(cur.rowcount or 0)
    conn.commit()
    return deleted


def resolve_route_outcomes(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "signal_routes"):
        return 0

    cur = conn.cursor()
    inserted = 0

    # 0) Realized outcomes from closed trades (best signal quality).
    if table_exists(conn, "trades"):
        cur.execute(
            """
            SELECT r.id, r.ticker, COALESCE(r.source_tag, 'internal'), r.routed_at
            FROM signal_routes r
            LEFT JOIN route_outcomes o ON o.route_id = r.id
            WHERE r.status='executed'
              AND r.decision='approved'
              AND (o.route_id IS NULL OR o.outcome_type='operational')
            ORDER BY r.id DESC
            LIMIT 300
            """
        )
        routes = cur.fetchall()
        for route_id, ticker, source_tag, routed_at in routes:
            # Deterministic route linkage if trades row carries route_id.
            if column_exists(conn, "trades", "route_id"):
                cur.execute(
                    """
                    SELECT COALESCE(pnl, 0), COALESCE(pnl_percent, 0), COALESCE(exit_date, created_at, ?)
                    FROM trades
                    WHERE route_id = ?
                      AND (COALESCE(status,'') IN ('closed','done','sold') OR COALESCE(exit_date,'') <> '')
                    ORDER BY datetime(COALESCE(exit_date, created_at, ?)) DESC
                    LIMIT 1
                    """,
                    (now_iso(), int(route_id), now_iso()),
                )
                by_route = cur.fetchone()
                if by_route:
                    pnl = float(by_route[0] or 0.0)
                    pnl_percent = float(by_route[1] or 0.0)
                    resolved_at = str(by_route[2] or now_iso())
                    if pnl > 0:
                        resolution = "win"
                    elif pnl < 0:
                        resolution = "loss"
                    else:
                        resolution = "push"
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO route_outcomes
                        (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(route_id),
                            ticker,
                            source_tag,
                            "realized",
                            resolution,
                            pnl,
                            pnl_percent,
                            resolved_at,
                            f"linked from trades.route_id; routed_at={routed_at}",
                        ),
                    )
                    inserted += 1
                    continue

            cur.execute(
                """
                SELECT COALESCE(pnl, 0), COALESCE(pnl_percent, 0), COALESCE(exit_date, created_at, ?)
                FROM trades
                WHERE upper(COALESCE(ticker,'')) = upper(?)
                  AND (COALESCE(status,'') IN ('closed','done','sold') OR COALESCE(exit_date,'') <> '')
                  AND datetime(COALESCE(exit_date, created_at, ?)) >= datetime(COALESCE(?, '1970-01-01'))
                  AND datetime(COALESCE(exit_date, created_at, ?)) <= datetime(COALESCE(?, '1970-01-01'), '+7 day')
                ORDER BY ABS(julianday(datetime(COALESCE(exit_date, created_at, ?))) - julianday(datetime(COALESCE(?, '1970-01-01')))) ASC
                LIMIT 1
                """,
                (now_iso(), ticker, now_iso(), routed_at, now_iso(), routed_at, now_iso(), routed_at),
            )
            row = cur.fetchone()
            if not row:
                continue

            pnl = float(row[0] or 0.0)
            pnl_percent = float(row[1] or 0.0)
            resolved_at = str(row[2] or now_iso())
            if pnl > 0:
                resolution = "win"
            elif pnl < 0:
                resolution = "loss"
            else:
                resolution = "push"

            cur.execute(
                """
                INSERT OR REPLACE INTO route_outcomes
                (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(route_id),
                    ticker,
                    source_tag,
                    "realized",
                    resolution,
                    pnl,
                    pnl_percent,
                    resolved_at,
                    f"linked from trades table; routed_at={routed_at}",
                ),
            )
            inserted += 1

    # 1) Operational failures from deterministic route links.
    if table_exists(conn, "route_trade_links"):
        cur.execute(
            """
            SELECT l.route_id, l.ticker, COALESCE(r.source_tag,'internal'), l.state, l.entry_status, COALESCE(l.notes,'')
            FROM route_trade_links l
            LEFT JOIN route_outcomes o ON o.route_id = l.route_id
            LEFT JOIN signal_routes r ON r.id = l.route_id
            WHERE o.route_id IS NULL
              AND lower(COALESCE(l.state,'')) IN ('failed')
            ORDER BY l.route_id DESC
            LIMIT 500
            """
        )
        for route_id, ticker, source_tag, state, entry_status, notes in cur.fetchall():
            penalty = _operational_pnl_penalty(conn, int(route_id))
            cur.execute(
                """
                INSERT OR REPLACE INTO route_outcomes
                (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(route_id),
                    ticker,
                    source_tag,
                    "operational",
                    "loss",
                    penalty,
                    -0.25,
                    now_iso(),
                    f"route_link_{state}:{entry_status}; {notes[:140]}",
                ),
            )
            inserted += 1

    # 2) Operational failures from blocked/rejected execution (learn from mistakes immediately).
    if table_exists(conn, "execution_learning"):
        cur.execute(
            """
            SELECT el.route_id, el.ticker, COALESCE(el.source_tag,'internal'), el.order_status, COALESCE(el.reason,'')
            FROM execution_learning el
            LEFT JOIN route_outcomes o ON o.route_id = el.route_id
            WHERE o.route_id IS NULL
              AND lower(COALESCE(el.order_status,'')) IN ('blocked','rejected','canceled','expired','stopped')
            ORDER BY el.id DESC
            LIMIT 300
            """
        )
        for route_id, ticker, source_tag, order_status, reason in cur.fetchall():
            # Operational misses get a small negative score to down-rank noisy sources over time.
            penalty = _operational_pnl_penalty(conn, int(route_id))
            cur.execute(
                """
                INSERT OR REPLACE INTO route_outcomes
                (route_id, ticker, source_tag, outcome_type, resolution, pnl, pnl_percent, resolved_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(route_id),
                    ticker,
                    source_tag,
                    "operational",
                    "loss",
                    penalty,
                    -0.25,
                    now_iso(),
                    f"operational_{order_status}: {reason[:180]}",
                ),
            )
            inserted += 1

    conn.commit()
    return inserted


def refresh_source_learning(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "route_outcomes"):
        return 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT source_tag,
               COUNT(*) AS n,
               SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN resolution='loss' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN resolution='push' THEN 1 ELSE 0 END) AS pushes,
               AVG(pnl) AS avg_pnl,
               AVG(pnl_percent) AS avg_pnl_percent
        FROM route_outcomes
        GROUP BY source_tag
        """
    )
    rows = cur.fetchall()

    cur.execute("DELETE FROM source_learning_stats")
    for source_tag, n, wins, losses, pushes, avg_pnl, avg_pnl_percent in rows:
        n = int(n or 0)
        wins = int(wins or 0)
        losses = int(losses or 0)
        pushes = int(pushes or 0)
        win_rate = round((wins / n) * 100.0, 2) if n else 0.0
        cur.execute(
            """
            INSERT INTO source_learning_stats
            (computed_at, source_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                source_tag,
                n,
                wins,
                losses,
                pushes,
                win_rate,
                round(float(avg_pnl or 0.0), 4),
                round(float(avg_pnl_percent or 0.0), 4),
            ),
        )
    conn.commit()
    return len(rows)


def refresh_strategy_learning(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "route_outcomes") or not table_exists(conn, "signal_routes"):
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(r.source_tag, o.source_tag, 'UNSPECIFIED') AS tag,
               COUNT(*) AS n,
               SUM(CASE WHEN o.resolution='win' THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN o.resolution='loss' THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN o.resolution='push' THEN 1 ELSE 0 END) AS pushes,
               AVG(o.pnl) AS avg_pnl,
               AVG(o.pnl_percent) AS avg_pnl_percent
        FROM route_outcomes o
        LEFT JOIN signal_routes r ON r.id = o.route_id
        GROUP BY tag
        """
    )
    raw_rows = cur.fetchall()
    rolled = {}
    for tag, n, wins, losses, pushes, avg_pnl, avg_pnl_percent in raw_rows:
        key = strategy_for(str(tag or ""))
        bucket = rolled.get(
            key,
            {"n": 0, "wins": 0, "losses": 0, "pushes": 0, "sum_pnl": 0.0, "sum_pnl_pct": 0.0},
        )
        ni = int(n or 0)
        bucket["n"] += ni
        bucket["wins"] += int(wins or 0)
        bucket["losses"] += int(losses or 0)
        bucket["pushes"] += int(pushes or 0)
        bucket["sum_pnl"] += float(avg_pnl or 0.0) * ni
        bucket["sum_pnl_pct"] += float(avg_pnl_percent or 0.0) * ni
        rolled[key] = bucket

    cur.execute("DELETE FROM strategy_learning_stats")
    for strategy_tag, bucket in sorted(rolled.items()):
        n = int(bucket["n"] or 0)
        wins = int(bucket["wins"] or 0)
        losses = int(bucket["losses"] or 0)
        pushes = int(bucket["pushes"] or 0)
        win_rate = round((wins / n) * 100.0, 2) if n else 0.0
        avg_pnl = (bucket["sum_pnl"] / n) if n else 0.0
        avg_pnl_percent = (bucket["sum_pnl_pct"] / n) if n else 0.0
        cur.execute(
            """
            INSERT INTO strategy_learning_stats
            (computed_at, strategy_tag, sample_size, wins, losses, pushes, win_rate, avg_pnl, avg_pnl_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                strategy_tag,
                n,
                wins,
                losses,
                pushes,
                win_rate,
                round(float(avg_pnl or 0.0), 4),
                round(float(avg_pnl_percent or 0.0), 4),
            ),
        )
    conn.commit()
    return len(rolled)


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        ensure_tables(conn)
        cleaned = clean_legacy_placeholder_outcomes(conn)
        backfilled = backfill_route_links(conn)
        features = snapshot_route_features(conn)
        resolved = resolve_route_outcomes(conn)
        mtm_resolved = resolve_mark_to_market_outcomes(conn)
        missed_enabled = False
        if table_exists(conn, "execution_controls"):
            c = conn.cursor()
            c.execute("SELECT value FROM execution_controls WHERE key='missed_opportunity_resolver_enabled' LIMIT 1")
            rw = c.fetchone()
            missed_enabled = bool(rw and str(rw[0]) == "1")
        missed_resolved = resolve_not_taken_opportunities(conn) if missed_enabled else 0
        op_backfilled = backfill_operational_pnl(conn)
        sources = refresh_source_learning(conn)
        strategies = refresh_strategy_learning(conn)
        feature_stats = refresh_input_feature_stats(conn)
        print(
            f"Learning feedback: cleaned {cleaned} placeholders, backfilled {backfilled} route links, "
            f"snapshotted {features} route feature rows, resolved {resolved} new route outcomes, "
            f"mtm_resolved {mtm_resolved}, missed_resolved {missed_resolved} (enabled={int(missed_enabled)}), operational pnl backfilled {op_backfilled}, refreshed {sources} source stats, "
            f"{strategies} strategy stats, {feature_stats} feature stats"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
