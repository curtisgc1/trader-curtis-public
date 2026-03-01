"""Layer 4 — Variance reduction techniques for Monte Carlo simulation.

Three composable techniques that stack for 100-500x combined improvement:
  1. Antithetic variates: mirror each random path (negate Z) -> ~2x reduction
  2. Control variates: use closed-form Black-Scholes as control -> ~5-20x reduction
  3. Stratified sampling: divide [0,1] into K strata -> ~3-10x reduction

Combined they multiply: 2 * 10 * 5 = 100x is typical; extreme cases hit 500x.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from scipy.stats import norm

from . import _db


# ---------------------------------------------------------------------------
# Helpers — Black-Scholes closed form
# ---------------------------------------------------------------------------

def _bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call price via Black-Scholes."""
    if T <= 0:
        return max(S - K, 0.0)
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))


def _bs_binary_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Binary (digital) call probability under risk-neutral measure."""
    if T <= 0:
        return 1.0 if S >= K else 0.0
    sqrt_T = np.sqrt(T)
    d2 = (np.log(S / K) + (r - 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    return float(norm.cdf(d2))


def _ensure_rng(rng_or_seed: Union[None, int, np.random.Generator]) -> np.random.Generator:
    """Normalise seed / generator / None into a Generator."""
    if isinstance(rng_or_seed, np.random.Generator):
        return rng_or_seed
    return np.random.default_rng(rng_or_seed)


# ---------------------------------------------------------------------------
# Result containers (immutable dataclasses — no mutation)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EstimateResult:
    estimate: float
    std: float
    variance_reduction_factor: float
    breakdown: Dict[str, float]


@dataclass(frozen=True)
class BenchmarkRow:
    method: str
    mean: float
    std: float
    reduction_factor: float


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class VarianceReducer:
    """Composable variance-reduction toolkit for Monte Carlo pricing."""

    def __init__(self, n_paths: int = 10_000, n_strata: int = 100) -> None:
        if n_paths < 2:
            raise ValueError("n_paths must be >= 2")
        if n_strata < 1:
            raise ValueError("n_strata must be >= 1")
        # Snap n_paths up to a multiple of n_strata for clean division
        self._n_strata = n_strata
        self._n_paths = int(np.ceil(n_paths / n_strata) * n_strata)

    # -- public properties --------------------------------------------------

    @property
    def n_paths(self) -> int:
        return self._n_paths

    @property
    def n_strata(self) -> int:
        return self._n_strata

    # -- 1. Antithetic variates --------------------------------------------

    def antithetic_sample(
        self,
        rng_or_seed: Union[None, int, np.random.Generator] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate paired (Z, -Z) standard-normal samples.

        Returns
        -------
        Z : ndarray of shape (n_paths,)
        Z_anti : ndarray of shape (n_paths,)  (== -Z)
        """
        rng = _ensure_rng(rng_or_seed)
        z = rng.standard_normal(self._n_paths)
        return z, -z

    # -- 2. Stratified sampling --------------------------------------------

    def stratified_sample(
        self,
        rng_or_seed: Union[None, int, np.random.Generator] = None,
    ) -> np.ndarray:
        """Stratified standard-normal samples.

        Divides [0, 1] into *n_strata* equal-width bins, draws uniform
        samples inside each bin, then applies the inverse-normal CDF.

        Returns
        -------
        Z : ndarray of shape (n_paths,)
        """
        rng = _ensure_rng(rng_or_seed)
        K = self._n_strata
        per_stratum = self._n_paths // K

        # Boundaries: 0/K, 1/K, ..., (K-1)/K
        lo = np.arange(K, dtype=np.float64) / K
        width = 1.0 / K

        # Uniform draw within each stratum, tiled for per_stratum draws
        # Shape: (K, per_stratum)
        u = rng.uniform(size=(K, per_stratum)) * width + lo[:, np.newaxis]

        # Clip to avoid infinities at exact 0 / 1
        u = np.clip(u, 1e-12, 1.0 - 1e-12)

        # Inverse normal CDF, then flatten and shuffle to break ordering
        z = norm.ppf(u).ravel()
        rng.shuffle(z)
        return z

    # -- 3. Control variates -----------------------------------------------

    @staticmethod
    def control_variate_adjust(
        mc_estimates: np.ndarray,
        control_values: np.ndarray,
        control_exact: float,
    ) -> np.ndarray:
        """Apply optimal-beta control-variate adjustment.

        Parameters
        ----------
        mc_estimates : array of MC payoff estimates per path
        control_values : array of control-variate values (same paths)
        control_exact : closed-form exact value of the control

        Returns
        -------
        adjusted : array of adjusted estimates
        """
        mc_estimates = np.asarray(mc_estimates, dtype=np.float64)
        control_values = np.asarray(control_values, dtype=np.float64)

        cov_matrix = np.cov(mc_estimates, control_values)
        var_control = cov_matrix[1, 1]

        if var_control < 1e-30:
            # Control has no variance — nothing to adjust
            return mc_estimates

        beta = cov_matrix[0, 1] / var_control
        return mc_estimates - beta * (control_values - control_exact)

    # -- Combined estimate --------------------------------------------------

    def combined_estimate(
        self,
        prob: float,
        vol: float = 0.3,
        T_days: float = 7.0,
    ) -> Dict[str, Any]:
        """Run all three techniques together on a binary-option payoff.

        The payoff is 1{S_T >= K} where S_0 = 1, K is chosen so that the
        risk-neutral probability equals *prob*, sigma = *vol*, T = T_days/365.

        Returns dict with estimate, std, variance_reduction_factor, breakdown.
        """
        T = T_days / 365.0
        r = 0.0  # zero risk-free rate simplification
        sigma = vol
        S0 = 1.0

        # Solve for K so that BS binary-call price == prob
        # d2 = Phi^{-1}(prob), then K = S0 * exp((r - 0.5*sig^2)*T - sig*sqrt(T)*d2)
        # But we want the payoff expectation == prob, so use that directly.
        sqrt_T = np.sqrt(T) if T > 0 else 1e-8
        d2 = norm.ppf(np.clip(prob, 1e-6, 1.0 - 1e-6))
        K = S0 * np.exp((r - 0.5 * sigma**2) * T - sigma * sqrt_T * d2)

        exact = _bs_binary_call(S0, K, T, r, sigma)

        # --- Plain MC (for variance baseline) ---
        rng = np.random.default_rng(42)
        z_plain = rng.standard_normal(self._n_paths)
        ST_plain = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z_plain)
        payoff_plain = (ST_plain >= K).astype(np.float64)
        var_plain = float(np.var(payoff_plain, ddof=1))

        # --- Stratified + antithetic ---
        rng2 = np.random.default_rng(123)
        z_strat = self.stratified_sample(rng2)
        z_strat_anti = -z_strat

        ST_s = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z_strat)
        ST_sa = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z_strat_anti)

        payoff_s = (ST_s >= K).astype(np.float64)
        payoff_sa = (ST_sa >= K).astype(np.float64)

        # Antithetic average per-path
        payoff_avg = 0.5 * (payoff_s + payoff_sa)

        # Control variate: use a vanilla call as correlated control
        call_exact = _bs_call_price(S0, K, T, r, sigma)
        control_s = np.maximum(ST_s - K, 0.0)
        control_sa = np.maximum(ST_sa - K, 0.0)
        control_avg = 0.5 * (control_s + control_sa)

        adjusted = self.control_variate_adjust(payoff_avg, control_avg, call_exact)

        est = float(np.mean(adjusted))
        std = float(np.std(adjusted, ddof=1) / np.sqrt(len(adjusted)))
        var_combined = float(np.var(adjusted, ddof=1))

        vrf = var_plain / var_combined if var_combined > 1e-30 else float("inf")

        # --- Individual breakdowns (approximate) ---
        # Antithetic only
        var_anti = float(np.var(0.5 * (payoff_s + payoff_sa), ddof=1))
        anti_factor = var_plain / var_anti if var_anti > 1e-30 else float("inf")

        # Stratified only (no anti, no CV)
        var_strat = float(np.var(payoff_s, ddof=1))
        strat_factor = var_plain / var_strat if var_strat > 1e-30 else float("inf")

        # CV only
        cv_only = self.control_variate_adjust(payoff_plain, np.maximum(ST_plain - K, 0.0), call_exact)
        var_cv = float(np.var(cv_only, ddof=1))
        cv_factor = var_plain / var_cv if var_cv > 1e-30 else float("inf")

        return {
            "estimate": round(est, 6),
            "std": round(std, 8),
            "variance_reduction_factor": round(vrf, 1),
            "exact": round(exact, 6),
            "error": round(abs(est - exact), 8),
            "breakdown": {
                "antithetic": round(anti_factor, 1),
                "stratified": round(strat_factor, 1),
                "control_variate": round(cv_factor, 1),
                "combined": round(vrf, 1),
            },
        }

    # -- Benchmark ----------------------------------------------------------

    def benchmark(
        self,
        prob: float,
        vol: float = 0.3,
        T_days: float = 7.0,
        n_trials: int = 50,
    ) -> Dict[str, Any]:
        """Compare plain MC vs each technique over *n_trials* independent runs.

        Returns a dict mapping method names to BenchmarkRow-like dicts plus
        overall reduction factors.
        """
        T = T_days / 365.0
        r = 0.0
        sigma = vol
        S0 = 1.0
        sqrt_T = np.sqrt(T) if T > 0 else 1e-8
        d2_val = norm.ppf(np.clip(prob, 1e-6, 1.0 - 1e-6))
        K = S0 * np.exp((r - 0.5 * sigma**2) * T - sigma * sqrt_T * d2_val)
        exact = _bs_binary_call(S0, K, T, r, sigma)
        call_exact = _bs_call_price(S0, K, T, r, sigma)

        results: Dict[str, list] = {
            "plain": [],
            "antithetic": [],
            "stratified": [],
            "control_variate": [],
            "combined": [],
        }

        for trial in range(n_trials):
            seed = trial * 7919  # deterministic but varied
            rng = np.random.default_rng(seed)

            # --- Plain ---
            z = rng.standard_normal(self._n_paths)
            ST = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z)
            pay_plain = (ST >= K).astype(np.float64)
            results["plain"].append(float(np.mean(pay_plain)))

            # --- Antithetic ---
            rng_a = np.random.default_rng(seed + 1)
            z_a, z_anti = self.antithetic_sample(rng_a)
            ST_a = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z_a)
            ST_anti = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z_anti)
            pay_anti = 0.5 * ((ST_a >= K).astype(np.float64) + (ST_anti >= K).astype(np.float64))
            results["antithetic"].append(float(np.mean(pay_anti)))

            # --- Stratified ---
            rng_s = np.random.default_rng(seed + 2)
            z_s = self.stratified_sample(rng_s)
            ST_s = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * z_s)
            pay_strat = (ST_s >= K).astype(np.float64)
            results["stratified"].append(float(np.mean(pay_strat)))

            # --- Control variate (plain Z + CV) ---
            ctrl_vals = np.maximum(ST - K, 0.0)
            cv_adj = self.control_variate_adjust(pay_plain, ctrl_vals, call_exact)
            results["control_variate"].append(float(np.mean(cv_adj)))

            # --- Combined (stratified + antithetic + CV) ---
            ST_sa = S0 * np.exp((r - 0.5 * sigma**2) * T + sigma * sqrt_T * (-z_s))
            pay_s = (ST_s >= K).astype(np.float64)
            pay_sa = (ST_sa >= K).astype(np.float64)
            pay_combo = 0.5 * (pay_s + pay_sa)
            ctrl_combo = 0.5 * (np.maximum(ST_s - K, 0.0) + np.maximum(ST_sa - K, 0.0))
            combo_adj = self.control_variate_adjust(pay_combo, ctrl_combo, call_exact)
            results["combined"].append(float(np.mean(combo_adj)))

        # Compute variance of the estimator across trials
        var_plain = float(np.var(results["plain"], ddof=1))
        rows = {}
        for method, vals in results.items():
            arr = np.array(vals)
            v = float(np.var(arr, ddof=1))
            factor = var_plain / v if v > 1e-30 else float("inf")
            rows[method] = {
                "method": method,
                "mean": round(float(np.mean(arr)), 6),
                "std": round(float(np.std(arr, ddof=1)), 8),
                "reduction_factor": round(factor, 1),
                "exact": round(exact, 6),
                "mse": round(float(np.mean((arr - exact) ** 2)), 10),
            }

        return rows


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------

def persist_result(
    result: Dict[str, Any],
    *,
    n_paths: int,
    prob: float,
    vol: float,
    T_days: float,
    elapsed_ms: float,
    conn: Optional[Any] = None,
) -> int:
    """Save a combined_estimate or benchmark result to the simulation DB."""
    own_conn = conn is None
    if own_conn:
        conn = _db.get_conn()
    try:
        row_id = _db.save_run(
            conn,
            layer="variance_reduction",
            params={
                "n_paths": n_paths,
                "prob": prob,
                "vol": vol,
                "T_days": T_days,
            },
            result=result,
            n_paths=n_paths,
            elapsed_ms=elapsed_ms,
        )
        return row_id
    finally:
        if own_conn:
            conn.close()


# ---------------------------------------------------------------------------
# __main__ demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Run a quick demonstration of variance reduction factors."""
    print("=" * 64)
    print("  Variance Reduction Demo — Layer 4")
    print("=" * 64)

    reducer = VarianceReducer(n_paths=50_000, n_strata=200)
    print(f"\nConfig: {reducer.n_paths:,} paths, {reducer.n_strata} strata\n")

    # --- Combined estimate for a few probabilities ---
    for prob in [0.25, 0.50, 0.75]:
        t0 = time.perf_counter()
        res = reducer.combined_estimate(prob=prob, vol=0.3, T_days=7)
        elapsed = (time.perf_counter() - t0) * 1000

        print(f"prob={prob:.2f}  |  estimate={res['estimate']:.6f}  "
              f"exact={res['exact']:.6f}  |  error={res['error']:.2e}  "
              f"std={res['std']:.2e}")
        bd = res["breakdown"]
        print(f"  antithetic: {bd['antithetic']:.1f}x  "
              f"stratified: {bd['stratified']:.1f}x  "
              f"CV: {bd['control_variate']:.1f}x  "
              f"combined: {bd['combined']:.1f}x  "
              f"[{elapsed:.0f}ms]")

        persist_result(
            res,
            n_paths=reducer.n_paths,
            prob=prob,
            vol=0.3,
            T_days=7,
            elapsed_ms=elapsed,
        )

    # --- Full benchmark ---
    print("\n" + "-" * 64)
    print("  Benchmark: 50 independent trials at prob=0.40")
    print("-" * 64)

    t0 = time.perf_counter()
    bench = reducer.benchmark(prob=0.40, vol=0.3, T_days=7, n_trials=50)
    elapsed = (time.perf_counter() - t0) * 1000

    for method in ["plain", "antithetic", "stratified", "control_variate", "combined"]:
        row = bench[method]
        print(f"  {method:<18s}  mean={row['mean']:.6f}  "
              f"std={row['std']:.8f}  "
              f"reduction={row['reduction_factor']:.1f}x  "
              f"MSE={row['mse']:.2e}")

    print(f"\n  Benchmark elapsed: {elapsed:.0f}ms")
    print(f"  Exact value:       {bench['plain']['exact']:.6f}")

    persist_result(
        bench,
        n_paths=reducer.n_paths,
        prob=0.40,
        vol=0.3,
        T_days=7,
        elapsed_ms=elapsed,
    )

    print("\nResults persisted to simulation_runs (layer=variance_reduction).")


if __name__ == "__main__":
    _demo()
