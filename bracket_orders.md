# Bracket Order Implementation
## For Future Trades - No More Wash Trade Issues

## What is a Bracket Order?

A single order that contains:
1. **Entry** - Buy shares
2. **Stop Loss** - Auto-sell if price drops
3. **Take Profit** - Auto-sell if target hit

When entry fills, stop and target become active automatically.

## Benefits

- ✅ **No wash trade conflicts** - One order, not separate buy/sell
- ✅ **Set and forget** - No manual stop setting needed
- ✅ **Instant protection** - Stop active immediately on fill
- ✅ **Disciplined exits** - Target and stop pre-defined

## Alpaca Bracket Order Format

```json
{
  "symbol": "TICKER",
  "qty": "10",
  "side": "buy",
  "type": "market",
  "time_in_force": "day",
  "order_class": "bracket",
  "take_profit": {
    "limit_price": "130.00"
  },
  "stop_loss": {
    "stop_price": "90.00",
    "limit_price": "89.50"
  }
}
```

## Example Trades

### Trade 1: AEM with Bracket
```json
{
  "symbol": "AEM",
  "qty": "4",
  "side": "buy",
  "type": "market",
  "time_in_force": "day",
  "order_class": "bracket",
  "take_profit": {"limit_price": "135.00"},
  "stop_loss": {"stop_price": "104.00", "limit_price": "103.50"}
}
```
- Entry: ~$116
- Stop: $104 (-10.3%)
- Target: $135 (+16.4%)

### Trade 2: Future Gold Miner
```json
{
  "symbol": "GOLD",
  "qty": "20",
  "side": "buy",
  "type": "market",
  "order_class": "bracket",
  "take_profit": {"limit_price": "25.00"},
  "stop_loss": {"stop_price": "19.00"}
}
```

## Implementation

**For all future auto-trades, I will:**
1. Calculate entry price
2. Calculate stop (-10% max)
3. Calculate target (+15-20%)
4. Submit ONE bracket order
5. Position is protected instantly

## Current Positions

Existing positions (NEM, ASTS, etc.) keep their current stops.
**All NEW trades use bracket orders.**

---

*No more wash trade issues. No more manual stop setting.*
