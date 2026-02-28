#!/usr/bin/env python3
"""
Pipeline L: DAPO Agent Inference

Loads a pre-trained DAPO checkpoint and runs inference on current market data
to produce buy/sell signals.  State vector matches StockTradingEnv format:
  [cash, close, holdings, macd, rsi_30, cci_30, dx_30]

action > 0 -> long   |action| > 0.7 -> confidence 0.85 (high)
action < 0 -> short  |action| 0.3–0.7 -> confidence 0.60 (medium)
|action| < min_action_threshold -> no signal emitted
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pipeline_store import connect, init_pipeline_tables, insert_signal

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
PIPELINE_ID = "DAPO_AGENT"

TECH_INDICATORS = ["macd", "rsi_30", "cci_30", "dx_30"]
_INFERENCE_CASH = 1_000_000.0
_INFERENCE_HOLDINGS = 0.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_log = logging.getLogger("pipeline_l")


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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    if not _table_exists(conn, "execution_controls"):
        return default
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def get_universe(conn: sqlite3.Connection, limit: int = 30) -> List[str]:
    tickers: List[str] = []
    if _table_exists(conn, "trade_candidates"):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT UPPER(COALESCE(ticker, ''))
            FROM trade_candidates
            WHERE COALESCE(ticker, '') <> ''
            ORDER BY score DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        tickers.extend([str(r[0]) for r in cur.fetchall() if r and r[0]])

    defaults = [
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
        "META", "GOOGL", "PLTR", "COIN", "MARA",
        "SPY", "QQQ",
    ]
    tickers.extend(defaults)

    seen: set = set()
    out: List[str] = []
    for t in tickers:
        u = str(t).upper().strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out[:limit]


def fetch_daily_bars_yahoo(ticker: str, limit: int = 60) -> List[dict]:
    """Fetch daily OHLCV from Yahoo Finance v8 chart API via urllib."""
    encoded = urllib.parse.quote(ticker.upper(), safe="")
    params = urllib.parse.urlencode({"range": "6mo", "interval": "1d", "includePrePost": "false"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        _log.warning("yahoo fetch failed for %s: %s", ticker, exc)
        return []

    chart = (data.get("chart") or {}).get("result") or []
    if not chart:
        return []
    item = chart[0]
    timestamps = item.get("timestamp") or []
    q = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    closes = q.get("close") or []
    volumes = q.get("volume") or []

    out: List[dict] = []
    for i, ts in enumerate(timestamps):
        try:
            o = float(opens[i]) if i < len(opens) and opens[i] is not None else None
            h = float(highs[i]) if i < len(highs) and highs[i] is not None else None
            l = float(lows[i]) if i < len(lows) and lows[i] is not None else None
            c = float(closes[i]) if i < len(closes) and closes[i] is not None else None
            v = float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0.0
        except (TypeError, ValueError):
            continue
        if None in (o, h, l, c):
            continue
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        out.append({"date": dt, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return out[-limit:] if len(out) > limit else out


def _bars_to_df(ticker: str, bars: List[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": b["date"], "tic": ticker.upper(),
            "open": float(b["open"]), "high": float(b["high"]),
            "low": float(b["low"]), "close": float(b["close"]),
            "volume": float(b["volume"]),
        }
        for b in bars
    ])


def _build_state_vector(df_ind: pd.DataFrame) -> Optional[np.ndarray]:
    """Build single-ticker state vector from most recent row of indicator df."""
    if df_ind.empty:
        return None
    for col in ["close"] + TECH_INDICATORS:
        if col not in df_ind.columns:
            _log.warning("missing column %s in indicator df", col)
            return None
    last = df_ind.iloc[-1]
    parts: List[float] = [_INFERENCE_CASH, float(last["close"]), _INFERENCE_HOLDINGS]
    for ind in TECH_INDICATORS:
        parts.append(float(last[ind]) if pd.notna(last[ind]) else 0.0)
    return np.array(parts, dtype=np.float32)


def _load_agent_from_checkpoint(path: str):
    """
    Reconstruct DAPOAgent from checkpoint saved by DAPOAgent.save().
    Returns agent instance with eval mode set, or None on any failure.
    """
    try:
        import torch
        from dapo_model import DAPOAgent
    except ImportError as exc:
        _log.warning("cannot import torch or dapo_model: %s", exc)
        return None

    try:
        checkpoint = torch.load(path, map_location="cpu")
    except Exception as exc:
        _log.warning("torch.load failed for %s: %s", path, exc)
        return None

    cfg = checkpoint.get("config") or {}
    state_dim = cfg.get("state_dim")
    action_dim = cfg.get("action_dim")

    if state_dim is None or action_dim is None:
        # Infer dims from saved weight shapes when config is absent
        sd = checkpoint.get("model_state_dict") or {}
        first_key = next((k for k in sd if "backbone" in k and k.endswith(".weight")), None)
        last_key = next(
            (k for k in reversed(list(sd)) if "actor_mean" in k and k.endswith(".weight")), None
        )
        if first_key and last_key:
            state_dim = sd[first_key].shape[1]
            action_dim = sd[last_key].shape[0]
        else:
            _log.warning("checkpoint %s missing config and cannot infer dims", path)
            return None

    agent = DAPOAgent(
        state_dim=int(state_dim),
        action_dim=int(action_dim),
        hidden_sizes=tuple(cfg.get("hidden_sizes", (512, 512))) or (512, 512),
        gamma=float(cfg.get("gamma", 0.99)),
        lam=float(cfg.get("lam", 0.95)),
        epsilon_low=float(cfg.get("epsilon_low", 0.2)),
        epsilon_high=float(cfg.get("epsilon_high", 0.28)),
        group_size=int(cfg.get("group_size", 8)),
        target_kl=float(cfg.get("target_kl", 0.02)),
        vf_coef=float(cfg.get("vf_coef", 0.5)),
        ent_coef=float(cfg.get("ent_coef", 0.01)),
        device="cpu",
    )
    try:
        agent.load(path)
    except Exception as exc:
        _log.warning("agent.load() failed for %s: %s", path, exc)
        return None

    agent.ac.eval()
    return agent


def _interpret_action(action: np.ndarray) -> Tuple[float, str]:
    """Mean of action vector -> scalar; sign -> direction."""
    scalar = float(np.mean(action))
    return scalar, ("long" if scalar >= 0 else "short")


def _action_to_confidence(abs_action: float) -> float:
    """Map |action| to confidence tier: >0.7 high (0.85), else medium (0.60)."""
    return 0.85 if abs_action > 0.7 else 0.60


def main() -> int:
    conn = connect()
    try:
        init_pipeline_tables(conn)

        if get_control(conn, "enable_dapo_pipeline", "0") != "1":
            _log.info("Pipeline L (DAPO Agent): disabled (enable_dapo_pipeline=0)")
            return 0

        model_path = get_control(conn, "dapo_model_path", "data/dapo_checkpoint.pth")
        min_threshold = float(get_control(conn, "dapo_min_action_threshold", "0.3"))
        universe_limit = int(float(get_control(conn, "dapo_universe_limit", "30")))

        resolved_path = Path(model_path)
        if not resolved_path.is_absolute():
            resolved_path = BASE_DIR / resolved_path

        if not resolved_path.exists():
            _log.warning(
                "Pipeline L (DAPO Agent): checkpoint not found at %s — skipping",
                resolved_path,
            )
            return 0

        agent = _load_agent_from_checkpoint(str(resolved_path))
        if agent is None:
            _log.warning("Pipeline L (DAPO Agent): failed to load checkpoint at %s", resolved_path)
            return 0

        try:
            from env_stocktrading import compute_technical_indicators
        except ImportError as exc:
            _log.warning("Pipeline L (DAPO Agent): cannot import env_stocktrading: %s", exc)
            return 1

        tickers = get_universe(conn, limit=universe_limit)
        if not tickers:
            _log.warning("Pipeline L (DAPO Agent): empty universe, nothing to do")
            return 0

        _log.info(
            "Pipeline L (DAPO Agent): inference on %d tickers "
            "(state_dim=%d action_dim=%d threshold=%.2f)",
            len(tickers), agent.state_dim, agent.action_dim, min_threshold,
        )

        created = skipped_no_data = skipped_below_threshold = 0

        for ticker in tickers:
            bars = fetch_daily_bars_yahoo(ticker, limit=60)
            if not bars:
                _log.debug("no bars for %s — skipping", ticker)
                skipped_no_data += 1
                continue

            try:
                df_ind = compute_technical_indicators(_bars_to_df(ticker, bars))
            except Exception as exc:
                _log.warning("compute_technical_indicators failed for %s: %s", ticker, exc)
                skipped_no_data += 1
                continue

            state = _build_state_vector(df_ind)
            if state is None:
                _log.debug("could not build state vector for %s — skipping", ticker)
                skipped_no_data += 1
                continue

            # Align state length to agent.state_dim (pad zeros or truncate)
            if len(state) < agent.state_dim:
                state = np.pad(state, (0, agent.state_dim - len(state)), constant_values=0.0)
            elif len(state) > agent.state_dim:
                state = state[: agent.state_dim]

            try:
                action = agent.predict(state)
            except Exception as exc:
                _log.warning("agent.predict failed for %s: %s", ticker, exc)
                continue

            scalar_action, direction = _interpret_action(action)
            abs_action = abs(scalar_action)

            if abs_action < min_threshold:
                skipped_below_threshold += 1
                continue

            confidence = _action_to_confidence(abs_action)
            score = round(abs_action * 100.0, 2)
            last_bar = bars[-1]
            rationale = (
                f"dapo_action={scalar_action:.4f}; abs_action={abs_action:.4f}; "
                f"direction={direction}; close={last_bar['close']:.4f}; "
                f"date={last_bar['date']}; checkpoint={resolved_path.name}"
            )

            insert_signal(
                conn=conn,
                pipeline_id=PIPELINE_ID,
                asset=ticker,
                direction=direction,
                horizon="1d",
                confidence=confidence,
                score=score,
                rationale=rationale,
                source_refs="yahoo_finance,dapo_model,env_stocktrading",
                ttl_minutes=180,
            )
            created += 1
            _log.debug(
                "signal: %s %s action=%.4f conf=%.2f score=%.1f",
                ticker, direction, scalar_action, confidence, score,
            )

        _log.info(
            "Pipeline L (DAPO Agent): created=%d skipped_no_data=%d skipped_below_threshold=%d",
            created, skipped_no_data, skipped_below_threshold,
        )
        return 0

    except sqlite3.OperationalError as exc:
        _log.warning("Pipeline L skipped (db error): %s", exc)
        return 0
    except Exception as exc:
        _log.exception("Pipeline L (DAPO Agent): unexpected error: %s", exc)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    rc = main()
    print(f"Pipeline L (DAPO Agent): exit code {rc}")
    raise SystemExit(rc)
