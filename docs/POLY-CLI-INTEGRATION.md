# Polymarket CLI Integration

## Status
- `polymarket` CLI installed via Homebrew (`polymarket 0.1.0` available at `/opt/homebrew/bin/polymarket`).
- Execution backend is switchable through `execution_controls.polymarket_exec_backend`.

## Backend Modes
- `pyclob` (default legacy): uses `py_clob_client` from `execution_polymarket.py`.
- `cli`: uses `polymarket clob market-order` for live submissions.

## Runtime Control Keys
- `polymarket_exec_backend`: `pyclob` or `cli`
- `polymarket_strict_funding_check`: `0|1`
- `polymarket_edge_unit_mode`: `auto|pct|fraction|ratio`

## Current Wiring
- `run-all-scans.sh` now calls `scripts/run_polymarket_exec.sh`.
- `scripts/run_polymarket_exec.sh` reads backend control and invokes `execution_polymarket.py`.
- `execution_polymarket.py` will use CLI submit path when:
  - `polymarket_exec_backend=cli`
  - live mode is enabled

## Wallet Notes
- If `POLY_FUNDER` and signer from `POLY_PRIVATE_KEY` differ, worker now logs warning and preserves configured funder (for proxy/API-wallet setups).
- If `POLY_FUNDER` is missing, it is auto-filled from signer address.

## Suggested CLI setup check
```bash
polymarket --version
polymarket clob ok
```

