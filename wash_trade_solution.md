# Wash Trade Solution

## Problem
When a stop-loss order exists on a position, Alpaca blocks additional buy orders for the same ticker (wash trade protection).

## Solutions

### Option 1: Cancel & Reset (Manual)
1. Cancel existing stop order
2. Place new buy order
3. Place new combined stop for total shares

### Option 2: Bracket Orders (Best)
Use OCO (One-Cancels-Other) bracket orders from entry:
- Entry: Market/Limit buy
- Attached: Stop-loss + Take-profit
- If one fills, other cancels automatically

### Option 3: Different Tickers (Simplest)
Instead of adding to existing positions, buy different but similar stocks:
- Want gold exposure? Buy AEM instead of more NEM
- Want crypto? Buy RIOT instead of more MARA

## Recommendation

**For NEM add:** Use Option 3 - Buy **AEM** (Agnico Eagle Mines) instead
- Same gold miner sector
- Similar chart pattern  
- No wash trade conflict
- Fresh position with clean stop/target

**For future trades:** Use bracket orders from entry to avoid this entirely.

## Implementation

```bash
# Cancel existing stops, add shares, reset
# OR
# Buy AEM: 4 shares @ ~$116 = ~$464
# Stop: $104 (-10%)
# Target: $135 (+16%)
```
