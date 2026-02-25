# Handoff — 2026-02-24 — Polymarket CLI + Wallet/Edge/Status Fixes

## Completed

### 1) Polymarket CLI integration
- Installed official CLI via Homebrew tap.
- Added backend switch in execution controls:
  - `polymarket_exec_backend` (`pyclob` | `cli`)
- Added runner wrapper:
  - `scripts/run_polymarket_exec.sh`
- Updated scan orchestrator:
  - `run-all-scans.sh` now calls wrapper.
- `execution_polymarket.py` now supports live submit via CLI (`polymarket clob market-order`) when backend is `cli`.

### 2) Wallet mismatch hardening
- Added signer/funder normalization logic in `execution_polymarket.py`.
- Behavior:
  - If `POLY_FUNDER` missing -> auto-set to signer address.
  - If `POLY_FUNDER` differs from signer -> warn only (do NOT overwrite), preserving proxy/API-wallet flows.

### 3) Edge unit normalization fix
- Added `polymarket_edge_unit_mode` control (`auto|pct|fraction|ratio`).
- `_evaluate_candidate` now compares normalized edge percentage to `polymarket_min_edge_pct`.
- Prevents threshold mismatch caused by mixed edge units.

### 4) Candidate status reset fix
- Blocked candidates are no longer force-overwritten to `blocked` every cycle.
- Only `awaiting_approval` status is set when appropriate and lifecycle is still pending.
- This preserves manual status workflows and avoids repeated auto-reset.

### 5) Funding check brittleness fix
- Added `polymarket_strict_funding_check` control.
- In non-strict mode (`0`), funding check failures create `funding_warn` but do not hard-block live attempt.
- This avoids false negatives when allowance APIs lag.

### 6) Hyperliquid wallet mismatch behavior
- In `execution_adapters.py`, removed forced account overwrite to signer address.
- Keeps configured funded account if provided (important for approved API-wallet flow).

## New/updated controls
- `polymarket_exec_backend=cli`
- `polymarket_strict_funding_check=0`
- `polymarket_edge_unit_mode=auto`

## Validation
- `polymarket --version` works.
- `polymarket clob ok` returns OK.
- Python compile checks pass for modified modules.
- Polymarket exec wrapper runs and resolves backend correctly.

## Files changed
- `execution_polymarket.py`
- `execution_adapters.py`
- `execution_guard.py`
- `dashboard-ui/data.py`
- `run-all-scans.sh`
- `scripts/run_polymarket_exec.sh`
- `docs/POLY-CLI-INTEGRATION.md`
