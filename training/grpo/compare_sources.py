#!/usr/bin/env python3
"""
Compare training sample composition by source (internal vs kaggle, etc).
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "datasets" / "grpo_train.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare GRPO dataset sources")
    ap.add_argument("--file", default=str(DEFAULT_PATH))
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(json.dumps({"error": f"file not found: {p}"}))
        return 1

    by_source = Counter()
    by_source_outcome = defaultdict(Counter)
    by_source_dir = defaultdict(Counter)

    total = 0
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        total += 1
        src = str(row.get("source") or "unknown")
        out = str(row.get("outcome_type") or "")
        rd = str((row.get("target") or {}).get("realized_direction") or "")
        by_source[src] += 1
        by_source_outcome[src][out] += 1
        by_source_dir[src][rd] += 1

    report = {
        "total_rows": total,
        "sources": [],
    }
    for src, n in sorted(by_source.items(), key=lambda kv: kv[1], reverse=True):
        report["sources"].append(
            {
                "source": src,
                "rows": n,
                "outcome_types": dict(by_source_outcome[src]),
                "realized_direction": dict(by_source_dir[src]),
            }
        )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
