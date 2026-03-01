"""Layer 3 — Sequential Monte Carlo particle filter for live market tracking.

Tracks the latent probability of binary contracts in real-time by maintaining
a weighted particle cloud in logit space.  Observations (market prices in
[0, 1]) are converted to logit space for the likelihood update, then particles
are resampled via systematic resampling when ESS drops below threshold.

State transition:  logit(p_{t+1}) = logit(p_t) + N(0, process_noise^2)
Observation model: obs_logit ~ N(particle_logit, observation_noise^2)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from . import _db

_LOGIT_CLIP = 8.0  # clamp logit to [-8, 8] => prob [0.00034, 0.99966]


def _logit(p: np.ndarray | float) -> np.ndarray:
    """Probability -> logit, with safe clamping."""
    p = np.asarray(p, dtype=np.float64)
    p = np.clip(p, 1e-8, 1.0 - 1e-8)
    return np.log(p / (1.0 - p))


def _sigmoid(x: np.ndarray | float) -> np.ndarray:
    """Logit -> probability."""
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=np.float64)))


def _systematic_resample(weights: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Systematic resampling — one draw, evenly spaced cumulative walk.
    Lower variance than multinomial, O(N).  Returns ancestor indices."""
    n = len(weights)
    positions = (rng.random() + np.arange(n)) / n
    cumsum = np.cumsum(weights)
    cumsum[-1] = 1.0  # guard against float drift
    return np.searchsorted(cumsum, positions)


def _effective_sample_size(weights: np.ndarray) -> float:
    """ESS = 1 / sum(w_i^2).  Range: [1, N]."""
    return float(1.0 / np.sum(weights ** 2))


@dataclass(frozen=True)
class FilterEstimate:
    """Single time-step output from the particle filter."""
    mean_prob: float
    std: float
    ci_95_lo: float
    ci_95_hi: float
    effective_n: float
    n_resamples: int
    step: int


class ParticleFilter:
    """Sequential Monte Carlo tracker for binary contract probabilities.

    Parameters
    ----------
    n_particles    : Number of particles in the cloud.
    process_noise  : Std-dev of the random walk in logit space per step.
    resample_threshold : ESS fraction triggering resampling (0.5 = ESS < N/2).
    seed           : RNG seed for reproducibility.
    """

    def __init__(
        self,
        n_particles: int = 1000,
        process_noise: float = 0.05,
        resample_threshold: float = 0.5,
        seed: Optional[int] = None,
    ) -> None:
        self._n = n_particles
        self._process_noise = process_noise
        self._resample_thresh = resample_threshold
        self._rng = np.random.default_rng(seed)

        self._particles: np.ndarray = np.zeros(n_particles, dtype=np.float64)
        self._weights: np.ndarray = np.ones(n_particles, dtype=np.float64) / n_particles
        self._initialized = False
        self._step = 0
        self._n_resamples = 0

    # -- Public API --------------------------------------------------------

    def initialize(self, prior_prob: float = 0.5) -> None:
        """Set up initial particle distribution centred on *prior_prob*.
        Draws from N(logit(prior), 2*process_noise) in logit space."""
        centre = float(_logit(prior_prob))
        spread = max(self._process_noise * 2.0, 0.05)
        self._particles = self._rng.normal(centre, spread, size=self._n)
        self._particles = np.clip(self._particles, -_LOGIT_CLIP, _LOGIT_CLIP)
        self._weights = np.ones(self._n, dtype=np.float64) / self._n
        self._initialized = True
        self._step = 0
        self._n_resamples = 0

    def update(
        self,
        observation: float,
        observation_noise: float = 0.02,
    ) -> FilterEstimate:
        """Incorporate a new market-price observation (in [0,1]).
        Returns the updated FilterEstimate."""
        if not self._initialized:
            self.initialize(prior_prob=observation)

        self._step += 1

        # 1. Predict (state transition — logit random walk)
        noise = self._rng.normal(0.0, self._process_noise, size=self._n)
        self._particles = self._particles + noise
        self._particles = np.clip(self._particles, -_LOGIT_CLIP, _LOGIT_CLIP)

        # 2. Update weights (Gaussian likelihood in logit space)
        obs_logit = float(_logit(observation))
        diff = self._particles - obs_logit
        log_lik = -0.5 * (diff ** 2) / (observation_noise ** 2)
        log_lik = log_lik - np.max(log_lik)  # numerical stability
        raw_weights = self._weights * np.exp(log_lik)

        weight_sum = np.sum(raw_weights)
        if weight_sum <= 0.0:
            self._weights = np.ones(self._n, dtype=np.float64) / self._n
        else:
            self._weights = raw_weights / weight_sum

        # 3. Resample if ESS is too low
        ess = _effective_sample_size(self._weights)
        if ess < self._resample_thresh * self._n:
            indices = _systematic_resample(self._weights, self._rng)
            self._particles = self._particles[indices]
            self._weights = np.ones(self._n, dtype=np.float64) / self._n
            self._n_resamples += 1

        return self._build_estimate()

    def predict(self, steps_ahead: int = 1) -> FilterEstimate:
        """Extrapolate forward without new observations.
        Does NOT mutate internal state — operates on copies."""
        if not self._initialized:
            raise RuntimeError("ParticleFilter has not been initialized.")

        projected = self._particles.copy()
        for _ in range(steps_ahead):
            projected = projected + self._rng.normal(0.0, self._process_noise, size=self._n)
            projected = np.clip(projected, -_LOGIT_CLIP, _LOGIT_CLIP)

        probs = _sigmoid(projected)
        weighted_mean = float(np.average(probs, weights=self._weights))
        weighted_var = float(np.average((probs - weighted_mean) ** 2, weights=self._weights))
        std = float(np.sqrt(weighted_var))

        order = np.argsort(probs)
        sorted_probs = probs[order]
        cum_w = np.cumsum(self._weights[order])
        ci_lo = float(sorted_probs[np.searchsorted(cum_w, 0.025)])
        ci_hi_idx = min(np.searchsorted(cum_w, 0.975, side="right"), len(sorted_probs) - 1)
        ci_hi = float(sorted_probs[ci_hi_idx])

        return FilterEstimate(
            mean_prob=weighted_mean,
            std=std,
            ci_95_lo=ci_lo,
            ci_95_hi=ci_hi,
            effective_n=_effective_sample_size(self._weights),
            n_resamples=self._n_resamples,
            step=self._step + steps_ahead,
        )

    def get_state(self) -> Dict[str, Any]:
        """Return a plain dict summary of current filter state."""
        if not self._initialized:
            return {
                "mean_prob": None,
                "std": None,
                "ci_95": (None, None),
                "effective_n": 0.0,
                "n_resamples": 0,
            }
        est = self._build_estimate()
        return {
            "mean_prob": est.mean_prob,
            "std": est.std,
            "ci_95": (est.ci_95_lo, est.ci_95_hi),
            "effective_n": est.effective_n,
            "n_resamples": est.n_resamples,
        }

    def run_sequence(
        self,
        observations: Sequence[float],
        observation_noise: float = 0.02,
        contract: str = "",
        ticker: str = "",
        persist: bool = False,
    ) -> List[FilterEstimate]:
        """Process a list of observations, return trajectory of estimates.

        When *persist* is True, saves the run summary via _db.save_run.
        """
        t0 = time.perf_counter()
        trajectory: List[FilterEstimate] = []

        for obs in observations:
            trajectory.append(self.update(obs, observation_noise=observation_noise))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if persist and trajectory:
            final = trajectory[-1]
            conn = _db.get_conn()
            try:
                _db.save_run(
                    conn,
                    layer="particle_filter",
                    contract=contract,
                    ticker=ticker,
                    params={
                        "n_particles": self._n,
                        "process_noise": self._process_noise,
                        "resample_threshold": self._resample_thresh,
                        "observation_noise": observation_noise,
                        "n_observations": len(observations),
                    },
                    result={
                        "mean_prob": final.mean_prob,
                        "std": final.std,
                        "ci_95": (final.ci_95_lo, final.ci_95_hi),
                        "effective_n": final.effective_n,
                        "n_resamples": final.n_resamples,
                    },
                    n_paths=self._n,
                    elapsed_ms=elapsed_ms,
                )
            finally:
                conn.close()

        return trajectory

    # -- Private -----------------------------------------------------------

    def _build_estimate(self) -> FilterEstimate:
        """Construct a FilterEstimate from current particles + weights."""
        probs = _sigmoid(self._particles)
        weighted_mean = float(np.average(probs, weights=self._weights))
        weighted_var = float(np.average((probs - weighted_mean) ** 2, weights=self._weights))
        std = float(np.sqrt(weighted_var))

        order = np.argsort(probs)
        sorted_probs = probs[order]
        cum_w = np.cumsum(self._weights[order])
        ci_lo = float(sorted_probs[np.searchsorted(cum_w, 0.025)])
        ci_hi_idx = min(np.searchsorted(cum_w, 0.975, side="right"), len(sorted_probs) - 1)
        ci_hi = float(sorted_probs[ci_hi_idx])

        return FilterEstimate(
            mean_prob=weighted_mean,
            std=std,
            ci_95_lo=ci_lo,
            ci_95_hi=ci_hi,
            effective_n=_effective_sample_size(self._weights),
            n_resamples=self._n_resamples,
            step=self._step,
        )


# -- Synthetic data for demos ---------------------------------------------

def _generate_synthetic_path(
    n_steps: int = 200,
    start_prob: float = 0.50,
    drift: float = 0.03,
    noise: float = 0.015,
    seed: int = 42,
) -> np.ndarray:
    """Random walk in logit space, returned as probabilities.
    Simulates a binary contract drifting toward resolution."""
    rng = np.random.default_rng(seed)
    logit_val = float(_logit(start_prob))
    path = np.empty(n_steps, dtype=np.float64)
    for i in range(n_steps):
        logit_val = logit_val + rng.normal(drift, noise)
        logit_val = np.clip(logit_val, -_LOGIT_CLIP, _LOGIT_CLIP)
        path[i] = float(_sigmoid(logit_val))
    return path


# -- __main__ demo ---------------------------------------------------------

def _main() -> None:
    """Generate a synthetic price path, run the filter, print tracking quality."""
    np.set_printoptions(precision=4)

    n_steps = 200
    true_prices = _generate_synthetic_path(n_steps=n_steps, seed=7)

    # Add observation noise to simulate real market jitter
    obs_rng = np.random.default_rng(99)
    observations = np.clip(
        true_prices + obs_rng.normal(0.0, 0.01, size=n_steps), 0.001, 0.999
    )

    pf = ParticleFilter(n_particles=2000, process_noise=0.04, resample_threshold=0.5, seed=123)
    pf.initialize(prior_prob=float(observations[0]))

    t0 = time.perf_counter()
    trajectory = pf.run_sequence(observations, observation_noise=0.03)
    elapsed = (time.perf_counter() - t0) * 1000.0

    # Tracking quality metrics
    estimates = np.array([e.mean_prob for e in trajectory])
    residuals = estimates - true_prices
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    max_err = float(np.max(np.abs(residuals)))

    inside_ci = sum(1 for e, p in zip(trajectory, true_prices) if e.ci_95_lo <= p <= e.ci_95_hi)
    coverage = inside_ci / n_steps

    final = pf.get_state()

    print()
    print("=== Particle Filter Tracking Report ===")
    print(f"  Particles:        {pf._n}")
    print(f"  Steps:            {n_steps}")
    print(f"  Elapsed:          {elapsed:.1f} ms")
    print(f"  Resamples:        {final['n_resamples']}")
    print(f"  Final ESS:        {final['effective_n']:.0f}")
    print()
    print(f"  MAE:              {mae:.5f}")
    print(f"  RMSE:             {rmse:.5f}")
    print(f"  Max error:        {max_err:.5f}")
    print(f"  95% CI coverage:  {coverage:.1%}")
    print()
    print(f"  Start price:      {true_prices[0]:.4f}")
    print(f"  End price:        {true_prices[-1]:.4f}")
    print(f"  Filter estimate:  {final['mean_prob']:.4f}")
    print(f"  Filter std:       {final['std']:.4f}")
    print(f"  Filter 95% CI:    [{final['ci_95'][0]:.4f}, {final['ci_95'][1]:.4f}]")
    print()

    # Prediction fan-out
    pred_1 = pf.predict(steps_ahead=1)
    pred_5 = pf.predict(steps_ahead=5)
    pred_20 = pf.predict(steps_ahead=20)
    print("  Predictions (no new data):")
    print(f"    +1  step:  {pred_1.mean_prob:.4f}  (std {pred_1.std:.4f})")
    print(f"    +5  steps: {pred_5.mean_prob:.4f}  (std {pred_5.std:.4f})")
    print(f"    +20 steps: {pred_20.mean_prob:.4f}  (std {pred_20.std:.4f})")
    print()

    if coverage >= 0.90:
        print("  PASS: 95% CI coverage is adequate.")
    else:
        print(f"  WARN: 95% CI coverage ({coverage:.1%}) is below 90%.")


if __name__ == "__main__":
    _main()
