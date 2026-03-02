"""Monte Carlo simulation engine for Polymarket binary contract pricing.

Layer 1 of the quant simulation stack. Uses logit-diffusion (NOT GBM) to
model bounded probability processes that resolve to 0 or 1.

Key corrections (per "Monte Carlo to Mirages" critique):
  - Logit-diffusion keeps paths in [0,1] by construction
  - Brownian bridge conditioning for near-expiry contracts
  - Brier Skill Score (BSS) alongside raw Brier
  - Execution cost model (spread + slippage)

Usage::

    from simulations.monte_carlo import MonteCarloEngine
    engine = MonteCarloEngine()
    result = engine.simulate(prob_estimate=0.62, market_price=0.55)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# DB integration -- optional so __main__ works without the package context
# ---------------------------------------------------------------------------
try:
    from . import _db
except ImportError:
    _db = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SimulationResult:
    """Immutable snapshot of a single Monte Carlo run."""

    fair_price: float
    edge_pct: float
    edge_after_costs: float
    brier: float
    brier_skill_score: float
    ci_95: Tuple[float, float]
    paths_won: int
    n_paths: int
    horizon_days: int
    vol: float
    prob_estimate: float
    market_price: float
    execution_cost_pct: float
    elapsed_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fair_price": round(self.fair_price, 6),
            "edge_pct": round(self.edge_pct, 4),
            "edge_after_costs": round(self.edge_after_costs, 4),
            "brier": round(self.brier, 6),
            "brier_skill_score": round(self.brier_skill_score, 6),
            "ci_95": [round(self.ci_95[0], 6), round(self.ci_95[1], 6)],
            "paths_won": self.paths_won,
            "n_paths": self.n_paths,
            "horizon_days": self.horizon_days,
            "vol": self.vol,
            "prob_estimate": self.prob_estimate,
            "market_price": self.market_price,
            "execution_cost_pct": round(self.execution_cost_pct, 4),
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


# ---------------------------------------------------------------------------
# Helpers -- pure functions, no mutation
# ---------------------------------------------------------------------------

def _logit(p: np.ndarray) -> np.ndarray:
    """Logit transform, clamped to avoid infinities."""
    p_safe = np.clip(p, 1e-8, 1.0 - 1e-8)
    return np.log(p_safe / (1.0 - p_safe))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Inverse logit (sigmoid), numerically stable."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-x)),
        np.exp(x) / (1.0 + np.exp(x)),
    )


def _logit_diffusion_paths(
    p0: float,
    vol: float,
    T: float,
    n_paths: int,
    n_steps: int,
    rng: np.random.Generator,
    resolution: Optional[float] = None,
) -> np.ndarray:
    """Generate logit-diffusion paths and return terminal probabilities.

    Correct model for prediction market contracts (NOT GBM):
      logit(p_{t+1}) = logit(p_t) + sigma * dW_t

    When resolution is provided (0 or 1), uses Brownian bridge conditioning
    to model near-expiry convergence toward the known outcome.

    All paths stay bounded in (0, 1) by construction.
    """
    dt = T / n_steps
    sqrt_dt = math.sqrt(dt)
    x0 = _logit(np.array([p0]))[0]

    if resolution is not None:
        # Brownian bridge: condition on resolving to 0 or 1
        logit_target = _logit(np.array([np.clip(resolution, 0.01, 0.99)]))[0]

        # Step-by-step bridge (drift toward target)
        x = np.full(n_paths, x0)
        for t in range(n_steps):
            remaining_steps = n_steps - t
            remaining_time = remaining_steps * dt
            bridge_drift = (logit_target - x) / max(remaining_time, dt) * dt
            noise = rng.standard_normal(n_paths) * vol * sqrt_dt
            x = x + bridge_drift + noise
        return _sigmoid(x)

    # Standard logit-diffusion (zero drift — no measure mixing)
    dW = rng.standard_normal((n_paths, n_steps)) * sqrt_dt
    increments = vol * dW
    x_T = x0 + np.sum(increments, axis=1)
    return _sigmoid(x_T)


def _brier_score(forecasts: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean Brier score. Lower is better; 0 = perfect."""
    f = np.asarray(forecasts, dtype=np.float64)
    o = np.asarray(outcomes, dtype=np.float64)
    if f.size == 0:
        return 1.0
    return float(np.mean((f - o) ** 2))


def _brier_skill_score(
    model_brier: float,
    base_rate: float,
) -> float:
    """Brier Skill Score: BSS = 1 - BS_model / BS_baseline.

    Baseline is the naive climatological forecast (always predict base_rate).
    BSS = 0 means no better than naive. BSS = 1 is perfect.
    BSS < 0 means actively worse than doing nothing.
    """
    # Naive baseline Brier: base_rate * (1-base_rate)^2 + (1-base_rate) * base_rate^2
    # Simplifies to: base_rate * (1 - base_rate)
    baseline_brier = base_rate * (1.0 - base_rate)
    if baseline_brier < 1e-10:
        return 0.0
    return 1.0 - model_brier / baseline_brier


def _execution_cost(
    market_price: float,
    spread_cents: float = 0.04,
    slippage_cents: float = 0.02,
    taker_fee_pct: float = 0.0315,
) -> float:
    """Estimate round-trip execution cost as percentage of edge.

    Based on typical Polymarket CLOB:
      - Spread: 3-8 cents (default 4c)
      - Slippage: 1-3 cents for typical sizes (default 2c)
      - Taker fee: 3.15% of notional
    """
    half_spread = spread_cents / 2.0
    effective_entry = market_price + half_spread + slippage_cents
    fee_cost = effective_entry * taker_fee_pct
    return (half_spread + slippage_cents + fee_cost) / max(market_price, 0.01) * 100.0


def _wilson_ci(p_hat: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score 95% confidence interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    denom = 1.0 + z * z / n
    centre = (p_hat + z * z / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt(
        p_hat * (1.0 - p_hat) / n + z * z / (4.0 * n * n)
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MonteCarloEngine:
    """Monte Carlo pricer for Polymarket-style binary contracts.

    All methods produce new result objects -- no internal state mutation.
    Optional *seed* makes runs reproducible.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        prob_estimate: float,
        market_price: float,
        *,
        n_paths: int = 10_000,
        horizon_days: int = 7,
        vol: float = 0.3,
        n_steps: int = 100,
        resolution: Optional[float] = None,
        spread_cents: float = 0.04,
        slippage_cents: float = 0.02,
        contract: str = "",
        ticker: str = "",
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Run a full MC simulation and return a result dictionary.

        Uses logit-diffusion (bounded [0,1]) instead of GBM.
        Supports Brownian bridge conditioning for near-expiry contracts.
        Computes Brier Skill Score (BSS) and execution costs.

        Args:
            resolution: If known (0.0 or 1.0), condition paths on this
                        outcome using Brownian bridge (near-expiry mode).
            spread_cents: Typical bid-ask spread on Polymarket.
            slippage_cents: Expected slippage from walking the book.
        """
        t_start = time.perf_counter()

        T = horizon_days / 365.0
        fair_price = self.price_binary(
            prob=prob_estimate, vol=vol, T=T, n_paths=n_paths,
            n_steps=n_steps, resolution=resolution,
        )

        paths_won = int(round(fair_price * n_paths))
        edge_pct = (
            (fair_price - market_price) / max(market_price, 1e-9) * 100.0
        )

        # Execution cost model
        exec_cost = _execution_cost(market_price, spread_cents, slippage_cents)
        edge_after_costs = edge_pct - exec_cost

        # Brier: treat market_price as forecast, model conviction as outcome
        outcome_indicator = 1.0 if prob_estimate >= 0.5 else 0.0
        brier = _brier_score(
            np.array([market_price]), np.array([outcome_indicator]),
        )

        # Brier Skill Score: compare against naive base-rate forecast
        bss = _brier_skill_score(brier, base_rate=market_price)

        ci_95 = _wilson_ci(fair_price, n_paths)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        result = SimulationResult(
            fair_price=fair_price,
            edge_pct=edge_pct,
            edge_after_costs=edge_after_costs,
            brier=brier,
            brier_skill_score=bss,
            ci_95=ci_95,
            paths_won=paths_won,
            n_paths=n_paths,
            horizon_days=horizon_days,
            vol=vol,
            prob_estimate=prob_estimate,
            market_price=market_price,
            execution_cost_pct=exec_cost,
            elapsed_ms=elapsed_ms,
        )

        result_dict = result.to_dict()

        if persist and _db is not None:
            self._persist_run(result=result, contract=contract, ticker=ticker)

        return result_dict

    def calibrate(
        self,
        settlements: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute calibration Brier score across historical settlements.

        Each settlement dict must have ``forecast`` (float 0-1) and
        ``outcome`` (int 0 or 1).  Returns overall brier, count, and
        per-decile bucket breakdown.
        """
        if not settlements:
            return {"brier": 1.0, "n": 0, "buckets": {}}

        forecasts = np.array([s["forecast"] for s in settlements], dtype=np.float64)
        outcomes = np.array([s["outcome"] for s in settlements], dtype=np.float64)
        overall_brier = _brier_score(forecasts, outcomes)

        # Per-decile calibration buckets
        buckets: Dict[str, Dict[str, Any]] = {}
        for lo_pct in range(0, 100, 10):
            lo = lo_pct / 100.0
            hi = (lo_pct + 10) / 100.0
            label = f"{lo_pct}-{lo_pct + 10}%"
            mask = (forecasts >= lo) & (forecasts < hi)
            n_bucket = int(mask.sum())
            if n_bucket == 0:
                buckets[label] = {
                    "n": 0, "mean_forecast": None,
                    "mean_outcome": None, "brier": None,
                }
            else:
                buckets[label] = {
                    "n": n_bucket,
                    "mean_forecast": round(float(forecasts[mask].mean()), 4),
                    "mean_outcome": round(float(outcomes[mask].mean()), 4),
                    "brier": round(
                        float(_brier_score(forecasts[mask], outcomes[mask])), 6,
                    ),
                }

        # Brier Skill Score against naive base-rate
        base_rate = float(outcomes.mean())
        bss = _brier_skill_score(overall_brier, base_rate)

        return {
            "brier": round(overall_brier, 6),
            "brier_skill_score": round(bss, 6),
            "base_rate": round(base_rate, 4),
            "n": len(settlements),
            "buckets": buckets,
        }

    def price_binary(
        self,
        prob: float,
        vol: float,
        T: float,
        n_paths: int,
        *,
        n_steps: int = 100,
        strike: float = 0.5,
        resolution: Optional[float] = None,
    ) -> float:
        """Raw MC pricing of P(contract settles YES).

        Simulates *n_paths* logit-diffusion trajectories starting from
        *prob*, returns fraction of terminal values above *strike*.

        Uses Brownian bridge when resolution is known (near-expiry).
        Zero drift by default (no P vs Q measure mixing).
        """
        terminal = _logit_diffusion_paths(
            p0=prob, vol=vol, T=T,
            n_paths=n_paths, n_steps=n_steps, rng=self._rng,
            resolution=resolution,
        )
        return float(np.mean(terminal >= strike))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _persist_run(
        self,
        result: SimulationResult,
        contract: str,
        ticker: str,
    ) -> Optional[int]:
        """Save a simulation run to the DB. Returns row id or None."""
        if _db is None:
            return None
        try:
            conn = _db.get_conn()
            row_id = _db.save_run(
                conn,
                layer="monte_carlo",
                contract=contract,
                ticker=ticker,
                params={
                    "prob_estimate": result.prob_estimate,
                    "market_price": result.market_price,
                    "horizon_days": result.horizon_days,
                    "vol": result.vol,
                    "n_paths": result.n_paths,
                },
                result=result.to_dict(),
                brier=result.brier,
                edge_pct=result.edge_pct,
                n_paths=result.n_paths,
                elapsed_ms=result.elapsed_ms,
            )
            conn.close()
            return row_id
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def _print_result(r: Dict[str, Any]) -> None:
    """Pretty-print a simulation result dict."""
    print(f"  Fair price     : {r['fair_price']:.4f}")
    print(f"  Market price   : {r['market_price']:.4f}")
    print(f"  Edge (raw)     : {r['edge_pct']:+.2f}%")
    print(f"  Exec cost      : {r['execution_cost_pct']:.2f}%")
    print(f"  Edge (net)     : {r['edge_after_costs']:+.2f}%")
    print(f"  Brier          : {r['brier']:.6f}")
    print(f"  Brier Skill    : {r['brier_skill_score']:+.6f}")
    print(f"  95% CI         : [{r['ci_95'][0]:.4f}, {r['ci_95'][1]:.4f}]")
    print(f"  Paths won      : {r['paths_won']:,} / {r['n_paths']:,}")
    print(f"  Elapsed        : {r['elapsed_ms']:.1f} ms")


def _demo() -> None:
    """Run sample simulations and print results to stdout."""
    engine = MonteCarloEngine(seed=42)

    print("=" * 60)
    print("  Monte Carlo Binary Contract Pricer -- Demo")
    print("=" * 60)

    scenarios = [
        ("Edge exists: model=62%, market=55%", 0.62, 0.55, 7, 0.3, None),
        ("Fair market: model=50%, market=50%", 0.50, 0.50, 14, 0.5, None),
        ("Contrarian:  model=30%, market=65%", 0.30, 0.65, 3, 0.25, None),
        ("Near-expiry bridge (resolve=1)", 0.85, 0.80, 0.1, 0.3, 1.0),
        ("Low base-rate (Brier trap)", 0.03, 0.02, 30, 0.2, None),
    ]

    for title, prob, mkt, days, vol, resolution in scenarios:
        print(f"\n--- {title} ---")
        result = engine.simulate(
            prob_estimate=prob, market_price=mkt,
            n_paths=50_000, horizon_days=days, vol=vol,
            resolution=resolution, persist=False,
        )
        _print_result(result)

    # --- Calibration demo -----------------------------------------------
    print("\n--- Calibration on synthetic settlements ---")
    rng = np.random.default_rng(99)
    settlements = []
    for _ in range(200):
        true_p = rng.uniform(0.1, 0.9)
        forecast = float(np.clip(true_p + rng.normal(0, 0.08), 0.01, 0.99))
        outcome = int(rng.random() < true_p)
        settlements.append({"forecast": forecast, "outcome": outcome})

    cal = engine.calibrate(settlements)
    print(f"  Overall Brier : {cal['brier']:.6f}")
    print(f"  Brier Skill   : {cal['brier_skill_score']:+.6f}")
    print(f"  Base rate     : {cal['base_rate']:.4f}")
    print(f"  Settlements   : {cal['n']}")
    print("  Bucket breakdown:")
    for label, stats in cal["buckets"].items():
        if stats["n"] > 0:
            print(
                f"    {label:>8s}  n={stats['n']:3d}  "
                f"avg_fc={stats['mean_forecast']:.3f}  "
                f"avg_out={stats['mean_outcome']:.3f}  "
                f"brier={stats['brier']:.4f}"
            )

    print("\n" + "=" * 60)
    print("  Done.")
    print("=" * 60)


if __name__ == "__main__":
    _demo()
