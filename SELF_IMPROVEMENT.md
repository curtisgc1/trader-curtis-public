# Trader Curtis - Self-Improvement Framework

## Core Directives (Auto-Approved)

✅ **Build tools as needed** — no asking permission  
✅ **Analyze every trade** — wins, losses, lessons  
✅ **Track sentiment accuracy** — did Reddit/Twitter predict right?  
✅ **Log decision quality** — what data led to what outcome  
✅ **Iterate continuously** — improve based on results  

---

## Trade Outcome Database Schema

```json
{
  "trade_id": "uuid",
  "ticker": "NEM",
  "entry_date": "2026-02-03",
  "exit_date": "2026-02-10",
  "entry_price": 111.50,
  "exit_price": 125.00,
  "shares": 100,
  "pnl": 1350,
  "pnl_percent": 12.1,
  
  "sentiment_at_entry": {
    "reddit_score": 72,
    "twitter_score": 68,
    "analyst_rating": "buy",
    "wsb_rank": null
  },
  
  "decision_factors": [
    "Gold at record highs",
    "Largest gold miner",
    "Copper diversification"
  ],
  
  "outcome_analysis": {
    "sentiment_correct": true,
    "thesis_validated": true,
    "key_lesson": "Limit orders work, don't chase"
  },
  
  "improvement_notes": "Gold correlation strong, watch dollar index"
}
```

---

## Analysis Routines

### Post-Trade Analysis (Run on every exit)
1. Compare entry sentiment vs exit reality
2. Grade decision quality (A-F)
3. Extract pattern for future trades
4. Update "what works" database

### Weekly Review (Every Friday)
1. Aggregate all trades
2. Calculate sentiment prediction accuracy
3. Identify best/worst performing signals
4. Adjust strategy weights

### Monthly Deep Dive
1. Full P&L analysis
2. Compare vs buy-and-hold
3. Risk-adjusted returns
4. Strategy refinement

---

## Learning Categories

| Category | Triggers | Storage |
|----------|----------|---------|
| Sentiment Accuracy | Every exit | `sentiment_predictions` table |
| Trade Outcomes | Every trade | `trade_journal` table |
| Decision Patterns | User corrections | `learning_patterns` |
| Risk Management | Stop hits | `risk_events` |
| Market Regimes | Major moves | `market_context` |

---

## Improvement Loop

```
1. EXECUTE → Place trade based on current strategy
2. OBSERVE → Track price action, sentiment shifts
3. RECORD → Log outcome with full context
4. ANALYZE → What worked? What didn't?
5. ADAPT → Update strategy/rules
6. REPEAT → Apply learnings to next trade
```

---

## Success Metrics

- **Win Rate**: Target >55%
- **Risk/Reward**: Target 1:2 minimum
- **Sentiment Accuracy**: Track % of correct predictions
- **Max Drawdown**: Keep <10% of account
- **Alpha vs SPY**: Beat market consistently

---

*Framework active as of 2026-02-01*
