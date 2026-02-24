# Handoff — 2026-02-24 — Kaggle Hardening and Control Wiring

## What was fixed
- Added missing `kaggle_*` control support in core execution defaults and dashboard control API allowlist:
  - `kaggle_auto_pull_enabled`
  - `kaggle_poly_dataset_slug`
- Installed Kaggle CLI for runtime Python 3.11 used by cron/scripts.
- Hardened `pipeline_j_kaggle_polymarket.py` downloader:
  - Resolves `kaggle` executable from PATH and common user-site script paths.
  - Returns `skipped:no_kaggle_cli` if unavailable.
- Hardened Kaggle ingest validity:
  - Removed permissive `title` fallback for question field.
  - Requires explicit resolved outcome field and non-neutral binary normalization.
  - Prevents unrelated datasets from poisoning `polymarket_kaggle_markets`.

## Data correction performed
- Removed contaminated rows from `polymarket_kaggle_markets` after test ingest with non-market dataset.
- Reset controls to safe defaults:
  - `kaggle_auto_pull_enabled=0`
  - `kaggle_poly_dataset_slug=''`

## Validation
- `python3 -m py_compile` passed for modified files.
- `./scripts/run_kaggle_ingest.sh` now runs cleanly with no slug and inserts 0 rows.
- GRPO dataset build still works (`internal` source only currently).

## Remaining operator action
- Provide valid Kaggle credentials (`~/.kaggle/kaggle.json`, mode 600).
- Set a real Polymarket dataset slug in `kaggle_poly_dataset_slug`.
- Flip `kaggle_auto_pull_enabled=1` after first manual successful ingest.
