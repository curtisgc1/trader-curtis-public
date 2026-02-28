#!/usr/bin/env python3
"""
Build normalized trade candidates from all signal inputs with configurable weights.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from training_mode import apply_training_mode

DB_PATH = Path(__file__).parent / "data" / "trades.db"

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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def ensure_input_source_controls(conn: sqlite3.Connection) -> None:
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


def seed_input_source_controls(conn: sqlite3.Connection) -> None:
    ensure_input_source_controls(conn)
    seeds = [
        ("family:social", "Social Sentiment", "family"),
        ("family:pattern", "Pattern Quality", "family"),
        ("family:external", "External Signals", "family"),
        ("family:copy", "Copy Signals", "family"),
        ("family:pipeline", "Pipeline Signals", "family"),
        ("family:liquidity", "Liquidity Map", "family"),
        ("family:kyle_williams", "Kyle Williams Setup", "family"),
        ("family:momentum", "Momentum Rank", "family"),
        ("family:event_alpha", "Event Alpha (Macro/Geo)", "family"),
        ("family:vix_regime", "VIX Regime Switch (TQQQ/BTAL)", "family"),
        ("family:dapo_agent", "DAPO RL Agent", "family"),
    ]
    for key, label, klass in seeds:
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

    # Phase 8: Seed noisy sources as disabled by default.
    # Uses DO NOTHING so user overrides are preserved.
    noise_seeds = [
        ("source:stocktwits", "Source stocktwits", "source_tag"),
        ("source:reddit", "Source reddit", "source_tag"),
        ("pipeline:D_BOOKMARKS", "Pipeline D_BOOKMARKS", "pipeline"),
        ("pipeline:E_BREAKTHROUGH", "Pipeline E_BREAKTHROUGH", "pipeline"),
    ]
    for key, label, klass in noise_seeds:
        conn.execute(
            """
            INSERT INTO input_source_controls
            (created_at, updated_at, source_key, source_label, source_class, enabled, manual_weight, auto_weight, notes)
            VALUES (datetime('now'), datetime('now'), ?, ?, ?, 0, 1.0, 1.0, 'noise_default_disabled')
            ON CONFLICT(source_key) DO NOTHING
            """,
            (key, label, klass),
        )

    conn.commit()


def load_input_controls(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    seed_input_source_controls(conn)
    out: Dict[str, Dict[str, float]] = {}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT source_key, enabled, manual_weight, auto_weight
        FROM input_source_controls
        """
    )
    for key, enabled, manual_weight, auto_weight in cur.fetchall():
        m = float(manual_weight or 1.0)
        a = float(auto_weight or 1.0)
        out[str(key)] = {
            "enabled": 1.0 if int(enabled or 0) == 1 else 0.0,
            "manual_weight": max(0.0, m),
            "auto_weight": max(0.1, a),
        }
    return out


def add_seen_control(conn: sqlite3.Connection, key: str, label: str, klass: str) -> None:
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


def weight_for(controls: Dict[str, Dict[str, float]], key: str) -> float:
    c = controls.get(key)
    if not c:
        return 1.0
    if c.get("enabled", 1.0) <= 0.0:
        return 0.0
    return float(c.get("manual_weight", 1.0)) * float(c.get("auto_weight", 1.0))


def load_tracked_sources(conn: sqlite3.Connection) -> dict:
    if not table_exists(conn, "tracked_x_sources"):
        return {}
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tracked_x_sources)")
    cols = {r[1] for r in cur.fetchall()}
    if "x_api_enabled" not in cols:
        conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN x_api_enabled INTEGER NOT NULL DEFAULT 1")
    if "source_weight" not in cols:
        conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN source_weight REAL NOT NULL DEFAULT 1.0")
    conn.commit()
    cur.execute(
        """
        SELECT lower(COALESCE(handle,'')), COALESCE(role_copy,1), COALESCE(role_alpha,1), COALESCE(active,1),
               COALESCE(x_api_enabled,1), COALESCE(source_weight,1.0)
        FROM tracked_x_sources
        WHERE COALESCE(active,1)=1
        """
    )
    out = {}
    for handle, role_copy, role_alpha, active, x_api_enabled, source_weight in cur.fetchall():
        h = str(handle or "").strip().lower()
        if not h:
            continue
        out[h] = {
            "role_copy": int(role_copy or 0) == 1,
            "role_alpha": int(role_alpha or 0) == 1,
            "active": int(active or 0) == 1,
            "x_api_enabled": int(x_api_enabled or 0) == 1,
            "source_weight": float(source_weight or 1.0),
        }
    return out


def ensure_candidates_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          generated_at TEXT,
          ticker TEXT,
          direction TEXT,
          score REAL,
          sentiment_score REAL,
          pattern_type TEXT,
          pattern_score REAL,
          external_confidence REAL,
          source_tag TEXT,
          rationale TEXT
        )
        """
    )
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(trade_candidates)")
    cols = {r[1] for r in cur.fetchall()}
    additions = {
        "confirmations": "INTEGER NOT NULL DEFAULT 0",
        "sources_total": "INTEGER NOT NULL DEFAULT 0",
        "consensus_ratio": "REAL NOT NULL DEFAULT 0",
        "consensus_flag": "INTEGER NOT NULL DEFAULT 0",
        "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
        "input_breakdown_json": "TEXT NOT NULL DEFAULT '[]'",
    }
    for col, spec in additions.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE trade_candidates ADD COLUMN {col} {spec}")
    conn.commit()


def latest_map(cur: sqlite3.Cursor, query: str):
    cur.execute(query)
    out = {}
    for row in cur.fetchall():
        ticker = row[0]
        if ticker not in out:
            out[ticker] = row[1:]
    return out


def contribution(
    controls: Dict[str, Dict[str, float]],
    key: str,
    base_value: float,
    default_weight: float = 1.0,
) -> Tuple[float, float]:
    w = weight_for(controls, key) * float(default_weight)
    return base_value * w, w


def strategy_weight_for(
    controls: Dict[str, Dict[str, float]],
    strategy_tag: str,
    family_key: str,
) -> float:
    tag = str(strategy_tag or "").strip().upper()
    if not tag:
        return 1.0
    key_a = f"strategy:{tag}:{family_key}"
    key_b = f"{family_key}:strategy:{tag}"
    if key_a in controls:
        return weight_for(controls, key_a)
    if key_b in controls:
        return weight_for(controls, key_b)
    return 1.0


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=20000")
    try:
        ensure_candidates_table(conn)
        ensure_input_source_controls(conn)
        cur = conn.cursor()
        tracked_sources = load_tracked_sources(conn)
        controls = {}
        if table_exists(conn, "execution_controls"):
            cur.execute("SELECT key, value FROM execution_controls")
            controls = apply_training_mode({str(k): str(v) for k, v in cur.fetchall()})
        input_controls = load_input_controls(conn)

        min_confirmations = int(float(controls.get("consensus_min_confirmations", "3") or 3))
        min_ratio = float(controls.get("consensus_min_ratio", "0.6") or 0.6)
        min_score = float(controls.get("consensus_min_score", "60") or 60.0)
        liq_boost = float(controls.get("liquidity_high_signal_boost", "0.08") or 0.08)
        liq_min_conf = float(controls.get("liquidity_min_confidence", "0.60") or 0.60)
        liq_min_rr = float(controls.get("liquidity_min_rr", "2.0") or 2.0)
        x_influence_enabled = str(controls.get("x_influence_enabled", "1")).strip() == "1"

        # Direction consensus config (Phase 7)
        direction_consensus_enabled = str(controls.get("direction_consensus_enabled", "1")).strip() == "1"
        min_direction_agreement = float(controls.get("min_direction_agreement", "0.6") or 0.6)

        # Premium Gate config (loaded once, applied per ticker)
        # Defaults: off (0) — enabled by user via dashboard checkboxes
        pg_stocks_min = int(float(controls.get("premium_gate_stocks_min", "0") or 0))
        pg_crypto_min = int(float(controls.get("premium_gate_crypto_min", "0") or 0))
        # Which of the 3 premium signals participate per asset class
        pg_kw_stocks  = str(controls.get("premium_gate_kw_stocks",  "1")).strip() == "1"
        pg_kw_crypto  = str(controls.get("premium_gate_kw_crypto",  "0")).strip() == "1"
        pg_liq_stocks = str(controls.get("premium_gate_liq_stocks", "1")).strip() == "1"
        pg_liq_crypto = str(controls.get("premium_gate_liq_crypto", "1")).strip() == "1"
        pg_mom_stocks = str(controls.get("premium_gate_mom_stocks", "1")).strip() == "1"
        pg_mom_crypto = str(controls.get("premium_gate_mom_crypto", "1")).strip() == "1"

        sentiment = {}
        if table_exists(conn, "unified_social_sentiment"):
            sentiment = latest_map(
                cur,
                """
                SELECT ticker, overall_score, timestamp
                FROM unified_social_sentiment
                ORDER BY timestamp DESC
                """,
            )

        patterns = {}
        if table_exists(conn, "institutional_patterns"):
            patterns = latest_map(
                cur,
                """
                SELECT ticker, pattern_type, direction, timestamp
                FROM institutional_patterns
                ORDER BY timestamp DESC
                """,
            )

        external = {}
        if table_exists(conn, "external_signals"):
            external = latest_map(
                cur,
                """
                SELECT ticker, source, direction, confidence, created_at
                FROM external_signals
                WHERE status IN ('new', 'active')
                ORDER BY created_at DESC
                """,
            )

        copy_signals = {}
        if table_exists(conn, "copy_trades"):
            copy_signals = latest_map(
                cur,
                """
                SELECT ticker, source_handle, call_type, call_timestamp
                FROM copy_trades
                WHERE status IN ('OPEN', 'PENDING')
                ORDER BY call_timestamp DESC
                """,
            )

        pipeline_signals = {}
        kyle_williams_signals = {}
        event_alpha_signals = {}
        vix_regime_signals = {}
        if table_exists(conn, "pipeline_signals"):
            # Exclude:
            #   CHART_LIQUIDITY — already captured by family:liquidity
            #   KYLE_WILLIAMS   — has its own family below
            #   B_LONGTERM      — redundant with family:social + family:copy (same X handles + innovation watchlist)
            #   E_BREAKTHROUGH  — redundant with family:external (same Google News RSS → keyword → ticker lists)
            pipeline_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                  AND UPPER(pipeline_id) NOT IN ('CHART_LIQUIDITY', 'KYLE_WILLIAMS', 'B_LONGTERM', 'E_BREAKTHROUGH', 'VIX_REGIME', 'DAPO_AGENT')
                ORDER BY generated_at DESC
                """,
            )
            # Kyle Williams signals — first_red_day_short and similar setups
            kyle_williams_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                  AND UPPER(pipeline_id) = 'KYLE_WILLIAMS'
                ORDER BY generated_at DESC
                """,
            )
            # C_EVENT — unique macro/geo regime signals (tariff shock → SPY, geopolitical → BTC)
            # Promoted to its own family:event_alpha — no other signal covers macro regime risk
            event_alpha_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                  AND UPPER(pipeline_id) = 'C_EVENT'
                ORDER BY generated_at DESC
                """,
            )
            # VIX_REGIME — standalone regime-switching strategy (TQQQ/BTAL)
            # Promoted to its own family:vix_regime — complete standalone systematic strategy
            vix_regime_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                  AND UPPER(pipeline_id) = 'VIX_REGIME'
                ORDER BY generated_at DESC
                """,
            )
            # DAPO_AGENT — RL-based trading agent (Pipeline L)
            # Standalone family with its own weight; gated on checkpoint existence
            dapo_agent_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                  AND UPPER(pipeline_id) = 'DAPO_AGENT'
                ORDER BY generated_at DESC
                """,
            )
            # Clean up stale controls that are no longer generated:
            # - strategy_family cross-products (30+ entries that cluttered the accordion)
            # - pipeline:* entries for excluded/promoted strategies
            # - source:internal / source:unspecified / source:manual-* (default fallback noise, never real signals)
            conn.execute("DELETE FROM input_source_controls WHERE source_class = 'strategy_family'")
            conn.execute(
                "DELETE FROM input_source_controls WHERE source_class = 'pipeline'"
                " AND UPPER(source_key) IN ("
                " 'PIPELINE:B_LONGTERM','PIPELINE:E_BREAKTHROUGH',"
                " 'PIPELINE:CHART_LIQUIDITY','PIPELINE:KYLE_WILLIAMS','PIPELINE:C_EVENT',"
                " 'PIPELINE:UNSPECIFIED'"
                ")"
            )
            conn.execute(
                "DELETE FROM input_source_controls"
                " WHERE source_class = 'source_tag'"
                " AND (LOWER(source_key) IN ('source:internal','source:unspecified')"
                "  OR source_key LIKE 'source:manual-%')"
            )

        chart_liq = {}
        if table_exists(conn, "chart_liquidity_signals"):
            chart_liq = latest_map(
                cur,
                """
                SELECT ticker, pattern, confidence, entry_hint, stop_hint, target_hint, created_at
                FROM chart_liquidity_signals
                WHERE COALESCE(pattern,'') <> 'insufficient_data'
                ORDER BY created_at DESC
                """,
            )

        # Load latest momentum batch (top 100 stocks + top 10 crypto)
        momentum_map: dict = {}
        crypto_tickers: set = set()
        if table_exists(conn, "momentum_signals"):
            cur.execute(
                """
                SELECT ticker, momentum_score, rank, rank_of, asset_class
                FROM momentum_signals
                WHERE batch_ts = (SELECT MAX(batch_ts) FROM momentum_signals)
                """
            )
            for row in cur.fetchall():
                ticker = row[0]
                if ticker not in momentum_map:
                    momentum_map[ticker] = row[1:]
                if str(row[4] or "").lower() == "crypto":
                    crypto_tickers.add(ticker)

        tickers = (
            set(sentiment.keys())
            | set(patterns.keys())
            | set(external.keys())
            | set(copy_signals.keys())
            | set(pipeline_signals.keys())
            | set(kyle_williams_signals.keys())
            | set(event_alpha_signals.keys())
            | set(chart_liq.keys())
            | set(vix_regime_signals.keys())
            # momentum_map intentionally NOT added to tickers — it only boosts
            # existing candidates; doesn't generate candidates on its own
        )
        rows = []

        for ticker in tickers:
            sent_score = float((sentiment.get(ticker) or (50, None))[0] or 50)
            pattern_type = str((patterns.get(ticker) or ("none", "unknown", None))[0] or "none").lower()
            pattern_direction = (patterns.get(ticker) or ("none", "unknown", None))[1] or "unknown"
            pattern_score = float(PATTERN_RELIABILITY.get(pattern_type, 0.50))

            ext_source, ext_direction, ext_conf = "internal", "unknown", 0.50
            if ticker in external:
                ext_source = external[ticker][0] or "external"
                ext_direction = external[ticker][1] or "unknown"
                ext_conf = float(external[ticker][2] or 0.50)

            copy_source, copy_direction = "", "unknown"
            if ticker in copy_signals:
                copy_source = str(copy_signals[ticker][0] or "")
                copy_direction = str(copy_signals[ticker][1] or "unknown")

            pipe_score = 50.0
            pipe_direction = "unknown"
            pipe_source = ""
            if ticker in pipeline_signals:
                pipe_score = float(pipeline_signals[ticker][0] or 50.0)
                pipe_direction = pipeline_signals[ticker][1] or "unknown"
                pipe_source = str(pipeline_signals[ticker][2] or "")

            # Kyle Williams signals (first_red_day_short etc.) — own family
            kw_score = 0.0
            kw_direction = "unknown"
            kw_hit = ticker in kyle_williams_signals
            if kw_hit:
                kw_score = float(kyle_williams_signals[ticker][0] or 0.0)
                kw_direction = kyle_williams_signals[ticker][1] or "unknown"

            # C_EVENT — macro/geo regime signal (own family:event_alpha)
            ea_score = 0.0
            ea_direction = "unknown"
            ea_hit = ticker in event_alpha_signals
            if ea_hit:
                ea_score = float(event_alpha_signals[ticker][0] or 0.0)
                ea_direction = event_alpha_signals[ticker][1] or "unknown"

            # Momentum rank signal
            mom_score = 0.0
            mom_hit = ticker in momentum_map
            if mom_hit:
                mom_score = float(momentum_map[ticker][0] or 0.0)

            liq_hit = False
            liq_pattern = ""
            liq_rr = 0.0
            if ticker in chart_liq:
                liq_pattern = str(chart_liq[ticker][0] or "")
                liq_conf = float(chart_liq[ticker][1] or 0.0)
                liq_entry = float(chart_liq[ticker][2] or 0.0)
                liq_stop = float(chart_liq[ticker][3] or 0.0)
                liq_target = float(chart_liq[ticker][4] or 0.0)
                risk = abs(liq_entry - liq_stop)
                reward = abs(liq_target - liq_entry)
                liq_rr = round((reward / risk), 4) if risk > 0 else 0.0
                liq_hit = (
                    liq_conf >= liq_min_conf
                    and liq_rr >= liq_min_rr
                    and any(k in liq_pattern for k in ["liquidity_grab", "stop_hunt", "fakeout"])
                )

            ext_lower = str(ext_source or "").strip().lower()
            copy_lower = str(copy_source or "").strip().lower()
            pipe_upper = str(pipe_source or "").strip().upper()
            pattern_key = f"pattern:{pattern_type}" if pattern_type and pattern_type != "none" else ""
            # Only register external source key if it's a real source (not the internal default fallback)
            _ext_is_real = ext_lower and ext_lower not in {"internal", "unspecified"} and not ext_lower.startswith("manual-")
            ext_key = f"source:{ext_lower}" if _ext_is_real else ""
            copy_key = f"source:{copy_lower}" if copy_lower else ""
            pipe_key = f"pipeline:{pipe_upper}" if pipe_upper else ""
            x_key = f"x:{ext_lower}" if ext_lower else ""

            if pattern_key:
                add_seen_control(conn, pattern_key, f"Pattern {pattern_type}", "pattern")
            if ext_key:
                add_seen_control(conn, ext_key, f"Source {ext_source}", "source_tag")
            if copy_key:
                add_seen_control(conn, copy_key, f"Source {copy_source}", "source_tag")
            if pipe_key:
                add_seen_control(conn, pipe_key, f"Pipeline {pipe_upper}", "pipeline")
            if x_key and ext_lower in tracked_sources:
                add_seen_control(conn, x_key, f"X @{ext_lower}", "x_account")

            breakdown: List[Dict[str, object]] = []
            c_social, w_social = contribution(input_controls, "family:social", (sent_score / 100.0) * 0.25)
            w_social_strategy = strategy_weight_for(input_controls, pipe_upper, "family:social")
            c_social *= w_social_strategy
            breakdown.append({"key": "family:social", "base": round((sent_score / 100.0) * 0.25, 6), "weight": round(w_social, 6), "value": round(c_social, 6)})

            c_pattern, w_pattern_family = contribution(input_controls, "family:pattern", pattern_score * 0.30)
            w_pattern_specific = weight_for(input_controls, pattern_key) if pattern_key else 1.0
            w_pattern_strategy = strategy_weight_for(input_controls, pipe_upper, "family:pattern")
            c_pattern *= (w_pattern_specific * w_pattern_strategy)
            breakdown.append({"key": "family:pattern", "base": round(pattern_score * 0.30, 6), "weight": round(w_pattern_family * w_pattern_specific * w_pattern_strategy, 6), "value": round(c_pattern, 6)})

            c_external, w_ext_family = contribution(input_controls, "family:external", ext_conf * 0.20)
            w_ext_specific = weight_for(input_controls, ext_key) if ext_key else 1.0
            w_ext_strategy = strategy_weight_for(input_controls, pipe_upper, "family:external")
            c_external *= (w_ext_specific * w_ext_strategy)
            breakdown.append({"key": "family:external", "base": round(ext_conf * 0.20, 6), "weight": round(w_ext_family * w_ext_specific * w_ext_strategy, 6), "value": round(c_external, 6)})

            # Only score pipeline if there's an actual signal — default 50 is noise, not a signal
            c_pipeline = 0.0
            if ticker in pipeline_signals:
                c_pipeline, w_pipe_family = contribution(input_controls, "family:pipeline", (pipe_score / 100.0) * 0.25)
                w_pipe_specific = weight_for(input_controls, pipe_key) if pipe_key else 1.0
                w_pipe_strategy = strategy_weight_for(input_controls, pipe_upper, "family:pipeline")
                c_pipeline *= (w_pipe_specific * w_pipe_strategy)
                breakdown.append({"key": "family:pipeline", "base": round((pipe_score / 100.0) * 0.25, 6), "weight": round(w_pipe_family * w_pipe_specific * w_pipe_strategy, 6), "value": round(c_pipeline, 6)})

            copy_component = 0.0
            if copy_source:
                copy_component = 0.08
                c_copy, w_copy_family = contribution(input_controls, "family:copy", copy_component)
                w_copy_specific = weight_for(input_controls, copy_key) if copy_key else 1.0
                w_copy_strategy = strategy_weight_for(input_controls, pipe_upper, "family:copy")
                c_copy *= (w_copy_specific * w_copy_strategy)
                breakdown.append({"key": "family:copy", "base": round(copy_component, 6), "weight": round(w_copy_family * w_copy_specific * w_copy_strategy, 6), "value": round(c_copy, 6)})
            else:
                c_copy = 0.0

            c_liq = 0.0
            if liq_hit:
                c_liq, w_liq = contribution(input_controls, "family:liquidity", liq_boost)
                w_liq_strategy = strategy_weight_for(input_controls, pipe_upper, "family:liquidity")
                c_liq *= w_liq_strategy
                breakdown.append({"key": "family:liquidity", "base": round(liq_boost, 6), "weight": round(w_liq * w_liq_strategy, 6), "value": round(c_liq, 6)})

            x_component = 0.0
            if x_influence_enabled and ext_lower in tracked_sources:
                src_cfg = tracked_sources.get(ext_lower, {})
                if bool(src_cfg.get("x_api_enabled", True)):
                    x_multiplier = float(src_cfg.get("source_weight", 1.0))
                    w_x = weight_for(input_controls, x_key) * x_multiplier
                    x_component = 0.05 * w_x
                    breakdown.append({"key": x_key, "base": 0.05, "weight": round(w_x, 6), "value": round(x_component, 6)})

            # Kyle Williams setup (first_red_day_short, ext_vs_vwap etc.) — own family
            c_kw = 0.0
            if kw_hit and kw_score > 0:
                c_kw, w_kw = contribution(input_controls, "family:kyle_williams", (kw_score / 100.0) * 0.22)
                breakdown.append({
                    "key": "family:kyle_williams",
                    "base": round((kw_score / 100.0) * 0.22, 6),
                    "weight": round(w_kw, 6),
                    "value": round(c_kw, 6),
                })

            # C_EVENT macro/geo regime — own family:event_alpha (e.g. tariff shock → SPY short)
            c_event_alpha = 0.0
            if ea_hit and ea_score > 0:
                c_event_alpha, w_ea = contribution(input_controls, "family:event_alpha", (ea_score / 100.0) * 0.20)
                breakdown.append({
                    "key": "family:event_alpha",
                    "base": round((ea_score / 100.0) * 0.20, 6),
                    "weight": round(w_ea, 6),
                    "value": round(c_event_alpha, 6),
                })

            # Momentum rank (top 100 stocks / top 10 crypto) — confirmation bonus
            c_mom = 0.0
            if mom_hit and mom_score > 0:
                c_mom, w_mom = contribution(input_controls, "family:momentum", mom_score * 0.12)
                breakdown.append({
                    "key": "family:momentum",
                    "base": round(mom_score * 0.12, 6),
                    "weight": round(w_mom, 6),
                    "value": round(c_mom, 6),
                })

            # VIX regime (TQQQ/BTAL) — standalone systematic strategy, weight 0.85
            # High weight because this strategy generates its own candidates and
            # doesn't need cross-confirmation from social/pattern families
            vr_score = 0.0
            vr_direction = "unknown"
            vr_hit = ticker in vix_regime_signals
            c_vr = 0.0
            if vr_hit:
                vr_score = float(vix_regime_signals[ticker][0] or 0.0)
                vr_direction = vix_regime_signals[ticker][1] or "unknown"
            if vr_hit and vr_score > 0:
                c_vr, w_vr = contribution(input_controls, "family:vix_regime", (vr_score / 100.0) * 0.85)
                breakdown.append({
                    "key": "family:vix_regime",
                    "base": round((vr_score / 100.0) * 0.85, 6),
                    "weight": round(w_vr, 6),
                    "value": round(c_vr, 6),
                })

            # DAPO RL agent — standalone RL-based signal, weight 0.70
            dapo_score = 0.0
            dapo_direction = "unknown"
            dapo_hit = ticker in dapo_agent_signals
            c_dapo = 0.0
            if dapo_hit:
                dapo_score = float(dapo_agent_signals[ticker][0] or 0.0)
                dapo_direction = dapo_agent_signals[ticker][1] or "unknown"
            if dapo_hit and dapo_score > 0:
                c_dapo, w_dapo = contribution(input_controls, "family:dapo_agent", (dapo_score / 100.0) * 0.70)
                breakdown.append({
                    "key": "family:dapo_agent",
                    "base": round((dapo_score / 100.0) * 0.70, 6),
                    "weight": round(w_dapo, 6),
                    "value": round(c_dapo, 6),
                })

            blended = c_social + c_pattern + c_external + c_pipeline + c_copy + c_liq + x_component + c_kw + c_event_alpha + c_mom + c_vr + c_dapo
            final_score = round(min(max(blended, 0.0), 1.0) * 100.0, 2)

            if direction_consensus_enabled:
                # Weighted voting: collect direction votes weighted by input family weights
                votes = {"long": 0.0, "short": 0.0}
                dir_inputs = [
                    (pattern_direction, weight_for(input_controls, "family:pattern")),
                    (ext_direction, weight_for(input_controls, "family:external")),
                    (copy_direction, weight_for(input_controls, "family:copy")),
                    (pipe_direction, weight_for(input_controls, "family:pipeline")),
                    (kw_direction, weight_for(input_controls, "family:kyle_williams")),
                    (ea_direction, weight_for(input_controls, "family:event_alpha")),
                    (vr_direction, weight_for(input_controls, "family:vix_regime")),
                    (dapo_direction, weight_for(input_controls, "family:dapo_agent")),
                ]
                for dir_val, w_dir in dir_inputs:
                    d = str(dir_val or "").strip().lower()
                    if d in ("long", "buy", "bullish"):
                        votes["long"] += w_dir
                    elif d in ("short", "sell", "bearish"):
                        votes["short"] += w_dir

                total_votes = votes["long"] + votes["short"]
                if total_votes > 0:
                    best = max(votes, key=votes.get)
                    agreement = votes[best] / total_votes
                    if agreement >= min_direction_agreement:
                        direction = best
                    else:
                        direction = "neutral"
                    evidence.append(f"direction_consensus:{direction}:{agreement:.2f}")
                else:
                    direction = "unknown"
            else:
                # Original cascade fallback
                direction = pattern_direction
                if direction == "unknown":
                    direction = ext_direction if ext_direction != "unknown" else copy_direction
                if direction == "unknown" and pipe_direction != "unknown":
                    direction = pipe_direction
                if direction == "unknown" and kw_direction != "unknown":
                    direction = kw_direction
                if direction == "unknown" and ea_direction != "unknown":
                    direction = ea_direction
                if direction == "unknown" and vr_direction != "unknown":
                    direction = vr_direction
                if direction == "unknown" and dapo_direction != "unknown":
                    direction = dapo_direction

            source_tag = ext_source if ext_source != "internal" else (copy_source or pipe_source or "internal")
            if source_tag == "internal" and kw_hit:
                source_tag = "KYLE_WILLIAMS"
            if source_tag == "internal" and ea_hit:
                source_tag = "C_EVENT"
            if source_tag == "internal" and vr_hit:
                source_tag = "VIX_REGIME"
            if source_tag == "internal" and dapo_hit:
                source_tag = "DAPO_AGENT"
            evidence = []
            if ticker in sentiment:
                evidence.append("social_sentiment")
            if pattern_type and pattern_type != "none":
                evidence.append(f"pattern:{pattern_type}")
            if ticker in external:
                evidence.append(f"external:{ext_source}")
            if ticker in copy_signals:
                evidence.append(f"copy:{copy_source or 'unknown'}")
            if ticker in pipeline_signals:
                evidence.append(f"pipeline:{pipe_source or 'unknown'}")
            if liq_hit:
                evidence.append(f"liquidity_map:{liq_pattern}:rr={liq_rr}")
            if x_influence_enabled and ext_lower in tracked_sources:
                evidence.append(f"x:{ext_lower}")
            if kw_hit:
                evidence.append("pipeline:KYLE_WILLIAMS")
            if ea_hit:
                evidence.append("event_alpha:C_EVENT")
            if mom_hit:
                evidence.append(f"momentum:rank_{momentum_map[ticker][1]}_of_{momentum_map[ticker][2]}")
            if vr_hit:
                evidence.append(f"vix_regime:{vr_direction}:{vr_score:.0f}")
            if dapo_hit:
                evidence.append(f"dapo_agent:{dapo_direction}:{dapo_score:.0f}")

            confirmations = len(set([e.split(":")[0] if ":" in e else e for e in evidence]))
            sources_total = 11  # social, pattern, external, copy, pipeline, liquidity, kyle_williams, event_alpha, momentum, vix_regime, dapo_agent
            consensus_ratio = round(min(1.0, confirmations / max(1, sources_total)), 4)
            consensus_flag = 1 if (
                confirmations >= min_confirmations
                and consensus_ratio >= min_ratio
                and final_score >= min_score
            ) else 0

            # Premium Gate: if enabled for this asset class, require min N of
            # (kyle_williams, liquidity, momentum) to have fired — otherwise block the trade.
            # Gate only blocks (sets consensus_flag=0); it never promotes a trade.
            asset_class = "crypto" if ticker in crypto_tickers else "stock"
            pg_min = pg_stocks_min if asset_class == "stock" else pg_crypto_min
            if pg_min > 0 and consensus_flag == 1:
                pg_hits = 0
                if asset_class == "stock":
                    if pg_kw_stocks  and kw_hit:  pg_hits += 1
                    if pg_liq_stocks and liq_hit:  pg_hits += 1
                    if pg_mom_stocks and mom_hit:  pg_hits += 1
                else:
                    if pg_kw_crypto  and kw_hit:  pg_hits += 1
                    if pg_liq_crypto and liq_hit:  pg_hits += 1
                    if pg_mom_crypto and mom_hit:  pg_hits += 1
                if pg_hits < pg_min:
                    consensus_flag = 0
                    evidence.append(f"premium_gate:blocked:{pg_hits}/{pg_min}")

            top_inputs = sorted(breakdown, key=lambda x: float(x.get("value", 0.0)), reverse=True)[:3]
            top_desc = ", ".join([f"{x.get('key')}={float(x.get('value', 0.0)):.3f}" for x in top_inputs]) or "none"
            rationale = (
                f"score={final_score:.2f}; top_inputs[{top_desc}]; "
                f"ext={ext_source}:{ext_conf:.2f}; pipe={pipe_source or 'none'}:{pipe_score:.1f}"
            )

            rows.append(
                (
                    now_iso(),
                    ticker,
                    direction,
                    final_score,
                    sent_score,
                    pattern_type,
                    round(pattern_score, 4),
                    round(ext_conf, 4),
                    source_tag,
                    rationale,
                    int(confirmations),
                    int(sources_total),
                    float(consensus_ratio),
                    int(consensus_flag),
                    json.dumps(evidence[:20]),
                    json.dumps(top_inputs[:8]),
                )
            )

        cur.execute("DELETE FROM trade_candidates")
        cur.executemany(
            """
            INSERT INTO trade_candidates
            (generated_at, ticker, direction, score, sentiment_score, pattern_type, pattern_score,
             external_confidence, source_tag, rationale, confirmations, sources_total, consensus_ratio, consensus_flag, evidence_json, input_breakdown_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        print(f"Generated {len(rows)} trade candidates")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
