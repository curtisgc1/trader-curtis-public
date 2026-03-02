#!/usr/bin/env python3
"""
EMPO² Trainer — Hybrid on/off-policy optimization loop.

Paper reference: arXiv:2602.23008, Algorithm 1

Training modes per sample:
  ON-POLICY:  Model generates with tips → update with tips-conditioned loss
  OFF-POLICY: Model generated with tips → update WITHOUT tips (knowledge distillation)
              Token masking applied for stability (Eq. 2)

Backend: MLX LoRA on Apple Silicon (same as existing GRPO pipeline).
Model: Qwen2.5-7B-Instruct-4bit (or configured via execution_controls).

This is the actual training loop. Prerequisites:
  1. Run build_dataset.py to generate empo_train.jsonl
  2. Ensure MLX and mlx_lm are installed
  3. Ollama running for tip generation (optional)
"""

import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "trades.db"
DATASETS_DIR = ROOT / "datasets"
MODELS_DIR = ROOT / "models"
LOGS_DIR = ROOT / "logs"


def _get_control(conn: sqlite3.Connection, key: str, default: str) -> str:
    cur = conn.cursor()
    cur.execute("SELECT value FROM execution_controls WHERE key=? LIMIT 1", (key,))
    row = cur.fetchone()
    return str(row[0]) if row and row[0] is not None else default


def _set_runtime(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO execution_controls (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (f"runtime:{key}", value),
    )
    conn.commit()


def check_prerequisites() -> Dict[str, Any]:
    """Verify MLX stack is available."""
    checks = {"mlx": False, "mlx_lm": False, "train_data": False}

    try:
        import mlx
        checks["mlx"] = True
    except ImportError:
        pass

    try:
        import mlx_lm
        checks["mlx_lm"] = True
    except ImportError:
        pass

    train_path = DATASETS_DIR / "mlx_empo_lora" / "train.jsonl"
    checks["train_data"] = train_path.exists()
    if checks["train_data"]:
        with open(train_path) as f:
            checks["train_rows"] = sum(1 for _ in f)
    else:
        checks["train_rows"] = 0

    return checks


def train(
    base_model: Optional[str] = None,
    iters: int = 200,
    batch_size: int = 4,
    learning_rate: float = 1e-5,
    lora_layers: int = 16,
    adapter_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run EMPO² fine-tuning via mlx_lm.lora.

    This wraps the MLX LoRA training with EMPO²-specific dataset format.
    The dual-mode (on/off-policy) is handled at dataset build time:
    - On-policy samples: prompt includes tips
    - Off-policy samples: prompt EXCLUDES tips (standard prompt only)
    - Token masking: handled by MLX's native mask_prompt=True

    Args:
        base_model: HuggingFace model ID (default from execution_controls)
        iters: Training iterations
        batch_size: Samples per gradient step
        learning_rate: Learning rate for LoRA
        lora_layers: Number of layers to apply LoRA
        adapter_path: Output path for trained adapter
        dry_run: Just validate, don't train
    """
    conn = sqlite3.connect(str(DB_PATH))

    if base_model is None:
        base_model = _get_control(
            conn, "empo_mlx_base_model",
            _get_control(conn, "grpo_mlx_base_model", "mlx-community/Qwen2.5-7B-Instruct-4bit"),
        )

    if adapter_path is None:
        adapter_path = str(MODELS_DIR / "mlx-empo-adapter")

    train_data = DATASETS_DIR / "mlx_empo_lora"
    if not (train_data / "train.jsonl").exists():
        conn.close()
        return {"status": "error", "message": "No training data. Run build_dataset.py --mlx first."}

    # Count rows
    with open(train_data / "train.jsonl") as f:
        row_count = sum(1 for _ in f)

    min_rows = int(_get_control(conn, "empo_mlx_min_train_rows",
                                _get_control(conn, "grpo_mlx_min_train_rows", "40")))
    if row_count < min_rows:
        conn.close()
        return {
            "status": "skipped",
            "message": f"Only {row_count} rows, need {min_rows}+",
            "rows": row_count,
        }

    if dry_run:
        conn.close()
        return {
            "status": "dry_run",
            "model": base_model,
            "rows": row_count,
            "iters": iters,
        }

    # Record start
    _set_runtime(conn, "empo_mlx_last_train_utc", datetime.utcnow().isoformat())
    _set_runtime(conn, "empo_mlx_last_status", "running")
    _set_runtime(conn, "empo_mlx_last_model", base_model)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "mlx-empo-train.log"

    # Build mlx_lm lora command
    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--model", base_model,
        "--data", str(train_data),
        "--adapter-path", adapter_path,
        "--train",
        "--iters", str(iters),
        "--batch-size", str(batch_size),
        "--learning-rate", str(learning_rate),
        "--num-layers", str(lora_layers),
        "--mask-prompt",
    ]

    # Add validation if exists
    if (train_data / "valid.jsonl").exists():
        cmd.extend(["--val-batches", "5"])

    start_ts = time.time()
    print(f"EMPO² TRAIN: model={base_model} rows={row_count} iters={iters}")
    print(f"  cmd: {' '.join(cmd)}")

    try:
        with open(log_path, "a") as logf:
            logf.write(f"\n{'='*60}\n")
            logf.write(f"EMPO² Training Run — {datetime.now().isoformat()}\n")
            logf.write(f"Model: {base_model}\n")
            logf.write(f"Rows: {row_count}, Iters: {iters}\n")
            logf.write(f"{'='*60}\n")

            result = subprocess.run(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                timeout=3600,  # 1 hour max
            )

        duration = time.time() - start_ts
        status = "success" if result.returncode == 0 else "failed"

        # Try to extract test loss from log
        test_loss = None
        try:
            log_text = log_path.read_text()
            for line in reversed(log_text.splitlines()):
                if "Test loss" in line:
                    import re
                    m = re.search(r"Test loss[:\s]+([\d.]+)", line)
                    if m:
                        test_loss = float(m.group(1))
                    break
        except Exception:
            pass

        _set_runtime(conn, "empo_mlx_last_status", status)
        _set_runtime(conn, "empo_mlx_last_duration_sec", f"{duration:.0f}")
        if test_loss is not None:
            _set_runtime(conn, "empo_mlx_last_test_loss", f"{test_loss:.4f}")

        conn.close()
        return {
            "status": status,
            "model": base_model,
            "rows": row_count,
            "iters": iters,
            "duration_sec": round(duration),
            "test_loss": test_loss,
            "adapter_path": adapter_path,
        }

    except subprocess.TimeoutExpired:
        _set_runtime(conn, "empo_mlx_last_status", "timeout")
        conn.close()
        return {"status": "timeout", "message": "Training exceeded 1 hour limit"}
    except Exception as e:
        _set_runtime(conn, "empo_mlx_last_status", f"error:{e}")
        conn.close()
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EMPO² MLX LoRA Trainer")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--lora-layers", type=int, default=16)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("EMPO² TRAINER")
    print("=" * 60)

    # Check prerequisites
    prereqs = check_prerequisites()
    print(f"\n  MLX installed:    {'yes' if prereqs['mlx'] else 'NO'}")
    print(f"  mlx_lm installed: {'yes' if prereqs['mlx_lm'] else 'NO'}")
    print(f"  Training data:    {'yes' if prereqs['train_data'] else 'NO'} ({prereqs['train_rows']} rows)")

    if not prereqs["mlx"] or not prereqs["mlx_lm"]:
        print("\n  Install: pip install mlx mlx_lm")
        sys.exit(1)

    result = train(
        base_model=args.model,
        iters=args.iters,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        lora_layers=args.lora_layers,
        dry_run=args.dry_run,
    )

    print(f"\n  Result: {json.dumps(result, indent=2)}")
