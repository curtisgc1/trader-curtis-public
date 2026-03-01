#!/usr/bin/env python3
"""
Pipeline X Bridge: ingest tracked X handles into external_signals/copy_trades.

This keeps tracked handles connected to candidate scoring by writing
handle-attributed rows (source=<handle>) into external_signals.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DB_PATH = Path(__file__).parent / "data" / "trades.db"

CASHTAG_RE = re.compile(r"\$([A-Z]{1,6})\b")
ALT_TICKERS = {"BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "BNB", "LTC"}
LONG_WORDS = (" long", " buy", " bullish", " calls", " adding", " accumulate")
SHORT_WORDS = (" short", " sell", " bearish", " puts", " trim", " reduce")
NOISE_WORDS = ("not a trading related post", "not trading related")


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


def get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT,
          source TEXT,
          source_url TEXT,
          ticker TEXT,
          direction TEXT,
          confidence REAL,
          notes TEXT,
          status TEXT DEFAULT 'new'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS copy_trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_handle TEXT,
          ticker TEXT,
          call_type TEXT,
          entry_price REAL,
          call_timestamp TEXT,
          copied_timestamp TEXT,
          shares INTEGER,
          copied_entry REAL,
          stop_loss REAL,
          target REAL,
          status TEXT,
          outcome TEXT,
          pnl_pct REAL,
          lag_seconds INTEGER,
          notes TEXT
        )
        """
    )
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
    if not column_exists(conn, "tracked_x_sources", "x_api_enabled"):
        conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN x_api_enabled INTEGER NOT NULL DEFAULT 1")
    if not column_exists(conn, "tracked_x_sources", "kol_category"):
        conn.execute("ALTER TABLE tracked_x_sources ADD COLUMN kol_category TEXT NOT NULL DEFAULT 'stocks'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS x_consensus_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          source_count INTEGER NOT NULL DEFAULT 1,
          sources TEXT NOT NULL DEFAULT '[]',
          avg_confidence REAL NOT NULL DEFAULT 0.5,
          weighted_confidence REAL NOT NULL DEFAULT 0.5,
          window_hours INTEGER NOT NULL DEFAULT 24,
          status TEXT NOT NULL DEFAULT 'active',
          UNIQUE(ticker, direction)
        )
        """
    )
    conn.commit()


def parse_created_at(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return now_iso()
    try:
        dt = datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return now_iso()


def normalize_handle(value: Any) -> str:
    h = str(value or "").strip().lstrip("@").lower()
    h = re.sub(r"[^a-z0-9_]", "", h)
    return h


def _extract_json_array(stdout: str) -> List[Dict[str, Any]]:
    lines = str(stdout or "").splitlines()
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == "[":
            start = i
            break
    if start < 0:
        return []
    payload = "\n".join(lines[start:])
    try:
        data = json.loads(payload)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def fetch_tweets(handle: str, limit: int) -> List[Dict[str, Any]]:
    cmd = ["bird", "--plain", "user-tweets", handle, "-n", str(max(1, limit)), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    if proc.returncode != 0:
        return []
    return _extract_json_array(proc.stdout)


def parse_tweet_signals(tweet: Dict[str, Any]) -> List[Tuple[str, str, float, str]]:
    text = str(tweet.get("text") or "")
    quoted = tweet.get("quotedTweet") if isinstance(tweet.get("quotedTweet"), dict) else {}
    quoted_text = str(quoted.get("text") or "")
    combined = f"{text}\n{quoted_text}".strip()
    lower = f" {combined.lower()} "

    if not combined:
        return []
    for marker in NOISE_WORDS:
        if marker in lower:
            return []

    long_hit = any(word in lower for word in LONG_WORDS)
    short_hit = any(word in lower for word in SHORT_WORDS)
    if long_hit and short_hit:
        direction = ""
    elif long_hit:
        direction = "long"
    elif short_hit:
        direction = "short"
    else:
        direction = ""

    tickers = set(CASHTAG_RE.findall(combined.upper()))
    if not tickers:
        for tk in ALT_TICKERS:
            if re.search(rf"\b{re.escape(tk)}\b", combined.upper()):
                tickers.add(tk)

    if not tickers or not direction:
        return []

    confidence = 0.56
    if re.search(r"\b(entry|target|stop)\b", lower):
        confidence += 0.08
    if len(tickers) == 1:
        confidence += 0.03
    confidence = max(0.40, min(0.88, confidence))

    snippet = re.sub(r"\s+", " ", combined).strip()[:180]
    out: List[Tuple[str, str, float, str]] = []
    for ticker in sorted(tickers):
        out.append((ticker, direction, confidence, snippet))
    return out


def external_exists(conn: sqlite3.Connection, source: str, source_url: str, ticker: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM external_signals
        WHERE lower(COALESCE(source,''))=?
          AND COALESCE(source_url,'')=?
          AND upper(COALESCE(ticker,''))=?
        LIMIT 1
        """,
        (source.lower(), source_url, ticker.upper()),
    )
    return cur.fetchone() is not None


def copy_exists(conn: sqlite3.Connection, handle: str, ticker: str, call_ts: str, direction: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM copy_trades
        WHERE lower(COALESCE(source_handle,''))=?
          AND upper(COALESCE(ticker,''))=?
          AND COALESCE(call_timestamp,'')=?
          AND upper(COALESCE(call_type,''))=?
        LIMIT 1
        """,
        (handle.lower(), ticker.upper(), call_ts, direction.upper()),
    )
    return cur.fetchone() is not None


def load_tracked(conn: sqlite3.Connection, handle_limit: int) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT handle, COALESCE(role_copy,1), COALESCE(role_alpha,1), COALESCE(active,1), COALESCE(x_api_enabled,1)
        FROM tracked_x_sources
        WHERE COALESCE(active,1)=1
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (int(max(1, handle_limit)),),
    )
    out: List[Dict[str, Any]] = []
    for handle, role_copy, role_alpha, active, x_api_enabled in cur.fetchall():
        h = normalize_handle(handle)
        if not h:
            continue
        if int(active or 0) != 1:
            continue
        if int(x_api_enabled or 0) != 1:
            continue
        out.append(
            {
                "handle": h,
                "role_copy": int(role_copy or 0) == 1,
                "role_alpha": int(role_alpha or 0) == 1,
            }
        )
    return out


def build_x_consensus(conn: sqlite3.Connection) -> int:
    """Aggregate external_signals into x_consensus_signals for multi-handle agreement."""
    min_hits = int(float(get_control(conn, "x_consensus_min_hits", "3") or 3))

    # Expire old consensus
    conn.execute(
        "UPDATE x_consensus_signals SET status='expired' WHERE created_at < datetime('now', '-48 hours')"
    )

    cur = conn.cursor()

    # Load handle win rates from route_outcomes for weighted confidence
    win_rates: Dict[str, float] = {}
    if table_exists(conn, "route_outcomes"):
        cur.execute(
            """
            SELECT source_tag,
                   SUM(CASE WHEN resolution='win' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS wr
            FROM route_outcomes
            GROUP BY source_tag
            HAVING COUNT(*) >= 3
            """
        )
        for tag, wr in cur.fetchall():
            win_rates[str(tag).lower()] = float(wr or 0.5)

    # Get consensus groups meeting min_hits threshold
    cur.execute(
        """
        SELECT ticker, direction,
               GROUP_CONCAT(DISTINCT source) AS sources,
               COUNT(DISTINCT source) AS src_count,
               AVG(confidence) AS avg_conf
        FROM external_signals
        WHERE status IN ('new', 'active')
          AND created_at >= datetime('now', '-24 hours')
        GROUP BY ticker, direction
        HAVING COUNT(DISTINCT source) >= ?
        """,
        (min_hits,),
    )
    rows = cur.fetchall()

    # For each consensus group, compute per-source weighted confidence
    inserted = 0
    for ticker, direction, sources_csv, src_count, avg_conf in rows:
        source_list = [s.strip() for s in str(sources_csv or "").split(",") if s.strip()]

        # Query individual source confidences for this ticker+direction
        placeholders = ",".join("?" for _ in source_list)
        cur.execute(
            f"""
            SELECT source, MAX(confidence) AS conf
            FROM external_signals
            WHERE ticker=? AND direction=? AND source IN ({placeholders})
              AND status IN ('new', 'active')
              AND created_at >= datetime('now', '-24 hours')
            GROUP BY source
            """,
            [ticker, direction] + source_list,
        )
        src_confs = {str(r[0]).lower(): float(r[1] or 0.5) for r in cur.fetchall()}

        # Win-rate-weighted average of per-source confidences
        total_w = 0.0
        weighted_sum = 0.0
        for s in source_list:
            wr = win_rates.get(s.lower(), 0.5)
            conf = src_confs.get(s.lower(), float(avg_conf or 0.5))
            weighted_sum += wr * conf
            total_w += wr
        weighted_conf = (weighted_sum / total_w) if total_w > 0 else float(avg_conf or 0.5)

        conn.execute(
            """
            INSERT INTO x_consensus_signals
            (created_at, ticker, direction, source_count, sources, avg_confidence, weighted_confidence, window_hours, status)
            VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, 24, 'active')
            ON CONFLICT(ticker, direction) DO UPDATE SET
              created_at=excluded.created_at,
              source_count=excluded.source_count,
              sources=excluded.sources,
              avg_confidence=excluded.avg_confidence,
              weighted_confidence=excluded.weighted_confidence,
              status='active'
            """,
            (
                ticker,
                direction,
                int(src_count),
                json.dumps(source_list),
                round(float(avg_conf or 0.5), 4),
                round(weighted_conf, 4),
            ),
        )
        inserted += 1

    conn.commit()
    return inserted


def main() -> int:
    if not shutil.which("bird"):
        print("PIPELINE_X_BRIDGE skipped: bird CLI not found")
        return 0

    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA busy_timeout=20000")
    try:
        ensure_tables(conn)

        enabled = get_control(conn, "x_bridge_enabled", "1") == "1"
        if not enabled:
            print("PIPELINE_X_BRIDGE skipped: x_bridge_enabled=0")
            return 0

        posts_per_handle = int(float(get_control(conn, "x_bridge_posts_per_handle", "12") or 12))
        max_signals = int(float(get_control(conn, "x_bridge_max_signals_per_cycle", "80") or 80))
        max_handles = int(float(get_control(conn, "x_bridge_max_handles", "30") or 30))

        tracked = load_tracked(conn, handle_limit=max_handles)
        if not tracked:
            print("PIPELINE_X_BRIDGE: no tracked active handles")
            return 0

        inserted_external = 0
        inserted_copy = 0
        scanned_posts = 0
        fetch_errors = 0

        for item in tracked:
            if inserted_external >= max_signals:
                break

            handle = str(item["handle"])
            tweets = fetch_tweets(handle, limit=posts_per_handle)
            if not tweets:
                fetch_errors += 1
                continue

            for tweet in tweets:
                if inserted_external >= max_signals:
                    break

                tweet_id = str(tweet.get("id") or "").strip()
                if not tweet_id:
                    continue
                source_url = f"https://x.com/{handle}/status/{tweet_id}"
                call_ts = parse_created_at(str(tweet.get("createdAt") or ""))
                signals = parse_tweet_signals(tweet)
                if not signals:
                    continue
                scanned_posts += 1

                for ticker, direction, confidence, snippet in signals:
                    if inserted_external >= max_signals:
                        break

                    if not external_exists(conn, handle, source_url, ticker):
                        conn.execute(
                            """
                            INSERT INTO external_signals
                            (created_at, source, source_url, ticker, direction, confidence, notes, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                            """,
                            (
                                call_ts,
                                handle,
                                source_url,
                                ticker.upper(),
                                direction,
                                float(confidence),
                                f"x_bridge @{handle}: {snippet}",
                            ),
                        )
                        inserted_external += 1

                    if bool(item.get("role_copy")):
                        call_type = "LONG" if direction == "long" else "SHORT"
                        if not copy_exists(conn, handle, ticker, call_ts, call_type):
                            conn.execute(
                                """
                                INSERT INTO copy_trades
                                (source_handle, ticker, call_type, entry_price, call_timestamp, copied_timestamp, shares, copied_entry, stop_loss, target, status, notes)
                                VALUES (?, ?, ?, 0.0, ?, ?, 0, 0.0, 0.0, 0.0, 'OPEN', ?)
                                """,
                                (
                                    handle,
                                    ticker.upper(),
                                    call_type,
                                    call_ts,
                                    now_iso(),
                                    f"x_bridge tweet_id={tweet_id} url={source_url}",
                                ),
                            )
                            inserted_copy += 1

        conn.commit()

        consensus_count = build_x_consensus(conn)

        print(
            "PIPELINE_X_BRIDGE "
            f"handles={len(tracked)} scanned_posts={scanned_posts} "
            f"external_inserted={inserted_external} copy_inserted={inserted_copy} "
            f"fetch_empty={fetch_errors} consensus_signals={consensus_count}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
