#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/with_polymarket_keychain.sh <command> [args...]
# Example:
#   ./scripts/with_polymarket_keychain.sh python3 execution_polymarket.py

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

acct="curtiscorum"
get_secret() {
  local service="$1"
  security find-generic-password -a "$acct" -s "$service" -w 2>/dev/null || true
}

export POLY_API_KEY="$(get_secret trader-curtis-POLY_API_KEY)"
export POLY_API_SECRET="$(get_secret trader-curtis-POLY_API_SECRET)"
export POLY_API_PASSPHRASE="$(get_secret trader-curtis-POLY_API_PASSPHRASE)"
export POLY_PRIVATE_KEY="$(get_secret trader-curtis-POLY_PRIVATE_KEY)"

if [ -z "${POLY_FUNDER:-}" ]; then
  funder="$(get_secret trader-curtis-POLY_FUNDER)"
  if [ -n "$funder" ]; then
    export POLY_FUNDER="$funder"
  fi
fi

exec "$@"
