# AUTO_TRADE_AUTHORIZATION.md
**Status:** FULLY AUTHORIZED  
**Date:** 2026-02-07  
**Grantor:** Curtis  

## Authorization Scope

Trader Curtis has **full authorization** to:

### ✅ Approved Actions
1. **Place stop-loss orders** on any open position
2. **Place take-profit orders** at predefined targets
3. **Sync data** between Alpaca and local database/memory
4. **Update logs** and trade records automatically
5. **Set price alerts** for watchlist items
6. **Generate reports** and analysis
7. **Adjust position sizes** within risk limits (max $500/trade)
8. **Cancel and replace** orders to optimize execution

### ⚠️ Requires Explicit Approval
- New buy orders (not already pre-approved by strategy)
- Sell orders that aren't stop-losses or take-profits
- Increasing position sizes beyond original plan
- Removing stop losses once set
- Trading outside market hours

### 🚫 Never Allowed
- Real money trading (paper only until explicitly authorized)
- Leverage or margin beyond 2x
- Options or derivatives
- Cryptocurrency (unless previously discussed)
- Sharing account credentials
- Deleting trade history

## Risk Limits (Hardcoded)
- Max $500 per new trade
- Max 2% account risk per trade
- Stop losses mandatory on ALL positions
- No more than 20% in single sector

## Notification Preferences
- Immediate: Stop losses triggered, major losses (>5%)
- Daily: EOD summary
- Weekly: Performance report

---
*Authorization active immediately.*
