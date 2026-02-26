#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from execution_adapters import hyperliquid_submit_reduce_only_stop_live


def main() -> int:
    p = argparse.ArgumentParser(description="Apply Hyperliquid reduce-only stop protection")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, help="buy or sell (exit side)")
    p.add_argument("--qty", required=True, type=float)
    p.add_argument("--stop-price", required=True, type=float, dest="stop_price")
    p.add_argument("--cancel-existing", default="1")
    args = p.parse_args()

    cancel_existing = str(args.cancel_existing).strip().lower() in {"1", "true", "yes", "on"}
    ok, message, details = hyperliquid_submit_reduce_only_stop_live(
        symbol=str(args.symbol).upper().strip(),
        side=str(args.side).lower().strip(),
        qty=float(args.qty),
        stop_price=float(args.stop_price),
        is_market=True,
        cancel_existing=cancel_existing,
    )
    print(
        json.dumps(
            {
                "ok": bool(ok),
                "message": str(message),
                "details": details if isinstance(details, dict) else {"raw": str(details)},
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
