"""Layer 6 -- Agent-based market simulation for prediction markets.

Heterogeneous agent model implementing Kyle (1985) price-impact dynamics
for binary-outcome prediction markets.  Four agent archetypes interact
through a simple price-impact order book:
    Informed  -- noisy signal of true probability, trade when edge > threshold
    Noise     -- random buy/sell, supply liquidity
    Momentum  -- chase recent price trends
    Maker     -- quote around mid with spread proportional to uncertainty

All prices are bounded to [0.01, 0.99] (binary contract).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

import numpy as np
from numpy.typing import NDArray

from . import _db

PRICE_LO = 0.01
PRICE_HI = 0.99


# -- Agent dataclasses -----------------------------------------------------

@dataclass(frozen=True)
class InformedAgent:
    """Knows true_prob with additive Gaussian noise."""
    signal_noise: float = 0.08
    edge_threshold: float = 0.03
    size: float = 1.0


@dataclass(frozen=True)
class NoiseAgent:
    """Random buy/sell each tick with configurable intensity."""
    intensity: float = 0.5
    size: float = 0.5


@dataclass(frozen=True)
class MomentumAgent:
    """Follows recent price trend over a lookback window."""
    lookback: int = 10
    scale: float = 2.0
    size: float = 0.8


@dataclass(frozen=True)
class MakerAgent:
    """Quotes around mid-price; spread widens with uncertainty."""
    base_spread: float = 0.02
    depth: float = 1.5


# -- Simulator --------------------------------------------------------------

@dataclass
class MarketSimulator:
    """Run an agent-based prediction-market simulation.

    Parameters
    ----------
    true_prob       -- latent ground-truth probability the event resolves YES
    n_informed/n_noise/n_momentum/n_makers -- counts per agent archetype
    tick_size       -- minimum price increment for rounding
    """
    true_prob: float = 0.5
    n_informed: int = 20
    n_noise: int = 50
    n_momentum: int = 10
    n_makers: int = 5
    tick_size: float = 0.01

    _informed: List[InformedAgent] = field(default_factory=list, repr=False)
    _noise: List[NoiseAgent] = field(default_factory=list, repr=False)
    _momentum: List[MomentumAgent] = field(default_factory=list, repr=False)
    _makers: List[MakerAgent] = field(default_factory=list, repr=False)
    _rng: np.random.Generator = field(
        default_factory=lambda: np.random.default_rng(), repr=False,
    )

    def __post_init__(self) -> None:
        self._build_agents()

    def _build_agents(self) -> None:
        """Instantiate agent populations with slight heterogeneity."""
        rng = self._rng
        self._informed = [
            InformedAgent(
                signal_noise=max(0.02, 0.08 + rng.normal(0, 0.02)),
                edge_threshold=max(0.005, 0.03 + rng.normal(0, 0.01)),
                size=max(0.2, 1.0 + rng.normal(0, 0.3)),
            )
            for _ in range(self.n_informed)
        ]
        self._noise = [
            NoiseAgent(
                intensity=max(0.1, 0.5 + rng.normal(0, 0.15)),
                size=max(0.1, 0.5 + rng.normal(0, 0.15)),
            )
            for _ in range(self.n_noise)
        ]
        self._momentum = [
            MomentumAgent(
                lookback=max(3, int(10 + rng.normal(0, 3))),
                scale=max(0.5, 2.0 + rng.normal(0, 0.5)),
                size=max(0.2, 0.8 + rng.normal(0, 0.2)),
            )
            for _ in range(self.n_momentum)
        ]
        self._makers = [
            MakerAgent(
                base_spread=max(0.005, 0.02 + rng.normal(0, 0.005)),
                depth=max(0.5, 1.5 + rng.normal(0, 0.3)),
            )
            for _ in range(self.n_makers)
        ]

    # -- Agent order generation (vectorised where possible) -----------------

    def _informed_orders(self, price: float) -> NDArray[np.float64]:
        """Signed order array for informed agents."""
        n = len(self._informed)
        if n == 0:
            return np.zeros(0)
        noises = np.array([a.signal_noise for a in self._informed])
        thresholds = np.array([a.edge_threshold for a in self._informed])
        sizes = np.array([a.size for a in self._informed])
        signals = np.clip(
            self.true_prob + self._rng.normal(0, noises), PRICE_LO, PRICE_HI,
        )
        edges = signals - price
        active = np.abs(edges) > thresholds
        return np.where(active, np.sign(edges) * sizes, 0.0)

    def _noise_orders(self) -> NDArray[np.float64]:
        """Signed order array for noise agents."""
        n = len(self._noise)
        if n == 0:
            return np.zeros(0)
        intensities = np.array([a.intensity for a in self._noise])
        sizes = np.array([a.size for a in self._noise])
        active = self._rng.random(n) < intensities
        directions = self._rng.choice([-1.0, 1.0], size=n)
        return np.where(active, directions * sizes, 0.0)

    def _momentum_orders(self, price_path: Sequence[float]) -> NDArray[np.float64]:
        """Signed order array for momentum agents."""
        n = len(self._momentum)
        if n == 0:
            return np.zeros(0)
        orders = np.zeros(n)
        path_arr = np.array(price_path)
        for i, agent in enumerate(self._momentum):
            if len(path_arr) < agent.lookback + 1:
                continue
            window = path_arr[-agent.lookback:]
            trend = (window[-1] - window[0]) / max(window[0], PRICE_LO)
            orders[i] = np.clip(trend * agent.scale, -1, 1) * agent.size
        return orders

    def _maker_orders(self, price: float) -> NDArray[np.float64]:
        """Market makers provide mean-reverting liquidity.

        Sell above 0.5, buy below 0.5, size proportional to deviation.
        Spread widens with uncertainty (highest at p=0.5).
        """
        n = len(self._makers)
        if n == 0:
            return np.zeros(0)
        spreads = np.array([a.base_spread for a in self._makers])
        depths = np.array([a.depth for a in self._makers])
        uncertainty = 4.0 * price * (1.0 - price)  # peaks at 1.0 when p=0.5
        effective_spread = spreads * (1.0 + uncertainty)
        deviation = price - 0.5
        return np.where(
            np.abs(deviation) > effective_spread,
            -np.sign(deviation) * depths * np.abs(deviation),
            0.0,
        )

    # -- Core simulation loop -----------------------------------------------

    def run(self, n_steps: int = 500, dt: float = 1.0) -> Dict[str, Any]:
        """Simulate market for *n_steps* ticks.

        Returns dict with: price_path, volume_path, order_flow,
        kyle_lambda, final_price, price_discovery_speed, true_prob.
        """
        t0 = time.perf_counter()
        price = 0.5  # start at maximum-uncertainty mid
        price_path: List[float] = [price]
        volume_path: List[float] = []
        order_flow: List[float] = []

        # Adaptive lambda: starts high (thin book), decays as volume grows
        base_lambda = 0.05 / max(
            1, (self.n_informed + self.n_noise + self.n_momentum) ** 0.5,
        )
        cumulative_volume = 0.0

        for _step in range(n_steps):
            inf = self._informed_orders(price)
            noi = self._noise_orders()
            mom = self._momentum_orders(price_path)
            mkr = self._maker_orders(price)

            signed_flow = float(inf.sum() + noi.sum() + mom.sum() + mkr.sum())
            abs_volume = float(
                np.abs(inf).sum() + np.abs(noi).sum()
                + np.abs(mom).sum() + np.abs(mkr).sum(),
            )
            cumulative_volume += abs_volume

            # Price impact with volume-adaptive decay
            volume_decay = 1.0 / (1.0 + 0.001 * cumulative_volume)
            delta_p = base_lambda * volume_decay * dt * signed_flow
            price = float(np.clip(price + delta_p, PRICE_LO, PRICE_HI))

            # Round to tick size
            price = round(round(price / self.tick_size) * self.tick_size, 10)
            price = float(np.clip(price, PRICE_LO, PRICE_HI))

            price_path.append(price)
            volume_path.append(abs_volume)
            order_flow.append(signed_flow)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        kyle_lam = self.estimate_kyle_lambda(price_path, order_flow)
        discovery_speed = self.price_discovery_metric(price_path, self.true_prob)

        result: Dict[str, Any] = {
            "price_path": price_path,
            "volume_path": volume_path,
            "order_flow": order_flow,
            "kyle_lambda": kyle_lam,
            "final_price": price_path[-1],
            "price_discovery_speed": discovery_speed,
            "true_prob": self.true_prob,
        }

        # Persist to DB (best-effort)
        try:
            conn = _db.get_conn()
            _db.save_run(
                conn,
                layer="market_sim",
                params={
                    "true_prob": self.true_prob,
                    "n_informed": self.n_informed,
                    "n_noise": self.n_noise,
                    "n_momentum": self.n_momentum,
                    "n_makers": self.n_makers,
                    "n_steps": n_steps,
                    "dt": dt,
                },
                result={
                    "kyle_lambda": kyle_lam,
                    "final_price": price_path[-1],
                    "price_discovery_speed": discovery_speed,
                    "mean_volume": float(np.mean(volume_path)),
                },
                edge_pct=(price_path[-1] - self.true_prob) * 100,
                elapsed_ms=elapsed_ms,
            )
            conn.close()
        except Exception:
            pass  # results still returned even if DB fails

        return result

    # -- Analytics ----------------------------------------------------------

    @staticmethod
    def estimate_kyle_lambda(
        price_path: Sequence[float],
        order_flow: Sequence[float],
    ) -> float:
        """Estimate Kyle's lambda via OLS: delta_p = lambda * signed_flow + eps.

        Higher lambda = larger permanent price impact per unit order flow.
        """
        prices = np.array(price_path)
        flows = np.array(order_flow)
        if len(prices) < 3 or len(flows) < 2:
            return 0.0

        delta_p = np.diff(prices[: len(flows) + 1])
        if len(delta_p) != len(flows):
            min_len = min(len(delta_p), len(flows))
            delta_p, flows = delta_p[:min_len], flows[:min_len]

        flow_var = float(np.var(flows))
        if flow_var < 1e-12:
            return 0.0

        cov = float(np.mean(delta_p * flows) - np.mean(delta_p) * np.mean(flows))
        return cov / flow_var

    @staticmethod
    def price_discovery_metric(
        price_path: Sequence[float],
        true_prob: float,
    ) -> float:
        """Half-life of price-discovery: ticks for |price - true_prob| to halve.

        Lower = faster discovery.  Falls back to len(price_path) if the
        error never reaches 50% of its initial value.
        """
        errors = np.abs(np.array(price_path) - true_prob)
        if len(errors) < 2 or errors[0] < 1e-9:
            return 0.0
        below = np.where(errors <= errors[0] / 2.0)[0]
        if len(below) == 0:
            return float(len(price_path))
        return float(below[0])

    @staticmethod
    def compute_edge(market_price: float, true_prob: float) -> float:
        """Expected profit per contract: true_prob - market_price.

        Positive = YES underpriced, negative = overpriced.
        """
        return true_prob - market_price

    def sensitivity_analysis(
        self,
        param_name: str,
        param_range: Sequence[float],
        n_trials: int = 20,
    ) -> Dict[str, Any]:
        """Sweep *param_name* over *param_range*, measure price discovery.

        Supported: true_prob, n_informed, n_noise, n_momentum, n_makers.
        Returns dict with param_values, kyle_lambdas, discovery_speeds,
        final_prices (each a list of means across trials).
        """
        valid = {"true_prob", "n_informed", "n_noise", "n_momentum", "n_makers"}
        if param_name not in valid:
            raise ValueError(f"Unknown param '{param_name}'. Choose from {valid}")

        int_params = {"n_informed", "n_noise", "n_momentum", "n_makers"}
        kyle_lambdas: List[float] = []
        discovery_speeds: List[float] = []
        final_prices: List[float] = []

        for value in param_range:
            kyles: List[float] = []
            speeds: List[float] = []
            finals: List[float] = []

            for _ in range(n_trials):
                kwargs: Dict[str, Any] = {
                    "true_prob": self.true_prob,
                    "n_informed": self.n_informed,
                    "n_noise": self.n_noise,
                    "n_momentum": self.n_momentum,
                    "n_makers": self.n_makers,
                    "tick_size": self.tick_size,
                }
                kwargs[param_name] = int(value) if param_name in int_params else float(value)
                out = MarketSimulator(**kwargs).run(n_steps=200)
                kyles.append(out["kyle_lambda"])
                speeds.append(out["price_discovery_speed"])
                finals.append(out["final_price"])

            kyle_lambdas.append(float(np.mean(kyles)))
            discovery_speeds.append(float(np.mean(speeds)))
            final_prices.append(float(np.mean(finals)))

        return {
            "param_name": param_name,
            "param_values": [float(v) for v in param_range],
            "kyle_lambdas": kyle_lambdas,
            "discovery_speeds": discovery_speeds,
            "final_prices": final_prices,
        }


# -- CLI demo ---------------------------------------------------------------

def _main() -> None:
    """Run a single simulation and print key metrics."""
    sim = MarketSimulator(true_prob=0.72, n_informed=25, n_noise=60)
    result = sim.run(n_steps=500)

    print("=== Market Simulation (Layer 6) ===")
    print(f"True probability   : {sim.true_prob:.4f}")
    print(f"Final market price : {result['final_price']:.4f}")
    print(f"Kyle's lambda      : {result['kyle_lambda']:.6f}")
    print(f"Discovery half-life: {result['price_discovery_speed']:.1f} ticks")
    print(f"Edge at close      : {sim.compute_edge(result['final_price'], sim.true_prob):+.4f}")
    print(f"Mean tick volume   : {np.mean(result['volume_path']):.2f}")

    print("\n--- Sensitivity: n_informed ---")
    sweep = sim.sensitivity_analysis("n_informed", [5, 10, 20, 40, 80], n_trials=10)
    for val, lam, spd in zip(
        sweep["param_values"], sweep["kyle_lambdas"], sweep["discovery_speeds"],
    ):
        print(f"  n_informed={int(val):3d}  lambda={lam:.6f}  half-life={spd:.1f}")


if __name__ == "__main__":
    _main()
