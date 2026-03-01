"""Quant Simulation Engine for Polymarket edge detection.

Seven-layer architecture:
  1. monte_carlo       — GBM binary contract pricing, Brier calibration
  2. importance_sampling — Exponential tilting for P < 0.01 contracts
  3. particle_filter    — Sequential MC for live market tracking
  4. variance_reduction — Antithetic + control variate + stratified
  5. copula             — Gaussian/t/Clayton correlated contract modeling
  6. market_sim         — Agent-based price discovery (Kyle's lambda)
  7. ensemble_engine    — Wires all layers, EVT VaR/ES, Brier tracking
"""
from __future__ import annotations

from .monte_carlo import MonteCarloEngine
from .importance_sampling import ImportanceSampler
from .particle_filter import ParticleFilter
from .variance_reduction import VarianceReducer
from .copula import CopulaModel
from .market_sim import MarketSimulator
from .ensemble_engine import EnsembleEngine
from . import _db

__all__ = [
    "MonteCarloEngine",
    "ImportanceSampler",
    "ParticleFilter",
    "VarianceReducer",
    "CopulaModel",
    "MarketSimulator",
    "EnsembleEngine",
    "_db",
]
