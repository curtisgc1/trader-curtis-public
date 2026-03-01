"""Layer 5 — Copula models for correlated prediction market contracts.

Models dependency structure between correlated Polymarket contracts using
three copula families: Gaussian, Student-t, and Clayton.  Pure math layer;
no Flask or HTTP concerns.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from numpy.typing import NDArray
from scipy import stats

from . import _db

FloatArray = NDArray[np.floating]
COPULA_TYPES = ("gaussian", "student_t", "clayton")


def _ensure_positive_definite(corr: FloatArray) -> FloatArray:
    """Clamp eigenvalues so the matrix is strictly positive-definite."""
    eigvals, eigvecs = np.linalg.eigh(corr)
    eigvals = np.clip(eigvals, 1e-8, None)
    out = eigvecs @ np.diag(eigvals) @ eigvecs.T
    d = np.sqrt(np.diag(out))
    out = out / np.outer(d, d)
    return out


@dataclass
class CopulaModel:
    """Multivariate copula for correlated contract simulation.

    Parameters
    ----------
    copula_type : ``"gaussian"`` | ``"student_t"`` | ``"clayton"``
    df : degrees of freedom (student_t only).
    """

    copula_type: str = "gaussian"
    df: int = 5

    # Internal state populated by fit()
    _corr: Optional[FloatArray] = field(default=None, repr=False)
    _dim: int = field(default=0, repr=False)
    _theta: float = field(default=0.0, repr=False)  # Clayton parameter

    # ---- fit -------------------------------------------------------------

    def fit(self, correlations: FloatArray) -> "CopulaModel":
        """Fit copula parameters from a (d, d) correlation matrix."""
        corr = np.array(correlations, dtype=np.float64)
        if corr.ndim != 2 or corr.shape[0] != corr.shape[1]:
            raise ValueError("correlations must be a square matrix")
        self._dim = corr.shape[0]
        self._corr = _ensure_positive_definite(corr)

        if self.copula_type == "clayton":
            # Estimate theta from average Kendall tau.
            # tau ~ 2/pi * arcsin(r);  theta = 2*tau / (1 - tau)
            taus: List[float] = []
            for i in range(self._dim):
                for j in range(i + 1, self._dim):
                    taus.append(2.0 / np.pi * np.arcsin(self._corr[i, j]))
            avg_tau = float(np.clip(np.mean(taus) if taus else 0.0, 0.01, 0.99))
            self._theta = 2.0 * avg_tau / (1.0 - avg_tau)
        return self

    # ---- sample ----------------------------------------------------------

    def sample(self, n: int = 10_000) -> FloatArray:
        """Generate (n, d) correlated uniform samples from the fitted copula."""
        if self._corr is None:
            raise RuntimeError("Call fit() before sample()")

        rng = np.random.default_rng()

        if self.copula_type == "gaussian":
            z = rng.multivariate_normal(np.zeros(self._dim), self._corr, size=n)
            return stats.norm.cdf(z)

        if self.copula_type == "student_t":
            z = rng.multivariate_normal(np.zeros(self._dim), self._corr, size=n)
            chi2 = rng.chisquare(self.df, size=(n, 1))
            return stats.t.cdf(z / np.sqrt(chi2 / self.df), df=self.df)

        if self.copula_type == "clayton":
            return self._sample_clayton(n, rng)

        raise ValueError(f"Unknown copula_type: {self.copula_type}")

    def _sample_clayton(self, n: int, rng: np.random.Generator) -> FloatArray:
        """Marshall-Olkin algorithm for Clayton copula."""
        theta, d = self._theta, self._dim
        # Gamma frailty V ~ Gamma(1/theta, 1), independent exponentials
        v = rng.gamma(1.0 / theta, 1.0, size=(n, 1))
        e = rng.exponential(1.0, size=(n, d))
        # Laplace-transform inverse: phi_inv(t) = (1 + t)^{-1/theta}
        u = (1.0 + e / v) ** (-1.0 / theta)
        return np.clip(u, 0.0, 1.0)

    # ---- joint_probability -----------------------------------------------

    def joint_probability(
        self,
        marginal_probs: FloatArray,
        correlation_matrix: FloatArray,
    ) -> float:
        """Estimate P(all contracts resolve YES) via Monte Carlo copula."""
        marginals = np.asarray(marginal_probs, dtype=np.float64)
        self.fit(correlation_matrix)
        u = self.sample(n=50_000)
        outcomes = u <= marginals[np.newaxis, :]
        return float(np.all(outcomes, axis=1).sum() / u.shape[0])

    # ---- tail_dependence -------------------------------------------------

    def tail_dependence(
        self, copula_type: Optional[str] = None
    ) -> Dict[str, float]:
        """Compute analytic lower/upper tail dependence coefficients.

        Returns dict with keys ``lambda_L`` and ``lambda_U``.
        """
        ct = copula_type or self.copula_type

        if ct == "gaussian":
            return {"lambda_L": 0.0, "lambda_U": 0.0}

        if ct == "student_t":
            rho = self._avg_rho()
            nu = self.df
            coeff = 2.0 * stats.t.cdf(
                -np.sqrt((nu + 1.0) * (1.0 - rho) / (1.0 + rho)),
                df=nu + 1,
            )
            return {"lambda_L": float(coeff), "lambda_U": float(coeff)}

        if ct == "clayton":
            theta = self._theta
            lam_l = 2.0 ** (-1.0 / theta) if theta > 0 else 0.0
            return {"lambda_L": float(lam_l), "lambda_U": 0.0}

        raise ValueError(f"Unknown copula_type: {ct}")

    # ---- conditional_prob ------------------------------------------------

    def conditional_prob(
        self,
        target_idx: int,
        given_indices: List[int],
        given_values: List[float],
        marginal_probs: FloatArray,
        corr: FloatArray,
    ) -> float:
        """Estimate P(target YES | given contracts = given_values).

        Parameters
        ----------
        target_idx : index of the contract to query.
        given_indices : indices of observed contracts.
        given_values : 1.0 (YES) or 0.0 (NO) for each given contract.
        marginal_probs : (d,) individual YES probabilities.
        corr : (d, d) correlation matrix.
        """
        marginals = np.asarray(marginal_probs, dtype=np.float64)
        self.fit(corr)
        u = self.sample(n=100_000)

        outcomes = (u <= marginals[np.newaxis, :]).astype(np.float64)

        # Filter paths matching the given conditions
        mask = np.ones(u.shape[0], dtype=bool)
        for idx, val in zip(given_indices, given_values):
            mask &= outcomes[:, idx] == val

        if mask.sum() < 10:
            return float(marginals[target_idx])  # too few paths; fallback
        return float(outcomes[mask, target_idx].mean())

    # ---- simulate_portfolio ----------------------------------------------

    def simulate_portfolio(
        self,
        marginal_probs: FloatArray,
        corr: FloatArray,
        n_paths: int = 10_000,
    ) -> Dict[str, Any]:
        """Simulate correlated contract outcomes for a portfolio.

        Returns expected hits, std, wipeout probability, VaR, per-contract
        win rates, and tail dependence coefficients.
        """
        marginals = np.asarray(marginal_probs, dtype=np.float64)
        d = marginals.shape[0]
        self.fit(corr)
        u = self.sample(n=n_paths)

        outcomes = (u <= marginals[np.newaxis, :]).astype(np.float64)
        hits = outcomes.sum(axis=1)

        return {
            "n_contracts": d,
            "n_paths": n_paths,
            "copula_type": self.copula_type,
            "expected_hits": float(hits.mean()),
            "std_hits": float(hits.std()),
            "prob_zero_hits": float((hits == 0).mean()),
            "prob_all_hit": float((hits == d).mean()),
            "var_5pct": float(np.percentile(hits, 5)),
            "per_contract_win_rate": outcomes.mean(axis=0).tolist(),
            "tail_dependence": self.tail_dependence(),
        }

    # ---- persistence -----------------------------------------------------

    def persist(
        self,
        result: Dict[str, Any],
        *,
        contract: str = "",
        ticker: str = "",
        n_paths: int = 0,
        elapsed_ms: float = 0.0,
    ) -> int:
        """Save a simulation run to the shared DB via _db.save_run."""
        conn = _db.get_conn()
        try:
            return _db.save_run(
                conn,
                layer="copula",
                contract=contract,
                ticker=ticker,
                params={
                    "copula_type": self.copula_type,
                    "df": self.df,
                    "dim": self._dim,
                    "theta": self._theta,
                },
                result=result,
                n_paths=n_paths,
                elapsed_ms=elapsed_ms,
            )
        finally:
            conn.close()

    # ---- internal --------------------------------------------------------

    def _avg_rho(self) -> float:
        """Average off-diagonal correlation."""
        if self._corr is None:
            return 0.0
        mask = ~np.eye(self._dim, dtype=bool)
        return float(np.mean(self._corr[mask]))


# --------------------------------------------------------------------------
# __main__ demo: 3-contract portfolio with all three copula families
# --------------------------------------------------------------------------

def _demo() -> None:
    contracts = [
        "Will BTC exceed $150k by June?",
        "Will ETH exceed $8k by June?",
        "Will total crypto market cap exceed $5T?",
    ]
    marginals = np.array([0.35, 0.25, 0.40])

    corr = np.array([
        [1.00, 0.65, 0.70],
        [0.65, 1.00, 0.60],
        [0.70, 0.60, 1.00],
    ])

    n_paths = 50_000
    sep = "=" * 64
    print(sep)
    print("  Layer 5: Copula Dependency Model  --  3-Contract Portfolio")
    print(sep)
    for i, name in enumerate(contracts):
        print(f"  [{i}] {name}  (marginal={marginals[i]:.0%})")
    print()

    for ctype in COPULA_TYPES:
        t0 = time.perf_counter()
        model = CopulaModel(copula_type=ctype, df=5)
        portfolio = model.simulate_portfolio(marginals, corr, n_paths=n_paths)
        elapsed = (time.perf_counter() - t0) * 1000.0

        joint_p = model.joint_probability(marginals, corr)
        tail = model.tail_dependence()

        print(f"--- {ctype.upper()} copula ---")
        print(f"  Joint P(all YES)    : {joint_p:.4f}")
        print(f"  Expected hits       : {portfolio['expected_hits']:.2f} / 3")
        print(f"  Std hits            : {portfolio['std_hits']:.2f}")
        print(f"  P(total wipeout)    : {portfolio['prob_zero_hits']:.4f}")
        print(f"  P(all hit)          : {portfolio['prob_all_hit']:.4f}")
        print(f"  VaR (5th pct)       : {portfolio['var_5pct']:.0f} hits")
        print(f"  Tail dep (L/U)      : {tail['lambda_L']:.4f} / {tail['lambda_U']:.4f}")
        print(f"  Win rates           : {[f'{r:.3f}' for r in portfolio['per_contract_win_rate']]}")
        print(f"  Elapsed             : {elapsed:.1f} ms")

        try:
            row_id = model.persist(
                {**portfolio, "joint_probability": joint_p},
                contract="crypto-basket-demo",
                ticker="BTC+ETH+CRYPTO",
                n_paths=n_paths,
                elapsed_ms=elapsed,
            )
            print(f"  Saved run id={row_id}")
        except Exception as exc:
            print(f"  DB save skipped: {exc}")
        print()

    # Conditional probability demo
    print("--- Conditional Probability ---")
    model = CopulaModel(copula_type="student_t", df=5)
    cond = model.conditional_prob(
        target_idx=2,
        given_indices=[0],
        given_values=[1.0],
        marginal_probs=marginals,
        corr=corr,
    )
    print(f"  P(Crypto>$5T | BTC>$150k = YES) : {cond:.4f}")
    print(f"  vs. marginal P(Crypto>$5T)       : {marginals[2]:.4f}")
    print(f"  Correlation uplift               : {cond - marginals[2]:+.4f}")
    print()

    # Independence baseline
    print("--- Independence Baseline ---")
    indep_joint = float(np.prod(marginals))
    copula_joint = CopulaModel(copula_type="gaussian").joint_probability(marginals, corr)
    print(f"  Independent joint P(all YES)     : {indep_joint:.4f}")
    print(f"  Gaussian copula joint P(all YES) : {copula_joint:.4f}")
    print(f"  Correlation premium              : {copula_joint - indep_joint:+.4f}")
    print(sep)


if __name__ == "__main__":
    _demo()
