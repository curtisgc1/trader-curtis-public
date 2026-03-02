# EMPO² Training Stack

**Exploratory Memory-Augmented On/Off-Policy Optimization**
Adapted from [arXiv:2602.23008](https://arxiv.org/abs/2602.23008) (ICLR 2026).

## What EMPO² Adds Over Base GRPO

| Aspect | Current GRPO | EMPO² |
|--------|-------------|-------|
| Training type | Supervised LoRA | Policy optimization with dual rollouts |
| Memory | None | Trade reflection buffer (tips) |
| Exploration | None | Intrinsic novelty bonus (1/n visits) |
| Update modes | On-policy only | Hybrid on-policy + off-policy |
| Knowledge distillation | None | Off-policy tips → no-tips transfer |
| Token masking | None | Low-prob token suppression for stability |

## Architecture

```
training/empo/
  __init__.py          — Module exports
  memory_buffer.py     — Trade reflection storage + cosine retrieval
  reward.py            — HGRM + exploration bonus + group advantages
  rollout.py           — Dual-mode generation (with/without tips)
  build_dataset.py     — Convert outcomes → EMPO² training format
  trainer.py           — MLX LoRA training loop
```

## How It Works

1. **Memory Buffer**: After each resolved trade, a reflective "tip" is generated
   (either rule-based or via Ollama LLM). Tips capture: what happened, what went
   right/wrong, actionable insight.

2. **Dual Rollout**: For each training sample, with probability p (default 0.6),
   relevant tips are retrieved by cosine similarity and prepended to the prompt.
   Standard (no-tips) prompts are also generated.

3. **On-Policy Update**: Model generates with tips → update conditioned on tips.
   Standard PPO clipped objective.

4. **Off-Policy Update**: Model generated with tips → update WITHOUT tips.
   This distills tip-conditioned knowledge into the base model, so it performs
   well even without memory at inference time.

5. **Exploration Bonus**: Novel market states (new ticker/venue/source combinations)
   get r_intrinsic = 1/(n+1) added to reward, encouraging the model to explore
   less-traded regimes.

## Usage

### 1. Build Dataset
```bash
cd /Users/Shared/curtis/trader-curtis
python3 -m training.empo.build_dataset --mlx
```

### 2. Train
```bash
python3 -m training.empo.trainer --iters 200 --dry-run  # validate first
python3 -m training.empo.trainer --iters 200             # actual training
```

### 3. Check Memory Buffer
```bash
python3 -m training.empo.memory_buffer
```

## Hyperparameters

| Param | Default | Description |
|-------|---------|-------------|
| memory_prob (p) | 0.6 | Probability of memory-augmented rollout |
| offpolicy_prob (q) | 0.4 | Probability of off-policy update for memory samples |
| exploration_alpha | 0.1 | Weight for intrinsic exploration bonus |
| similarity_threshold | 0.5 | Min cosine sim for tip retrieval |
| max_tips | 10 | Max tips retrieved per state |
| base_model | Qwen2.5-7B-Instruct-4bit | MLX model for fine-tuning |
| iters | 200 | Training iterations |
| batch_size | 4 | Samples per gradient step |
| learning_rate | 1e-5 | LoRA learning rate |
| lora_layers | 16 | Number of LoRA layers |

## Data Requirements

- Minimum 40 realized trade outcomes (configurable via `empo_mlx_min_train_rows`)
- Paper used Qwen2.5-7B-Instruct — same model already configured
- Runs on Apple Silicon via MLX (M3 Ultra with 512GB RAM is more than sufficient)

## Execution Controls

| Key | Default | Description |
|-----|---------|-------------|
| `empo_mlx_train_enabled` | 0 | Master enable for EMPO² training |
| `empo_mlx_base_model` | (falls back to grpo_mlx_base_model) | Model to train |
| `empo_mlx_min_train_rows` | 40 | Min samples to trigger training |
| `empo_memory_prob` | 0.6 | Memory rollout probability |
| `empo_exploration_alpha` | 0.1 | Exploration bonus weight |

## Paper Citation

```
@inproceedings{liu2026empo,
  title={EMPO²: Exploratory Memory-Augmented On- and Off-Policy Optimization},
  author={Liu, Zeyuan and Kim, Jeonghye and Luo, Xufang and Li, Dongsheng and Yang, Yuqing},
  booktitle={ICLR 2026},
  year={2026}
}
```
