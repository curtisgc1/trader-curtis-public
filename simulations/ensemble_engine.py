"""Layer 7 — Ensemble Engine: production integration.

Wires all simulation layers into a single entry-point that:
  1. Runs MC + variance-reduction to get a calibrated fair price
  2. Uses importance sampling for tail-risk if contract is extreme
  3. Tracks live probability via particle filter
  4. Estimates correlated portfolio risk via copula
  5. Gauges price-discovery dynamics via agent-based sim
  6. Combines into EVT-inspired VaR/ES + Brier tracking
  7. Emits a kelly-compatible (prob, edge) signal for kelly_signal.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from . import _db
from .monte_carlo import MonteCarloEngine
from .importance_sampling import ImportanceSampler
from .particle_filter import ParticleFilter
from .variance_reduction import VarianceReducer
from .copula import CopulaModel
from .market_sim import MarketSimulator


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnsembleResult:
    """Immutable result from a full ensemble run."""
    contract: str
    ensemble_prob: float
    market_price: float
    edge_pct: float
    brier: float
    var_95: float
    es_95: float
    effective_n: int
    layer_results: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract": self.contract,
            "ensemble_prob": round(self.ensemble_prob, 6),
            "market_price": round(self.market_price, 6),
            "edge_pct": round(self.edge_pct, 4),
            "brier": round(self.brier, 6),
            "var_95": round(self.var_95, 4),
            "es_95": round(self.es_95, 4),
            "effective_n": self.effective_n,
            "layer_results": self.layer_results,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


# ---------------------------------------------------------------------------
# Ensemble Engine
# ---------------------------------------------------------------------------

class EnsembleEngine:
    """Production integration layer: runs all sim modules and combines results."""

    def __init__(
        self,
        n_mc_paths: int = 10_000,
        n_is_samples: int = 20_000,
        n_particles: int = 500,
        n_market_steps: int = 300,
        vol: float = 0.30,
        horizon_days: float = 7.0,
        tail_threshold: float = 0.05,
    ) -> None:
        self.n_mc_paths = n_mc_paths
        self.n_is_samples = n_is_samples
        self.n_particles = n_particles
        self.n_market_steps = n_market_steps
        self.vol = vol
        self.horizon_days = horizon_days
        self.tail_threshold = tail_threshold

    # ------------------------------------------------------------------
    # Core: full ensemble for a single contract
    # ------------------------------------------------------------------

    def run(
        self,
        contract: str,
        prob_estimate: float,
        market_price: float,
        price_history: Optional[List[float]] = None,
        correlated_probs: Optional[List[float]] = None,
        correlation_matrix: Optional[np.ndarray] = None,
        persist: bool = True,
    ) -> EnsembleResult:
        """Run all layers and combine into a single edge signal."""
        t0 = time.monotonic()
        layers: Dict[str, Any] = {}

        # --- Layer 1: Monte Carlo ---
        mc = MonteCarloEngine()
        mc_result = mc.simulate(
            prob_estimate=prob_estimate,
            market_price=market_price,
            n_paths=self.n_mc_paths,
            horizon_days=self.horizon_days,
            vol=self.vol,
        )
        layers["monte_carlo"] = mc_result

        # --- Layer 2: Importance Sampling (only for rare events) ---
        is_result: Dict[str, Any] = {}
        if prob_estimate < self.tail_threshold or prob_estimate > (1.0 - self.tail_threshold):
            sampler = ImportanceSampler()
            is_result = sampler.estimate_tail_risk(
                prob=prob_estimate,
                threshold=0.01,
                n_samples=self.n_is_samples,
            )
        layers["importance_sampling"] = is_result

        # --- Layer 3: Particle Filter (if price history available) ---
        pf_result: Dict[str, Any] = {}
        if price_history and len(price_history) >= 3:
            pf = ParticleFilter(n_particles=self.n_particles)
            pf.initialize(prior_prob=price_history[0])
            estimates = pf.run_sequence(price_history[1:])
            state = pf.get_state()
            pf_result = {
                "final_prob": state["mean_prob"],
                "std": state["std"],
                "ci_95": state["ci_95"],
                "effective_n": state["effective_n"],
                "n_steps": len(price_history) - 1,
            }
        layers["particle_filter"] = pf_result

        # --- Layer 4: Variance Reduction ---
        vr = VarianceReducer(n_paths=self.n_mc_paths)
        vr_result = vr.combined_estimate(
            prob=prob_estimate,
            vol=self.vol,
            T_days=self.horizon_days,
        )
        layers["variance_reduction"] = vr_result

        # --- Layer 5: Copula (if correlated contracts provided) ---
        copula_result: Dict[str, Any] = {}
        if correlated_probs and correlation_matrix is not None:
            n_contracts = len(correlated_probs)
            if correlation_matrix.shape == (n_contracts, n_contracts):
                cop = CopulaModel(copula_type="t", df=5)
                cop.fit(correlation_matrix)
                copula_result = cop.simulate_portfolio(
                    marginal_probs=correlated_probs,
                    corr=correlation_matrix,
                    n_paths=self.n_mc_paths,
                )
        layers["copula"] = copula_result

        # --- Layer 6: Agent-Based Market Sim ---
        msim = MarketSimulator(true_prob=prob_estimate)
        market_result = msim.run(n_steps=self.n_market_steps)
        layers["market_sim"] = {
            "kyle_lambda": market_result.get("kyle_lambda", 0.0),
            "price_discovery_speed": market_result.get("price_discovery_speed", 0.0),
            "final_price": market_result.get("final_price", 0.0),
        }

        # --- Combine into ensemble estimate ---
        ensemble_prob, effective_n = self._combine_estimates(
            mc_result=mc_result,
            pf_result=pf_result,
            vr_result=vr_result,
            is_result=is_result,
        )

        edge_pct = (ensemble_prob - market_price) * 100.0
        brier = (ensemble_prob - float(prob_estimate > 0.5)) ** 2

        # EVT-inspired VaR/ES from MC paths
        var_95, es_95 = self._compute_risk_measures(
            ensemble_prob, market_price, mc_result
        )

        elapsed_ms = (time.monotonic() - t0) * 1000.0

        result = EnsembleResult(
            contract=contract,
            ensemble_prob=ensemble_prob,
            market_price=market_price,
            edge_pct=edge_pct,
            brier=brier,
            var_95=var_95,
            es_95=es_95,
            effective_n=effective_n,
            layer_results=layers,
            elapsed_ms=elapsed_ms,
        )

        if persist:
            self._persist(result, contract)

        return result

    # ------------------------------------------------------------------
    # Batch: run across multiple contracts
    # ------------------------------------------------------------------

    def run_batch(
        self,
        contracts: List[Dict[str, Any]],
        persist: bool = True,
    ) -> List[EnsembleResult]:
        """Run ensemble on a batch of contracts.

        Each item should have keys: contract, prob_estimate, market_price,
        and optionally price_history.
        """
        return [
            self.run(
                contract=c["contract"],
                prob_estimate=c["prob_estimate"],
                market_price=c["market_price"],
                price_history=c.get("price_history"),
                persist=persist,
            )
            for c in contracts
        ]

    # ------------------------------------------------------------------
    # Brier tracking across historical settlements
    # ------------------------------------------------------------------

    def backtest_brier(
        self,
        settlements: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute Brier score across historical settlements.

        Each settlement should have: prob_estimate, outcome (0 or 1).
        """
        if not settlements:
            return {"brier": 1.0, "n": 0, "calibration": []}

        forecasts = np.array([s["prob_estimate"] for s in settlements])
        outcomes = np.array([float(s["outcome"]) for s in settlements])
        brier = float(np.mean((forecasts - outcomes) ** 2))

        # Calibration buckets (deciles)
        buckets = []
        for lo in np.arange(0, 1.0, 0.1):
            hi = lo + 0.1
            mask = (forecasts >= lo) & (forecasts < hi)
            n_bucket = int(mask.sum())
            if n_bucket > 0:
                mean_forecast = float(forecasts[mask].mean())
                mean_outcome = float(outcomes[mask].mean())
                buckets.append({
                    "range": f"{lo:.1f}-{hi:.1f}",
                    "n": n_bucket,
                    "mean_forecast": round(mean_forecast, 4),
                    "mean_outcome": round(mean_outcome, 4),
                    "gap": round(abs(mean_forecast - mean_outcome), 4),
                })

        return {"brier": round(brier, 6), "n": len(settlements), "calibration": buckets}

    # ------------------------------------------------------------------
    # Internal: estimate combination
    # ------------------------------------------------------------------

    def _combine_estimates(
        self,
        mc_result: Dict[str, Any],
        pf_result: Dict[str, Any],
        vr_result: Dict[str, Any],
        is_result: Dict[str, Any],
    ) -> tuple[float, int]:
        """Weighted average of layer estimates.

        Weights reflect precision: variance-reduced estimate gets highest weight,
        particle filter next (if available), then base MC.
        """
        estimates = []
        weights = []

        # MC fair price
        mc_fp = float(mc_result.get("fair_price", 0.5))
        if 0.0 < mc_fp < 1.0:
            estimates.append(mc_fp)
            weights.append(1.0)

        # Variance-reduced estimate
        vr_est = float(vr_result.get("estimate", 0.0)) if isinstance(vr_result, dict) else 0.0
        vr_factor = float(vr_result.get("variance_reduction_factor", 1.0)) if isinstance(vr_result, dict) else 1.0
        if 0.0 < vr_est < 1.0:
            estimates.append(vr_est)
            weights.append(min(vr_factor, 100.0))  # cap weight at 100x

        # Particle filter
        pf_prob = float(pf_result.get("final_prob", 0.0))
        pf_eff = int(pf_result.get("effective_n", 0))
        if 0.0 < pf_prob < 1.0 and pf_eff > 10:
            estimates.append(pf_prob)
            weights.append(min(float(pf_eff) / 100.0, 10.0))

        # IS tail estimate (only informative for extreme probabilities)
        is_prob = float(is_result.get("is_prob", 0.0)) if isinstance(is_result, dict) else 0.0
        if 0.0 < is_prob < 1.0:
            is_vr = float(is_result.get("variance_reduction_factor", 1.0)) if isinstance(is_result, dict) else 1.0
            estimates.append(is_prob)
            weights.append(min(is_vr / 10.0, 5.0))  # IS gets moderate weight

        if not estimates:
            return 0.5, 0

        arr_est = np.array(estimates)
        arr_w = np.array(weights)
        arr_w = arr_w / arr_w.sum()
        ensemble = float(np.dot(arr_w, arr_est))
        effective_n = max(1, int(1.0 / float(np.sum(arr_w ** 2))))

        return round(np.clip(ensemble, 0.01, 0.99), 6), effective_n

    # ------------------------------------------------------------------
    # Internal: risk measures
    # ------------------------------------------------------------------

    def _compute_risk_measures(
        self,
        ensemble_prob: float,
        market_price: float,
        mc_result: Dict[str, Any],
    ) -> tuple[float, float]:
        """Compute 95% VaR and ES from the MC result."""
        # PnL per contract: if we buy at market_price, payoff is 1 or 0
        # Use ensemble_prob as the probability of winning
        rng = np.random.default_rng(42)
        n = 10_000
        outcomes = rng.random(n) < ensemble_prob
        pnl = np.where(outcomes, 1.0 - market_price, -market_price)

        var_95 = float(-np.percentile(pnl, 5))
        tail = pnl[pnl <= -var_95]
        es_95 = float(-tail.mean()) if len(tail) > 0 else var_95

        return round(var_95, 6), round(es_95, 6)

    # ------------------------------------------------------------------
    # Internal: persistence
    # ------------------------------------------------------------------

    def _persist(self, result: EnsembleResult, contract: str) -> None:
        """Save ensemble run to simulation_runs table."""
        try:
            conn = _db.get_conn()
            _db.save_run(
                conn,
                layer="ensemble",
                contract=contract,
                params={
                    "n_mc_paths": self.n_mc_paths,
                    "n_is_samples": self.n_is_samples,
                    "n_particles": self.n_particles,
                    "vol": self.vol,
                    "horizon_days": self.horizon_days,
                },
                result={
                    "ensemble_prob": result.ensemble_prob,
                    "edge_pct": result.edge_pct,
                    "brier": result.brier,
                    "var_95": result.var_95,
                    "es_95": result.es_95,
                    "effective_n": result.effective_n,
                },
                brier=result.brier,
                edge_pct=result.edge_pct,
                n_paths=self.n_mc_paths,
                elapsed_ms=result.elapsed_ms,
            )
            conn.close()
        except Exception:
            pass  # Non-fatal: never crash the engine for a DB issue


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    engine = EnsembleEngine(
        n_mc_paths=5_000,
        n_is_samples=10_000,
        n_particles=300,
        n_market_steps=200,
    )

    print("=" * 60)
    print("Ensemble Engine Demo")
    print("=" * 60)

    # Scenario 1: Moderate probability contract
    r1 = engine.run(
        contract="BTC_100K_2026",
        prob_estimate=0.65,
        market_price=0.58,
        persist=True,
    )
    print(f"\n[1] {r1.contract}")
    print(f"    Ensemble prob: {r1.ensemble_prob:.4f}")
    print(f"    Market price:  {r1.market_price:.4f}")
    print(f"    Edge:          {r1.edge_pct:+.2f}%")
    print(f"    Brier:         {r1.brier:.4f}")
    print(f"    VaR(95):       {r1.var_95:.4f}")
    print(f"    ES(95):        {r1.es_95:.4f}")
    print(f"    Effective N:   {r1.effective_n}")
    print(f"    Elapsed:       {r1.elapsed_ms:.0f}ms")

    # Scenario 2: Extreme probability (triggers IS)
    r2 = engine.run(
        contract="RARE_EVENT",
        prob_estimate=0.03,
        market_price=0.08,
        persist=True,
    )
    print(f"\n[2] {r2.contract}")
    print(f"    Ensemble prob: {r2.ensemble_prob:.4f}")
    print(f"    Edge:          {r2.edge_pct:+.2f}%")
    print(f"    Brier:         {r2.brier:.4f}")
    print(f"    Elapsed:       {r2.elapsed_ms:.0f}ms")

    # Scenario 3: With price history (triggers particle filter)
    price_hist = [0.50, 0.52, 0.55, 0.53, 0.58, 0.60, 0.62, 0.59, 0.63, 0.65]
    r3 = engine.run(
        contract="ETH_5K_2026",
        prob_estimate=0.65,
        market_price=0.60,
        price_history=price_hist,
        persist=True,
    )
    print(f"\n[3] {r3.contract} (with price history)")
    print(f"    Ensemble prob: {r3.ensemble_prob:.4f}")
    print(f"    PF final:      {r3.layer_results.get('particle_filter', {}).get('final_prob', 'N/A')}")
    print(f"    Edge:          {r3.edge_pct:+.2f}%")
    print(f"    Elapsed:       {r3.elapsed_ms:.0f}ms")

    # Backtest
    settlements = [
        {"prob_estimate": 0.7, "outcome": 1},
        {"prob_estimate": 0.3, "outcome": 0},
        {"prob_estimate": 0.9, "outcome": 1},
        {"prob_estimate": 0.2, "outcome": 1},
        {"prob_estimate": 0.8, "outcome": 0},
    ]
    bt = engine.backtest_brier(settlements)
    print(f"\nBacktest Brier: {bt['brier']:.4f} (n={bt['n']})")

    print("\nDone.")
