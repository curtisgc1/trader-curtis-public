#!/usr/bin/env bash
set -euo pipefail

cd /Users/Shared/curtis/trader-curtis

echo "HL env keys present:"
awk -F= '/^(HL_AGENT_PRIVATE_KEY|HL_WALLET_ADDRESS|HL_USE_TESTNET|HL_API_URL|HL_INFO_URL)=/{print " - "$1"=<set>"}' .env || true

if security find-generic-password -a "curtiscorum" -s "trader-curtis-HL_AGENT_PRIVATE_KEY" -w >/dev/null 2>&1; then
  echo " - HL_AGENT_PRIVATE_KEY=<set: keychain>"
else
  echo " - HL_AGENT_PRIVATE_KEY=<missing: keychain>"
fi

echo
echo "Runtime probe:"
python3 - <<'PY'
from execution_adapters import load_env, _hl_runtime_urls, _fetch_hl_universe

env = load_env()
api_url, info_url, network = _hl_runtime_urls(env)
ok, msg, universe = _fetch_hl_universe(env)
print(f"network={network}")
print(f"api_url={api_url}")
print(f"info_url={info_url}")
print(f"meta_ok={ok}")
print(f"meta_msg={msg}")
print(f"universe_size={len(universe)}")
print(f"btc_listed={'BTC' in universe}")
PY
