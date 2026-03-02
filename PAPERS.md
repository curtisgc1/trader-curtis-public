# Research Papers Referenced

Papers that have informed the design, training, and simulation layers of this system.

## Implemented

| Paper | arXiv | Year | Used In | Status |
|-------|-------|------|---------|--------|
| **EMPO²**: Exploratory Memory-Augmented On/Off-Policy Optimization | [2602.23008](https://arxiv.org/abs/2602.23008) | ICLR 2026 | `training/empo/` | Implemented, 392 training samples |
| **GRPO**: Group Relative Policy Optimization | [2402.03300](https://arxiv.org/abs/2402.03300) | 2024 | `training/grpo/` | Implemented, 325 training samples |
| **DAPO**: Direct Alignment from Preferences Optimization | [2505.06408](https://arxiv.org/abs/2505.06408) | 2025 | `dapo_model.py`, `train_dapo.py` | Offline only (NASDAQ-100) |

## Evaluated (Not Yet Integrated)

| Paper | arXiv | Year | Relevance | Action |
|-------|-------|------|-----------|--------|
| **Agent Lightning**: Train ANY AI Agents with RL | [2508.03680](https://arxiv.org/abs/2508.03680) | Microsoft 2025 | Zero-code-change RL optimization for agents | Evaluate after 200+ realized outcomes |

## Simulation Engine References

The Monte Carlo simulation engine (`simulations/`) was corrected based on peer critique identifying 6 foundational errors (2026-03-01):

| Correction | What Changed | Reference |
|-----------|-------------|-----------|
| GBM to logit-diffusion | Paths now bounded [0,1] by construction | Standard logit-normal diffusion model |
| Brownian bridge | Near-expiry contracts drift toward resolution | Brownian bridge conditioning (Karatzas & Shreve) |
| Brier Skill Score | Raw Brier replaced with BSS = 1 - BS/baseline | Brier (1950), Murphy & Winkler (1987) |
| Execution cost model | Spread + slippage + taker fee subtracted from edge | Polymarket fee schedule (3.15% taker) |
| Zero drift (no P/Q mixing) | Removed drift parameter from public API | Fundamental theorem of asset pricing |
| DCC for copulas (TODO) | Static correlation to be replaced with dynamic | Engle (2002) DCC-GARCH |

## How to Add a Paper

When evaluating a new paper for integration:
1. Add it to the "Evaluated" table above
2. Note relevance and action criteria
3. Update SERVICES.md Training Pipelines section
4. Update agent workspace MEMORY.md files (ORION, trader-curtis)
5. When implemented, move to "Implemented" table with file locations
