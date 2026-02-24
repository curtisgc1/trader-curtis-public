# Hyperliquid Auto-Trader Setup (Perps vs Spot)

## Why confusion happens
Hyperliquid has separate state views:
- `clearinghouseState` = **perps/margin account** data
- `spotClearinghouseState` = **spot token balances**

If your agent only reads perps state, it can show `$0` even when spot balances exist.

## Correct wallet model for automation
Use two roles:
1. **Account wallet** (funded wallet, the one you trade from)
- `HL_WALLET_ADDRESS`
2. **Signer/API wallet** (isolated key for automation)
- `HL_AGENT_PRIVATE_KEY`

Signer must be authorized/whitelisted to act for account wallet on the same network (testnet/mainnet).

## Required runtime settings
- `HL_USE_TESTNET=1` for testnet
- `HL_API_URL=https://api.hyperliquid-testnet.xyz`
- `HL_INFO_URL=https://api.hyperliquid-testnet.xyz/info`
- `HL_WALLET_ADDRESS=<funded account wallet>`
- `HL_AGENT_PRIVATE_KEY=<authorized signer key>`

## Agent behavior requirements
The auto trader should:
1. Read both `clearinghouseState` and `spotClearinghouseState`
2. Distinguish:
- perp account value / withdrawable
- spot balances by token
3. Block orders with explicit reasons if:
- signer not authorized
- perp collateral unavailable
- asset not listed on target network

## In this build
- Dashboard API `get_portfolio_snapshot()` now reads both states.
- Hyperliquid execution already supports signer + separate account address.

## Useful commands
```bash
cd /Users/Shared/curtis/trader-curtis
./scripts/configure_hl_testnet.sh
./scripts/check_hl_setup.sh
python3.11 ./sync_wallet_config.py
```

## Primary docs
- Hyperliquid API / Info endpoint (state queries): https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- Hyperliquid exchange/account abstraction overview: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction
