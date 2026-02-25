#!/usr/bin/env python3
"""
Convert GRPO dataset artifacts into MLX LoRA prompt/completion files.

Input files:
- datasets/grpo_train.jsonl
- datasets/grpo_eval.jsonl

Output files (for mlx_lm lora):
- datasets/mlx_grpo_lora/train.jsonl
- datasets/mlx_grpo_lora/valid.jsonl
- datasets/mlx_grpo_lora/test.jsonl
- datasets/mlx_grpo_lora/summary.json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRAIN = ROOT / "datasets" / "grpo_train.jsonl"
DEFAULT_EVAL = ROOT / "datasets" / "grpo_eval.jsonl"
DEFAULT_OUT = ROOT / "datasets" / "mlx_grpo_lora"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _norm_direction(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in {"buy", "bull", "bullish", "up", "yes", "1"}:
        return "long"
    if s in {"sell", "bear", "bearish", "down", "no", "-1"}:
        return "short"
    if s in {"long", "short", "neutral"}:
        return s
    return "neutral"


def _norm_strength(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s == "strong":
        return "strong"
    return "weak"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _completion_from_row(row: Dict[str, Any]) -> str:
    target = row.get("target") or {}
    meta = row.get("meta") or {}

    direction = _norm_direction(target.get("realized_direction") or target.get("predicted_direction"))
    strength = _norm_strength(target.get("trading_strength"))
    reward = _f(target.get("hgrm_reward"), 0.0)
    ticker = str(meta.get("ticker") or "")
    venue = str(meta.get("venue") or "")
    source = str(meta.get("source_tag") or row.get("source") or "")

    payload = {
        "direction": direction,
        "strength": strength,
        "rationale": (
            f"Outcome-backed label from {source or 'internal'}"
            f" for {ticker or 'asset'} on {venue or 'venue'}"
            f" with reward {reward:.3f}."
        ),
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _prompt_from_row(row: Dict[str, Any]) -> str:
    base = str(row.get("prompt") or "").strip()
    if not base:
        base = "You are an event-driven trader."
    return (
        base
        + "\nReturn strict JSON only with keys: direction, strength, rationale."
    )


def to_mlx_records(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for row in rows:
        out.append(
            {
                "prompt": _prompt_from_row(row),
                "completion": _completion_from_row(row),
            }
        )
    return out


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
            n += 1
    return n


def split_valid_test(eval_rows: List[Dict[str, str]]) -> tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if not eval_rows:
        return [], []
    if len(eval_rows) == 1:
        return [eval_rows[0]], [eval_rows[0]]
    pivot = max(1, len(eval_rows) // 2)
    return eval_rows[:pivot], eval_rows[pivot:]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build MLX LoRA dataset from GRPO artifacts")
    ap.add_argument("--train-file", default=str(DEFAULT_TRAIN), help="path to GRPO train jsonl")
    ap.add_argument("--eval-file", default=str(DEFAULT_EVAL), help="path to GRPO eval jsonl")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT), help="output directory for mlx dataset files")
    ap.add_argument("--max-train-rows", type=int, default=0, help="optional cap for train rows")
    ap.add_argument("--max-eval-rows", type=int, default=0, help="optional cap for eval rows")
    args = ap.parse_args()

    train_file = Path(args.train_file).expanduser()
    eval_file = Path(args.eval_file).expanduser()
    out_dir = Path(args.out_dir).expanduser()

    raw_train = load_jsonl(train_file)
    raw_eval = load_jsonl(eval_file)

    if args.max_train_rows and args.max_train_rows > 0:
        raw_train = raw_train[: int(args.max_train_rows)]
    if args.max_eval_rows and args.max_eval_rows > 0:
        raw_eval = raw_eval[: int(args.max_eval_rows)]

    train_rows = to_mlx_records(raw_train)
    eval_rows = to_mlx_records(raw_eval)
    valid_rows, test_rows = split_valid_test(eval_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    train_n = write_jsonl(out_dir / "train.jsonl", train_rows)
    valid_n = write_jsonl(out_dir / "valid.jsonl", valid_rows)
    test_n = write_jsonl(out_dir / "test.jsonl", test_rows)

    summary = {
        "generated_at": now_iso(),
        "source_train_file": str(train_file),
        "source_eval_file": str(eval_file),
        "train_rows": train_n,
        "valid_rows": valid_n,
        "test_rows": test_n,
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    print(
        "MLX dataset build:"
        f" train={train_n} valid={valid_n} test={test_n}"
        f" out_dir={out_dir}"
    )
    if train_n == 0:
        print("warning=no_train_rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
