#!/usr/bin/env python3
"""
Ingest tracked Polymarket wallet activity + profile performance.

Sources:
- Public profile page HTML (for handle -> proxy wallet resolution and embedded JSON)
- Data API activity endpoint (fallback / refresh)
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

DB = Path(__file__).parent / "data" / "trades.db"
PROFILE_BASE = "https://polymarket.com"
ACTIVITY_API = "https://data-api.polymarket.com/activity"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((r[1] == column) for r in cur.fetchall())


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked_polymarket_wallets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          handle TEXT NOT NULL UNIQUE,
          profile_url TEXT NOT NULL DEFAULT '',
          role_copy INTEGER NOT NULL DEFAULT 1,
          role_alpha INTEGER NOT NULL DEFAULT 1,
          active INTEGER NOT NULL DEFAULT 1,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    extra_cols = {
        "wallet_address": "TEXT NOT NULL DEFAULT ''",
        "last_synced_at": "TEXT NOT NULL DEFAULT ''",
        "last_activity_ts": "INTEGER NOT NULL DEFAULT 0",
    }
    for col, spec in extra_cols.items():
        if not _column_exists(conn, "tracked_polymarket_wallets", col):
            conn.execute(f"ALTER TABLE tracked_polymarket_wallets ADD COLUMN {col} {spec}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_wallet_activity (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          synced_at TEXT NOT NULL,
          handle TEXT NOT NULL,
          wallet_address TEXT NOT NULL,
          market_slug TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          event_slug TEXT NOT NULL DEFAULT '',
          condition_id TEXT NOT NULL DEFAULT '',
          side TEXT NOT NULL DEFAULT '',
          outcome TEXT NOT NULL DEFAULT '',
          price REAL NOT NULL DEFAULT 0,
          size REAL NOT NULL DEFAULT 0,
          usdc_size REAL NOT NULL DEFAULT 0,
          timestamp_unix INTEGER NOT NULL DEFAULT 0,
          tx_hash TEXT NOT NULL DEFAULT '',
          asset_id TEXT NOT NULL DEFAULT '',
          raw_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_poly_wallet_activity
        ON polymarket_wallet_activity (
          handle,
          tx_hash,
          asset_id,
          side,
          outcome,
          timestamp_unix,
          price,
          size
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_wallet_performance (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          synced_at TEXT NOT NULL,
          handle TEXT NOT NULL,
          wallet_address TEXT NOT NULL,
          trades_count INTEGER NOT NULL DEFAULT 0,
          largest_win REAL NOT NULL DEFAULT 0,
          views_count INTEGER NOT NULL DEFAULT 0,
          join_date TEXT NOT NULL DEFAULT '',
          pnl_all REAL NOT NULL DEFAULT 0,
          volume_all REAL NOT NULL DEFAULT 0,
          raw_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poly_wallet_perf_handle ON polymarket_wallet_performance(handle, synced_at)")
    conn.commit()


def _safe_json_loads(raw: str) -> Optional[Any]:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_next_data(html: str) -> Dict[str, Any]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, flags=re.DOTALL)
    if not m:
        return {}
    payload = _safe_json_loads(m.group(1).strip())
    if not isinstance(payload, dict):
        return {}
    return payload


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _build_profile_url(handle: str, profile_url: str) -> str:
    if profile_url and profile_url.startswith("http"):
        return profile_url
    h = handle.strip().lstrip("@")
    return f"{PROFILE_BASE}/@{h}"


def _extract_profile_blob(next_data: Dict[str, Any]) -> Dict[str, Any]:
    page_props = ((next_data.get("props") or {}).get("pageProps") or {}) if isinstance(next_data, dict) else {}
    out: Dict[str, Any] = {
        "username": str(page_props.get("username") or "").strip().lstrip("@"),
        "wallet_address": str(
            page_props.get("proxyAddress")
            or page_props.get("baseAddress")
            or page_props.get("primaryAddress")
            or ""
        ).strip(),
        "activity": [],
        "stats": {},
        "volume": {},
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

        if "profile|activity" in key_text:
            pages = (data or {}).get("pages") if isinstance(data, dict) else None
            if isinstance(pages, list):
                for page in pages:
                    if isinstance(page, list):
                        for row in page:
                            if isinstance(row, dict):
                                out["activity"].append(row)
        elif "user-stats" in key_text and isinstance(data, dict):
            out["stats"] = data
        elif "/api/profile/volume" in key_text and isinstance(data, dict):
            out["volume"] = data
        elif "/api/profile/userdata" in key_text and isinstance(data, dict):
            if not out["wallet_address"]:
                out["wallet_address"] = str(data.get("proxyWallet") or "").strip()
            if not out["username"]:
                out["username"] = str(data.get("name") or "").strip().lstrip("@")

    return out


def _fetch_profile_blob(handle: str, profile_url: str) -> Dict[str, Any]:
    url = _build_profile_url(handle, profile_url)
    try:
        resp = requests.get(url, timeout=25)
        if resp.status_code >= 400:
            return {}
    except Exception:
        return {}
    next_data = _extract_next_data(resp.text or "")
    return _extract_profile_blob(next_data)


def _fetch_activity_fallback(wallet_address: str, limit: int = 300) -> List[Dict[str, Any]]:
    if not wallet_address:
        return []
    try:
        resp = requests.get(
            ACTIVITY_API,
            params={"user": wallet_address, "limit": int(limit), "offset": 0},
            timeout=20,
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _normalize_activity(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        tx_hash = str(r.get("transactionHash") or "").strip()
        if not tx_hash:
            continue
        ts = _coerce_int(r.get("timestamp"), 0)
        out.append(
            {
                "market_slug": str(r.get("slug") or "").strip().lower(),
                "title": str(r.get("title") or "").strip(),
                "event_slug": str(r.get("eventSlug") or "").strip().lower(),
                "condition_id": str(r.get("conditionId") or "").strip(),
                "side": str(r.get("side") or "").strip().upper(),
                "outcome": str(r.get("outcome") or "").strip(),
                "price": _coerce_float(r.get("price"), 0.0),
                "size": _coerce_float(r.get("size"), 0.0),
                "usdc_size": _coerce_float(r.get("usdcSize"), 0.0),
                "timestamp_unix": ts,
                "tx_hash": tx_hash,
                "asset_id": str(r.get("asset") or "").strip(),
                "raw_json": json.dumps(r, separators=(",", ":")),
            }
        )
    return out


def ingest() -> int:
    conn = _connect()
    ensure_tables(conn)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT handle, COALESCE(profile_url,''), COALESCE(wallet_address,'')
        FROM tracked_polymarket_wallets
        WHERE COALESCE(active,1)=1
        ORDER BY updated_at DESC
        """
    )
    wallets = [(str(h).strip().lstrip("@"), str(u or "").strip(), str(a or "").strip()) for h, u, a in cur.fetchall()]

    inserted_total = 0
    synced_wallets = 0
    for handle, profile_url, known_address in wallets:
        blob = _fetch_profile_blob(handle, profile_url)
        wallet_address = str(blob.get("wallet_address") or known_address or "").strip()

        activity = blob.get("activity") if isinstance(blob.get("activity"), list) else []
        if not activity and wallet_address:
            activity = _fetch_activity_fallback(wallet_address, limit=350)
        rows = _normalize_activity(activity)

        for row in rows:
            cur_ins = conn.execute(
                """
                INSERT OR IGNORE INTO polymarket_wallet_activity
                (synced_at, handle, wallet_address, market_slug, title, event_slug, condition_id,
                 side, outcome, price, size, usdc_size, timestamp_unix, tx_hash, asset_id, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    handle,
                    wallet_address,
                    row["market_slug"],
                    row["title"],
                    row["event_slug"],
                    row["condition_id"],
                    row["side"],
                    row["outcome"],
                    row["price"],
                    row["size"],
                    row["usdc_size"],
                    row["timestamp_unix"],
                    row["tx_hash"],
                    row["asset_id"],
                    row["raw_json"],
                ),
            )
            inserted_total += int(cur_ins.rowcount or 0)

        stats = blob.get("stats") if isinstance(blob.get("stats"), dict) else {}
        volume = blob.get("volume") if isinstance(blob.get("volume"), dict) else {}
        conn.execute(
            """
            INSERT INTO polymarket_wallet_performance
            (synced_at, handle, wallet_address, trades_count, largest_win, views_count, join_date, pnl_all, volume_all, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                handle,
                wallet_address,
                _coerce_int(stats.get("trades"), 0),
                _coerce_float(stats.get("largestWin"), 0.0),
                _coerce_int(stats.get("views"), 0),
                str(stats.get("joinDate") or ""),
                _coerce_float(volume.get("pnl"), 0.0),
                _coerce_float(volume.get("amount"), 0.0),
                json.dumps({"stats": stats, "volume": volume}, separators=(",", ":")),
            ),
        )

        last_ts = max([int(r.get("timestamp_unix") or 0) for r in rows], default=0)
        conn.execute(
            """
            UPDATE tracked_polymarket_wallets
            SET updated_at=?, wallet_address=?, last_synced_at=?, last_activity_ts=?
            WHERE lower(handle)=lower(?)
            """,
            (now_iso(), wallet_address, now_iso(), int(last_ts), handle),
        )
        synced_wallets += 1

    conn.commit()
    conn.close()
    print(f"poly_wallet_ingest: wallets={synced_wallets} activity_rows={inserted_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(ingest())
