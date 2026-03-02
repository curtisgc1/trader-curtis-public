# EMPO² — Exploratory Memory-Augmented On/Off-Policy Optimization
# Adapted from arXiv:2602.23008 (ICLR 2026) for trading signal evaluation.
#
# Modules:
#   memory_buffer  — Trade reflection storage + cosine-similarity retrieval
#   reward         — HGRM reward + exploration bonus (novel market regimes)
#   rollout        — Dual-mode generation (with/without trade tips)
#   trainer        — Hybrid on/off-policy optimization loop (MLX backend)
#   build_dataset  — Convert trade outcomes to EMPO² training format
