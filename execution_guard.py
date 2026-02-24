#!/usr/bin/env python3
"""
Execution risk guard for Trader Curtis.
Evaluates candidate signals against hard risk limits before routing.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from training_mode import apply_training_mode

DB_PATH = Path(__file__).parent / "data" / "trades.db"

DEFAULT_CONTROLS = {
    "agent_master_enabled": "0",
    "allow_live_trading": "0",
    "allow_hyperliquid_live": "0",
    "min_candidate_score": "60",
    "max_open_positions": "5",
    "max_daily_new_notional_usd": "1000",
    "max_signal_notional_usd": "150",
    "enable_alpaca_paper_auto": "1",
    "alpaca_min_route_score": "60",
    "allow_equity_shorts": "1",
    "enable_hyperliquid_test_auto": "1",
    "hyperliquid_min_route_score": "60",
    "hyperliquid_test_notional_usd": "10",
    "hyperliquid_test_leverage": "1",
    "enable_polymarket_auto": "0",
    "allow_polymarket_live": "0",
    "polymarket_max_notional_usd": "25",
    "polymarket_min_edge_pct": "2.0",
    "polymarket_min_confidence_pct": "60",
    "polymarket_fee_gate_enabled": "1",
    "polymarket_taker_fee_pct": "3.15",
    "polymarket_fee_buffer_pct": "0.50",
    "polymarket_copy_enabled": "1",
    "polymarket_arb_enabled": "1",
    "polymarket_alpha_enabled": "1",
    "polymarket_copy_max_notional_usd": "25",
    "polymarket_arb_max_notional_usd": "25",
    "polymarket_alpha_max_notional_usd": "25",
    "consensus_enforce": "1",
    "consensus_min_confirmations": "3",
    "consensus_min_ratio": "0.6",
    "consensus_min_score": "60",
    "liquidity_high_signal_boost": "0.08",
    "liquidity_min_confidence": "0.60",
    "liquidity_min_rr": "2.0",
    "high_beta_only": "1",
    "high_beta_min_beta": "1.5",
    "weather_strict_station_required": "1",
    "mm_enabled": "0",
    "mm_risk_aversion": "0.25",
    "mm_base_spread_bps": "80",
    "mm_inventory_limit": "200",
    "mm_toxicity_threshold": "0.72",
    "mm_min_edge_bps": "50",
    "quant_gate_enforce": "1",
    "enable_allocator_causal": "1",
    "allocator_regime_override": "auto",
    "allocator_min_source_samples": "12",
    "allocator_block_posterior_floor": "0.35",
    "allocator_max_scale_up": "1.35",
    "allocator_max_scale_down": "0.60",
    "auto_tuner_apply": "0",
    "training_mode_enabled": "0",
    "training_min_candidate_score": "55",
    "training_consensus_min_confirmations": "2",
    "training_consensus_min_ratio": "0.55",
    "training_consensus_min_score": "60",
    "training_alpaca_min_route_score": "60",
    "training_hyperliquid_min_route_score": "60",
    "training_polymarket_min_confidence_pct": "60",
    "training_max_signal_notional_usd": "10",
    "training_max_daily_new_notional_usd": "50",
    "training_hyperliquid_test_notional_usd": "1",
    "training_polymarket_max_notional_usd": "5",
    "training_polymarket_max_daily_exposure": "20",
    "kaggle_auto_pull_enabled": "0",
    "kaggle_poly_dataset_slug": "",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def init_controls(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_controls (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          ticker TEXT NOT NULL,
          direction TEXT NOT NULL,
          candidate_score REAL NOT NULL,
          proposed_notional REAL NOT NULL,
          approved INTEGER NOT NULL,
          reason TEXT NOT NULL
        )
        """
    )
    cur = conn.cursor()
    for key, value in DEFAULT_CONTROLS.items():
        cur.execute(
            "INSERT OR IGNORE INTO execution_controls (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now_iso()),
        )
    conn.commit()


def load_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    init_controls(conn)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    base = {key: value for key, value in cur.fetchall()}
    return apply_training_mode(base)


def _count_open_positions(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    total = 0
    if _table_exists(conn, "trades"):
        cur.execute("SELECT COUNT(*) FROM trades WHERE lower(COALESCE(status,'')) IN ('open','live')")
        total += int(cur.fetchone()[0] or 0)
    if _table_exists(conn, "signal_routes"):
        cur.execute("SELECT COUNT(*) FROM signal_routes WHERE status='queued'")
        total += int(cur.fetchone()[0] or 0)
    return total


def _todays_routed_notional(conn: sqlite3.Connection) -> float:
    if not _table_exists(conn, "signal_routes"):
        return 0.0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(proposed_notional), 0)
        FROM signal_routes
        WHERE date(routed_at)=date('now') AND decision='approved'
        """
    )
    return float(cur.fetchone()[0] or 0.0)


def evaluate_candidate(
    conn: sqlite3.Connection,
    ticker: str,
    direction: str,
    candidate_score: float,
    proposed_notional: float,
    mode: str,
) -> Tuple[bool, str]:
    controls = load_controls(conn)
    min_score = float(controls.get("min_candidate_score", "60"))
    max_open = int(float(controls.get("max_open_positions", "5")))
    max_daily_notional = float(controls.get("max_daily_new_notional_usd", "1000"))
    max_signal_notional = float(controls.get("max_signal_notional_usd", "150"))
    allow_live = controls.get("allow_live_trading", "0") == "1"

    if mode == "live" and not allow_live:
        return False, "live trading disabled by control"
    if candidate_score < min_score:
        return False, f"score below threshold ({candidate_score:.2f} < {min_score:.2f})"
    if proposed_notional > max_signal_notional:
        return False, f"proposed notional above per-signal cap ({proposed_notional:.2f} > {max_signal_notional:.2f})"

    open_positions = _count_open_positions(conn)
    if open_positions >= max_open:
        return False, f"open position cap reached ({open_positions} >= {max_open})"

    today_notional = _todays_routed_notional(conn)
    if today_notional + proposed_notional > max_daily_notional:
        return False, (
            f"daily routed notional cap exceeded ({today_notional + proposed_notional:.2f} > {max_daily_notional:.2f})"
        )

    return True, "approved"


def log_risk_event(
    conn: sqlite3.Connection,
    ticker: str,
    direction: str,
    candidate_score: float,
    proposed_notional: float,
    approved: bool,
    reason: str,
) -> None:
    conn.execute(
        """
        INSERT INTO risk_events
        (created_at, ticker, direction, candidate_score, proposed_notional, approved, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            ticker,
            direction,
            float(candidate_score),
            float(proposed_notional),
            1 if approved else 0,
            reason,
        ),
    )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one trade candidate against risk controls.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--direction", default="unknown")
    parser.add_argument("--score", type=float, required=True)
    parser.add_argument("--notional", type=float, default=100.0)
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    args = parser.parse_args()

    conn = _connect()
    try:
        init_controls(conn)
        approved, reason = evaluate_candidate(
            conn=conn,
            ticker=args.ticker.upper(),
            direction=args.direction,
            candidate_score=float(args.score),
            proposed_notional=float(args.notional),
            mode=args.mode,
        )
        log_risk_event(
            conn=conn,
            ticker=args.ticker.upper(),
            direction=args.direction,
            candidate_score=float(args.score),
            proposed_notional=float(args.notional),
            approved=approved,
            reason=reason,
        )
        payload = {
            "ticker": args.ticker.upper(),
            "direction": args.direction,
            "score": float(args.score),
            "notional": float(args.notional),
            "mode": args.mode,
            "approved": approved,
            "reason": reason,
        }
        print(json.dumps(payload))
        return 0 if approved else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
