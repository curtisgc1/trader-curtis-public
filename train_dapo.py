"""
train_dapo.py — Offline DAPO agent training script.

Run manually against historical NASDAQ-100 data. NOT part of the live scan pipeline.

Usage:
    python3 train_dapo.py [--epochs N] [--tickers AAPL,MSFT,...] [--output path]
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yfinance as yf

from dapo_model import DAPOAgent
from env_stocktrading import StockTradingEnv, compute_technical_indicators

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO",
    "COSTCO", "AMD", "NFLX", "ADBE", "QCOM", "INTC", "CSCO", "PEP", "TXN",
    "AMGN", "HON", "INTU", "SBUX", "MDLZ", "ISRG", "LRCX", "MU", "KLAC",
    "ASML", "PANW", "AMAT",
]

TRAIN_START = "2013-01-01"
TRAIN_END   = "2023-12-31"

# Hyperparameters
HP = {
    "hidden":          512,
    "layers":          2,
    "epochs":          100,
    "steps_per_epoch": 4096,
    "epsilon_low":     0.2,
    "epsilon_high":    0.28,
    "gamma":           0.99,
    "lam":             0.95,
    "lr":              3e-4,
    "group_size":      8,
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def download_bars(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Download adjusted daily OHLCV bars from Yahoo Finance and return a
    flat DataFrame with columns: date, tic, open, high, low, close, volume."""
    print(f"[data] Downloading {len(tickers)} tickers from {start} to {end} ...")
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    # yfinance returns a MultiIndex when multiple tickers are requested
    if isinstance(raw.columns, pd.MultiIndex):
        frames = []
        for tic in tickers:
            try:
                df = raw.xs(tic, axis=1, level=1).copy()
            except KeyError:
                print(f"[data]   warning: no data for {tic}, skipping")
                continue
            df = df.dropna(subset=["Close"])
            df["tic"] = tic
            df.index.name = "date"
            df = df.reset_index()
            frames.append(df)
        combined = pd.concat(frames, ignore_index=True)
    else:
        # Single ticker fallback
        raw = raw.dropna(subset=["Close"])
        raw["tic"] = tickers[0]
        raw.index.name = "date"
        combined = raw.reset_index()

    combined.columns = [c.lower() for c in combined.columns]
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values(["date", "tic"]).reset_index(drop=True)
    print(f"[data] Downloaded {len(combined)} rows across {combined['tic'].nunique()} tickers.")
    return combined


def add_sentiment_features(df: pd.DataFrame) -> pd.DataFrame:
    """Placeholder: LLM sentiment/risk features not available offline.
    Fills columns with neutral 0.5 values so the env signature stays stable."""
    df = df.copy()
    df["llm_sentiment"]   = 0.5
    df["llm_risk"]        = 0.5
    df["llm_macro_score"] = 0.5
    return df


def build_dataset(tickers: list[str]) -> pd.DataFrame:
    df = download_bars(tickers, TRAIN_START, TRAIN_END)
    print("[data] Computing technical indicators ...")
    df = compute_technical_indicators(df)
    df = add_sentiment_features(df)
    df = df.dropna().reset_index(drop=True)
    print(f"[data] Final dataset: {len(df)} rows, {df.columns.tolist()}")
    return df


# ---------------------------------------------------------------------------
# Trajectory collection
# ---------------------------------------------------------------------------

def collect_trajectory(
    env: StockTradingEnv,
    agent: DAPOAgent,
    steps: int,
    gamma: float,
    lam: float,
) -> dict:
    """Roll out the agent in the env for `steps` steps and return a buffer
    dict with keys: states, actions, log_probs, rewards, values, dones."""
    states, actions, log_probs, rewards, values, dones = [], [], [], [], [], []

    obs, _ = env.reset()
    obs = torch.tensor(obs, dtype=torch.float32)

    for _ in range(steps):
        with torch.no_grad():
            action, log_prob, value = agent.act(obs)

        next_obs, reward, terminated, truncated, _ = env.step(action.numpy())
        done = terminated or truncated

        states.append(obs)
        actions.append(action)
        log_probs.append(log_prob)
        rewards.append(torch.tensor(reward, dtype=torch.float32))
        values.append(value)
        dones.append(torch.tensor(done, dtype=torch.float32))

        obs = torch.tensor(next_obs, dtype=torch.float32)
        if done:
            obs, _ = env.reset()
            obs = torch.tensor(obs, dtype=torch.float32)

    # Compute advantages (GAE-lambda)
    with torch.no_grad():
        last_value = agent.act(obs)[2]

    advantages = _gae(rewards, values, dones, last_value, gamma, lam)
    returns    = [adv + val for adv, val in zip(advantages, values)]

    return {
        "states":     torch.stack(states),
        "actions":    torch.stack(actions),
        "log_probs":  torch.stack(log_probs),
        "rewards":    torch.stack(rewards),
        "values":     torch.stack(values),
        "dones":      torch.stack(dones),
        "advantages": torch.stack(advantages),
        "returns":    torch.stack(returns),
    }


def _gae(rewards, values, dones, last_value, gamma: float, lam: float) -> list:
    advantages = []
    gae = torch.tensor(0.0)
    next_value = last_value
    for r, v, d in zip(reversed(rewards), reversed(values), reversed(dones)):
        delta = r + gamma * next_value * (1.0 - d) - v
        gae   = delta + gamma * lam * (1.0 - d) * gae
        advantages.insert(0, gae.clone())
        next_value = v
    return advantages


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train(
    df:       pd.DataFrame,
    epochs:   int,
    output:   str,
) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("[train] Building StockTradingEnv ...")
    env = StockTradingEnv(df)

    obs_dim    = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0] if hasattr(env.action_space, "shape") else env.action_space.n

    print(f"[train] obs_dim={obs_dim}  action_dim={action_dim}")
    print(f"[train] Hyperparameters: {HP}")

    agent = DAPOAgent(
        obs_dim=obs_dim,
        action_dim=action_dim,
        hidden_size=HP["hidden"],
        num_layers=HP["layers"],
        epsilon_low=HP["epsilon_low"],
        epsilon_high=HP["epsilon_high"],
        lr=HP["lr"],
        group_size=HP["group_size"],
    )

    best_cumulative_reward = -float("inf")

    for epoch in range(1, epochs + 1):
        # Collect experience
        buf = collect_trajectory(
            env,
            agent,
            steps=HP["steps_per_epoch"],
            gamma=HP["gamma"],
            lam=HP["lam"],
        )

        # Update agent
        losses = agent.update(
            states=buf["states"],
            actions=buf["actions"],
            old_log_probs=buf["log_probs"],
            advantages=buf["advantages"],
            returns=buf["returns"],
        )

        mean_reward       = buf["rewards"].mean().item()
        cumulative_reward = buf["rewards"].sum().item()
        policy_loss       = losses.get("policy_loss", float("nan"))
        value_loss        = losses.get("value_loss", float("nan"))

        # Retrieve final portfolio value from env if available
        portfolio_value = getattr(env, "portfolio_value", float("nan"))

        print(
            f"[epoch {epoch:>3}/{epochs}] "
            f"mean_reward={mean_reward:+.4f}  "
            f"cum_reward={cumulative_reward:+.2f}  "
            f"portfolio={portfolio_value:.2f}  "
            f"policy_loss={policy_loss:.4f}  "
            f"value_loss={value_loss:.4f}"
        )

        # Save best checkpoint
        if cumulative_reward > best_cumulative_reward:
            best_cumulative_reward = cumulative_reward
            torch.save(
                {
                    "epoch":             epoch,
                    "cumulative_reward": cumulative_reward,
                    "model_state":       agent.state_dict(),
                    "hp":                HP,
                },
                output_path,
            )
            print(f"[train]   ** new best checkpoint saved to {output_path} (cum_reward={cumulative_reward:+.2f}) **")

    print(f"\n[train] Done. Best cumulative reward: {best_cumulative_reward:+.2f}")
    print(f"[train] Checkpoint saved at: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline DAPO agent training on historical NASDAQ-100 data."
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=HP["epochs"],
        help=f"Number of training epochs (default: {HP['epochs']})",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Comma-separated list of tickers (default: top 30 NASDAQ-100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/dapo_checkpoint.pth",
        help="Path to save best checkpoint (default: data/dapo_checkpoint.pth)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tickers = (
        [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        if args.tickers
        else DEFAULT_TICKERS
    )
    if not tickers:
        print("[error] No tickers specified.")
        sys.exit(1)

    # Override epoch count from CLI
    HP["epochs"] = args.epochs

    print("=" * 60)
    print("DAPO Offline Training")
    print(f"  Tickers : {tickers}")
    print(f"  Date    : {TRAIN_START} -> {TRAIN_END}")
    print(f"  Epochs  : {args.epochs}")
    print(f"  Output  : {args.output}")
    print("=" * 60)

    df = build_dataset(tickers)
    train(df=df, epochs=args.epochs, output=args.output)


if __name__ == "__main__":
    main()
