#!/usr/bin/env python3
"""
Real-time whale watcher daemon — polls the CLOB REST API every N seconds
for whale-sized trades, profile-scrapes new addresses, and auto-tracks
qualifying fresh accounts.

Uses REST over WebSocket because the public WS feed doesn't expose
trader wallet addresses (only price/size).

Run as:  python3 watch_fresh_whales.py
Stop:    Ctrl-C or SIGTERM (graceful shutdown)
"""

from __future__ import annotations

import asyncio
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from scan_fresh_whales import (
    DB,
    CLOB_DELAY,
    PROFILE_DELAY,
    ensure_tables,
    _filter_whale_trades,
    _recently_checked,
    _resolve_profile_by_address,
    _is_fresh_account,
    _already_tracked,
    _auto_add_wallet,
    _get_top_markets,
    _fetch_market_trades,
    now_iso,
)

POLL_INTERVAL = 30
REFRESH_MARKETS_EVERY = 300
CONTROLS_REFRESH_EVERY = 60


def _read_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,)
        )
        row = cur.fetchone()
        return str(row[0]) if row else default
    except Exception:
        return default


def _load_controls(conn: sqlite3.Connection) -> Dict[str, Any]:
    return {
        "enabled": _read_control(conn, "fw_scanner_enabled", "1") == "1",
        "min_usdc": float(_read_control(conn, "fw_min_trade_usdc", "50000")),
        "max_age_days": int(float(_read_control(conn, "fw_max_account_age_days", "7"))),
        "top_markets": int(float(_read_control(conn, "fw_top_markets", "30"))),
        "poll_seconds": int(float(_read_control(conn, "fw_watcher_poll_seconds", "30"))),
    }


async def _poll_cycle(
    conn: sqlite3.Connection,
    markets: List[Dict[str, Any]],
    min_usdc: float,
    max_age_days: int,
) -> int:
    """Scan all markets for whale trades. Returns count of new auto-tracked whales."""
    whale_addresses: Dict[str, Dict[str, Any]] = {}

    for idx, mkt in enumerate(markets):
        cid = mkt["condition_id"]
        slug = mkt["slug"]
        trades = _fetch_market_trades(cid)
        whales = _filter_whale_trades(trades, min_usdc)

        for w in whales:
            addr = w["_address"]
            if addr not in whale_addresses or w["_usdc"] > whale_addresses[addr]["_usdc"]:
                whale_addresses[addr] = {**w, "_slug": slug, "_cid": cid}

        if idx < len(markets) - 1:
            await asyncio.sleep(CLOB_DELAY)

    added = 0
    for whale in whale_addresses.values():
        addr = whale["_address"]

        if _recently_checked(conn, addr, hours=24):
            continue

        await asyncio.sleep(PROFILE_DELAY)
        profile = _resolve_profile_by_address(addr)

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

    return added


async def run_daemon() -> None:
    """Main daemon loop — runs until SIGINT/SIGTERM."""
    shutdown = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    conn = sqlite3.connect(str(DB))
    ensure_tables(conn)

    controls = _load_controls(conn)
    if not controls["enabled"]:
        print("whale-watcher: disabled (fw_scanner_enabled=0)")
        conn.close()
        return

    markets = _get_top_markets(conn, controls["top_markets"])
    print(
        f"whale-watcher: started, monitoring {len(markets)} markets "
        f"(poll={controls['poll_seconds']}s, min=${controls['min_usdc']:,.0f}, "
        f"max_age={controls['max_age_days']}d)"
    )

    last_market_refresh = time.monotonic()
    last_controls_refresh = time.monotonic()
    cycle = 0

    while not shutdown.is_set():
        now = time.monotonic()

        if now - last_controls_refresh >= CONTROLS_REFRESH_EVERY:
            controls = _load_controls(conn)
            last_controls_refresh = now
            if not controls["enabled"]:
                print("whale-watcher: disabled via controls, stopping")
                break

        if now - last_market_refresh >= REFRESH_MARKETS_EVERY:
            markets = _get_top_markets(conn, controls["top_markets"])
            last_market_refresh = now
            print(f"whale-watcher: refreshed market list ({len(markets)} markets)")

        if not markets:
            print("whale-watcher: no active markets, waiting...")
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=controls["poll_seconds"])
            except asyncio.TimeoutError:
                pass
            continue

        cycle += 1
        t0 = time.monotonic()
        added = await _poll_cycle(
            conn, markets, controls["min_usdc"], controls["max_age_days"]
        )
        elapsed = time.monotonic() - t0

        if added > 0:
            print(f"whale-watcher: cycle {cycle} — {added} new whale(s) tracked ({elapsed:.1f}s)")

        try:
            await asyncio.wait_for(shutdown.wait(), timeout=controls["poll_seconds"])
        except asyncio.TimeoutError:
            pass

    conn.close()
    print("whale-watcher: shutdown complete")


def main() -> int:
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        print("\nwhale-watcher: interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
