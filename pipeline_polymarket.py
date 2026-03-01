#!/usr/bin/env python3
"""
Polymarket pipeline:
- ingest active markets from Gamma API
- compute strategy candidates: POLY_ALPHA / POLY_COPY / POLY_ARB / POLY_MOMENTUM / POLY_OPTIONS_ARB
- multi-source alpha aggregation with longshot bias correction
- gabagool-style intra-market arbitrage with profit calculation
- performance-weighted wallet copy signals
"""

import json
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
GAMMA_BASE = "https://gamma-api.polymarket.com"


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


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_markets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          fetched_at TEXT NOT NULL,
          market_id TEXT NOT NULL UNIQUE,
          condition_id TEXT NOT NULL DEFAULT '',
          event_id TEXT NOT NULL DEFAULT '',
          slug TEXT NOT NULL DEFAULT '',
          question TEXT NOT NULL DEFAULT '',
          outcomes_json TEXT NOT NULL DEFAULT '[]',
          outcome_prices_json TEXT NOT NULL DEFAULT '[]',
          clob_token_ids_json TEXT NOT NULL DEFAULT '[]',
          liquidity REAL NOT NULL DEFAULT 0,
          volume_24h REAL NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          closed INTEGER NOT NULL DEFAULT 0,
          market_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    # Backfill new columns for existing DBs.
    if _table_exists(conn, "polymarket_markets") and not _column_exists(conn, "polymarket_markets", "condition_id"):
        conn.execute("ALTER TABLE polymarket_markets ADD COLUMN condition_id TEXT NOT NULL DEFAULT ''")
    if _table_exists(conn, "polymarket_markets") and not _column_exists(conn, "polymarket_markets", "clob_token_ids_json"):
        conn.execute("ALTER TABLE polymarket_markets ADD COLUMN clob_token_ids_json TEXT NOT NULL DEFAULT '[]'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          strategy_id TEXT NOT NULL,
          market_id TEXT NOT NULL,
          slug TEXT NOT NULL DEFAULT '',
          question TEXT NOT NULL DEFAULT '',
          outcome TEXT NOT NULL,
          implied_prob REAL NOT NULL,
          model_prob REAL NOT NULL,
          edge REAL NOT NULL,
          confidence REAL NOT NULL,
          source_tag TEXT NOT NULL DEFAULT '',
          rationale TEXT NOT NULL DEFAULT '',
          market_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    # Backfill arb_pair_id column for gabagool-style paired arb.
    if _table_exists(conn, "polymarket_candidates") and not _column_exists(conn, "polymarket_candidates", "arb_pair_id"):
        conn.execute("ALTER TABLE polymarket_candidates ADD COLUMN arb_pair_id TEXT NOT NULL DEFAULT ''")
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
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def fetch_markets(limit: int = 150) -> List[Dict[str, Any]]:
    # Try common Gamma endpoints with fallback.
    endpoints = [
        f"{GAMMA_BASE}/markets?active=true&closed=false&limit={limit}",
        f"{GAMMA_BASE}/events?active=true&closed=false&limit={limit}",
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=20)
            if res.status_code >= 400:
                continue
            data = res.json()
        except Exception:
            continue
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Common wrappers.
            for k in ("data", "markets", "events"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
    return []


def normalize_market(raw: Dict[str, Any]) -> Dict[str, Any]:
    market_id = str(raw.get("id") or raw.get("marketId") or raw.get("conditionId") or "")
    condition_id = str(raw.get("conditionId") or raw.get("condition_id") or "")
    slug = str(raw.get("slug") or "")
    question = str(raw.get("question") or raw.get("title") or "")
    event_id = str(raw.get("eventId") or raw.get("event_id") or "")
    outcomes = raw.get("outcomes") or []
    outcome_prices = raw.get("outcomePrices") or raw.get("outcome_prices") or []
    clob_token_ids = raw.get("clobTokenIds") or raw.get("clob_token_ids") or []
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
            outcome_prices = []
    if isinstance(clob_token_ids, str):
        try:
            clob_token_ids = json.loads(clob_token_ids)
        except Exception:
            clob_token_ids = []
    liquidity = float(raw.get("liquidity") or raw.get("liquidityNum") or 0.0)
    volume_24h = float(raw.get("volume24hr") or raw.get("volume24h") or raw.get("volume") or 0.0)
    active = 1 if bool(raw.get("active", True)) else 0
    closed = 1 if bool(raw.get("closed", False)) else 0
    market_url = f"https://polymarket.com/market/{slug}" if slug else ""
    return {
        "market_id": market_id,
        "condition_id": condition_id,
        "event_id": event_id,
        "slug": slug,
        "question": question,
        "outcomes": outcomes if isinstance(outcomes, list) else [],
        "outcome_prices": outcome_prices if isinstance(outcome_prices, list) else [],
        "clob_token_ids": clob_token_ids if isinstance(clob_token_ids, list) else [],
        "liquidity": liquidity,
        "volume_24h": volume_24h,
        "active": active,
        "closed": closed,
        "market_url": market_url,
    }


def store_markets(conn: sqlite3.Connection, markets: List[Dict[str, Any]]) -> int:
    cur = conn.cursor()
    inserted = 0
    for m in markets:
        if not m["market_id"]:
            continue
        cur.execute(
            """
            INSERT INTO polymarket_markets
            (fetched_at, market_id, condition_id, event_id, slug, question, outcomes_json, outcome_prices_json, clob_token_ids_json, liquidity, volume_24h, active, closed, market_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
              fetched_at=excluded.fetched_at,
              condition_id=excluded.condition_id,
              event_id=excluded.event_id,
              slug=excluded.slug,
              question=excluded.question,
              outcomes_json=excluded.outcomes_json,
              outcome_prices_json=excluded.outcome_prices_json,
              clob_token_ids_json=excluded.clob_token_ids_json,
              liquidity=excluded.liquidity,
              volume_24h=excluded.volume_24h,
              active=excluded.active,
              closed=excluded.closed,
              market_url=excluded.market_url
            """,
            (
                now_iso(),
                m["market_id"],
                m["condition_id"],
                m["event_id"],
                m["slug"],
                m["question"],
                json.dumps(m["outcomes"]),
                json.dumps(m["outcome_prices"]),
                json.dumps(m["clob_token_ids"]),
                m["liquidity"],
                m["volume_24h"],
                m["active"],
                m["closed"],
                m["market_url"],
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def _latest_source_reliability(conn: sqlite3.Connection) -> float:
    if not _table_exists(conn, "source_scores"):
        return 0.5
    cur = conn.cursor()
    cur.execute("SELECT AVG(reliability_score) FROM source_scores")
    v = float((cur.fetchone() or [50.0])[0] or 50.0)
    return max(0.0, min(1.0, v / 100.0))


def _event_bias(conn: sqlite3.Connection, question: str) -> float:
    if not _table_exists(conn, "event_alerts"):
        return 0.0
    q = question.lower()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(confidence,0.5), COALESCE(alert_message,''), COALESCE(direction,'')
        FROM event_alerts
        ORDER BY created_at DESC
        LIMIT 25
        """
    )
    bump = 0.0
    for conf, msg, direction in cur.fetchall():
        text = f"{msg} {direction}".lower()
        # rough keyword overlap.
        overlap = sum(1 for token in ("trump", "tariff", "iran", "btc", "fed", "war", "crypto", "election") if token in q and token in text)
        if overlap > 0:
            bump += min(0.08, 0.02 * overlap) * float(conf or 0.5)
    return max(-0.2, min(0.2, bump))


def _wallet_activity_by_slug(conn: sqlite3.Connection, lookback_hours: int = 48) -> Dict[str, List[Dict[str, Any]]]:
    if not _table_exists(conn, "polymarket_wallet_activity"):
        return {}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          lower(COALESCE(a.market_slug, '')),
          lower(COALESCE(a.outcome, '')),
          upper(COALESCE(a.side, '')),
          lower(COALESCE(a.handle, '')),
          COALESCE(MAX(a.timestamp_unix), 0) AS ts_last,
          COALESCE(SUM(COALESCE(a.usdc_size, 0)), 0) AS usdc_total,
          COALESCE(COUNT(*), 0) AS n_trades,
          COALESCE(MAX(s.reliability_score), 50.0) AS reliability
        FROM polymarket_wallet_activity a
        LEFT JOIN polymarket_wallet_scores s
          ON lower(COALESCE(s.handle,'')) = lower(COALESCE(a.handle,''))
        WHERE COALESCE(a.timestamp_unix, 0) >= (strftime('%s','now') - ?)
        GROUP BY
          lower(COALESCE(a.market_slug, '')),
          lower(COALESCE(a.outcome, '')),
          upper(COALESCE(a.side, '')),
          lower(COALESCE(a.handle, ''))
        """,
        (int(max(1, lookback_hours) * 3600),),
    )
    out: Dict[str, List[Dict[str, Any]]] = {}

    def _norm_slug(s: str) -> str:
        # 5m up/down markets often rotate by trailing epoch; normalize so copy-trade signal survives interval roll.
        return re.sub(r"-\\d{9,}$", "", str(s or "").strip().lower())

    for slug, outcome, side, handle, ts_last, usdc_total, n_trades, reliability in cur.fetchall():
        s = str(slug or "").strip()
        if not s:
            continue
        row = {
            "outcome": str(outcome or "").strip(),
            "side": str(side or "").strip(),
            "handle": str(handle or "").strip(),
            "ts_last": int(ts_last or 0),
            "usdc_total": float(usdc_total or 0.0),
            "n_trades": int(n_trades or 0),
            "reliability": float(reliability or 50.0),
        }
        s_norm = _norm_slug(s)
        out.setdefault(s, []).append(row)
        if s_norm and s_norm != s:
            out.setdefault(s_norm, []).append(row)
    return out


def _wallet_signal_for_candidate(
    market_slug: str,
    outcome: str,
    wallet_activity: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    def _norm_slug(s: str) -> str:
        return re.sub(r"-\\d{9,}$", "", str(s or "").strip().lower())

    raw_slug = str(market_slug or "").lower().strip()
    items = list(wallet_activity.get(raw_slug, []))
    norm_slug = _norm_slug(raw_slug)
    if norm_slug and norm_slug != raw_slug:
        items.extend(wallet_activity.get(norm_slug, []))
    if not items:
        return {"score": 0.0, "handle": "", "reliability": 50.0, "count": 0}
    target = str(outcome or "").lower().strip()
    total = 0.0
    lead_handle = ""
    lead_weight = 0.0
    lead_reliability = 50.0
    count = 0
    for item in items:
        h = str(item.get("handle") or "").strip()
        side = str(item.get("side") or "BUY").upper()
        this_outcome = str(item.get("outcome") or "").lower().strip()
        rel = max(0.0, min(100.0, float(item.get("reliability") or 50.0)))
        usdc = max(0.0, float(item.get("usdc_total") or 0.0))
        # Reward consistent/active wallets but cap influence hard.
        weight = min(1.25, (rel / 100.0) * (1.0 + min(1.0, math.log1p(usdc) / 5.0)))
        if side not in {"BUY", "SELL"}:
            continue
        aligned = (this_outcome == target and bool(target)) or (this_outcome == "" and side == "BUY")
        direction = 1.0 if aligned else -0.6
        if side == "SELL":
            direction *= -1.0
        contribution = direction * weight
        total += contribution
        count += int(item.get("n_trades") or 0)
        if abs(contribution) > lead_weight:
            lead_weight = abs(contribution)
            lead_handle = h
            lead_reliability = rel
    return {
        "score": max(-2.0, min(2.0, total)),
        "handle": lead_handle,
        "reliability": lead_reliability,
        "count": count,
    }


def _get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row else default


def _longshot_bias_correction(implied: float) -> float:
    """Longshot bias: retail overpays for unlikely outcomes, underpays for favorites."""
    if implied < 0.15:
        return -(implied * 0.12)
    if implied > 0.85:
        return (1.0 - implied) * 0.10
    return 0.0


def _pipeline_signal_adjustment(conn: sqlite3.Connection, question: str) -> float:
    """Pull latest pipeline_signals for matching tickers and convert to probability adjustment."""
    if not _table_exists(conn, "pipeline_signals"):
        return 0.0
    q = question.lower()
    ticker_map = {
        "btc": "BTC", "bitcoin": "BTC",
        "eth": "ETH", "ethereum": "ETH",
        "sol": "SOL", "solana": "SOL",
        "xrp": "XRP", "ripple": "XRP",
        "doge": "DOGE", "dogecoin": "DOGE",
    }
    matched_ticker = None
    for keyword, ticker in ticker_map.items():
        if keyword in q:
            matched_ticker = ticker
            break
    if not matched_ticker:
        return 0.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT direction, score
        FROM pipeline_signals
        WHERE upper(asset)=?
        ORDER BY datetime(COALESCE(created_at,'1970-01-01')) DESC
        LIMIT 1
        """,
        (matched_ticker,),
    )
    row = cur.fetchone()
    if not row:
        return 0.0
    direction = str(row[0] or "").lower()
    score = max(0.0, min(100.0, float(row[1] or 0.0)))
    magnitude = (score / 100.0) * 0.08
    if direction in ("long", "buy", "bullish"):
        return magnitude
    if direction in ("short", "sell", "bearish"):
        return -magnitude
    return 0.0


def _historical_base_rate(conn: sqlite3.Connection, question: str) -> Optional[float]:
    """Compute historical hit rate for recurring market types from resolved kaggle data."""
    if not _table_exists(conn, "polymarket_kaggle_markets"):
        return None
    q = question.lower()
    keywords = []
    for tok in ("5 minute", "15 minute", "up or down", "above", "below", "price"):
        if tok in q:
            keywords.append(tok)
    if not keywords:
        return None
    conditions = []
    params = []
    for kw in keywords[:3]:
        conditions.append("lower(COALESCE(question,'')) LIKE ?")
        params.append(f"%{kw}%")
    like_clause = " AND ".join(conditions)
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN COALESCE(resolution,'') IN ('Yes','yes','1','true') THEN 1 ELSE 0 END) AS yes_count
            FROM polymarket_kaggle_markets
            WHERE {like_clause}
              AND COALESCE(resolution,'') != ''
            """,
            params,
        )
    except Exception:
        return None
    row = cur.fetchone()
    if not row or int(row[0] or 0) < 10:
        return None
    total = int(row[0])
    yes_count = int(row[1] or 0)
    return yes_count / total


def _wallet_performance_weight(
    conn: sqlite3.Connection, handle: str
) -> Dict[str, Any]:
    """Get wallet performance stats for copy-trade weighting."""
    result = {"win_rate": 0.0, "pnl_all": 0.0, "sample_size": 0, "qualified": False}
    if not handle:
        return result
    # Try polymarket_wallet_scores first (our computed scores)
    if _table_exists(conn, "polymarket_wallet_scores"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(win_rate,0), COALESCE(avg_pnl_pct,0), COALESCE(sample_size,0)
            FROM polymarket_wallet_scores
            WHERE lower(COALESCE(handle,''))=?
            LIMIT 1
            """,
            (handle.lower(),),
        )
        row = cur.fetchone()
        if row:
            wr = float(row[0] or 0)
            pnl = float(row[1] or 0)
            samples = int(row[2] or 0)
            min_wr = float(_get_control(conn, "polymarket_copy_min_wallet_winrate", "55"))
            min_samples = int(float(_get_control(conn, "polymarket_copy_min_wallet_samples", "10")))
            return {
                "win_rate": wr,
                "pnl_all": pnl,
                "sample_size": samples,
                "qualified": wr >= min_wr and samples >= min_samples,
            }
    return result


def _recency_decay(ts_last: int) -> float:
    """Apply recency decay: trades > 24h old get 50% weight, > 48h get 25%."""
    if ts_last <= 0:
        return 0.25
    age_hours = (time.time() - ts_last) / 3600.0
    if age_hours <= 24:
        return 1.0
    if age_hours <= 48:
        return 0.5
    return 0.25


def build_candidates(conn: sqlite3.Connection, limit: int = 120) -> int:
    cur = conn.cursor()
    cur.execute("DELETE FROM polymarket_candidates")
    src_rel = _latest_source_reliability(conn)

    wallet_activity = _wallet_activity_by_slug(conn, lookback_hours=48)

    cur.execute(
        """
        SELECT market_id, slug, question, outcomes_json, outcome_prices_json, liquidity, volume_24h, market_url
        FROM polymarket_markets
        WHERE active=1 AND closed=0
        ORDER BY volume_24h DESC, liquidity DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()

    copy_handles = set()
    if _table_exists(conn, "bookmark_alpha_ideas"):
        cur.execute(
            """
            SELECT lower(COALESCE(source_handle,''))
            FROM bookmark_alpha_ideas
            WHERE strategy_tag='POLY_COPY'
            ORDER BY id DESC
            LIMIT 100
            """
        )
        copy_handles.update([h for h in (_normalize_x_handle(r[0]) for r in cur.fetchall()) if h])
    if _table_exists(conn, "copy_trades"):
        cur.execute(
            """
            SELECT lower(COALESCE(source_handle,''))
            FROM copy_trades
            ORDER BY call_timestamp DESC
            LIMIT 100
            """
        )
        copy_handles.update([h for h in (_normalize_x_handle(r[0]) for r in cur.fetchall()) if h])
    tracked_copy_handles = set()
    tracked_alpha_handles = set()
    if _table_exists(conn, "tracked_x_sources"):
        cur.execute(
            """
            SELECT lower(COALESCE(handle,'')), COALESCE(role_copy,1), COALESCE(role_alpha,1)
            FROM tracked_x_sources
            WHERE COALESCE(active,1)=1
            """
        )
        for handle, role_copy, role_alpha in cur.fetchall():
            h = _normalize_x_handle(handle)
            if not h:
                continue
            if int(role_copy or 0) == 1:
                tracked_copy_handles.add(h)
            if int(role_alpha or 0) == 1:
                tracked_alpha_handles.add(h)

    # Phase 4: Multi-source alpha controls
    use_pipeline_signals = _get_control(conn, "polymarket_alpha_use_pipeline_signals", "1") == "1"
    use_longshot_correction = _get_control(conn, "polymarket_alpha_longshot_correction", "1") == "1"

    # Phase 3: Arb profit controls
    arb_min_profit_pct = float(_get_control(conn, "polymarket_arb_min_profit_pct", "1.0"))
    taker_fee_pct = float(_get_control(conn, "polymarket_taker_fee_pct", "3.15"))

    people_markets = (
        "election",
        "nominee",
        "president",
        "winner",
        "candidate",
        "poll",
        "prime minister",
        "parliament",
        "become the next",
        "next prime minister",
        "next president",
    )
    macro_markets = ("fed", "rate", "tariff", "war", "iran", "oil", "bitcoin", "btc", "ethereum", "eth", "crypto")
    created = 0
    for market_id, slug, question, outcomes_json, prices_json, liquidity, volume_24h, market_url in rows:
        try:
            outcomes = json.loads(outcomes_json or "[]")
            prices = [float(x) for x in json.loads(prices_json or "[]")]
        except Exception:
            continue
        if not outcomes or not prices or len(outcomes) != len(prices):
            continue

        # ── Phase 3: Gabagool-style intra-market arb ──────────────────
        # SAFETY: Only execute arb on strictly binary markets (exactly 2 outcomes).
        # Multi-outcome markets (3+) can lose both legs even if sum < 1.0.
        if len(prices) == 2 and len(outcomes) == 2:
            cost_per_pair = prices[0] + prices[1]
            if cost_per_pair > 0.01 and cost_per_pair < 1.0 and float(liquidity or 0) >= 5000:
                guaranteed_profit_pct = ((1.0 - cost_per_pair) / cost_per_pair) * 100.0
                net_profit_pct = guaranteed_profit_pct - (taker_fee_pct * 2)
                if net_profit_pct > arb_min_profit_pct:
                    pair_id = f"arb-{market_id}-{int(time.time())}"
                    for i, outcome in enumerate(outcomes[:2]):
                        implied = max(0.01, min(0.99, float(prices[i])))
                        cur.execute(
                            """
                            INSERT INTO polymarket_candidates
                            (created_at, strategy_id, market_id, slug, question, outcome,
                             implied_prob, model_prob, edge, confidence, source_tag,
                             rationale, market_url, status, arb_pair_id)
                            VALUES (?, 'POLY_ARB', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                            """,
                            (
                                now_iso(), market_id, slug, question, str(outcome),
                                implied, implied,
                                round(net_profit_pct, 4), 0.90,
                                "POLY_ARB:gabagool",
                                f"gabagool arb cost={cost_per_pair:.4f} guaranteed={guaranteed_profit_pct:.2f}% "
                                f"net={net_profit_pct:.2f}% (fee={taker_fee_pct}%x2) "
                                f"liq={float(liquidity or 0):.0f}",
                                market_url, pair_id,
                            ),
                        )
                        created += 1
                    continue  # Skip per-outcome processing for arb markets

        # ── Per-outcome candidate generation ──────────────────────────
        for i, outcome in enumerate(outcomes):
            implied = max(0.0, min(1.0, float(prices[i] if i < len(prices) else 0.0)))
            q = question.lower()

            # ── Phase 4: Multi-source probability aggregation ─────────
            # Component weights (sum to ~1.0)
            w_market = 0.40
            w_event = 0.15
            w_wallet = 0.15
            w_pipeline = 0.12
            w_historical = 0.10
            w_longshot = 0.08

            # 1. Base: market implied probability
            base_prob = implied

            # 2. Event bias (existing)
            event_adj = _event_bias(conn, question) * (1.1 if i == 0 else (-1.1 if i == 1 else 0.0))

            # 3. Source reliability adjustment
            src_adj = (src_rel - 0.5) * 0.06

            # 4. Wallet consensus
            wallet_sig = _wallet_signal_for_candidate(slug, str(outcome), wallet_activity)
            wallet_score = float(wallet_sig.get("score") or 0.0)
            wallet_handle = str(wallet_sig.get("handle") or "")
            wallet_adj = wallet_score * 0.04

            # 5. Pipeline signal crossover (Phase 4)
            pipeline_adj = 0.0
            if use_pipeline_signals:
                pipeline_adj = _pipeline_signal_adjustment(conn, question)
                if i == 1:
                    pipeline_adj = -pipeline_adj
                elif i >= 2:
                    pipeline_adj = 0.0

            # 6. Historical base rate
            hist_rate = _historical_base_rate(conn, question)
            hist_adj = 0.0
            if hist_rate is not None:
                if i == 0:
                    hist_adj = (hist_rate - implied) * 0.5
                elif i == 1:
                    hist_adj = ((1.0 - hist_rate) - implied) * 0.5

            # 7. Longshot bias correction
            longshot_adj = 0.0
            if use_longshot_correction:
                longshot_adj = _longshot_bias_correction(implied)
                if i == 1:
                    longshot_adj = -longshot_adj
                elif i >= 2:
                    longshot_adj = 0.0

            # Weighted aggregation (bounded)
            model = (
                w_market * base_prob
                + w_event * (base_prob + event_adj)
                + w_wallet * (base_prob + wallet_adj)
                + w_pipeline * (base_prob + pipeline_adj)
                + w_historical * (base_prob + hist_adj)
                + w_longshot * (base_prob + longshot_adj)
                + src_adj
            )
            model = max(0.01, min(0.99, model))
            edge = round((model - implied) * 100.0, 4)
            conf = round(max(0.35, min(0.9, abs(edge) / 20.0 + 0.45)), 4)

            strategy = "POLY_ALPHA"
            src_tag = "POLY_ALPHA:internal"
            rationale = (
                f"alpha model vs implied; event={event_adj:+.4f} wallet={wallet_adj:+.4f} "
                f"pipeline={pipeline_adj:+.4f} hist={hist_adj:+.4f} longshot={longshot_adj:+.4f}; "
                f"liq={liquidity}; vol24h={volume_24h}"
            )

            # Wallet-informed confidence boost
            if abs(wallet_score) > 0.05:
                conf = round(max(0.35, min(0.95, conf + min(0.12, abs(wallet_score) * 0.06))), 4)

            # ── Phase 5: Performance-weighted copy strategy ───────────
            copy_hit = any(h and h in q for h in copy_handles)
            person_topic = any(tok in q for tok in people_markets)
            macro_topic = any(tok in q for tok in macro_markets)
            copy_watch_enabled = len(tracked_copy_handles) > 0
            alpha_watch_enabled = len(tracked_alpha_handles) > 0

            if abs(wallet_score) >= 0.35 and wallet_handle:
                perf = _wallet_performance_weight(conn, wallet_handle)
                # Apply recency decay
                ts_last = int(wallet_sig.get("ts_last", 0) if isinstance(wallet_sig, dict) else 0)
                decay = _recency_decay(ts_last)
                effective_score = wallet_score * decay

                if perf["qualified"]:
                    # High-quality wallet: auto-copy with boosted confidence
                    strategy = "POLY_COPY"
                    src_tag = f"POLY_COPY:wallet:{wallet_handle}"
                    conf = round(min(0.95, conf * (1.0 + perf["win_rate"] / 200.0)), 4)
                    rationale = (
                        f"wallet_copy boost={round(effective_score,3)} "
                        f"wallet={wallet_handle} win_rate={perf['win_rate']:.1f}% "
                        f"samples={perf['sample_size']} decay={decay:.2f}; "
                        f"liq={round(float(liquidity or 0.0),2)}"
                    )
                elif abs(effective_score) >= 0.25:
                    # Unqualified wallet: still generate but lower confidence
                    strategy = "POLY_COPY"
                    src_tag = f"POLY_COPY:wallet:{wallet_handle}:unqualified"
                    conf = round(max(0.35, conf * 0.7), 4)
                    rationale = (
                        f"wallet_copy (unqualified) boost={round(effective_score,3)} "
                        f"wallet={wallet_handle} win_rate={perf['win_rate']:.1f}% "
                        f"samples={perf['sample_size']} decay={decay:.2f}; "
                        f"liq={round(float(liquidity or 0.0),2)}"
                    )
            elif copy_hit or (person_topic and copy_watch_enabled):
                strategy = "POLY_COPY"
                src_tag = "POLY_COPY:watchlist"
                why = "handle-match" if copy_hit else "people-market+tracked-sources"
                rationale = (
                    f"copy prior market signal ({why}); "
                    f"tracked_copy_sources={len(tracked_copy_handles)}; liq={round(float(liquidity or 0.0),2)}"
                )
            elif macro_topic:
                strategy = "POLY_ALPHA"
                src_tag = "POLY_ALPHA:watchlist" if alpha_watch_enabled else "POLY_ALPHA:macro"
                rationale = (
                    f"macro-event alpha cue; "
                    f"tracked_alpha_sources={len(tracked_alpha_handles)}; liq={round(float(liquidity or 0.0),2)}"
                )

            if abs(edge) < 1.0:
                continue
            cur.execute(
                """
                INSERT INTO polymarket_candidates
                (created_at, strategy_id, market_id, slug, question, outcome, implied_prob, model_prob,
                 edge, confidence, source_tag, rationale, market_url, status, arb_pair_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '')
                """,
                (
                    now_iso(),
                    strategy,
                    market_id,
                    slug,
                    question,
                    str(outcome),
                    implied,
                    model,
                    edge,
                    conf,
                    src_tag,
                    rationale,
                    market_url,
                ),
            )
            created += 1
    conn.commit()
    return created


def main() -> int:
    conn = _connect()
    try:
        ensure_tables(conn)
        # Pull a wider market universe so ticker->market matching has enough coverage.
        raw = fetch_markets(limit=500)
        normalized = [normalize_market(x) for x in raw]
        markets_written = store_markets(conn, normalized)
        candidates_written = build_candidates(conn, limit=350)

        # Phase 1: Momentum lag scanner (runs inline — time-sensitive)
        momentum_count = 0
        try:
            from polymarket_momentum_scanner import scan as momentum_scan
            momentum_count = momentum_scan(conn)
        except Exception as exc:
            print(f"POLYMARKET: momentum scanner skipped: {exc}")

        # Phase 2: Options bridge (runs inline)
        options_count = 0
        try:
            from polymarket_options_bridge import scan as options_scan
            options_count = options_scan(conn)
        except Exception as exc:
            print(f"POLYMARKET: options bridge skipped: {exc}")

        print(
            f"POLYMARKET: fetched={len(raw)} stored={markets_written} "
            f"candidates={candidates_written} momentum={momentum_count} options_arb={options_count}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
