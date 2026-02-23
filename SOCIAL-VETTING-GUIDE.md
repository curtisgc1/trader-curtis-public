# 🕵️ Social Source Vetting Quick Guide

## How It Works

1. **Log a call** when you see someone predict a stock
2. **Verify the outcome** when it hits target or stops out
3. **System auto-grades** the source based on accuracy
4. **Build your trusted list** over time

---

## Tier 1 Sources (Start Here)

### Reddit - Users
- **u/DeepFuckingValue** (r/wallstreetbets) - GME legend, fundamental analysis

### Reddit - Subreddits  
- **r/investing** - Fundamental focus, long-term
- **r/stocks** - More conservative than WSB
- **r/StockMarket** - News aggregation
- **r/options** - Options-specific discussion

### X/Twitter - Institutional
- **@OptionsHawk** - Options flow, institutional activity
- **@unusual_whales** - Congress/insider trades
- **@elerianm** - Mohamed El-Erian, economist at Allianz
- **@GoldmanSachs** - Investment bank research
- **@markets** - Bloomberg Markets (verified news)
- **@WSJ** - Wall Street Journal (verified news)

### X/Twitter - News
- **@CNBC** - Mainstream market news
- **@Benzinga** - Real-time news

### StockTwits - Verified
- **Benzinga** - News feed
- **YahooFinance** - Market data
- **MarketWatch** - Financial news

---

## Tier 2 (Verify Independently)

- **u/scanning4life** (Reddit) - Technical analysis
- **u/pdwp90** (Reddit) - Quant-style
- **@stocktalkweekly** (X) - Market commentary
- **@SpacGuru** (X) - SPAC-specific

---

## Tier 3 (Use Caution)

- **r/wallstreetbets** - Meme stocks, high noise
- **r/pennystocks** - High risk, pump potential
- **@MrZackMorris** - Penny stock pumps
- **@AtlasTrading** - Pump alerts
- **@jimcramer** - Inverse Cramer meme

---

## Logging a Call

```python
from social_vetter import log_social_call

# Log bullish call on AAPL from OptionsHawk
call_id = log_social_call(
    platform='x_twitter',
    source_name='OptionsHawk', 
    ticker='AAPL',
    call_type='bullish',
    content_snippet='Large call flow detected at $180 strike',
    price_at_call=175.50,
    target_price=185.00,
    timeframe='swing'
)
# Returns: call_id (save this!)
```

---

## Verifying Outcome

```python
from social_vetter import verify_call_outcome

# Call worked - AAPL hit $190
verify_call_outcome(
    call_id=1,  # use the ID from log_social_call
    outcome='correct',  # 'correct', 'wrong', or 'partial'
    price_at_outcome=190.00,
    pnl_pct=8.3  # percentage gain
)

# System auto-updates:
# - Source accuracy rate
# - Grade (A-F)
# - Status (TRUSTED/TESTING/AVOID)
```

---

## Status Meanings

| Status | Accuracy | Calls Needed | Action |
|--------|----------|--------------|--------|
| **TRUSTED** | >60% | 5+ | ✅ Use their calls |
| **TESTING** | 30-60% | <5 | ⚪ Evaluate more |
| **AVOID** | <30% | 5+ | ❌ Ignore them |

---

## Grading System

| Grade | Accuracy | Description |
|-------|----------|-------------|
| **A** | >70% | Elite, follow religiously |
| **B** | 60-70% | Reliable, strong consideration |
| **C** | 40-60% | Average, verify independently |
| **D** | 30-40% | Below average, use caution |
| **F** | <30% | Avoid, consistently wrong |

---

## Red Flags (Auto-detected)

Source gets AVOID status when:
- <30% accuracy after 5+ calls
- 3+ consecutive wrong calls
- Average loss > average win
- Pump-and-dump patterns detected

---

## Workflow Example

```
Monday:
→ See @OptionsHawk post about unusual AAPL calls
→ Log the call with log_social_call()
→ Save the call_id

Friday:
→ AAPL hit target or stopped out
→ Verify with verify_call_outcome()
→ System updates OptionsHawk's accuracy

After 10 calls:
→ OptionsHawk has 8 correct (80% accuracy)
→ System marks as TRUSTED, Grade A
→ Now you know to weight their calls heavily
```

---

## Command Reference

```bash
# View all vetted sources
cd /Users/Shared/curtis/trader-curtis && python3 social_vetter.py

# Check specific source
cd /Users/Shared/curtis/trader-curtis && sqlite3 data/trades.db "SELECT * FROM social_sources WHERE name='OptionsHawk'"

# View call history
cd /Users/Shared/curtis/trader-curtis && sqlite3 data/trades.db "SELECT * FROM social_calls ORDER BY call_date DESC LIMIT 10"

# Top performers
cd /Users/Shared/curtis/trader-curtis && sqlite3 data/trades.db "SELECT s.name, v.accuracy_rate, v.total_calls FROM social_sources s JOIN source_vetting_scores v ON s.id=v.source_id WHERE v.status='TRUSTED' ORDER BY v.accuracy_rate DESC"
```

---

*Last updated: 2026-02-15*
