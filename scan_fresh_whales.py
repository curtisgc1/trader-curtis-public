#!/usr/bin/env python3
"""
Fresh Whale Scanner — discover new Polymarket accounts placing large bets.

Scans recent trades on top-volume markets via the public CLOB endpoint,
filters for whale-size fills, profile-scrapes each trader to check account age,
and auto-adds qualifying wallets to tracked_polymarket_wallets.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DB = Path(__file__).parent / "data" / "trades.db"
CLOB_BASE = "https://clob.polymarket.com"
PROFILE_BASE = "https://polymarket.com"

CLOB_DELAY = 0.3
PROFILE_DELAY = 1.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB))


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fresh_whale_discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discovered_at TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            handle TEXT NOT NULL DEFAULT '',
            join_date TEXT NOT NULL DEFAULT '',
            account_age_days REAL NOT NULL DEFAULT 0,
            market_slug TEXT NOT NULL DEFAULT '',
            condition_id TEXT NOT NULL DEFAULT '',
            trade_size_usdc REAL NOT NULL DEFAULT 0,
            side TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL DEFAULT '',
            auto_tracked INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def _get_top_markets(conn: sqlite3.Connection, limit: int) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT condition_id, slug, volume_24h
        FROM polymarket_markets
        WHERE active=1 AND closed=0 AND condition_id != ''
        ORDER BY volume_24h DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    return [
        {"condition_id": r[0], "slug": r[1], "volume_24h": float(r[2] or 0)}
        for r in cur.fetchall()
    ]


def _fetch_market_trades(condition_id: str) -> List[Dict[str, Any]]:
    url = f"{CLOB_BASE}/live-activity/events/{condition_id}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code >= 400:
            return []
        data = resp.json()
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _filter_whale_trades(
    trades: List[Dict[str, Any]], min_usdc: float
) -> List[Dict[str, Any]]:
    whales: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        usdc = float(t.get("usdcSize") or 0)
        if usdc <= 0:
            size = float(t.get("size") or 0)
            price = float(t.get("price") or 0)
            usdc = size * price
        if usdc < min_usdc:
            continue
        addr = str(
            t.get("maker_address")
            or t.get("taker_address")
            or t.get("proxyAddress")
            or t.get("user")
            or ""
        ).strip().lower()
        if not addr:
            continue
        existing = whales.get(addr)
        if existing is None or usdc > float(existing.get("_usdc", 0)):
            whales[addr] = {
                **t,
                "_usdc": usdc,
                "_address": addr,
            }
    return list(whales.values())


def _recently_checked(
    conn: sqlite3.Connection, wallet_address: str, hours: int = 24
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM fresh_whale_discoveries
        WHERE lower(wallet_address) = lower(?)
          AND datetime(discovered_at) >= datetime('now', ? || ' hours')
        LIMIT 1
        """,
        (wallet_address, f"-{hours}"),
    )
    return cur.fetchone() is not None


def _extract_next_data(html: str) -> Dict[str, Any]:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.DOTALL
    )
    if not m:
        return {}
    try:
        payload = json.loads(m.group(1).strip())
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _extract_profile_blob(next_data: Dict[str, Any]) -> Dict[str, Any]:
    page_props = (
        ((next_data.get("props") or {}).get("pageProps") or {})
        if isinstance(next_data, dict)
        else {}
    )
    out: Dict[str, Any] = {
        "username": str(page_props.get("username") or "").strip().lstrip("@"),
        "wallet_address": str(
            page_props.get("proxyAddress")
            or page_props.get("baseAddress")
            or page_props.get("primaryAddress")
            or ""
        ).strip(),
    }

    dehydrated = page_props.get("dehydratedState") if isinstance(page_props, dict) else None
    queries = (dehydrated or {}).get("queries") if isinstance(dehydrated, dict) else None
    if not isinstance(queries, list):
        return out

    for q in queries:
        if not isinstance(q, dict):
            continue
        qk = q.get("queryKey")
        state = q.get("state") if isinstance(q.get("state"), dict) else {}
        data = state.get("data")

        key_text = ""
        if isinstance(qk, list):
            key_text = "|".join([str(x) for x in qk]).lower()
        else:
            key_text = str(qk or "").lower()

        if "user-stats" in key_text and isinstance(data, dict):
            out["join_date"] = str(data.get("joinDate") or "")
        elif "/api/profile/userdata" in key_text and isinstance(data, dict):
            if not out["wallet_address"]:
                out["wallet_address"] = str(data.get("proxyWallet") or "").strip()
            if not out["username"]:
                out["username"] = str(data.get("name") or "").strip().lstrip("@")

    return out


def _resolve_profile_by_address(wallet_address: str) -> Optional[Dict[str, Any]]:
    url = f"{PROFILE_BASE}/profile/{wallet_address}"
    try:
        resp = requests.get(url, timeout=25, allow_redirects=True)
        if resp.status_code >= 400:
            return None
    except Exception:
        return None
    next_data = _extract_next_data(resp.text or "")
    blob = _extract_profile_blob(next_data)
    if not blob.get("username") and not blob.get("join_date"):
        return None
    return {
        "handle": blob.get("username") or "",
        "join_date": blob.get("join_date") or "",
        "wallet_address": blob.get("wallet_address") or wallet_address,
    }


def _is_fresh_account(join_date_str: str, max_age_days: int) -> Tuple[bool, float]:
    if not join_date_str:
        return False, -1.0
    try:
        jd = datetime.fromisoformat(join_date_str.replace("Z", "+00:00"))
        if jd.tzinfo is None:
            jd = jd.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - jd).total_seconds() / 86400.0
        return age <= max_age_days, round(age, 2)
    except Exception:
        return False, -1.0


def _already_tracked(
    conn: sqlite3.Connection, wallet_address: str, handle: str
) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM tracked_polymarket_wallets
        WHERE lower(wallet_address) = lower(?)
           OR (? != '' AND lower(handle) = lower(?))
        LIMIT 1
        """,
        (wallet_address, handle, handle),
    )
    return cur.fetchone() is not None


def _auto_add_wallet(
    conn: sqlite3.Connection, handle: str, wallet_address: str, notes: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO tracked_polymarket_wallets
        (created_at, updated_at, handle, wallet_address, profile_url, role_copy, role_alpha, active, notes)
        VALUES (?, ?, ?, ?, ?, 1, 1, 1, ?)
        """,
        (
            now_iso(),
            now_iso(),
            handle,
            wallet_address,
            f"{PROFILE_BASE}/@{handle}" if handle else "",
            notes,
        ),
    )
    conn.commit()


def scan(conn: Optional[sqlite3.Connection] = None) -> int:
    own_conn = conn is None
    if own_conn:
        conn = _connect()

    ensure_tables(conn)

    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='execution_controls'")
    if not cur.fetchone():
        return 0

    cur.execute("SELECT value FROM execution_controls WHERE key='fw_scanner_enabled'")
    row = cur.fetchone()
    if row and str(row[0]) != "1":
        print("fw_scanner: disabled (fw_scanner_enabled=0)")
        return 0

    cur.execute("SELECT value FROM execution_controls WHERE key='fw_min_trade_usdc'")
    row = cur.fetchone()
    min_usdc = float(row[0]) if row else 50000.0

    cur.execute("SELECT value FROM execution_controls WHERE key='fw_max_account_age_days'")
    row = cur.fetchone()
    max_age_days = int(float(row[0])) if row else 7

    cur.execute("SELECT value FROM execution_controls WHERE key='fw_top_markets'")
    row = cur.fetchone()
    top_n = int(float(row[0])) if row else 30

    markets = _get_top_markets(conn, top_n)
    if not markets:
        print("fw_scanner: no active markets found")
        if own_conn:
            conn.close()
        return 0

    whale_addresses: Dict[str, Dict[str, Any]] = {}
    markets_scanned = 0

    for mkt in markets:
        cid = mkt["condition_id"]
        slug = mkt["slug"]
        trades = _fetch_market_trades(cid)
        whales = _filter_whale_trades(trades, min_usdc)

        for w in whales:
            addr = w["_address"]
            if addr not in whale_addresses or w["_usdc"] > whale_addresses[addr]["_usdc"]:
                whale_addresses[addr] = {
                    **w,
                    "_slug": slug,
                    "_cid": cid,
                }

        markets_scanned += 1
        if markets_scanned < len(markets):
            time.sleep(CLOB_DELAY)

    unique_whales = [v for v in whale_addresses.values()]
    skip_recent = 0
    profiles_checked = 0
    added = 0

    for whale in unique_whales:
        addr = whale["_address"]

        if _recently_checked(conn, addr, hours=24):
            skip_recent += 1
            continue

        time.sleep(PROFILE_DELAY)
        profile = _resolve_profile_by_address(addr)
        profiles_checked += 1

        handle = (profile or {}).get("handle", "")
        join_date = (profile or {}).get("join_date", "")
        is_fresh, age_days = _is_fresh_account(join_date, max_age_days)

        usdc = whale["_usdc"]
        slug = whale["_slug"]
        cid = whale["_cid"]
        side = str(whale.get("side") or "").upper()
        outcome = str(whale.get("outcome") or "")

        auto_tracked = 0
        notes = f"${usdc:,.0f} on {slug}"

        if is_fresh and handle and not _already_tracked(conn, addr, handle):
            _auto_add_wallet(conn, handle, addr, f"fresh_whale_auto: {notes}")
            auto_tracked = 1
            added += 1

        conn.execute(
            """
            INSERT INTO fresh_whale_discoveries
            (discovered_at, wallet_address, handle, join_date, account_age_days,
             market_slug, condition_id, trade_size_usdc, side, outcome, auto_tracked, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                addr,
                handle,
                join_date,
                age_days if age_days >= 0 else 0,
                slug,
                cid,
                usdc,
                side,
                outcome,
                auto_tracked,
                notes,
            ),
        )
        conn.commit()

    if own_conn:
        conn.close()

    print(
        f"fw_scanner: markets={markets_scanned} whale_trades={len(unique_whales)} "
        f"skipped_recent={skip_recent} profiles_checked={profiles_checked} added={added}"
    )
    return added


def main() -> int:
    return 0 if scan() >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
