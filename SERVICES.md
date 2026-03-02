# Service Dependencies & API Keys

> **READ THIS FIRST IN EVERY SESSION.** This file is the single source of truth
> for all external services, API keys, and integration status. If a key is missing
> from `.env` or keychain, the pipeline will silently degrade.

## Active Services

| Service | Env Var | Location | Plan | Status | Used By |
|---------|---------|----------|------|--------|---------|
| Alpaca (paper) | `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` | `.env` | Free paper | Active | `execution_worker.py`, `sync_alpaca_order_status.py` |
| Hyperliquid | `HL_AGENT_PRIVATE_KEY` | macOS Keychain (`trader-curtis-HL_AGENT_PRIVATE_KEY`) | Free | Testnet | `execution_adapters.py` |
| Polymarket CLOB | `POLY_PRIVATE_KEY` | macOS Keychain (`trader-curtis-POLY_PRIVATE_KEY`) | Free | Active | `execution_polymarket.py` |
| Predexon | `PREDEXON_API_KEY` + `PREDEXON_SECRET_KEY` | `.env` | Dev (120 req/min) | Active | `predexon_client.py` |
| xAI / Grok | `XAI_API_KEY` | `.env` | Paid | Active | `grok_alpha_once.py`, `grok_score_once.py`, `trader_brain.py` |
| OpenAI | `OPENAI_API_KEY` | `.env` | Paid | Active | Various LLM calls |
| Moonshot / Kimi | `MOONSHOT_API_KEY` | `.env` | Paid | Active | Agent model |
| Brave Search | `BRAVE_API_KEY` | `.env` | Free | Active | `pipeline_d_bookmarks.py` |
| HuggingFace | `HF_TOKEN` | `.env` | Free | Active | Model downloads |
| Chart-Img | `CHART_IMG_API_KEY` | `.env` (MISSING) | Free | Needs key | `live_chart_analyzer.py` |
| Ollama | Local | `localhost:11434` | Free | Active | GRPO training, regime analysis |
| Binance WS | None (public) | N/A | Free | Active | `binance_ws_feed.py` |
| CoinGecko | None (public) | N/A | Free (rate limited) | Fallback | `polymarket_momentum_scanner.py` |

## macOS Keychain Entries

Accessed via `security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "<service>" -w`

| Service Name | Description | Used By |
|-------------|-------------|---------|
| `trader-curtis-HL_AGENT_PRIVATE_KEY` | Hyperliquid signer key | `execution_adapters.py` |
| `trader-curtis-POLY_PRIVATE_KEY` | Polymarket order signing | `execution_polymarket.py` |
| `trader-curtis-POLY_API_KEY` | Polymarket CLOB API key | `execution_polymarket.py` |
| `trader-curtis-POLY_API_SECRET` | Polymarket CLOB API secret | `execution_polymarket.py` |
| `trader-curtis-POLY_PASSPHRASE` | Polymarket CLOB passphrase | `execution_polymarket.py` |

`KEYCHAIN_ACCOUNT` env var must be set (your macOS username).

## Predexon API Details

- **Base URL:** `https://api.predexon.com`
- **Auth:** `x-api-key` header
- **Plan:** Dev (120 req/min, smart money + cross-platform + Binance data)
- **Dashboard:** https://dashboard.predexon.com
- **Docs:** https://docs.predexon.com
- **Key endpoints used:**
  - `GET /v2/polymarket/crypto-updown` (free, unlimited)
  - `GET /v2/polymarket/markets` (free, unlimited)
  - `GET /v2/polymarket/market/{id}/smart-money` (Dev)
  - `GET /v2/polymarket/markets/smart-activity` (Dev)
  - `GET /v2/polymarket/candlesticks` (free)
  - `GET /v2/polymarket/orderbooks` (free)
  - `GET /v2/binance/candles` (Dev)
  - `GET /v2/matching/pairs` (Dev)

## Training Pipelines

### GRPO (existing)
- **Location**: `training/grpo/`
- **Model**: `mlx-community/Qwen2.5-7B-Instruct-4bit` (MLX LoRA)
- **Dataset**: 325 train / 81 eval from route_outcomes
- **Run**: `scripts/run_mlx_grpo_train.sh`
- **Control**: `grpo_mlx_train_enabled=1`

### EMPO² (arXiv:2602.23008, ICLR 2026)
- **Location**: `training/empo/`
- **Paper**: Exploratory Memory-Augmented On/Off-Policy Optimization (128.6% over GRPO on exploration)
- **What it adds**: Memory buffer (trade reflections), dual rollout, exploration bonus, on/off-policy hybrid
- **Dataset**: 392 samples, 393 tips in memory buffer
- **Run**: `scripts/run_empo_train.sh` or `python3 -m training.empo.build_dataset --mlx && python3 -m training.empo.trainer`
- **Control**: `empo_mlx_train_enabled=1`
- **DB tables**: `empo_memory_tips`, `empo_state_visits`
- **Integration**: EMPO² is a **separate** training track from GRPO, not built into it. Both produce MLX LoRA adapters. EMPO² adds memory + exploration on top.

### DAPO (arXiv:2505.06408)
- **Location**: `dapo_model.py`, `train_dapo.py`, `pipeline_l_dapo_agent.py`
- **Status**: Offline training on historical NASDAQ-100 data. NOT in live pipeline.
- **Note**: Separate RL agent for stock trading, not prediction markets.

### Simulation Engine Corrections (2026-03-01)
- **Critique**: "From Monte Carlo to Mirages" identified 6 errors in Layer 1
- **Fixed**: `simulations/monte_carlo.py` — GBM replaced with logit-diffusion, Brownian bridge for near-expiry, Brier Skill Score added, execution cost model, zero drift (no P/Q mixing)
- **Still TODO**: copula.py needs DCC (Dynamic Conditional Correlation), particle_filter.py needs Empirical Bayes hyperparameter calibration

### Microsoft Agent Lightning (arXiv:2508.03680)
- **Paper**: "Train ANY AI Agents with Reinforcement Learning" (Microsoft Research)
- **Status**: Evaluated 2026-02-17, not yet integrated
- **Relevance**: Could replace manual RL training with zero-code-change agent optimization
- **Action**: Evaluate for GRPO/EMPO² replacement after both pipelines have 200+ outcomes

## Execution Controls (DB)

Key settings in `execution_controls` table that affect trading:

| Key | Current | Description |
|-----|---------|-------------|
| `quant_gate_enforce` | `1` | Hard gate on signal quality |
| `consensus_enforce` | `1` | Multi-source agreement required |
| `allow_polymarket_live` | `0` | Paper mode (set to 1 for live) |
| `enable_polymarket_auto` | `1` | Auto-execution enabled |
| `polymarket_arb_enabled` | `1` | Micro-arb strategy on |
| `polymarket_momentum_enabled` | `1` | Momentum strategy on |
| `polymarket_alpha_enabled` | `0` | Alpha strategy off |
| `polymarket_copy_enabled` | `0` | Copy trading off |
| `daily_target_usd` | `100` | Daily PnL auto-pause target |
| `grpo_apply_weight_updates` | `1` | HGRM live weight updates |
| `grpo_kaggle_max_pct` | `0` | No Kaggle data in training |
| `empo_mlx_train_enabled` | `0` | EMPO² training (enable when ready) |

## Verification Script

Run to check all services are reachable:
```bash
python3 -c "
from pathlib import Path
import os, subprocess, requests

env = {}
for line in (Path(__file__).parent / '.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()

checks = {
    'Alpaca': bool(env.get('ALPACA_API_KEY')),
    'Predexon': bool(env.get('PREDEXON_API_KEY')),
    'xAI': bool(env.get('XAI_API_KEY')),
    'OpenAI': bool(env.get('OPENAI_API_KEY')),
    'Moonshot': bool(env.get('MOONSHOT_API_KEY')),
    'Brave': bool(env.get('BRAVE_API_KEY')),
    'HuggingFace': bool(env.get('HF_TOKEN')),
    'Chart-Img': bool(env.get('CHART_IMG_API_KEY')),
}
for name, ok in checks.items():
    print(f'  {\"OK\" if ok else \"MISSING\":>7}  {name}')
"
```

## Change Log

| Date | Change | By |
|------|--------|-----|
| 2026-03-01 | Initial manifest created | Claude |
| 2026-03-01 | Added Predexon API key + secret to .env | Claude |
| 2026-03-01 | Removed hardcoded Alpaca creds from 3 files | Claude |
| 2026-03-01 | Removed hardcoded Chart-Img key from live_chart_analyzer.py | Claude |
| 2026-03-01 | Created `predexon_client.py` — full API client (all Dev tier endpoints) | Claude |
| 2026-03-01 | Rewrote `polymarket_momentum_scanner.py` to use Predexon crypto-updown API (was 0 markets found with regex, now 1752) | Claude |
