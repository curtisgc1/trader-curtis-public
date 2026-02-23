---
status: open
priority: high
owner: trader-curtis
project: policy-trade-intel
due: '2026-02-17'
tags:
  - bessent
  - treasury
  - yields
  - free-method
  - grok-search
  - no-api-cost
created: '2026-02-17T01:52:43.949Z'
updated: '2026-02-17T19:34:00.000Z'
---
# Monitor Sec Bessent X/Twitter - Treasury Policy

## Objective
Monitor Treasury Secretary statements affecting yields, dollar, and bonds **WITHOUT** API costs.

## ✅ FREE METHOD DEPLOYED

Same approach as Trump monitoring:
1. **Grok web search** - Searches for Bessent statements
2. **Brave News API** - Treasury news coverage
3. **Reddit chatter** - r/investing and r/stocks discussion

## Why Free Method Works for Bessent

Bessent (or any Treasury Secretary) statements on yields/dollar are:
- **Immediately newsworthy** → Bloomberg, Reuters, WSJ cover instantly
- **Market-moving** → Every trader reacts within minutes
- **Discussed everywhere** → Reddit, X, StockTwits all chatter

No need for direct X API when statements are syndicated across financial media.

## Implementation

**Script:** `political_monitor_free.py` (same as Trump)
- Searches for "Bessent treasury yield dollar statement"
- Checks news coverage
- Scores impact (treasury keywords = high weight)

**Keywords Tracked:**
- Treasury, yields, bonds, Fed
- Dollar strength/weakness
- Gold, commodities
- Inflation, recession

## Test Results (19:34 PST)
```
🔥 POLITICAL ALPHA ALERT - CRITICAL
Source: Bessent
Impact Score: 35/50
Keywords: treasury, yield, dollar, gold, crypto

Sources Checked:
- Grok web search: ✓ Found
- Brave news: ✓ Found
```

## Treasury-Specific Alerts

When Bessent mentions:
- **Yields up** → TLT↓, TMF↓, banks↑
- **Yields down** → TLT↑, TMF↑, REITs↑
- **Strong dollar** → UUP↑, exporters↓
- **Weak dollar** → Commodities↑, gold↑

## Cost: $0
Uses existing API keys:
- XAI_API_KEY (Grok)
- BRAVE_API_KEY (news)
- Reddit (free public API)

## Next Steps
- [ ] Verify Bessent actually becomes Treasury Secretary
- [ ] Add specific Bessent keywords
- [ ] Tune yield-related impact weights

## Related
- [[monitor-trump-truth-social-market-impact]]
- `political_monitor_free.py`
