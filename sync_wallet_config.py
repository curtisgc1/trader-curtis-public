#!/usr/bin/env python3
"""
Persist non-secret wallet/runtime configuration for dashboard visibility.
Never stores private keys or API secrets.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "trades.db"
ENV_PATH = BASE_DIR / ".env"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def is_true(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def hl_network(env: Dict[str, str]) -> str:
    if is_true(env.get("HL_USE_TESTNET", "0")):
        return "testnet"
    api = str(env.get("HL_API_URL", "")).lower()
    if "testnet" in api:
        return "testnet"
    return "mainnet"


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_config (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT 'env',
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def upsert(conn: sqlite3.Connection, key: str, value: str, source: str = "env") -> None:
    conn.execute(
        """
        INSERT INTO wallet_config (key, value, source, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          value=excluded.value,
          source=excluded.source,
          updated_at=excluded.updated_at
        """,
        (key, value, source, now_iso()),
    )


def main() -> int:
    env = load_env()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ensure_table(conn)

        # Hyperliquid (safe fields only)
        upsert(conn, "hl_wallet_address", env.get("HL_WALLET_ADDRESS", ""))
        upsert(conn, "hl_network", hl_network(env))
        upsert(conn, "hl_api_url", env.get("HL_API_URL", "https://api.hyperliquid.xyz"))
        upsert(conn, "hl_use_testnet", "1" if is_true(env.get("HL_USE_TESTNET", "0")) else "0")

        # Polymarket (safe fields only)
        # Prefer explicit funder; fallback to known wallet env if user adds one.
        poly_addr = env.get("POLY_FUNDER", "") or env.get("POLY_WALLET_ADDRESS", "")
        upsert(conn, "poly_wallet_address", poly_addr)
        upsert(conn, "poly_clob_host", env.get("POLY_CLOB_HOST", "https://clob.polymarket.com"))
        upsert(conn, "poly_chain_id", env.get("POLY_CHAIN_ID", "137"))

        # Alpaca mode visibility (safe)
        upsert(conn, "alpaca_base_url", env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
        upsert(conn, "alpaca_key_present", "1" if bool(env.get("ALPACA_API_KEY")) else "0")

        conn.commit()
        print("wallet_config: synced")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

