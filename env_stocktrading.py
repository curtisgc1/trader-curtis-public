"""
StockTradingEnv — Gymnasium trading environment for the DAPO agent.
Adapted from FinRL. Supports LLM sentiment/risk columns and turbulence-based
forced liquidation.
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces
from typing import Optional


DEFAULT_TECH_INDICATORS = ["macd", "rsi_30", "cci_30", "dx_30"]


class StockTradingEnv(gym.Env):
    """
    Multi-stock trading environment compatible with Gymnasium.

    State vector layout:
        [cash, price_0..price_n, holding_0..holding_n,
         indicator_0_0..indicator_n_k,
         (optional) sentiment_0..sentiment_n,
         (optional) risk_0..risk_n]

    Action space: Box(-1, 1, shape=(stock_dim,))
        Positive → buy, negative → sell, scaled by hmax.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        df: pd.DataFrame,
        stock_dim: int,
        hmax: int = 100,
        initial_amount: float = 1_000_000.0,
        transaction_cost_pct: float = 0.001,
        reward_scaling: float = 1e-4,
        tech_indicator_list: Optional[list[str]] = None,
        turbulence_threshold: float = float("inf"),
        sentiment_col: Optional[str] = None,
        risk_col: Optional[str] = None,
    ) -> None:
        super().__init__()

        self.df = df.reset_index(drop=True)
        self.stock_dim = stock_dim
        self.hmax = hmax
        self.initial_amount = float(initial_amount)
        self.transaction_cost_pct = transaction_cost_pct
        self.reward_scaling = reward_scaling
        self.tech_indicator_list = (
            tech_indicator_list if tech_indicator_list is not None
            else list(DEFAULT_TECH_INDICATORS)
        )
        self.turbulence_threshold = turbulence_threshold
        self.sentiment_col = sentiment_col
        self.risk_col = risk_col

        self._dates: list = sorted(self.df["date"].unique().tolist())
        self._n_days: int = len(self._dates)
        self._use_sentiment = sentiment_col is not None and sentiment_col in df.columns
        self._use_risk = risk_col is not None and risk_col in df.columns

        n_ind = len(self.tech_indicator_list)
        state_dim = (
            1
            + self.stock_dim          # prices
            + self.stock_dim          # holdings
            + self.stock_dim * n_ind  # indicators
            + (self.stock_dim if self._use_sentiment else 0)
            + (self.stock_dim if self._use_risk else 0)
        )

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(state_dim,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.stock_dim,), dtype=np.float32
        )

        # Mutable episode state
        self._day: int = 0
        self._cash: float = self.initial_amount
        self._holdings: np.ndarray = np.zeros(self.stock_dim, dtype=np.float64)
        self._portfolio_value: float = self.initial_amount
        self._terminated: bool = False

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        self._day = 0
        self._cash = self.initial_amount
        self._holdings = np.zeros(self.stock_dim, dtype=np.float64)
        self._portfolio_value = self.initial_amount
        self._terminated = False
        return self._get_state(), {}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        if self._terminated:
            raise RuntimeError("Cannot call step() after episode has terminated.")

        day_df = self._day_df(self._day)
        prices: np.ndarray = day_df["close"].to_numpy(dtype=np.float64)

        # Turbulence guard: liquidate all before acting
        turbulence = self._get_turbulence(day_df)
        if turbulence > self.turbulence_threshold:
            self._liquidate_all(prices)
            action = np.zeros(self.stock_dim, dtype=np.float32)

        scaled: np.ndarray = (action * self.hmax).astype(np.float64)

        # Sells first (frees cash for buys)
        for i in range(self.stock_dim):
            if scaled[i] < 0:
                shares = min(int(-scaled[i]), int(self._holdings[i]))
                if shares > 0:
                    proceeds = shares * prices[i]
                    self._cash += proceeds - proceeds * self.transaction_cost_pct
                    self._holdings[i] -= shares

        # Buys
        for i in range(self.stock_dim):
            if scaled[i] > 0 and prices[i] > 0:
                shares = int(scaled[i])
                max_aff = int(self._cash / (prices[i] * (1 + self.transaction_cost_pct)))
                shares = min(shares, max_aff)
                if shares > 0:
                    spend = shares * prices[i]
                    self._cash -= spend + spend * self.transaction_cost_pct
                    self._holdings[i] += shares

        prev_value = self._portfolio_value
        self._day += 1
        terminated = self._day >= self._n_days
        self._terminated = terminated

        if not terminated:
            next_prices = self._day_df(self._day)["close"].to_numpy(dtype=np.float64)
            self._portfolio_value = self._get_portfolio_value(next_prices)
            state = self._get_state()
        else:
            self._portfolio_value = self._get_portfolio_value(prices)
            state = np.zeros(self.observation_space.shape, dtype=np.float32)

        reward = (self._portfolio_value - prev_value) * self.reward_scaling
        info = {
            "portfolio_value": self._portfolio_value,
            "cash": self._cash,
            "holdings": self._holdings.copy(),
            "day": self._day,
            "turbulence": turbulence,
        }
        return state, float(reward), terminated, False, info

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _day_df(self, day_idx: int) -> pd.DataFrame:
        date = self._dates[day_idx]
        return (
            self.df[self.df["date"] == date]
            .sort_values("tic")
            .reset_index(drop=True)
        )

    def _get_state(self) -> np.ndarray:
        day_df = self._day_df(self._day)
        prices = day_df["close"].to_numpy(dtype=np.float64)

        parts: list[np.ndarray] = [
            np.array([self._cash], dtype=np.float64),
            prices,
            self._holdings.copy(),
        ]
        for indicator in self.tech_indicator_list:
            col = (
                day_df[indicator].to_numpy(dtype=np.float64)
                if indicator in day_df.columns
                else np.zeros(self.stock_dim, dtype=np.float64)
            )
            parts.append(col)
        if self._use_sentiment:
            parts.append(day_df[self.sentiment_col].fillna(0.0).to_numpy(dtype=np.float64))
        if self._use_risk:
            parts.append(day_df[self.risk_col].fillna(0.0).to_numpy(dtype=np.float64))

        return np.concatenate(parts).astype(np.float32)

    def _get_portfolio_value(self, prices: np.ndarray) -> float:
        return float(self._cash + np.dot(self._holdings, prices))

    def _get_turbulence(self, day_df: pd.DataFrame) -> float:
        if "turbulence" in day_df.columns:
            vals = day_df["turbulence"].dropna()
            if not vals.empty:
                return float(vals.iloc[0])
        return 0.0

    def _liquidate_all(self, prices: np.ndarray) -> None:
        for i in range(self.stock_dim):
            if self._holdings[i] > 0 and prices[i] > 0:
                proceeds = self._holdings[i] * prices[i]
                self._cash += proceeds - proceeds * self.transaction_cost_pct
                self._holdings[i] = 0.0


# ---------------------------------------------------------------------------
# Technical indicator computation (no TA-Lib dependency)
# ---------------------------------------------------------------------------

def compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute MACD, RSI(30), CCI(30), and DX(30) for each ticker in df.

    Parameters
    ----------
    df : pd.DataFrame
        Raw OHLCV DataFrame with columns [date, tic, open, high, low, close, volume].

    Returns
    -------
    pd.DataFrame
        Original DataFrame augmented with [macd, rsi_30, cci_30, dx_30] columns.
    """
    df = df.copy().sort_values(["tic", "date"]).reset_index(drop=True)
    results: list[pd.DataFrame] = []

    for _tic, group in df.groupby("tic"):
        group = group.copy().sort_values("date").reset_index(drop=True)
        close = group["close"]
        high = group["high"]
        low = group["low"]

        # MACD: difference of 12-period and 26-period EMAs
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        group["macd"] = ema12 - ema26

        # RSI(30): exponential smoothed gains vs losses
        delta = close.diff()
        avg_gain = delta.clip(lower=0).ewm(com=29, adjust=False).mean()
        avg_loss = (-delta).clip(lower=0).ewm(com=29, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        group["rsi_30"] = (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)

        # CCI(30): (Typical Price - SMA_TP) / (0.015 * MAD)
        tp = (high + low + close) / 3.0
        sma_tp = tp.rolling(30, min_periods=1).mean()
        mad = tp.rolling(30, min_periods=1).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
        )
        group["cci_30"] = ((tp - sma_tp) / (0.015 * mad.replace(0, np.nan))).fillna(0.0)

        # DX(30): Directional Movement Index
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        up_move = high.diff()
        dn_move = -low.diff()
        plus_dm = up_move.where((up_move > dn_move) & (up_move > 0), 0.0)
        minus_dm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0)
        atr = tr.rolling(30, min_periods=1).mean()
        plus_di = 100.0 * plus_dm.rolling(30, min_periods=1).mean() / atr.replace(0, np.nan)
        minus_di = 100.0 * minus_dm.rolling(30, min_periods=1).mean() / atr.replace(0, np.nan)
        di_sum = plus_di + minus_di
        group["dx_30"] = (100.0 * (plus_di - minus_di).abs() / di_sum.replace(0, np.nan)).fillna(0.0)

        results.append(group)

    return pd.concat(results, ignore_index=True).sort_values(["date", "tic"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-01", periods=60, freq="B").strftime("%Y-%m-%d").tolist()
    tickers = ["AAPL", "MSFT", "GOOG"]
    rows = []
    for tic in tickers:
        price = 100.0
        for d in dates:
            price *= 1 + rng.normal(0, 0.01)
            rows.append({
                "date": d, "tic": tic,
                "open": price * 0.99, "high": price * 1.01,
                "low": price * 0.98, "close": price,
                "volume": int(rng.integers(1_000_000, 5_000_000)),
            })
    raw_df = pd.DataFrame(rows)

    print("Computing technical indicators...")
    df = compute_technical_indicators(raw_df)
    print(df[["date", "tic", "close", "macd", "rsi_30", "cci_30", "dx_30"]].tail(9).to_string())

    env = StockTradingEnv(df=df, stock_dim=len(tickers))
    obs, _ = env.reset()
    print(f"\nObservation shape : {obs.shape}")
    print(f"Action space      : {env.action_space}")

    total_reward, steps, terminated = 0.0, 0, False
    while not terminated:
        obs, reward, terminated, _, info = env.step(env.action_space.sample())
        total_reward += reward
        steps += 1

    print(f"\nEpisode finished   : {steps} steps")
    print(f"Total reward       : {total_reward:.4f}")
    print(f"Final portfolio    : ${info['portfolio_value']:,.2f}")
    print(f"Cash remaining     : ${info['cash']:,.2f}")
