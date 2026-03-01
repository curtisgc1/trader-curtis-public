#!/usr/bin/env python3
"""
Discover high-value finance X accounts using xAI Grok search.

Runs daily to find new accounts that publicly call trades with cashtags.
Discovered accounts go into x_discovery_candidates for manual review
before being added to tracked_x_sources.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
SECRETS_PATH = Path.home() / ".secrets" / "xai-api-key.json"
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL = "grok-3"

_JSON_SCHEMA = (
    'Return ONLY a JSON array of 20+ objects with these exact keys: '
    '{"handle": "username_without_at", "display_name": "...", "followers": 12345, '
    '"description": "...", "sample_call": "example tweet text"}. '
    "No markdown, no explanation, just the JSON array."
)

STOCKS_DISCOVERY_PROMPT = (
    "Search X for the most active stock trading accounts that call specific equity trades "
    "with cashtags ($TSLA, $NVDA, $AAPL, $META, $AMZN). Focus on accounts that: post "
    "entry/exit levels for stocks, have >10k followers, post at least weekly. "
    "Exclude crypto-only accounts, news outlets, and bots. " + _JSON_SCHEMA
)

CRYPTO_DISCOVERY_PROMPT = (
    "Search X for the most active crypto trading accounts that call specific crypto trades "
    "($BTC, $ETH, $SOL, $DOGE, $XRP, $AVAX). Focus on accounts that: post entry/exit for "
    "crypto pairs, discuss on-chain signals, have >5k followers, post at least weekly. "
    "Exclude stock-only accounts, news outlets, and bots. " + _JSON_SCHEMA
)

POLYMARKET_DISCOVERY_PROMPT = (
    "Search X for the most active prediction market and Polymarket traders who post about "
    "political outcomes, event contracts, and probability trading. Focus on accounts that "
    "discuss specific Polymarket positions, odds, edge, and outcomes. Have >2k followers. "
    "Exclude generic news accounts and bots. " + _JSON_SCHEMA
)

NETWORK_SEED_TEMPLATE = (
    "Search X for finance accounts similar to {seeds}. "
    "Who do these accounts interact with, retweet, or reply to? "
    "Who else calls specific stock/crypto trades in a similar style? " + _JSON_SCHEMA
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_api_key() -> str:
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(f"xAI API key not found at {SECRETS_PATH}")
    data = json.loads(SECRETS_PATH.read_text())
    key = str(data.get("api_key") or "").strip()
    if not key:
        raise ValueError("api_key is empty in xai-api-key.json")
    return key


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS x_discovery_candidates (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          discovered_at TEXT NOT NULL,
          handle TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL DEFAULT '',
          followers INTEGER NOT NULL DEFAULT 0,
          description TEXT NOT NULL DEFAULT '',
          sample_call TEXT NOT NULL DEFAULT '',
          discovery_source TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new',
          notes TEXT NOT NULL DEFAULT '',
          kol_category TEXT NOT NULL DEFAULT 'stocks'
        )
        """
    )
    # Migration: add kol_category if missing
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(x_discovery_candidates)")
    cols = {row[1] for row in cur.fetchall()}
    if "kol_category" not in cols:
        conn.execute("ALTER TABLE x_discovery_candidates ADD COLUMN kol_category TEXT NOT NULL DEFAULT 'stocks'")
    conn.commit()


def normalize_handle(value: Any) -> str:
    h = str(value or "").strip().lstrip("@").lower()
    h = re.sub(r"[^a-z0-9_]", "", h)
    return h


_HANDLE_TABLES = frozenset({"tracked_x_sources", "x_discovery_candidates"})


def get_existing_handles(conn: sqlite3.Connection) -> set:
    handles: set = set()
    cur = conn.cursor()
    for table in _HANDLE_TABLES:
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        if cur.fetchone():
            # table name is from the frozen allowlist, safe for interpolation
            cur.execute(f"SELECT lower(COALESCE(handle,'')) FROM {table}")
            for (h,) in cur.fetchall():
                if h:
                    handles.add(h)
    return handles


def get_top_performers(conn: sqlite3.Connection, limit: int = 3) -> List[str]:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='route_outcomes'")
    if not cur.fetchone():
        return ["contrariancurse", "tradestl", "off_the_tape"]
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tracked_x_sources'")
    if not cur.fetchone():
        return ["contrariancurse", "tradestl", "off_the_tape"]
    cur.execute(
        """
        SELECT ro.source_tag,
               COUNT(*) AS n,
               SUM(CASE WHEN ro.resolution='win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS wr
        FROM route_outcomes ro
        JOIN tracked_x_sources tx ON lower(tx.handle)=lower(ro.source_tag) AND tx.active=1
        GROUP BY ro.source_tag
        HAVING n >= 5
        ORDER BY wr DESC, n DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    if not rows:
        return ["contrariancurse", "tradestl", "off_the_tape"]
    return [str(r[0]) for r in rows]


def grok_search(api_key: str, prompt: str) -> List[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": XAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You have access to the x_search tool. Use it to search X/Twitter "
                    "for finance/trading accounts. Return results as a raw JSON array only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "x_search",
                    "description": "Search X (Twitter) posts, users, and threads",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for X",
                            }
                        },
                        "required": ["query"],
                    },
                },
            }
        ],
    }
    resp = requests.post(
        f"{XAI_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    content = ""
    for choice in data.get("choices", []):
        msg = choice.get("message", {})
        content += str(msg.get("content") or "")
    return _extract_accounts(content)


def _extract_accounts(text: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].strip().startswith("```") else 0
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])
    bracket = text.find("[")
    if bracket >= 0:
        text = text[bracket:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        handle = normalize_handle(item.get("handle") or item.get("username") or "")
        if not handle:
            continue
        out.append(
            {
                "handle": handle,
                "display_name": str(item.get("display_name") or item.get("name") or ""),
                "followers": int(item.get("followers") or item.get("follower_count") or 0),
                "description": str(item.get("description") or item.get("bio") or ""),
                "sample_call": str(item.get("sample_call") or item.get("sample_tweet") or ""),
            }
        )
    return out


def insert_candidates(
    conn: sqlite3.Connection,
    accounts: List[Dict[str, Any]],
    existing: set,
    source: str,
    kol_category: str = "stocks",
) -> int:
    inserted = 0
    for acct in accounts:
        handle = acct["handle"]
        if handle in existing:
            continue
        conn.execute(
            """
            INSERT INTO x_discovery_candidates
            (discovered_at, handle, display_name, followers, description, sample_call, discovery_source, status, notes, kol_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new', '', ?)
            ON CONFLICT(handle) DO UPDATE SET
              display_name=COALESCE(NULLIF(excluded.display_name,''), x_discovery_candidates.display_name),
              followers=MAX(excluded.followers, x_discovery_candidates.followers),
              description=COALESCE(NULLIF(excluded.description,''), x_discovery_candidates.description),
              sample_call=COALESCE(NULLIF(excluded.sample_call,''), x_discovery_candidates.sample_call)
            """,
            (
                now_iso(),
                handle,
                acct["display_name"],
                acct["followers"],
                acct["description"],
                acct["sample_call"],
                source,
                kol_category,
            ),
        )
        existing.add(handle)
        inserted += 1
    conn.commit()
    return inserted


def main() -> int:
    api_key = load_api_key()

    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.execute("PRAGMA busy_timeout=20000")
    try:
        ensure_tables(conn)
        existing = get_existing_handles(conn)
        total_discovered = 0
        total_returned = 0

        # Category-specific discovery prompts
        category_prompts = [
            ("stocks", STOCKS_DISCOVERY_PROMPT, "stocks_discovery"),
            ("crypto", CRYPTO_DISCOVERY_PROMPT, "crypto_discovery"),
            ("polymarket", POLYMARKET_DISCOVERY_PROMPT, "polymarket_discovery"),
        ]
        for cat, prompt, source in category_prompts:
            print(f"DISCOVER_X: Running {cat} discovery search...")
            accounts = grok_search(api_key, prompt)
            n = insert_candidates(conn, accounts, existing, source, kol_category=cat)
            total_discovered += n
            total_returned += len(accounts)
            print(f"DISCOVER_X: {cat} discovery found {len(accounts)} accounts, {n} new")

        # Network-seeded from top performers (mixed category)
        top_handles = get_top_performers(conn)
        seeds = ", ".join(f"@{h}" for h in top_handles)
        print(f"DISCOVER_X: Running network-seeded search from {seeds}...")
        network_prompt = NETWORK_SEED_TEMPLATE.format(seeds=seeds)
        network_accounts = grok_search(api_key, network_prompt)
        n_network = insert_candidates(conn, network_accounts, existing, "network_seed", kol_category="mixed")
        total_discovered += n_network
        total_returned += len(network_accounts)
        print(f"DISCOVER_X: Network seed found {len(network_accounts)} accounts, {n_network} new")

        print(
            f"DISCOVER_X complete: "
            f"discovered={total_discovered} new, "
            f"already_tracked={total_returned - total_discovered}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
