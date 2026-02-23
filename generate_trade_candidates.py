#!/usr/bin/env python3
"""
Build normalized trade candidates from internal + external signal tables.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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

COPY_TRADE_SOURCE_BOOSTS = {
    "NoLimitGains": 0.08,
    "ZenomTrader": 0.05,
}


def load_tracked_sources(conn: sqlite3.Connection) -> dict:
    if not table_exists(conn, "tracked_x_sources"):
        return {}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT lower(COALESCE(handle,'')), COALESCE(role_copy,1), COALESCE(role_alpha,1), COALESCE(active,1)
        FROM tracked_x_sources
        WHERE COALESCE(active,1)=1
        """
    )
    out = {}
    for handle, role_copy, role_alpha, active in cur.fetchall():
        h = str(handle or "").strip().lower()
        if not h:
            continue
        out[h] = {
            "role_copy": int(role_copy or 0) == 1,
            "role_alpha": int(role_alpha or 0) == 1,
            "active": int(active or 0) == 1,
        }
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


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
    # Backfill additional consensus columns for older DBs.
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(trade_candidates)")
    cols = {r[1] for r in cur.fetchall()}
    additions = {
        "confirmations": "INTEGER NOT NULL DEFAULT 0",
        "sources_total": "INTEGER NOT NULL DEFAULT 0",
        "consensus_ratio": "REAL NOT NULL DEFAULT 0",
        "consensus_flag": "INTEGER NOT NULL DEFAULT 0",
        "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
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


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_candidates_table(conn)
        cur = conn.cursor()
        tracked_sources = load_tracked_sources(conn)
        controls = {}
        if table_exists(conn, "execution_controls"):
            cur.execute("SELECT key, value FROM execution_controls")
            controls = {str(k): str(v) for k, v in cur.fetchall()}
        min_confirmations = int(float(controls.get("consensus_min_confirmations", "3") or 3))
        min_ratio = float(controls.get("consensus_min_ratio", "0.6") or 0.6)
        min_score = float(controls.get("consensus_min_score", "60") or 60.0)
        liq_boost = float(controls.get("liquidity_high_signal_boost", "0.08") or 0.08)
        liq_min_conf = float(controls.get("liquidity_min_confidence", "0.60") or 0.60)
        liq_min_rr = float(controls.get("liquidity_min_rr", "2.0") or 2.0)

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
        if table_exists(conn, "pipeline_signals"):
            pipeline_signals = latest_map(
                cur,
                """
                SELECT asset, score, direction, pipeline_id, generated_at
                FROM pipeline_signals
                WHERE status = 'new'
                ORDER BY generated_at DESC
                """,
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

        tickers = (
            set(sentiment.keys())
            | set(patterns.keys())
            | set(external.keys())
            | set(copy_signals.keys())
            | set(pipeline_signals.keys())
            | set(chart_liq.keys())
        )
        rows = []

        for ticker in tickers:
            sent_score = float((sentiment.get(ticker) or (50, None))[0] or 50)
            pattern_type = (patterns.get(ticker) or ("none", "unknown", None))[0] or "none"
            pattern_direction = (patterns.get(ticker) or ("none", "unknown", None))[1] or "unknown"
            pattern_score = float(PATTERN_RELIABILITY.get(pattern_type, 0.50))
            source_boost = 0.0

            ext_source, ext_direction, ext_conf = "internal", "unknown", 0.50
            if ticker in external:
                ext_source = external[ticker][0] or "external"
                ext_direction = external[ticker][1] or "unknown"
                ext_conf = float(external[ticker][2] or 0.50)
                ext_lower = str(ext_source).lower()
                if any(h in ext_lower for h in tracked_sources.keys()):
                    source_boost += 0.05

            copy_source, copy_direction = None, None
            if ticker in copy_signals:
                copy_source = copy_signals[ticker][0] or ""
                copy_direction = copy_signals[ticker][1] or ""
                source_boost += COPY_TRADE_SOURCE_BOOSTS.get(copy_source, 0.03)
                if str(copy_source).lower() in tracked_sources:
                    source_boost += 0.04

            pipe_score = 50.0
            pipe_direction = "unknown"
            pipe_source = None
            if ticker in pipeline_signals:
                pipe_score = float(pipeline_signals[ticker][0] or 50.0)
                pipe_direction = pipeline_signals[ticker][1] or "unknown"
                pipe_source = pipeline_signals[ticker][2] or ""
                source_boost += 0.04

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
                if (
                    liq_conf >= liq_min_conf
                    and liq_rr >= liq_min_rr
                    and any(k in liq_pattern for k in ["liquidity_grab", "stop_hunt", "fakeout"])
                ):
                    liq_hit = True
                    source_boost += liq_boost

            # Weighted blend + small source boost cap.
            blended = (
                (sent_score / 100.0) * 0.25
                + pattern_score * 0.30
                + ext_conf * 0.20
                + (pipe_score / 100.0) * 0.25
                + min(source_boost, 0.10)
            )
            final_score = round(min(blended, 1.0) * 100.0, 2)

            direction = pattern_direction
            if direction == "unknown":
                direction = ext_direction if ext_direction != "unknown" else copy_direction or "unknown"
            if direction == "unknown" and pipe_direction != "unknown":
                direction = pipe_direction

            source_tag = ext_source if ext_source != "internal" else (copy_source or pipe_source or "internal")
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
            if ticker in tracked_sources and tracked_sources[ticker].get("active"):
                evidence.append("tracked_source_direct")
            confirmations = len(set([e.split(":")[0] if ":" in e else e for e in evidence]))
            # Five source families: social, pattern, external, copy, pipeline.
            sources_total = 5
            consensus_ratio = round(min(1.0, confirmations / max(1, sources_total)), 4)
            consensus_flag = 1 if (
                confirmations >= min_confirmations
                and consensus_ratio >= min_ratio
                and final_score >= min_score
            ) else 0
            rationale = (
                f"sent={sent_score:.0f}, pattern={pattern_type}, ext={ext_source}:{ext_conf:.2f}, "
                f"pipe={pipe_source or 'none'}:{pipe_score:.1f}"
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
                    json.dumps(evidence[:12]),
                )
            )

        # Keep only fresh generated set.
        cur.execute("DELETE FROM trade_candidates")
        cur.executemany(
            """
            INSERT INTO trade_candidates
            (generated_at, ticker, direction, score, sentiment_score, pattern_type, pattern_score,
             external_confidence, source_tag, rationale, confirmations, sources_total, consensus_ratio, consensus_flag, evidence_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
