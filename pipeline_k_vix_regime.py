#!/usr/bin/env python3
"""
Pipeline K: VIX Regime-Switching Strategy (TQQQ/BTAL)

2.17 Sharpe, 72.7% CAGR paper strategy:
- VIX < low_threshold  -> low_vol regime  -> signal TQQQ long
- VIX > high_threshold -> high_vol regime -> signal BTAL long
- Between             -> transition       -> no signal (avoids flip-flopping)

Leverage scaling via notional sizing (TQQQ is already 3x leveraged).
GEX from dealer_gamma table for optional confirmation.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

from pipeline_store import connect, init_pipeline_tables, insert_signal

BASE_DIR = Path(__file__).parent
PIPELINE_ID = "VIX_REGIME"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def _seed_controls(conn: sqlite3.Connection) -> None:
    """Seed VIX regime controls with ON CONFLICT DO NOTHING."""
    if not _table_exists(conn, "execution_controls"):
        return
    seeds = [
        ("enable_vix_regime_pipeline", "0"),
        ("vix_regime_low_threshold", "20"),
        ("vix_regime_high_threshold", "30"),
        ("vix_regime_tqqq_notional_usd", "75"),
        ("vix_regime_btal_notional_usd", "75"),
        ("vix_regime_gex_confirm_required", "0"),
        ("vix_regime_stale_hours", "6"),
    ]
    ts = now_iso()
    for key, value in seeds:
        conn.execute(
            """
            INSERT INTO execution_controls (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (key, value, ts),
        )
    conn.commit()


def ensure_vix_regime_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vix_regime_state (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          fetched_at TEXT NOT NULL,
          vix_close REAL NOT NULL,
          vix_5d_avg REAL NOT NULL,
          regime TEXT NOT NULL,
          leverage_scale REAL NOT NULL,
          gex_signal TEXT NOT NULL DEFAULT '',
          gex_confirmed INTEGER NOT NULL DEFAULT 0,
          signal_ticker TEXT NOT NULL DEFAULT '',
          signal_direction TEXT NOT NULL DEFAULT '',
          confidence REAL NOT NULL DEFAULT 0.0,
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


def fetch_vix_bars(days: int = 30) -> list:
    """Fetch ^VIX daily bars from Yahoo Finance."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
    params = {"range": f"{days}d", "interval": "1d", "includePrePost": "false"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=20)
        if res.status_code >= 400:
            return []
        data = res.json()
    except Exception:
        return []
    chart = (data.get("chart") or {}).get("result") or []
    if not chart:
        return []
    item = chart[0]
    ts_list = item.get("timestamp") or []
    q = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    out = []
    for i, t in enumerate(ts_list):
        try:
            c = float(closes[i]) if closes[i] is not None else None
        except Exception:
            continue
        if c is None:
            continue
        out.append({"ts": int(t), "close": c})
    return out


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """Linear interpolation: map x in [x0,x1] to [y0,y1], clamped."""
    if x1 <= x0:
        return y0
    t = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
    return y0 + t * (y1 - y0)


def classify_regime(
    vix_close: float,
    low_threshold: float,
    high_threshold: float,
) -> Tuple[str, float, str, str]:
    """
    Returns (regime, leverage_scale, signal_ticker, signal_direction).
    """
    if vix_close < low_threshold:
        # Low vol -> TQQQ long
        if vix_close < 15.0:
            scale = 1.25
        else:
            scale = round(_lerp(vix_close, 15.0, low_threshold, 1.25, 1.0), 4)
        return "low_vol", scale, "TQQQ", "long"

    if vix_close > high_threshold:
        # High vol -> BTAL long
        if vix_close > 40.0:
            scale = 0.50
        else:
            scale = round(_lerp(vix_close, high_threshold, 40.0, 1.0, 0.75), 4)
        return "high_vol", scale, "BTAL", "long"

    # Transition zone -> no signal
    return "transition", 0.85, "", ""


def read_gex_signal(conn: sqlite3.Connection) -> Tuple[str, bool]:
    """Read latest GEX signal from dealer_gamma table if it exists."""
    if not _table_exists(conn, "dealer_gamma"):
        return "", False
    cur = conn.cursor()
    cur.execute(
        """
        SELECT signal, gamma_level
        FROM dealer_gamma
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return "", False
    signal = str(row[0] or "").strip()
    return signal, bool(signal)


def compute_confidence(
    regime: str,
    vix_close: float,
    vix_5d_avg: float,
    gex_confirmed: bool,
    gex_required: bool,
) -> float:
    """Compute signal confidence based on regime clarity and GEX confirmation."""
    if regime == "transition":
        return 0.0

    # Base confidence from VIX clarity
    if regime == "low_vol":
        # Clearer signal when VIX is well below threshold
        clarity = min(1.0, max(0.0, (20.0 - vix_close) / 10.0))
        base = 0.60 + clarity * 0.18
    else:
        # high_vol: clearer when VIX is well above threshold
        clarity = min(1.0, max(0.0, (vix_close - 30.0) / 15.0))
        base = 0.58 + clarity * 0.20

    # Trend alignment: VIX close vs 5d avg
    if regime == "low_vol" and vix_close < vix_5d_avg:
        base += 0.04  # VIX declining in low vol -> stronger TQQQ signal
    elif regime == "high_vol" and vix_close > vix_5d_avg:
        base += 0.04  # VIX rising in high vol -> stronger BTAL signal

    # GEX confirmation bonus
    if gex_confirmed:
        base += 0.06

    # If GEX required but missing, reduce confidence
    if gex_required and not gex_confirmed:
        base *= 0.70

    return round(min(0.88, base), 4)


def main() -> int:
    conn = connect()
    try:
        init_pipeline_tables(conn)
        ensure_vix_regime_table(conn)
        _seed_controls(conn)

        enabled = _control(conn, "enable_vix_regime_pipeline", "0")
        if enabled != "1":
            print("Pipeline K (VIX Regime): disabled (enable_vix_regime_pipeline=0)")
            return 0

        low_threshold = float(_control(conn, "vix_regime_low_threshold", "20"))
        high_threshold = float(_control(conn, "vix_regime_high_threshold", "30"))
        tqqq_notional = float(_control(conn, "vix_regime_tqqq_notional_usd", "75"))
        btal_notional = float(_control(conn, "vix_regime_btal_notional_usd", "75"))
        gex_required = _control(conn, "vix_regime_gex_confirm_required", "0") == "1"
        stale_hours = int(float(_control(conn, "vix_regime_stale_hours", "6")))

        # Fetch VIX data
        bars = fetch_vix_bars(days=30)
        if not bars:
            print("Pipeline K (VIX Regime): no VIX data from Yahoo Finance")
            return 0

        # Check staleness: most recent bar timestamp
        latest_bar = bars[-1]
        bar_dt = datetime.fromtimestamp(latest_bar["ts"], tz=timezone.utc)
        age = datetime.now(timezone.utc) - bar_dt
        if age > timedelta(hours=stale_hours + 24):
            # Allow up to stale_hours + 24h (weekends/holidays)
            print(f"Pipeline K (VIX Regime): VIX data too stale ({age})")
            return 0

        vix_close = latest_bar["close"]

        # 5-day average
        recent_closes = [b["close"] for b in bars[-5:]]
        vix_5d_avg = round(sum(recent_closes) / len(recent_closes), 4) if recent_closes else vix_close

        # Classify regime
        regime, leverage_scale, signal_ticker, signal_direction = classify_regime(
            vix_close, low_threshold, high_threshold
        )

        # Read GEX
        gex_signal, gex_confirmed = read_gex_signal(conn)

        # Compute confidence
        confidence = compute_confidence(
            regime=regime,
            vix_close=vix_close,
            vix_5d_avg=vix_5d_avg,
            gex_confirmed=gex_confirmed,
            gex_required=gex_required,
        )

        notes_parts = [f"vix={vix_close:.2f}", f"5d_avg={vix_5d_avg:.2f}", f"regime={regime}"]
        if gex_signal:
            notes_parts.append(f"gex={gex_signal}")
        notes = "; ".join(notes_parts)

        # Write vix_regime_state row
        conn.execute(
            """
            INSERT INTO vix_regime_state
            (fetched_at, vix_close, vix_5d_avg, regime, leverage_scale,
             gex_signal, gex_confirmed, signal_ticker, signal_direction,
             confidence, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                vix_close,
                vix_5d_avg,
                regime,
                leverage_scale,
                gex_signal,
                1 if gex_confirmed else 0,
                signal_ticker,
                signal_direction,
                confidence,
                notes,
            ),
        )
        conn.commit()

        # Insert pipeline signal if we have a signal
        created = 0
        if signal_ticker and signal_direction and confidence > 0:
            base_notional = tqqq_notional if signal_ticker == "TQQQ" else btal_notional
            scaled_notional = round(base_notional * leverage_scale, 2)

            rationale = (
                f"vix_regime={regime}; vix={vix_close:.2f}; 5d_avg={vix_5d_avg:.2f}; "
                f"scale={leverage_scale:.4f}; notional={scaled_notional}; "
                f"gex={gex_signal or 'none'}; gex_confirmed={gex_confirmed}"
            )

            insert_signal(
                conn=conn,
                pipeline_id=PIPELINE_ID,
                asset=signal_ticker,
                direction=signal_direction,
                horizon="swing",
                confidence=confidence,
                score=round(confidence * 100.0, 2),
                rationale=rationale,
                source_refs="yahoo_vix,vix_regime_rules,dealer_gamma",
                ttl_minutes=480,
            )
            created = 1

        print(
            f"Pipeline K (VIX Regime): regime={regime} vix={vix_close:.2f} "
            f"scale={leverage_scale:.2f} signal={signal_ticker or 'none'} "
            f"conf={confidence:.2f} created={created}"
        )
        return 0
    except sqlite3.OperationalError as exc:
        print(f"Pipeline K skipped: {exc}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
