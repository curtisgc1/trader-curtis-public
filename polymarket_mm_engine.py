#!/usr/bin/env python3
"""
Polymarket MM v1 engine (paper-first advisory layer).
Builds execution-ready market-making snapshots from flagged consensus candidates,
with inventory skew, toxicity guard, and historical-accuracy blending.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_mm_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          candidate_score REAL NOT NULL,
          confirmations INTEGER NOT NULL DEFAULT 0,
          sources_total INTEGER NOT NULL DEFAULT 0,
          consensus_ratio REAL NOT NULL DEFAULT 0,
          market_id TEXT NOT NULL DEFAULT '',
          market_question TEXT NOT NULL DEFAULT '',
          market_url TEXT NOT NULL DEFAULT '',
          match_score INTEGER NOT NULL DEFAULT 0,
          implied_prob REAL NOT NULL DEFAULT 0,
          fair_prob REAL NOT NULL DEFAULT 0,
          reservation_price REAL NOT NULL DEFAULT 0,
          bid_price REAL NOT NULL DEFAULT 0,
          ask_price REAL NOT NULL DEFAULT 0,
          spread_bps REAL NOT NULL DEFAULT 0,
          edge_bps REAL NOT NULL DEFAULT 0,
          inventory_qty REAL NOT NULL DEFAULT 0,
          inventory_util_pct REAL NOT NULL DEFAULT 0,
          toxicity REAL NOT NULL DEFAULT 0,
          source_accuracy REAL NOT NULL DEFAULT 0,
          poly_exec_accuracy REAL NOT NULL DEFAULT 0,
          state TEXT NOT NULL DEFAULT 'normal',
          execution_ready INTEGER NOT NULL DEFAULT 0,
          rationale TEXT NOT NULL DEFAULT '',
          evidence_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    conn.commit()


def load_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not _table_exists(conn, "execution_controls"):
        return out
    cur = conn.cursor()
    cur.execute("SELECT key,value FROM execution_controls")
    for k, v in cur.fetchall():
        out[str(k)] = str(v)
    return out


def _source_accuracy_map(conn: sqlite3.Connection) -> Dict[str, Tuple[float, int]]:
    m: Dict[str, Tuple[float, int]] = {}
    cur = conn.cursor()
    if _table_exists(conn, "source_learning_stats"):
        cur.execute("SELECT source_tag, COALESCE(win_rate,0), COALESCE(sample_size,0) FROM source_learning_stats")
        for tag, wr, n in cur.fetchall():
            m[str(tag).lower()] = (float(wr or 0.0), int(n or 0))
    if _table_exists(conn, "source_scores"):
        cur.execute("SELECT source_tag, COALESCE(approved_rate,0), COALESCE(sample_size,0) FROM source_scores")
        for tag, wr, n in cur.fetchall():
            key = str(tag).lower()
            prev = m.get(key)
            if (not prev) or int(prev[1]) < int(n or 0):
                m[key] = (float(wr or 0.0), int(n or 0))
    return m


def _norm_source_key(tag: str) -> List[str]:
    raw = str(tag or "").strip().lower()
    if not raw:
        return []
    keys = [raw]
    if raw.startswith("liquidity_map:"):
        keys.append("pipeline:chart_liquidity")
    if ":" in raw:
        p = raw.split(":")
        if len(p) >= 2:
            keys.append(f"{p[0]}:{p[1]}")
        keys.append(p[0])
    return list(dict.fromkeys(keys))


def _weighted_source_accuracy(evidence: List[str], acc_map: Dict[str, Tuple[float, int]]) -> float:
    vals: List[Tuple[float, int]] = []
    for e in evidence:
        found = None
        for k in _norm_source_key(e):
            if k in acc_map:
                found = acc_map[k]
                break
        if found:
            vals.append(found)
    if not vals:
        return 50.0
    total_w = sum(max(1, n) for _, n in vals)
    if total_w <= 0:
        return 50.0
    score = sum(float(wr) * max(1, n) for wr, n in vals) / float(total_w)
    return _clamp(score, 0.0, 100.0)


def _poly_exec_accuracy(conn: sqlite3.Connection, days: int = 30) -> float:
    if not _table_exists(conn, "polymarket_orders"):
        return 50.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          SUM(CASE WHEN status IN ('filled_live','filled_paper','submitted_live','submitted_paper','accepted_live','open_live','partially_filled_live') THEN 1 ELSE 0 END) AS success_n,
          SUM(CASE WHEN status IN ('filled_live','filled_paper','submitted_live','submitted_paper','accepted_live','open_live','partially_filled_live','submission_failed','rejected_live') THEN 1 ELSE 0 END) AS total_n
        FROM polymarket_orders
        WHERE datetime(COALESCE(created_at,'1970-01-01')) >= datetime('now', ?)
        """,
        (f"-{int(days)} day",),
    )
    row = cur.fetchone() or (0, 0)
    good = int(row[0] or 0)
    total = int(row[1] or 0)
    if total <= 0:
        return 50.0
    return _clamp((good / total) * 100.0, 0.0, 100.0)


def _poly_signal_accuracy(conn: sqlite3.Connection, days: int = 30) -> float:
    if not (_table_exists(conn, "signal_routes") and _table_exists(conn, "route_outcomes")):
        return 50.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' AND o.resolution='win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN COALESCE(o.outcome_type,'realized')='realized' AND o.resolution IN ('win','loss') THEN 1 ELSE 0 END) AS total_n
        FROM route_outcomes o
        JOIN signal_routes r ON r.id=o.route_id
        WHERE datetime(COALESCE(r.routed_at,'1970-01-01')) >= datetime('now', ?)
          AND (
            UPPER(COALESCE(r.source_tag,'')) LIKE 'POLY%'
            OR UPPER(COALESCE(r.source_tag,'')) LIKE '%POLY%'
          )
        """,
        (f"-{int(days)} day",),
    )
    row = cur.fetchone() or (0, 0)
    wins = int(row[0] or 0)
    total = int(row[1] or 0)
    if total <= 0:
        return 50.0
    return _clamp((wins / total) * 100.0, 0.0, 100.0)


def _toxicity_score(conn: sqlite3.Connection, lookback_orders: int = 200) -> float:
    if not _table_exists(conn, "polymarket_orders"):
        return 0.25
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(side,''), COALESCE(status,''), COALESCE(notional,0)
        FROM polymarket_orders
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(lookback_orders),),
    )
    buys = 0.0
    sells = 0.0
    fail = 0
    total = 0
    for side, status, notional in cur.fetchall():
        total += 1
        n = abs(float(notional or 0.0))
        s = str(side or "").lower()
        st = str(status or "").lower()
        if s == "buy":
            buys += max(1.0, n)
        elif s == "sell":
            sells += max(1.0, n)
        if ("fail" in st) or ("reject" in st) or st.startswith("blocked"):
            fail += 1
    if total <= 0:
        return 0.25
    flow_imbalance = abs(buys - sells) / max(1.0, buys + sells)
    fail_rate = fail / total
    # blend into 0..1
    return _clamp(0.65 * flow_imbalance + 0.35 * fail_rate, 0.0, 1.0)


def _inventory_for_market(conn: sqlite3.Connection, market_id: str) -> float:
    if not _table_exists(conn, "polymarket_orders"):
        return 0.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(side,''), COALESCE(size,0)
        FROM polymarket_orders
        WHERE market_id=?
          AND status IN ('filled_live','filled_paper','partially_filled_live')
        ORDER BY id DESC
        LIMIT 400
        """,
        (str(market_id),),
    )
    inv = 0.0
    for side, size in cur.fetchall():
        qty = float(size or 0.0)
        if str(side or "").lower() == "buy":
            inv += qty
        elif str(side or "").lower() == "sell":
            inv -= qty
    return inv


def _alias_tokens(ticker: str) -> List[str]:
    t = str(ticker or "").upper().strip()
    aliases: Dict[str, List[str]] = {
        "TSLA": ["tesla", "elon", "musk"],
        "AEM": ["agnico", "agnico eagle", "gold price"],
        "MSFT": ["microsoft", "openai", "copilot"],
        "NVDA": ["nvidia", "ai chips", "semiconductor"],
        "BTC": ["bitcoin", "btc", "crypto"],
        "ETH": ["ethereum", "eth", "crypto"],
        "SPY": ["s&p", "sp500", "stocks"],
    }
    return [t.lower()] + aliases.get(t, [])


def _best_market_match(conn: sqlite3.Connection, ticker: str, direction: str) -> Dict[str, Any]:
    if not _table_exists(conn, "polymarket_markets"):
        return {}
    tokens = [x for x in dict.fromkeys([x.strip().lower() for x in _alias_tokens(ticker) if x])]
    if not tokens:
        return {}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT market_id, question, market_url, outcomes_json, outcome_prices_json, liquidity, volume_24h, slug
        FROM polymarket_markets
        WHERE active=1 AND closed=0
        ORDER BY liquidity DESC, volume_24h DESC
        LIMIT 1000
        """
    )
    sports_noise = ("stanley cup", "nba finals", "world series", "super bowl", "champions league")
    best: Dict[str, Any] = {}
    for market_id, question, market_url, outcomes_json, prices_json, liquidity, volume_24h, slug in cur.fetchall():
        q = str(question or "").lower()
        s = str(slug or "").lower()
        if any(x in q for x in sports_noise) and str(ticker or "").upper() not in {"BTC", "ETH"}:
            continue
        score = 0
        q_hits = 0
        hits = []
        for tok in tokens:
            if len(tok) < 3 and tok not in {"btc", "eth", "spy"}:
                continue
            if re.search(rf"(^|[^a-z0-9]){re.escape(tok)}([^a-z0-9]|$)", q):
                score += 5
                q_hits += 1
                hits.append(tok)
            elif re.search(rf"(^|[^a-z0-9]){re.escape(tok)}([^a-z0-9]|$)", s):
                score += 2
                hits.append(tok)
        if q_hits <= 0:
            continue

        implied = 0.5
        try:
            outcomes = json.loads(outcomes_json or "[]")
            prices = json.loads(prices_json or "[]")
            if isinstance(outcomes, list) and isinstance(prices, list) and outcomes and prices:
                implied = float(prices[0] or 0.5)
        except Exception:
            implied = 0.5

        row = {
            "market_id": str(market_id or ""),
            "question": str(question or ""),
            "market_url": str(market_url or ""),
            "liquidity": float(liquidity or 0.0),
            "volume_24h": float(volume_24h or 0.0),
            "match_score": int(score),
            "matched_terms": sorted(list(set(hits))),
            "implied_prob": _clamp(float(implied), 0.01, 0.99),
        }
        if (not best) or (row["match_score"], row["liquidity"], row["volume_24h"]) > (
            int(best.get("match_score", 0)),
            float(best.get("liquidity", 0.0)),
            float(best.get("volume_24h", 0.0)),
        ):
            best = row
    return best


def build_snapshots(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "trade_candidates"):
        return 0

    controls = load_controls(conn)
    mm_enabled = str(controls.get("mm_enabled", "0")).lower() in {"1", "true", "yes", "on"}
    risk_aversion = float(controls.get("mm_risk_aversion", "0.25") or 0.25)
    base_spread_bps = float(controls.get("mm_base_spread_bps", "80") or 80)
    tox_cut = float(controls.get("mm_toxicity_threshold", "0.72") or 0.72)
    inv_limit = float(controls.get("mm_inventory_limit", "200") or 200)
    min_edge_bps = float(controls.get("mm_min_edge_bps", "50") or 50)

    toxicity = _toxicity_score(conn)
    source_acc_map = _source_accuracy_map(conn)
    poly_exec_acc = _poly_exec_accuracy(conn, days=30)
    poly_signal_acc = _poly_signal_accuracy(conn, days=30)

    cur = conn.cursor()
    cur.execute("DELETE FROM polymarket_mm_snapshots")
    cur.execute(
        """
        SELECT ticker, direction, score,
               COALESCE(confirmations,0), COALESCE(sources_total,0), COALESCE(consensus_ratio,0),
               COALESCE(evidence_json,'[]')
        FROM trade_candidates
        WHERE COALESCE(consensus_flag,0)=1
        ORDER BY score DESC
        LIMIT 80
        """
    )
    rows = cur.fetchall()
    out_n = 0

    for ticker, direction, score, conf_n, src_n, c_ratio, evidence_json in rows:
        ticker_s = str(ticker or "").upper()
        direction_s = str(direction or "").lower()
        try:
            evidence = json.loads(evidence_json or "[]")
            if not isinstance(evidence, list):
                evidence = []
        except Exception:
            evidence = []

        match = _best_market_match(conn, ticker_s, direction_s)
        if not match:
            continue

        implied = float(match.get("implied_prob", 0.5))
        source_acc = _weighted_source_accuracy([str(x) for x in evidence], source_acc_map)
        score_norm = _clamp((float(score or 50.0) - 50.0) / 50.0, -1.0, 1.0)
        dir_sign = 1.0 if direction_s == "long" else (-1.0 if direction_s == "short" else 0.0)

        consensus_boost = _clamp((float(c_ratio or 0.0) - 0.5) * 0.20, -0.10, 0.10)
        source_boost = _clamp((source_acc - 50.0) / 500.0, -0.10, 0.10)
        hist_boost = _clamp(((poly_signal_acc - 50.0) / 500.0) + ((poly_exec_acc - 50.0) / 700.0), -0.10, 0.10)
        score_boost = 0.18 * score_norm * dir_sign

        fair_prob = _clamp(implied + score_boost + consensus_boost + source_boost + hist_boost, 0.01, 0.99)

        inv_qty = _inventory_for_market(conn, str(match.get("market_id", "")))
        inv_util = _clamp(abs(inv_qty) / max(1.0, inv_limit), 0.0, 3.0)
        inv_sign = 1.0 if inv_qty > 0 else (-1.0 if inv_qty < 0 else 0.0)

        # Reservation shifts against current inventory to encourage mean reversion.
        reservation = _clamp(fair_prob - (risk_aversion * inv_util * 0.15 * inv_sign), 0.01, 0.99)

        spread_bps = max(10.0, base_spread_bps * (1.0 + (toxicity * 1.8) + (inv_util * 0.6)))
        spread = spread_bps / 10000.0
        bid = _clamp(reservation - spread / 2.0, 0.01, 0.99)
        ask = _clamp(reservation + spread / 2.0, 0.01, 0.99)

        edge_bps = abs(fair_prob - implied) * 10000.0

        state = "normal"
        if toxicity >= tox_cut:
            state = "killswitch"
        elif (toxicity >= (tox_cut * 0.8)) or (inv_util >= 0.85):
            state = "caution"

        execution_ready = 1 if (mm_enabled and state != "killswitch" and edge_bps >= min_edge_bps) else 0

        rationale = (
            f"implied={implied:.4f}, fair={fair_prob:.4f}, edge_bps={edge_bps:.1f}, "
            f"tox={toxicity:.2f}, inv_util={inv_util*100:.1f}%, src_acc={source_acc:.1f}, "
            f"poly_exec_acc={poly_exec_acc:.1f}, poly_signal_acc={poly_signal_acc:.1f}"
        )

        cur.execute(
            """
            INSERT INTO polymarket_mm_snapshots (
              created_at, ticker, direction, candidate_score, confirmations, sources_total, consensus_ratio,
              market_id, market_question, market_url, match_score,
              implied_prob, fair_prob, reservation_price, bid_price, ask_price,
              spread_bps, edge_bps, inventory_qty, inventory_util_pct, toxicity,
              source_accuracy, poly_exec_accuracy, state, execution_ready, rationale, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                ticker_s,
                direction_s,
                float(score or 0.0),
                int(conf_n or 0),
                int(src_n or 0),
                float(c_ratio or 0.0),
                str(match.get("market_id", "")),
                str(match.get("question", "")),
                str(match.get("market_url", "")),
                int(match.get("match_score", 0)),
                float(implied),
                float(fair_prob),
                float(reservation),
                float(bid),
                float(ask),
                float(spread_bps),
                float(edge_bps),
                float(inv_qty),
                float(inv_util * 100.0),
                float(toxicity),
                float(source_acc),
                float(poly_exec_acc),
                state,
                int(execution_ready),
                rationale,
                json.dumps(evidence[:10]),
            ),
        )
        out_n += 1

    conn.commit()
    return out_n


def main() -> int:
    conn = _connect()
    try:
        ensure_tables(conn)
        n = build_snapshots(conn)
        print(f"POLY_MM_V1: snapshots={n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
