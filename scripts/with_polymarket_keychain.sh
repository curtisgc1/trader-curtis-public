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

export POLY_PRIVATE_KEY="$(get_secret trader-curtis-POLY_PRIVATE_KEY)"
export POLY_API_KEY="$(get_secret trader-curtis-POLY_API_KEY)"
export POLY_API_SECRET="$(get_secret trader-curtis-POLY_API_SECRET)"
export POLY_API_PASSPHRASE="$(get_secret trader-curtis-POLY_API_PASSPHRASE)"

if [ -z "${POLY_FUNDER:-}" ]; then
  funder="$(get_secret trader-curtis-POLY_FUNDER)"
  if [ -n "$funder" ]; then
    export POLY_FUNDER="$funder"
  fi
fi

if [ -z "${POLY_SIGNATURE_TYPE:-}" ]; then
  sig_type="$(get_secret trader-curtis-POLY_SIGNATURE_TYPE)"
  if [ -n "$sig_type" ]; then
    export POLY_SIGNATURE_TYPE="$sig_type"
  fi
fi

# Direct-wallet mode: disable API-wallet/proxy ambiguity.
# Default OFF so API-key mode works unless explicitly enabled.
direct_mode="${POLY_DIRECT_EOA:-0}"
case "$(printf '%s' "$direct_mode" | tr '[:upper:]' '[:lower:]')" in
  0|false|no|off)
    ;;
  *)
    export POLY_SIGNATURE_TYPE="0"
    # Keep execution tied to signer wallet; do not use proxy/API wallet controls.
    unset POLY_API_KEY POLY_API_SECRET POLY_API_PASSPHRASE
    if [ -n "${POLY_PRIVATE_KEY:-}" ]; then
      signer_addr="$(
        python3 - <<'PY'
from eth_account import Account
import os
pk = os.environ.get("POLY_PRIVATE_KEY", "").strip()
if not pk:
    print("")
else:
    try:
        print(Account.from_key(pk).address)
    except Exception:
        print("")
PY
      )"
      if [ -n "$signer_addr" ]; then
        export POLY_FUNDER="$signer_addr"
      fi
    fi
    ;;
esac

exec "$@"
