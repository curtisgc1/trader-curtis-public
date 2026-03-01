#!/usr/bin/env python3
"""
Route top trade candidates through execution_guard into a queue table.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from execution_guard import evaluate_candidate, init_controls, log_risk_event
from execution_adapters import is_hl_eligible
from market_regime_cloud import get_regime
from quant_gate import evaluate_quant_candidate, ensure_tables as ensure_quant_tables
from kelly_signal import _get_win_prob, _get_payout, kelly_formula
from allocator_causal import (
    ensure_tables as ensure_allocator_tables,
    allocate_candidate,
    log_allocator_decision,
)

DB_PATH = Path(__file__).parent / "data" / "trades.db"
HIGH_BETA_TICKERS = {
    "TSLA", "NVDA", "PLTR", "MSTR", "COIN", "MARA", "RIOT", "ASTS", "SMCI",
    "SOFI", "AFRM", "UPST", "HOOD", "RIVN", "NIO", "TQQQ", "SQQQ", "BTAL",
    "BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def ensure_route_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_routes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          routed_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          score REAL NOT NULL,
          source_tag TEXT NOT NULL,
          proposed_notional REAL NOT NULL,
          mode TEXT NOT NULL,
          validation_id INTEGER NOT NULL DEFAULT 0,
          decision TEXT NOT NULL,
          reason TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued'
        )
        """
    )
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "validation_id"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN validation_id INTEGER NOT NULL DEFAULT 0")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_factor"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_factor REAL NOT NULL DEFAULT 1.0")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_regime"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_regime TEXT NOT NULL DEFAULT 'neutral'")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_reason"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_reason TEXT NOT NULL DEFAULT ''")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "allocator_blocked"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN allocator_blocked INTEGER NOT NULL DEFAULT 0")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "venue_scores_json"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN venue_scores_json TEXT NOT NULL DEFAULT '{}'")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "venue_decisions_json"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN venue_decisions_json TEXT NOT NULL DEFAULT '{}'")
    if _table_exists(conn, "signal_routes") and not _column_exists(conn, "signal_routes", "preferred_venue"):
        conn.execute("ALTER TABLE signal_routes ADD COLUMN preferred_venue TEXT NOT NULL DEFAULT ''")
    conn.commit()


def ensure_venue_matrix(conn: sqlite3.Connection) -> None:
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
    controls = {}
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
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (venue, int(enabled), float(min_score), float(max_notional), mode, now_iso()),
        )
    conn.commit()


def _load_venue_matrix(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    ensure_venue_matrix(conn)
    cur = conn.cursor()
    cur.execute("SELECT venue, enabled, min_score, max_notional, mode FROM venue_matrix")
    out: Dict[str, Dict[str, float]] = {}
    for venue, enabled, min_score, max_notional, mode in cur.fetchall():
        out[str(venue)] = {
            "enabled": int(enabled or 0),
            "min_score": float(min_score or 60.0),
            "max_notional": float(max_notional or 100.0),
            "mode": str(mode or "paper"),
        }
    return out


def ensure_ticker_trade_profiles(conn: sqlite3.Connection) -> None:
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


def _load_json_str_list(raw: str, lower: bool = False) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: List[str] = []
    for item in data:
        v = str(item or "").strip()
        if not v:
            continue
        out.append(v.lower() if lower else v)
    return out


def load_ticker_trade_profiles(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    ensure_ticker_trade_profiles(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT UPPER(COALESCE(ticker,'')),
               COALESCE(active,1),
               LOWER(COALESCE(preferred_venue,'')),
               COALESCE(allowed_venues_json,'[]'),
               COALESCE(required_inputs_json,'[]'),
               COALESCE(min_score,0),
               COALESCE(notional_override,0),
               COALESCE(notes,'')
        FROM ticker_trade_profiles
        WHERE COALESCE(active,1)=1
        """
    )
    out: Dict[str, Dict[str, Any]] = {}
    for ticker, active, preferred, allowed_json, required_json, min_score, notional_override, notes in cur.fetchall():
        t = str(ticker or "").strip().upper()
        if not t or int(active or 0) != 1:
            continue
        allowed = set(_load_json_str_list(str(allowed_json), lower=True))
        allowed = {v for v in allowed if v in {"stocks", "crypto", "prediction"}}
        if not allowed:
            allowed = {"stocks", "crypto", "prediction"}
        required = [v.lower() for v in _load_json_str_list(str(required_json), lower=True) if v]
        pref = str(preferred or "").strip().lower()
        if pref not in {"", "stocks", "crypto", "prediction"}:
            pref = ""
        out[t] = {
            "allowed_venues": allowed,
            "preferred_venue": pref,
            "required_inputs": required,
            "min_score": float(min_score or 0.0),
            "notional_override": float(notional_override or 0.0),
            "notes": str(notes or "").strip(),
        }
    return out


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _is_prediction_source(source_tag: str, ticker: str) -> bool:
    s = str(source_tag or "").upper()
    t = str(ticker or "").upper()
    if s.startswith("POLY_") or "POLY" in s:
        return True
    if any(x in s for x in ("WEATHER", "EVENT", "BOOKMARK")):
        return True
    return t in {"BTC", "ETH", "SOL"} and "EVENT" in s


def _compute_venue_scores(base_score: float, ticker: str, source_tag: str) -> Dict[str, float]:
    t = str(ticker or "").upper()
    s = str(source_tag or "")
    is_crypto = is_hl_eligible(t)
    is_pred = _is_prediction_source(s, t)
    return {
        "stocks": _clamp(base_score + (4.0 if not is_crypto else -22.0)),
        "crypto": _clamp(base_score + (6.0 if is_crypto else -28.0)),
        "prediction": _clamp(base_score + (6.0 if is_pred else -18.0)),
    }


def _seed_regime_ticker_profiles(conn: sqlite3.Connection) -> None:
    """Seed ticker_trade_profiles for TQQQ and BTAL (ON CONFLICT DO NOTHING)."""
    ensure_ticker_trade_profiles(conn)
    for ticker in ("TQQQ", "BTAL"):
        conn.execute(
            """
            INSERT INTO ticker_trade_profiles
            (created_at, updated_at, ticker, active, preferred_venue,
             allowed_venues_json, required_inputs_json, min_score, notional_override, notes)
            VALUES (datetime('now'), datetime('now'), ?, 1, 'stocks',
                    '["stocks"]', '[]', 55.0, 0.0, 'VIX regime strategy')
            ON CONFLICT(ticker) DO NOTHING
            """,
            (ticker,),
        )
    conn.commit()


def fetch_candidates(conn: sqlite3.Connection, limit: int) -> List[Dict]:
    cur = conn.cursor()
    if _table_exists(conn, "trade_candidates"):
        enforce_consensus = False
        if _table_exists(conn, "execution_controls"):
            cur.execute("SELECT value FROM execution_controls WHERE key='consensus_enforce' LIMIT 1")
            row = cur.fetchone()
            enforce_consensus = bool(row and str(row[0]) == "1")
        where = "WHERE consensus_flag=1" if enforce_consensus else ""
        cur.execute(
            """
            SELECT ticker, direction, score, source_tag, COALESCE(consensus_flag,0),
                   COALESCE(rationale,''), COALESCE(input_breakdown_json,'[]')
            FROM trade_candidates
            """ + where + """
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "ticker": row[0],
                "direction": row[1] or "unknown",
                "score": float(row[2] or 0.0),
                "source": row[3] or "internal",
                "consensus_flag": int(row[4] or 0),
                "rationale": str(row[5] or ""),
                "input_breakdown_json": str(row[6] or "[]"),
            }
            for row in rows
        ]
    return []


def _extract_candidate_input_keys(input_breakdown_json: str) -> Set[str]:
    text = str(input_breakdown_json or "").strip()
    if not text:
        return set()
    try:
        arr = json.loads(text)
    except Exception:
        return set()
    if not isinstance(arr, list):
        return set()
    out: Set[str] = set()
    for item in arr:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        if not key:
            continue
        try:
            val = float(item.get("value", 0.0) or 0.0)
        except Exception:
            val = 0.0
        if val > 0.0:
            out.add(key)
    return out


def clear_old_queue(conn: sqlite3.Connection, mode: str) -> None:
    conn.execute("DELETE FROM signal_routes WHERE status='queued' AND mode=?", (mode,))
    conn.commit()


def _is_high_beta_ticker(conn: sqlite3.Connection, ticker: str, min_beta: float) -> bool:
    t = str(ticker or "").upper().strip()
    if not t:
        return False
    if t in HIGH_BETA_TICKERS:
        return True
    # Optional dynamic table support if user backfills with measured betas.
    if _table_exists(conn, "ticker_beta_snapshot"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(beta_1y, 0), COALESCE(beta_6m, 0)
            FROM ticker_beta_snapshot
            WHERE UPPER(ticker)=?
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (t,),
        )
        row = cur.fetchone()
        if row:
            b1 = float(row[0] or 0.0)
            b6 = float(row[1] or 0.0)
            return max(b1, b6) >= float(min_beta)
    return False


def route_signals(limit: int, mode: str, default_notional: float) -> int:
    conn = _connect()
    try:
        init_controls(conn)
        ensure_route_table(conn)
        ensure_venue_matrix(conn)
        ensure_ticker_trade_profiles(conn)
        _seed_regime_ticker_profiles(conn)
        ensure_quant_tables(conn)
        ensure_allocator_tables(conn)
        venue_matrix = _load_venue_matrix(conn)
        ticker_profiles = load_ticker_trade_profiles(conn)
        ctl = conn.cursor()
        ctl.execute("SELECT value FROM execution_controls WHERE key='quant_gate_enforce' LIMIT 1")
        row = ctl.fetchone()
        quant_gate_enforce = False if (row and str(row[0]) == "0") else True
        ctl.execute("SELECT value FROM execution_controls WHERE key='high_beta_only' LIMIT 1")
        row_beta = ctl.fetchone()
        high_beta_only = False if (row_beta and str(row_beta[0]) == "0") else True
        ctl.execute("SELECT value FROM execution_controls WHERE key='high_beta_min_beta' LIMIT 1")
        row_minb = ctl.fetchone()
        min_beta = float((row_minb[0] if row_minb else 1.5) or 1.5)
        ctl.execute("SELECT value FROM execution_controls WHERE key='regime_filter_enabled' LIMIT 1")
        row_rf = ctl.fetchone()
        regime_filter_enabled = False if (row_rf and str(row_rf[0]) == "0") else True
        ctl.execute("SELECT value FROM execution_controls WHERE key='regime_filter_stale_hours' LIMIT 1")
        row_rs = ctl.fetchone()
        regime_stale_hours = float((row_rs[0] if row_rs else 26) or 26)
        candidates = fetch_candidates(conn, limit=limit)
        clear_old_queue(conn, mode=mode)

        routed = 0
        approved = 0
        cur = conn.cursor()
        for c in candidates:
            ticker = (c.get("ticker") or "").upper()
            direction = c.get("direction") or "unknown"
            score = float(c.get("score") or 0.0)
            source = c.get("source") or "internal"
            candidate_rationale = str(c.get("rationale") or "")
            candidate_input_keys = _extract_candidate_input_keys(str(c.get("input_breakdown_json") or "[]"))
            notional = float(default_notional)
            profile = ticker_profiles.get(ticker, None)

            if high_beta_only and (not _is_high_beta_ticker(conn, ticker, min_beta)):
                reason = f"high_beta_only_filter: {ticker} below required beta profile"
                cur.execute(
                    """
                    INSERT INTO signal_routes
                    (routed_at, ticker, direction, score, source_tag, proposed_notional, mode, validation_id, decision, reason, status,
                     allocator_factor, allocator_regime, allocator_reason, allocator_blocked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso(),
                        ticker,
                        direction,
                        score,
                        source,
                        notional,
                        mode,
                        0,
                        "rejected",
                        reason[:260],
                        "blocked",
                        1.0,
                        "high_beta",
                        "pre-allocator high-beta gate",
                        1,
                    ),
                )
                log_risk_event(
                    conn=conn,
                    ticker=ticker,
                    direction=direction,
                    candidate_score=score,
                    proposed_notional=notional,
                    approved=False,
                    reason=reason,
                )
                routed += 1
                continue

            # ── Regime filter: Ripster 34/50 EMA cloud gate ──
            if regime_filter_enabled:
                ac = "crypto" if is_hl_eligible(ticker) else "stocks"
                regime = get_regime(conn, ac, stale_hours=regime_stale_hours)
                if regime:
                    blocked_by_regime = False
                    if regime["trend"] == "bearish" and direction == "long":
                        blocked_by_regime = True
                    elif regime["trend"] == "bullish" and direction == "short":
                        blocked_by_regime = True
                    if blocked_by_regime:
                        reason = (
                            f"regime_filter:{ac}_{regime['trend']}_blocks_{direction} "
                            f"(EMA34={regime['ema_fast']:.2f} "
                            f"{'<' if regime['trend'] == 'bearish' else '>'} "
                            f"EMA50={regime['ema_slow']:.2f})"
                        )
                        cur.execute(
                            """
                            INSERT INTO signal_routes
                            (routed_at, ticker, direction, score, source_tag, proposed_notional, mode, validation_id, decision, reason, status,
                             allocator_factor, allocator_regime, allocator_reason, allocator_blocked)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                now_iso(), ticker, direction, score, source, notional, mode,
                                0, "rejected", reason[:260], "blocked",
                                1.0, "regime", "pre-allocator regime gate", 1,
                            ),
                        )
                        log_risk_event(
                            conn=conn, ticker=ticker, direction=direction,
                            candidate_score=score, proposed_notional=notional,
                            approved=False, reason=reason,
                        )
                        routed += 1
                        continue

            alloc = allocate_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                candidate_score=score,
                proposed_notional=notional,
            )
            log_allocator_decision(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                result=alloc,
                base_score=score,
                base_notional=notional,
            )

            score_adj = float(alloc.adjusted_score)
            notional_adj = float(alloc.adjusted_notional)

            # Kelly sizing: scale notional by fractional Kelly if data exists
            _kelly_ctl = conn.execute(
                "SELECT value FROM execution_controls WHERE key='kelly_scale_routing' LIMIT 1"
            ).fetchone()
            kelly_scale_enabled = str(_kelly_ctl[0]) == "1" if _kelly_ctl else True
            kelly_fraction_applied = 1.0
            if kelly_scale_enabled:
                try:
                    win_prob, k_n = _get_win_prob(conn, source, ticker, direction)
                    if k_n >= 3 and win_prob > 0.0:
                        payout_map = {}  # Lightweight: use default payout
                        avg_win, avg_loss, _ = _get_payout(payout_map, source, 24)
                        b = avg_win / max(abs(avg_loss), 0.01) if avg_loss != 0 else 1.5
                        fk = kelly_formula(win_prob, b)
                        if fk > 0:
                            # Quarter-Kelly cap: never bet more than 25% of full Kelly
                            kelly_fraction_applied = min(fk * 0.25, 1.0)
                            notional_adj = round(notional_adj * kelly_fraction_applied, 2)
                except Exception:
                    pass  # Non-fatal: fall through to allocator notional

            q_ok, q_reason, q_metrics = evaluate_quant_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                source_tag=source,
                candidate_score=score_adj,
            )
            ok, reason = evaluate_candidate(
                conn=conn,
                ticker=ticker,
                direction=direction,
                candidate_score=score_adj,
                proposed_notional=notional_adj,
                mode=mode,
            )
            allocator_blocked = 0
            profile_notes: List[str] = []
            if not alloc.allowed:
                ok = False
                allocator_blocked = 1
                reason = alloc.reason
            if ok and not q_ok:
                if quant_gate_enforce:
                    ok = False
                    reason = f"quant_gate_failed: {q_reason}"
                else:
                    reason = f"quant_gate_warn_only: {q_reason}"
            if profile:
                p_min_score = float(profile.get("min_score", 0.0) or 0.0)
                if p_min_score > 0 and score_adj < p_min_score:
                    profile_notes.append(f"profile_min_score_failed:{score_adj:.2f}<{p_min_score:.2f}")
                if ok and p_min_score > 0 and score_adj < p_min_score:
                    ok = False
                    reason = f"ticker_profile_min_score_failed: {score_adj:.2f} < {p_min_score:.2f}"
                required_inputs = [str(x).strip().lower() for x in (profile.get("required_inputs") or []) if str(x).strip()]
                missing_inputs = [k for k in required_inputs if k not in candidate_input_keys]
                if missing_inputs:
                    missing_str = ",".join(missing_inputs[:5])
                    profile_notes.append(f"profile_missing_inputs:{missing_str}")
                if ok and missing_inputs:
                    ok = False
                    reason = f"ticker_profile_missing_inputs: {missing_str}"
            reason_full = f"{reason} | allocator={alloc.reason}"
            if profile_notes:
                reason_full = f"{reason_full} | {';'.join(profile_notes)}"
            if candidate_rationale:
                reason_full = f"{reason_full} | inputs={candidate_rationale[:120]}"
            venue_scores = _compute_venue_scores(score_adj, ticker, source)
            venue_decisions: Dict[str, Dict[str, object]] = {}
            best_venue = ""
            best_margin = -1e9
            allowed_venues = {"stocks", "crypto", "prediction"}
            preferred_venue_profile = ""
            if profile:
                allowed_venues = set(profile.get("allowed_venues") or allowed_venues)
                preferred_venue_profile = str(profile.get("preferred_venue") or "").strip().lower()
            for venue_name in ("stocks", "crypto", "prediction"):
                cfg = venue_matrix.get(venue_name, {"enabled": 0, "min_score": 60.0, "max_notional": 100.0, "mode": "paper"})
                v_score = float(venue_scores.get(venue_name, 0.0))
                enabled = int(cfg.get("enabled", 0)) == 1 and venue_name in allowed_venues
                min_score = float(cfg.get("min_score", 60.0))
                approved_v = enabled and (v_score >= min_score)
                margin = v_score - min_score
                venue_decisions[venue_name] = {
                    "enabled": enabled,
                    "score": round(v_score, 2),
                    "min_score": round(min_score, 2),
                    "approved": approved_v,
                    "margin": round(margin, 2),
                }
                if approved_v and margin > best_margin:
                    best_margin = margin
                    best_venue = venue_name

            if ok and preferred_venue_profile:
                pref_decision = venue_decisions.get(preferred_venue_profile, {})
                if bool(pref_decision.get("approved")):
                    best_venue = preferred_venue_profile
                else:
                    ok = False
                    reason_full = f"{reason_full} | ticker_profile_preferred_venue_unavailable:{preferred_venue_profile}"
            if ok and not best_venue:
                ok = False
                reason_full = f"{reason_full} | no venue passed matrix thresholds"
            if ok and best_venue == "prediction":
                # Prediction execution runs through execution_polymarket candidate lane.
                ok = False
                reason_full = f"{reason_full} | prediction venue routed to polymarket pipeline"

            if ok and best_venue:
                cfg = venue_matrix.get(best_venue, {})
                cap = float(cfg.get("max_notional", notional_adj))
                notional_adj = min(notional_adj, cap)
            if ok and profile:
                p_notional = float(profile.get("notional_override", 0.0) or 0.0)
                if p_notional > 0.0:
                    notional_adj = min(notional_adj, p_notional)

            decision = "approved" if ok else "rejected"
            status = "queued" if ok else "blocked"
            if ok:
                approved += 1
            routed += 1

            cur.execute(
                """
                INSERT INTO signal_routes
                (routed_at, ticker, direction, score, source_tag, proposed_notional, mode, validation_id, decision, reason, status,
                 allocator_factor, allocator_regime, allocator_reason, allocator_blocked, venue_scores_json, venue_decisions_json, preferred_venue)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    ticker,
                    direction,
                    score_adj,
                    source,
                    notional_adj,
                    mode,
                    int(q_metrics.get("validation_id") or 0),
                    decision,
                    reason_full[:260],
                    status,
                    float(alloc.factor),
                    alloc.regime,
                    alloc.reason[:260],
                    int(allocator_blocked),
                    json.dumps(venue_scores, separators=(",", ":"), ensure_ascii=True),
                    json.dumps(venue_decisions, separators=(",", ":"), ensure_ascii=True),
                    best_venue,
                ),
            )
            log_risk_event(
                conn=conn,
                ticker=ticker,
                direction=direction,
                candidate_score=score_adj,
                proposed_notional=notional_adj,
                approved=ok,
                reason=reason_full,
            )

        conn.commit()
        print(f"Routed {routed} candidates ({approved} approved, {routed - approved} blocked) in {mode} mode")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Route trade candidates through risk controls.")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--notional", type=float, default=100.0)
    args = parser.parse_args()
    return route_signals(limit=args.limit, mode=args.mode, default_notional=args.notional)


if __name__ == "__main__":
    raise SystemExit(main())
