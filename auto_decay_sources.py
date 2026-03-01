#!/usr/bin/env python3
"""
Auto-decay sources: zero out any source flagged as decaying.

Runs as a pipeline step before candidate generation so decaying sources
get weight=0 before they can influence new candidates.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "dashboard-ui"))
from data import auto_dampen_decaying_sources


def main() -> int:
    result = auto_dampen_decaying_sources()
    enabled = result.get("auto_decay_enabled", False)
    if not enabled:
        print("Auto-decay: DISABLED (auto_decay_enabled=0)")
        return 0
    checked = result.get("checked", 0)
    zeroed = result.get("zeroed", [])
    print(f"Auto-decay: checked {checked} sources, zeroed {len(zeroed)}")
    for tag in zeroed:
        print(f"  → {tag} set to weight=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
