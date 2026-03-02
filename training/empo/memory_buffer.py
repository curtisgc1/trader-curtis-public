#!/usr/bin/env python3
"""
EMPO² Memory Buffer — Trade reflection storage and retrieval.

Paper reference: arXiv:2602.23008, Section 3.1 (Memory Mechanism)

Stores reflective "tips" generated after each trade outcome:
  - What happened (direction, PnL, market conditions)
  - What the signal source got right/wrong
  - Actionable insight for future similar trades

Retrieved by cosine similarity against current market state embedding.
Tips condition the model's trade evaluation, improving signal quality.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "trades.db"

# Max tips retrieved per state (paper uses 10)
MAX_TIPS_PER_QUERY = 10

# Similarity threshold for retrieval (paper uses 0.5)
SIMILARITY_THRESHOLD = 0.5

# Similarity threshold for exploration novelty
NOVELTY_THRESHOLD = 0.7


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create memory buffer tables if they don't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS empo_memory_tips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            route_id INTEGER,
            ticker TEXT NOT NULL DEFAULT '',
            venue TEXT NOT NULL DEFAULT '',
            source_tag TEXT NOT NULL DEFAULT '',
            timeframe TEXT NOT NULL DEFAULT '',
            market_regime TEXT NOT NULL DEFAULT '',
            tip_text TEXT NOT NULL,
            embedding_json TEXT NOT NULL DEFAULT '[]',
            hgrm_reward REAL NOT NULL DEFAULT 0.0,
            pnl_percent REAL NOT NULL DEFAULT 0.0,
            direction TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS empo_state_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            state_hash TEXT NOT NULL,
            embedding_json TEXT NOT NULL DEFAULT '[]',
            visit_count INTEGER NOT NULL DEFAULT 1,
            last_visit TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_empo_tips_ticker
        ON empo_memory_tips(ticker)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_empo_visits_hash
        ON empo_state_visits(state_hash)
        """
    )
    conn.commit()


def _text_to_embedding(text: str) -> np.ndarray:
    """
    Convert text to embedding vector.

    Uses a simple TF-IDF-like hash embedding for fast local operation.
    Can be upgraded to sentence-transformers or Ollama embeddings later.
    """
    # Simple bag-of-words hash embedding (128-dim)
    # Sufficient for cosine similarity retrieval of trade tips
    dim = 128
    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    for w in words:
        h = hash(w) % dim
        vec[h] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = float(np.dot(a, b))
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _state_text(ticker: str, venue: str, source_tag: str,
                timeframe: str = "", regime: str = "") -> str:
    """Build state text for embedding from market context."""
    parts = [ticker, venue, source_tag]
    if timeframe:
        parts.append(timeframe)
    if regime:
        parts.append(regime)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Tip generation (post-trade reflection)
# ---------------------------------------------------------------------------

def generate_tip(
    ticker: str,
    venue: str,
    source_tag: str,
    direction: str,
    pnl_percent: float,
    route_score: float,
    hgrm_reward: float,
    strategy_tag: str = "",
    timeframe: str = "",
    market_regime: str = "",
    ollama_model: Optional[str] = None,
) -> str:
    """
    Generate a reflective tip from a trade outcome.

    If ollama_model is provided, uses LLM for richer reflection.
    Otherwise generates a structured rule-based tip.
    """
    if ollama_model:
        return _generate_tip_llm(
            ticker, venue, source_tag, direction, pnl_percent,
            route_score, hgrm_reward, strategy_tag, timeframe,
            market_regime, ollama_model,
        )
    return _generate_tip_rule(
        ticker, venue, source_tag, direction, pnl_percent,
        route_score, hgrm_reward, strategy_tag, timeframe,
        market_regime,
    )


def _generate_tip_rule(
    ticker: str, venue: str, source_tag: str, direction: str,
    pnl_pct: float, route_score: float, hgrm_reward: float,
    strategy_tag: str, timeframe: str, regime: str,
) -> str:
    """Rule-based tip generation (fast, no LLM needed)."""
    outcome = "profit" if pnl_pct > 0 else "loss"
    strength = "strong" if abs(pnl_pct) > 3.0 else "moderate" if abs(pnl_pct) > 1.0 else "small"
    dir_label = direction if direction in ("long", "short") else "neutral"

    parts = []
    parts.append(
        f"{ticker} {dir_label} on {venue} via {source_tag}: "
        f"{strength} {outcome} ({pnl_pct:+.1f}%)."
    )

    if hgrm_reward > 0.3:
        parts.append(f"Signal was well-calibrated (reward={hgrm_reward:.2f}).")
    elif hgrm_reward < -0.3:
        parts.append(f"Signal was poorly calibrated (reward={hgrm_reward:.2f}).")

    if route_score > 70 and pnl_pct < -1:
        parts.append("High-confidence signal underperformed — check for regime shift.")
    elif route_score < 40 and pnl_pct > 2:
        parts.append("Low-confidence signal outperformed — may indicate hidden edge.")

    if timeframe:
        parts.append(f"Timeframe: {timeframe}.")
    if regime:
        parts.append(f"Market regime: {regime}.")

    return " ".join(parts)


def _generate_tip_llm(
    ticker: str, venue: str, source_tag: str, direction: str,
    pnl_pct: float, route_score: float, hgrm_reward: float,
    strategy_tag: str, timeframe: str, regime: str,
    model: str,
) -> str:
    """LLM-based tip generation via Ollama."""
    import subprocess

    prompt = (
        "Generate a single-sentence trading reflection (under 100 words) from this outcome:\n"
        f"Ticker: {ticker}, Venue: {venue}, Source: {source_tag}\n"
        f"Direction: {direction}, PnL: {pnl_pct:+.1f}%, Score: {route_score:.0f}\n"
        f"Reward: {hgrm_reward:.2f}, Strategy: {strategy_tag}\n"
        f"Timeframe: {timeframe}, Regime: {regime}\n"
        "Focus on: what went right/wrong, actionable insight for next similar trade."
    )
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=30,
        )
        tip = result.stdout.strip()
        if tip and len(tip) < 500:
            return tip
    except Exception:
        pass
    # Fallback to rule-based
    return _generate_tip_rule(
        ticker, venue, source_tag, direction, pnl_pct,
        route_score, hgrm_reward, strategy_tag, timeframe, regime,
    )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store_tip(
    conn: sqlite3.Connection,
    tip_text: str,
    ticker: str = "",
    venue: str = "",
    source_tag: str = "",
    timeframe: str = "",
    market_regime: str = "",
    route_id: Optional[int] = None,
    hgrm_reward: float = 0.0,
    pnl_percent: float = 0.0,
    direction: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """Store a tip in the memory buffer. Returns tip ID."""
    ensure_tables(conn)

    state = _state_text(ticker, venue, source_tag, timeframe, market_regime)
    emb = _text_to_embedding(f"{state} {tip_text}")

    cur = conn.execute(
        """
        INSERT INTO empo_memory_tips
        (created_at, route_id, ticker, venue, source_tag, timeframe,
         market_regime, tip_text, embedding_json, hgrm_reward,
         pnl_percent, direction, metadata_json)
        VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            route_id, ticker, venue, source_tag, timeframe,
            market_regime, tip_text, json.dumps(emb.tolist()),
            hgrm_reward, pnl_percent, direction,
            json.dumps(metadata or {}),
        ),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Retrieval (cosine similarity search)
# ---------------------------------------------------------------------------

def retrieve_tips(
    conn: sqlite3.Connection,
    ticker: str = "",
    venue: str = "",
    source_tag: str = "",
    timeframe: str = "",
    regime: str = "",
    max_tips: int = MAX_TIPS_PER_QUERY,
    threshold: float = SIMILARITY_THRESHOLD,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant tips by cosine similarity to current state.

    Paper: tipst <- Retr(ot; M) subset of M, limited to 10 tips.
    """
    ensure_tables(conn)

    state = _state_text(ticker, venue, source_tag, timeframe, regime)
    query_emb = _text_to_embedding(state)

    cur = conn.execute(
        "SELECT id, tip_text, embedding_json, hgrm_reward, ticker, venue, source_tag FROM empo_memory_tips"
    )

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in cur.fetchall():
        tip_id, tip_text, emb_json, reward, t_ticker, t_venue, t_source = row
        try:
            emb = np.array(json.loads(emb_json), dtype=np.float32)
        except Exception:
            continue
        sim = _cosine_sim(query_emb, emb)
        if sim >= threshold:
            scored.append((sim, {
                "id": tip_id,
                "tip_text": tip_text,
                "similarity": round(sim, 4),
                "hgrm_reward": reward,
                "ticker": t_ticker,
                "venue": t_venue,
                "source_tag": t_source,
            }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:max_tips]]


def format_tips_for_prompt(tips: List[Dict[str, Any]]) -> str:
    """Format retrieved tips into a prompt section."""
    if not tips:
        return ""
    lines = ["Past trade reflections (use as context):"]
    for i, t in enumerate(tips, 1):
        lines.append(f"  {i}. {t['tip_text']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exploration bonus (intrinsic reward for novel states)
# ---------------------------------------------------------------------------

def compute_exploration_bonus(
    conn: sqlite3.Connection,
    ticker: str,
    venue: str,
    source_tag: str,
    timeframe: str = "",
    regime: str = "",
) -> float:
    """
    Paper: r_intrinsic = 1/n where n = visit count of similar states.

    Returns exploration bonus in [0, 1].
    Novel states get bonus=1.0, frequently-visited states approach 0.
    """
    ensure_tables(conn)

    state = _state_text(ticker, venue, source_tag, timeframe, regime)
    query_emb = _text_to_embedding(state)
    state_hash = str(hash(state))

    # Check if this exact state has been visited
    cur = conn.execute(
        "SELECT visit_count FROM empo_state_visits WHERE state_hash=?",
        (state_hash,),
    )
    row = cur.fetchone()
    if row:
        n = row[0]
        conn.execute(
            "UPDATE empo_state_visits SET visit_count=visit_count+1, last_visit=datetime('now') WHERE state_hash=?",
            (state_hash,),
        )
    else:
        n = 0
        conn.execute(
            "INSERT INTO empo_state_visits (created_at, state_hash, embedding_json, visit_count, last_visit) VALUES (datetime('now'), ?, ?, 1, datetime('now'))",
            (state_hash, json.dumps(query_emb.tolist())),
        )
    conn.commit()

    # r_intrinsic = 1 / (n + 1)
    return 1.0 / (n + 1)


def buffer_size(conn: sqlite3.Connection) -> int:
    """Return number of tips in memory buffer."""
    ensure_tables(conn)
    cur = conn.execute("SELECT COUNT(*) FROM empo_memory_tips")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    conn = _connect()
    ensure_tables(conn)

    print("=" * 60)
    print("EMPO² MEMORY BUFFER — status")
    print("=" * 60)
    print(f"  Tips stored: {buffer_size(conn)}")

    cur = conn.execute("SELECT COUNT(*) FROM empo_state_visits")
    print(f"  States visited: {cur.fetchone()[0]}")

    # Show recent tips
    cur = conn.execute(
        "SELECT ticker, venue, source_tag, tip_text, hgrm_reward FROM empo_memory_tips ORDER BY id DESC LIMIT 5"
    )
    rows = cur.fetchall()
    if rows:
        print(f"\n  Recent tips:")
        for ticker, venue, src, tip, reward in rows:
            print(f"    [{ticker}/{venue}] reward={reward:.2f} — {tip[:80]}...")

    conn.close()
