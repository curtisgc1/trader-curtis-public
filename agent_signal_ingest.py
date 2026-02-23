#!/usr/bin/env python3
"""
Natural-ish command ingest for agent-driven DB updates.

Examples:
  ./agent_signal_ingest.py --text "copy trade @NoLimitGains long NVDA entry 142 stop 135 target 165 notes momentum breakout"
  ./agent_signal_ingest.py --text "external signal source ZenomTrader ticker TSLA short conf 0.72 url https://x.com/... notes fade rally"
"""

import argparse
import re
import shlex
import subprocess
from pathlib import Path

BASE = Path(__file__).parent


def _run(cmd: list[str]) -> int:
    p = subprocess.run(cmd, cwd=str(BASE))
    return int(p.returncode)


def _extract(tokens: list[str], key: str, default: str = "") -> str:
    key_l = key.lower()
    for i, t in enumerate(tokens[:-1]):
        if t.lower() == key_l:
            return tokens[i + 1]
    return default


def ingest_copy(text: str) -> int:
    tokens = shlex.split(text)
    low = [t.lower() for t in tokens]
    source = ""
    for t in tokens:
        if t.startswith("@"):
            source = t[1:]
            break
    if not source:
        source = _extract(tokens, "source", "manual")

    ticker = ""
    explicit_ticker = _extract(tokens, "ticker", "").strip().upper()
    if explicit_ticker:
        ticker = explicit_ticker
    if not ticker:
        # Prefer $TICKER notation.
        for t in tokens:
            m = re.fullmatch(r"\$([A-Za-z]{1,6})", t)
            if m:
                ticker = m.group(1).upper()
                break
    if not ticker:
        stop_words = {
            "copy", "trade", "long", "short", "entry", "stop", "target", "notes", "source", "status",
            "from", "agent", "test",
        }
        for t in tokens:
            if re.fullmatch(r"[A-Za-z]{1,6}", t) and t.lower() not in stop_words:
                ticker = t.upper()
                break
    direction = "long" if "long" in low else ("short" if "short" in low else "long")
    entry = _extract(tokens, "entry", "0")
    stop = _extract(tokens, "stop", "0")
    target = _extract(tokens, "target", "0")
    status = _extract(tokens, "status", "OPEN")
    notes = ""
    if "notes" in low:
        idx = low.index("notes")
        notes = " ".join(tokens[idx + 1 :]).strip()

    if not ticker:
        print("Could not parse ticker from copy-trade command")
        return 2

    cmd = [
        str(BASE / "add_copy_trade_signal.py"),
        "--source",
        source,
        "--ticker",
        ticker,
        "--direction",
        direction,
        "--entry",
        str(entry),
        "--stop",
        str(stop),
        "--target",
        str(target),
        "--status",
        status,
        "--notes",
        notes,
    ]
    return _run(cmd)


def ingest_external(text: str) -> int:
    tokens = shlex.split(text)
    low = [t.lower() for t in tokens]
    source = _extract(tokens, "source", "manual")
    ticker = _extract(tokens, "ticker", "").upper()
    if not ticker:
        for t in tokens:
            if re.fullmatch(r"[A-Za-z]{1,6}", t) and t.lower() not in {
                "external", "signal", "source", "ticker", "long", "short", "conf", "url", "notes"
            }:
                ticker = t.upper()
    direction = "long" if "long" in low else ("short" if "short" in low else "long")
    conf = _extract(tokens, "conf", "0.6")
    url = _extract(tokens, "url", "")
    notes = ""
    if "notes" in low:
        idx = low.index("notes")
        notes = " ".join(tokens[idx + 1 :]).strip()

    if not ticker:
        print("Could not parse ticker from external-signal command")
        return 2

    cmd = [
        str(BASE / "add_external_signal.py"),
        "--source",
        source,
        "--url",
        url or "manual://agent",
        "--ticker",
        ticker,
        "--direction",
        direction,
        "--confidence",
        str(conf),
        "--notes",
        notes,
    ]
    return _run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True, help="agent command text")
    args = parser.parse_args()
    text = args.text.strip()
    low = text.lower()
    if "copy trade" in low or low.startswith("copy "):
        return ingest_copy(text)
    if "external signal" in low or low.startswith("signal ") or low.startswith("external "):
        return ingest_external(text)
    print("Unsupported command. Use copy trade ... or external signal ...")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
