# Database Strategy - Trader Curtis

## PHASE 1: Paper Trading (Now - 2-3 weeks)
**Database:** SQLite  
**Cost:** FREE  
**Location:** `/Users/shared/curtis/trader-curtis/data/trades.db`

### Why SQLite:
- ✅ Zero cost
- ✅ Zero setup/maintenance
- ✅ Handles 1000s of trades easily
- ✅ All analytics scripts work
- ✅ Perfect for learning/testing

### Working Features:
- Trade logging
- Position tracking
- Performance metrics
- Sentiment accuracy tracking
- Daily reports

---

## PHASE 2: Live Trading (After validation)
**Database:** ClickHouse Cloud  
**Cost:** $300 free credits, then ~$20-60/month  
**Signup:** https://clickhouse.cloud

### Why ClickHouse Cloud:
- 🚀 Millisecond query times
- 📊 Handles millions of rows
- 🔍 Advanced analytics (window functions, aggregations)
- 🤖 ML model training
- 📈 Real-time dashboards
- 💾 300GB storage

### Migration Plan:
1. Export SQLite data
2. Import to ClickHouse Cloud
3. Update connection strings
4. All scripts work unchanged

---

## DECISION LOG

**Date:** 2026-02-03  
**Decision:** Stick with SQLite for Phase 1  
**Reason:** Cost-effective, all features work, upgrade only when needed  
**Review:** Revisit when going live with real money

---

*Smart approach: Prove profitability first, then invest in infrastructure.*
