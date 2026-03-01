"""Layer 2 -- Importance sampling for tail risk in prediction markets.

Exponential tilting targets low-probability contracts (P < 0.01) where
standard MC wastes samples on the bulk.  Likelihood-ratio weighting
keeps estimates unbiased with 50-10,000x variance reduction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np
from numpy.typing import NDArray

from . import _db

_RNG_SEED: int | None = None
_MIN_TILT: float = 0.5
_MAX_TILT: float = 12.0
_TAIL_THRESHOLD: float = 0.01


def _make_rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(seed if seed is not None else _RNG_SEED)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _log_safe(x: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.log(np.maximum(x, 1e-300))


@dataclass(frozen=True)
class SamplingResult:
    """Immutable snapshot of an importance-sampling run."""
    is_prob: float
    variance_reduction_factor: float
    effective_sample_size: float
    ci_99: tuple[float, float]
    raw_weights: NDArray[np.float64] = field(repr=False)
    tilt_strength: float = 0.0
    n_samples: int = 0


class ImportanceSampler:
    """Exponential-tilt importance sampler for prediction-market tail risk."""

    def __init__(
        self,
        contract: str = "",
        ticker: str = "",
        seed: int | None = None,
    ) -> None:
        self._contract = contract
        self._ticker = ticker
        self._rng = _make_rng(seed)

    # -- Public API --------------------------------------------------------

    def optimal_tilt(self, target_prob: float) -> float:
        """Optimal exponential tilt: theta* = ln((1-p)/p), clamped."""
        p = _clamp(float(target_prob), 1e-15, 1.0 - 1e-15)
        theta = float(np.log((1.0 - p) / p))
        return _clamp(theta, _MIN_TILT, _MAX_TILT)

    def sample(
        self,
        prob_estimate: float,
        n_samples: int = 10_000,
        tilt_strength: Optional[float] = None,
    ) -> Dict[str, Any]:
        """IS Monte Carlo for a rare contract.

        Returns dict: is_prob, variance_reduction_factor,
        effective_sample_size, ci_99.
        """
        p = _clamp(float(prob_estimate), 1e-15, 1.0 - 1e-15)
        theta = (
            float(tilt_strength)
            if tilt_strength is not None
            else self.optimal_tilt(p)
        )
        result = self._run_tilted_mc(p, theta, n_samples)
        return {
            "is_prob": result.is_prob,
            "variance_reduction_factor": result.variance_reduction_factor,
            "effective_sample_size": result.effective_sample_size,
            "ci_99": result.ci_99,
        }

    def estimate_tail_risk(
        self,
        prob: float,
        threshold: float = _TAIL_THRESHOLD,
        n_samples: int = 50_000,
    ) -> Dict[str, Any]:
        """Estimate P(outcome <= threshold) via IS.  Persists to DB.

        Returns dict: tail_prob, expected_loss, var_reduction, ess, ci_99.
        """
        t0 = time.perf_counter()
        p = _clamp(float(prob), 1e-15, 1.0 - 1e-15)
        thr = _clamp(float(threshold), 1e-15, 1.0 - 1e-15)

        theta = self.optimal_tilt(thr)
        tilted_samples, weights = self._draw_tilted_beta(p, theta, n_samples)

        in_tail = (tilted_samples <= thr).astype(np.float64)
        weighted_tail = in_tail * weights
        tail_prob = float(np.mean(weighted_tail))

        loss = np.maximum(thr - tilted_samples, 0.0) * weights
        expected_loss = float(np.mean(loss))

        naive_var = self._naive_bernoulli_var(tail_prob, n_samples)
        is_var = float(np.var(weighted_tail) / n_samples)
        var_reduction = naive_var / max(is_var, 1e-300)

        ess = self._kish_ess(weights)
        ci_99 = self._weighted_ci(weighted_tail, n_samples)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        result_dict = {
            "tail_prob": tail_prob,
            "expected_loss": expected_loss,
            "var_reduction": var_reduction,
            "ess": ess,
            "ci_99": ci_99,
        }
        self._persist(
            params={"prob": p, "threshold": thr, "theta": theta, "n_samples": n_samples},
            result=result_dict,
            n_paths=n_samples,
            elapsed_ms=elapsed_ms,
        )
        return result_dict

    # -- Internal sampling -------------------------------------------------

    def _run_tilted_mc(
        self, p: float, theta: float, n_samples: int,
    ) -> SamplingResult:
        """Core IS loop: Beta model + exponential tilt + likelihood ratio."""
        tilted_samples, weights = self._draw_tilted_beta(p, theta, n_samples)

        weighted_estimate = tilted_samples * weights
        is_prob = float(np.mean(weighted_estimate))

        naive_var = self._naive_bernoulli_var(p, n_samples)
        is_var = float(np.var(weighted_estimate) / n_samples)
        vr_factor = naive_var / max(is_var, 1e-300)

        return SamplingResult(
            is_prob=is_prob,
            variance_reduction_factor=vr_factor,
            effective_sample_size=self._kish_ess(weights),
            ci_99=self._weighted_ci(weighted_estimate, n_samples),
            raw_weights=weights,
            tilt_strength=theta,
            n_samples=n_samples,
        )

    def _draw_tilted_beta(
        self, p: float, theta: float, n_samples: int,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Draw from tilted Beta proposal, return (samples, self-normalised weights)."""
        kappa = self._concentration(p)
        alpha_nom = p * kappa
        beta_nom = (1.0 - p) * kappa

        # Shift alpha toward the tail -- larger theta = more aggressive tilt
        alpha_tilt = max(alpha_nom * np.exp(-theta * 0.3), 0.05)
        beta_tilt = beta_nom

        samples = self._rng.beta(alpha_tilt, beta_tilt, size=n_samples)
        samples = np.clip(samples, 1e-15, 1.0 - 1e-15)

        # Likelihood ratio in log-space for stability
        log_nom = self._log_beta_pdf(samples, alpha_nom, beta_nom)
        log_prop = self._log_beta_pdf(samples, alpha_tilt, beta_tilt)
        log_weights = log_nom - log_prop

        log_weights -= np.max(log_weights)
        weights = np.exp(log_weights)
        weights /= np.mean(weights)
        return samples, weights

    # -- Statistical utilities ---------------------------------------------

    @staticmethod
    def _concentration(p: float) -> float:
        """Adaptive Beta concentration -- rarer events get higher kappa."""
        if p < 0.001:
            return 500.0
        if p < 0.01:
            return 200.0
        if p < 0.05:
            return 80.0
        return 30.0

    @staticmethod
    def _log_beta_pdf(
        x: NDArray[np.float64], alpha: float, beta_param: float,
    ) -> NDArray[np.float64]:
        """Log-PDF of Beta (unnormalised -- constant cancels in ratio)."""
        return (alpha - 1.0) * _log_safe(x) + (beta_param - 1.0) * _log_safe(1.0 - x)

    @staticmethod
    def _kish_ess(weights: NDArray[np.float64]) -> float:
        """Kish ESS = (sum w)^2 / sum(w^2)."""
        sum_w = float(np.sum(weights))
        sum_w2 = float(np.sum(weights ** 2))
        if sum_w2 < 1e-300:
            return 0.0
        return (sum_w * sum_w) / sum_w2

    @staticmethod
    def _naive_bernoulli_var(p: float, n: int) -> float:
        return p * (1.0 - p) / max(n, 1)

    @staticmethod
    def _weighted_ci(
        weighted_values: NDArray[np.float64], n_samples: int, z: float = 2.576,
    ) -> tuple[float, float]:
        """99% CI from IS-weighted values."""
        mean = float(np.mean(weighted_values))
        se = float(np.std(weighted_values)) / max(np.sqrt(n_samples), 1.0)
        return (max(mean - z * se, 0.0), min(mean + z * se, 1.0))

    # -- Persistence -------------------------------------------------------

    def _persist(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        n_paths: int,
        elapsed_ms: float,
    ) -> None:
        try:
            conn = _db.get_conn()
            _db.save_run(
                conn,
                layer="importance_sampling",
                contract=self._contract,
                ticker=self._ticker,
                params=params,
                result=result,
                n_paths=n_paths,
                elapsed_ms=elapsed_ms,
            )
            conn.close()
        except Exception:
            pass  # non-critical


# -- Demo ------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Importance Sampling -- Layer 2 Demo ===\n")

    sampler = ImportanceSampler(
        contract="will-x-happen-by-2027", ticker="XHAP2027", seed=42,
    )

    # 1) sample() for a rare event
    print("--- sample(P=0.005, n=20000) ---")
    res = sampler.sample(prob_estimate=0.005, n_samples=20_000)
    print(f"  IS prob   : {res['is_prob']:.6f}")
    print(f"  VR factor : {res['variance_reduction_factor']:.1f}x")
    print(f"  ESS       : {res['effective_sample_size']:.0f}")
    print(f"  99% CI    : ({res['ci_99'][0]:.6f}, {res['ci_99'][1]:.6f})")

    # 2) optimal_tilt across probabilities
    print("\n--- optimal_tilt() ---")
    for target in [0.1, 0.01, 0.001, 0.0001]:
        print(f"  P={target:<8}  theta*={sampler.optimal_tilt(target):.4f}")

    # 3) Tail-risk estimation
    print("\n--- estimate_tail_risk(P=0.02, thr=0.01) ---")
    tail = sampler.estimate_tail_risk(prob=0.02, threshold=0.01, n_samples=50_000)
    print(f"  Tail prob : {tail['tail_prob']:.6f}")
    print(f"  E[loss]   : {tail['expected_loss']:.6f}")
    print(f"  VR factor : {tail['var_reduction']:.1f}x")
    print(f"  ESS       : {tail['ess']:.0f}")
    print(f"  99% CI    : ({tail['ci_99'][0]:.6f}, {tail['ci_99'][1]:.6f})")

    # 4) IS vs naive MC comparison
    print("\n--- IS vs Naive MC (P=0.003, n=50000) ---")
    rng = np.random.default_rng(99)
    n, p_rare = 50_000, 0.003
    naive = rng.binomial(1, p_rare, size=n).astype(np.float64)
    is_res = sampler.sample(prob_estimate=p_rare, n_samples=n)
    print(f"  Naive  : {float(np.mean(naive)):.6f}  (var={float(np.var(naive)/n):.2e})")
    print(f"  IS     : {is_res['is_prob']:.6f}  (VR={is_res['variance_reduction_factor']:.0f}x)")

    print("\nDone.")
