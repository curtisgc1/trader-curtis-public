#!/usr/bin/env python3
"""
Extract high-signal internal plays and align them to live Polymarket markets.

Goal: prioritize high-signal + lower-interest opportunities while still exposing
high-signal direct-tradable setups.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

UP_WORDS = {"up", "rise", "higher", "above", "yes", "bull", "increase", "gain", "beats", "exceed"}
DOWN_WORDS = {"down", "fall", "lower", "below", "no", "bear", "decrease", "drop", "miss", "under"}

TICKER_ALIASES: Dict[str, List[str]] = {
    "TSLA": ["tesla", "elon", "musk"],
    "AEM": ["agnico", "agnico eagle", "gold miners", "gold price"],
    "NEM": ["newmont", "gold miners", "gold price"],
    "BTC": ["bitcoin", "btc", "crypto"],
    "ETH": ["ethereum", "eth", "crypto"],
    "SOL": ["solana", "sol", "crypto"],
    "XRP": ["ripple", "xrp", "crypto"],
    "NVDA": ["nvidia", "ai", "chips", "semiconductor"],
    "ASML": ["asml", "lithography", "semiconductor"],
    "PLTR": ["palantir", "defense", "software"],
    "SPY": ["s&p", "sp500", "stocks", "equities"],
    "QQQ": ["nasdaq", "tech stocks", "nq"],
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
    return any((r[1] == column) for r in cur.fetchall())


def _coerce_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(d)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_aligned_setups (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          generated_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          candidate_score REAL NOT NULL DEFAULT 0,
          confirmations INTEGER NOT NULL DEFAULT 0,
          sources_total INTEGER NOT NULL DEFAULT 0,
          consensus_ratio REAL NOT NULL DEFAULT 0,
          source_tag TEXT NOT NULL DEFAULT '',
          evidence_json TEXT NOT NULL DEFAULT '[]',
          market_id TEXT NOT NULL,
          market_slug TEXT NOT NULL DEFAULT '',
          question TEXT NOT NULL DEFAULT '',
          market_url TEXT NOT NULL DEFAULT '',
          liquidity REAL NOT NULL DEFAULT 0,
          volume_24h REAL NOT NULL DEFAULT 0,
          implied_prob REAL NOT NULL DEFAULT 0,
          match_score REAL NOT NULL DEFAULT 0,
          alignment_confidence REAL NOT NULL DEFAULT 0,
          signal_strength REAL NOT NULL DEFAULT 0,
          source_quality REAL NOT NULL DEFAULT 0,
          resolution_clarity REAL NOT NULL DEFAULT 0,
          crowding_penalty REAL NOT NULL DEFAULT 0,
          fee_drag REAL NOT NULL DEFAULT 0,
          alpha_score REAL NOT NULL DEFAULT 0,
          class_tag TEXT NOT NULL DEFAULT 'watchlist',
          rationale TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    # Backfill columns for older versions.
    add_cols = {
        "signal_strength": "REAL NOT NULL DEFAULT 0",
        "source_quality": "REAL NOT NULL DEFAULT 0",
        "resolution_clarity": "REAL NOT NULL DEFAULT 0",
        "crowding_penalty": "REAL NOT NULL DEFAULT 0",
        "fee_drag": "REAL NOT NULL DEFAULT 0",
        "alpha_score": "REAL NOT NULL DEFAULT 0",
        "class_tag": "TEXT NOT NULL DEFAULT 'watchlist'",
    }
    for col, spec in add_cols.items():
        if not _column_exists(conn, "polymarket_aligned_setups", col):
            conn.execute(f"ALTER TABLE polymarket_aligned_setups ADD COLUMN {col} {spec}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_align_generated ON polymarket_aligned_setups(generated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_align_ticker ON polymarket_aligned_setups(ticker, direction)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_align_class ON polymarket_aligned_setups(class_tag, alpha_score)")
    conn.commit()


def _load_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    if not _table_exists(conn, "execution_controls"):
        return {}
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    return {str(k): str(v) for k, v in cur.fetchall()}


def _source_quality(conn: sqlite3.Connection, source_tag: str) -> float:
    s = str(source_tag or "").strip().lower()
    if not s:
        return 0.5
    cur = conn.cursor()
    if _table_exists(conn, "source_learning_stats"):
        cur.execute(
            """
            SELECT COALESCE(win_rate,0)
            FROM source_learning_stats
            WHERE lower(COALESCE(source_tag,''))=?
            ORDER BY sample_size DESC
            LIMIT 1
            """,
            (s,),
        )
        row = cur.fetchone()
        if row:
            return max(0.0, min(1.0, _coerce_float(row[0], 50.0) / 100.0))

    if _table_exists(conn, "source_scores"):
        if _column_exists(conn, "source_scores", "source_tag"):
            cur.execute(
                """
                SELECT COALESCE(reliability_score,50)
                FROM source_scores
                WHERE lower(COALESCE(source_tag,''))=?
                ORDER BY sample_size DESC
                LIMIT 1
                """,
                (s,),
            )
            row = cur.fetchone()
            if row:
                return max(0.0, min(1.0, _coerce_float(row[0], 50.0) / 100.0))
    return 0.5


def _load_high_signal_candidates(conn: sqlite3.Connection, limit: int = 80) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "trade_candidates"):
        return []
    ctl = _load_controls(conn)
    min_score = _coerce_float(ctl.get("consensus_min_score"), 60.0)
    min_confirms = int(_coerce_float(ctl.get("consensus_min_confirmations"), 3))
    min_ratio = _coerce_float(ctl.get("consensus_min_ratio"), 0.6)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT generated_at, ticker, direction, score, source_tag,
               COALESCE(confirmations,0), COALESCE(sources_total,0),
               COALESCE(consensus_ratio,0), COALESCE(evidence_json,'[]')
        FROM trade_candidates
        WHERE COALESCE(consensus_flag,0)=1
          AND COALESCE(score,0) >= ?
          AND COALESCE(confirmations,0) >= ?
          AND COALESCE(consensus_ratio,0) >= ?
        ORDER BY score DESC, consensus_ratio DESC, confirmations DESC
        LIMIT ?
        """,
        (float(min_score), int(min_confirms), float(min_ratio), int(limit)),
    )
    out: List[Dict[str, Any]] = []
    for row in cur.fetchall():
        evidence: List[str] = []
        try:
            parsed = json.loads(row[8] or "[]")
            if isinstance(parsed, list):
                evidence = [str(x) for x in parsed[:12]]
        except Exception:
            pass
        out.append(
            {
                "generated_at": str(row[0] or ""),
                "ticker": str(row[1] or "").upper(),
                "direction": str(row[2] or "").lower(),
                "score": _coerce_float(row[3], 0.0),
                "source_tag": str(row[4] or ""),
                "confirmations": int(row[5] or 0),
                "sources_total": int(row[6] or 0),
                "consensus_ratio": _coerce_float(row[7], 0.0),
                "evidence": evidence,
            }
        )
    return out


def _tokenize_candidate(ticker: str, evidence: List[str]) -> List[str]:
    t = str(ticker or "").upper().strip()
    toks = [t.lower()] if t else []
    toks.extend(TICKER_ALIASES.get(t, []))
    for e in (evidence or []):
        low = str(e or "").lower()
        for piece in re.split(r"[^a-z0-9]+", low):
            if len(piece) >= 4 and piece not in {"pipeline", "signal", "event", "chart", "source", "trade"}:
                toks.append(piece)
    uniq: List[str] = []
    seen = set()
    for x in toks:
        k = str(x).strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        uniq.append(k)
    return uniq[:24]


def _score_market(question: str, slug: str, direction: str, tokens: List[str]) -> Tuple[float, List[str]]:
    q = str(question or "").lower()
    s = str(slug or "").lower()
    score = 0.0
    hits: List[str] = []

    for tok in tokens:
        if len(tok) < 3 and tok not in {"btc", "eth", "sol", "xrp", "spy", "qqq"}:
            continue
        patt = rf"(^|[^a-z0-9]){re.escape(tok)}([^a-z0-9]|$)"
        if re.search(patt, q):
            score += 5.0
            hits.append(tok)
        elif re.search(patt, s):
            score += 2.0
            hits.append(tok)

    d = str(direction or "").lower()
    if d == "long" and any(w in q for w in UP_WORDS):
        score += 1.2
    if d == "short" and any(w in q for w in DOWN_WORDS):
        score += 1.2

    if score > 0 and not any(re.search(rf"(^|[^a-z0-9]){re.escape(tok)}([^a-z0-9]|$)", q) for tok in tokens if tok):
        score *= 0.5

    return score, sorted(list(set(hits)))


def _is_direct_tradable(market_slug: str, question: str) -> bool:
    s = str(market_slug or "").lower()
    q = str(question or "").lower()
    if "updown" in s or "up or down" in q:
        return True
    if any(x in q for x in ["bitcoin", "btc", "ethereum", "eth", "solana", "xrp"]):
        return True
    if any(x in q for x in ["above", "below", "hits", "reach", "price"]):
        return True
    return False


def _resolution_clarity(question: str, market_slug: str) -> float:
    q = str(question or "").lower()
    s = str(market_slug or "").lower()
    clarity = 0.45
    if any(k in q for k in [" at ", " by ", " before ", " between ", " max temperature", "airport"]):
        clarity += 0.20
    if "updown" in s or "up or down" in q:
        clarity += 0.22
    if any(k in q for k in ["will", "yes", "no"]):
        clarity += 0.08
    return max(0.0, min(1.0, clarity))


def _crowding_penalty(liquidity: float, vol24h: float) -> float:
    l = math.log10(max(1.0, liquidity))
    v = math.log10(max(1.0, vol24h))
    # Higher when market is crowded/highly competed.
    raw = (0.07 * l) + (0.10 * v) - 0.40
    return max(0.0, min(1.0, raw))


def _fee_drag(market_slug: str, question: str) -> float:
    s = str(market_slug or "").lower()
    q = str(question or "").lower()
    if "updown" in s or "5m" in s or "15m" in s or "up or down" in q:
        return 0.28
    return 0.08


def _alpha_components(candidate_score: float, consensus_ratio: float, source_quality: float, resolution_clarity: float, crowding_penalty: float, fee_drag: float, match_score: float) -> Dict[str, float]:
    signal_strength = max(0.0, min(1.0, candidate_score / 100.0))
    match_norm = max(0.0, min(1.0, match_score / 12.0))

    alpha = (
        0.38 * signal_strength
        + 0.22 * source_quality
        + 0.18 * resolution_clarity
        + 0.12 * max(0.0, min(1.0, consensus_ratio))
        + 0.10 * match_norm
        - 0.20 * crowding_penalty
        - 0.12 * fee_drag
    )
    alpha = max(0.0, min(1.0, alpha))
    return {
        "signal_strength": signal_strength,
        "alpha_score": alpha,
    }


def build_alignments(conn: sqlite3.Connection, candidate_limit: int = 80, market_limit: int = 900) -> int:
    cands = _load_high_signal_candidates(conn, limit=candidate_limit)
    if not cands or not _table_exists(conn, "polymarket_markets"):
        conn.execute("DELETE FROM polymarket_aligned_setups")
        conn.commit()
        return 0

    cur = conn.cursor()
    cur.execute(
        """
        SELECT market_id, slug, question, market_url, liquidity, volume_24h, outcome_prices_json
        FROM polymarket_markets
        WHERE active=1 AND closed=0
        ORDER BY volume_24h DESC, liquidity DESC
        LIMIT ?
        """,
        (int(market_limit),),
    )
    markets = cur.fetchall()

    conn.execute("DELETE FROM polymarket_aligned_setups")
    written = 0

    for c in cands:
        tokens = _tokenize_candidate(c["ticker"], c.get("evidence", []))
        src_q = _source_quality(conn, c.get("source_tag", ""))
        ranked: List[Dict[str, Any]] = []

        for market_id, slug, question, market_url, liquidity, volume_24h, prices_json in markets:
            mscore, hits = _score_market(question, slug, c["direction"], tokens)
            if mscore < 5.0:
                continue

            implied = 0.0
            try:
                arr = json.loads(prices_json or "[]")
                if isinstance(arr, list) and arr:
                    implied = _coerce_float(arr[0], 0.0)
            except Exception:
                pass

            liq = _coerce_float(liquidity, 0.0)
            v24 = _coerce_float(volume_24h, 0.0)
            clarity = _resolution_clarity(question, slug)
            crowd = _crowding_penalty(liq, v24)
            fee = _fee_drag(slug, question)
            comp = _alpha_components(c["score"], c["consensus_ratio"], src_q, clarity, crowd, fee, mscore)
            alpha = comp["alpha_score"]

            is_direct = _is_direct_tradable(slug, question)
            if alpha >= 0.72 and crowd <= 0.45:
                class_tag = "high_signal_low_interest"
            elif is_direct and alpha >= 0.68:
                class_tag = "high_signal_direct"
            else:
                class_tag = "watchlist"

            ranked.append(
                {
                    "market_id": str(market_id or ""),
                    "market_slug": str(slug or ""),
                    "question": str(question or ""),
                    "market_url": str(market_url or ""),
                    "liquidity": liq,
                    "volume_24h": v24,
                    "implied_prob": implied,
                    "match_score": round(mscore, 4),
                    "alignment_confidence": round(alpha, 4),
                    "signal_strength": round(comp["signal_strength"], 4),
                    "source_quality": round(src_q, 4),
                    "resolution_clarity": round(clarity, 4),
                    "crowding_penalty": round(crowd, 4),
                    "fee_drag": round(fee, 4),
                    "alpha_score": round(alpha, 4),
                    "class_tag": class_tag,
                    "hits": hits,
                }
            )

        ranked.sort(key=lambda x: (x["alpha_score"], x["match_score"], -x["crowding_penalty"], x["liquidity"]), reverse=True)
        for hit in ranked[:3]:
            rationale = (
                f"alpha={hit['alpha_score']} class={hit['class_tag']} matched_terms={','.join(hit['hits'][:8])}; "
                f"signal={round(c['score'],2)} consensus={round(c['consensus_ratio'],3)} crowd={hit['crowding_penalty']}"
            )
            conn.execute(
                """
                INSERT INTO polymarket_aligned_setups
                (generated_at, ticker, direction, candidate_score, confirmations, sources_total, consensus_ratio,
                 source_tag, evidence_json, market_id, market_slug, question, market_url, liquidity, volume_24h,
                 implied_prob, match_score, alignment_confidence, signal_strength, source_quality, resolution_clarity,
                 crowding_penalty, fee_drag, alpha_score, class_tag, rationale, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    now_iso(),
                    c["ticker"],
                    c["direction"],
                    _coerce_float(c["score"], 0.0),
                    int(c.get("confirmations") or 0),
                    int(c.get("sources_total") or 0),
                    _coerce_float(c.get("consensus_ratio"), 0.0),
                    str(c.get("source_tag") or ""),
                    json.dumps(c.get("evidence", [])),
                    hit["market_id"],
                    hit["market_slug"],
                    hit["question"],
                    hit["market_url"],
                    hit["liquidity"],
                    hit["volume_24h"],
                    hit["implied_prob"],
                    hit["match_score"],
                    hit["alignment_confidence"],
                    hit["signal_strength"],
                    hit["source_quality"],
                    hit["resolution_clarity"],
                    hit["crowding_penalty"],
                    hit["fee_drag"],
                    hit["alpha_score"],
                    hit["class_tag"],
                    rationale,
                ),
            )
            written += 1

    conn.commit()
    return written


def _crossfeed_polymarket_to_equity(conn: sqlite3.Connection) -> int:
    """
    Phase 6: Bidirectional signal bridge — Polymarket → equity/crypto.

    When a Polymarket crypto market moves significantly (>15% probability shift in 24h),
    write a signal to external_signals for equity pipeline consumption.
    Also feeds options-implied probabilities from polymarket_options_bridge.
    """
    ctl = _load_controls(conn)
    if ctl.get("polymarket_crossfeed_enabled", "1") != "1":
        return 0

    if not _table_exists(conn, "external_signals"):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS external_signals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              source TEXT NOT NULL DEFAULT '',
              ticker TEXT NOT NULL DEFAULT '',
              direction TEXT NOT NULL DEFAULT '',
              confidence REAL NOT NULL DEFAULT 0,
              notes TEXT NOT NULL DEFAULT '',
              expires_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()

    written = 0
    cur = conn.cursor()

    # 1. Detect significant Polymarket probability shifts in crypto markets
    if _table_exists(conn, "polymarket_candidates"):
        ticker_map = {
            "bitcoin": "BTC", "btc": "BTC",
            "ethereum": "ETH", "eth": "ETH",
            "solana": "SOL", "sol": "SOL",
            "xrp": "XRP", "ripple": "XRP",
            "dogecoin": "DOGE", "doge": "DOGE",
        }

        cur.execute(
            """
            SELECT question, implied_prob, model_prob, edge, strategy_id, slug
            FROM polymarket_candidates
            WHERE datetime(created_at) >= datetime('now', '-4 hours')
              AND ABS(edge) >= 8.0
            ORDER BY ABS(edge) DESC
            LIMIT 30
            """
        )
        for question, implied, model, edge, strategy, slug in cur.fetchall():
            q = str(question or "").lower()
            matched_ticker = None
            for keyword, ticker in ticker_map.items():
                if keyword in q:
                    matched_ticker = ticker
                    break
            if not matched_ticker:
                continue

            direction = "long" if float(edge or 0) > 0 else "short"
            conf = min(0.85, abs(float(edge or 0)) / 20.0)

            # Avoid duplicate signals
            cur.execute(
                """
                SELECT 1 FROM external_signals
                WHERE source='polymarket_crossfeed' AND ticker=?
                  AND datetime(created_at) >= datetime('now', '-4 hours')
                LIMIT 1
                """,
                (matched_ticker,),
            )
            if cur.fetchone():
                continue

            conn.execute(
                """
                INSERT INTO external_signals
                (created_at, source, ticker, direction, confidence, notes, expires_at)
                VALUES (?, 'polymarket_crossfeed', ?, ?, ?, ?, datetime('now', '+24 hours'))
                """,
                (
                    now_iso(), matched_ticker, direction, round(conf, 4),
                    f"polymarket {strategy} edge={float(edge or 0):+.2f}% "
                    f"implied={float(implied or 0):.4f} model={float(model or 0):.4f} "
                    f"slug={slug}",
                ),
            )
            written += 1

    # 2. Feed options-implied probability signals
    if _table_exists(conn, "options_implied_signals"):
        cur.execute(
            """
            SELECT ticker, options_prob, market_prob, divergence_pct, direction, spot_price, strike
            FROM options_implied_signals
            WHERE datetime(created_at) >= datetime('now', '-6 hours')
              AND divergence_pct >= 10.0
            ORDER BY divergence_pct DESC
            LIMIT 10
            """
        )
        for ticker, opts_prob, mkt_prob, div_pct, direction, spot, strike in cur.fetchall():
            # Avoid duplicate signals
            cur.execute(
                """
                SELECT 1 FROM external_signals
                WHERE source='options_implied_crossfeed' AND ticker=?
                  AND datetime(created_at) >= datetime('now', '-6 hours')
                LIMIT 1
                """,
                (str(ticker or ""),),
            )
            if cur.fetchone():
                continue

            sig_direction = "long" if str(direction or "") == "above" else "short"
            conf = min(0.85, float(div_pct or 0) / 25.0)

            conn.execute(
                """
                INSERT INTO external_signals
                (created_at, source, ticker, direction, confidence, notes, expires_at)
                VALUES (?, 'options_implied_crossfeed', ?, ?, ?, ?, datetime('now', '+24 hours'))
                """,
                (
                    now_iso(), str(ticker or ""), sig_direction, round(conf, 4),
                    f"options_implied divergence={float(div_pct or 0):.2f}% "
                    f"opts_prob={float(opts_prob or 0):.4f} mkt_prob={float(mkt_prob or 0):.4f} "
                    f"spot={float(spot or 0):.2f} strike={float(strike or 0):.0f}",
                ),
            )
            written += 1

    conn.commit()
    return written


def main() -> int:
    conn = _connect()
    try:
        ensure_tables(conn)
        n = build_alignments(conn, candidate_limit=90, market_limit=900)
        crossfeed = _crossfeed_polymarket_to_equity(conn)
        print(f"POLY_ALIGN: setups={n} crossfeed_signals={crossfeed}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
