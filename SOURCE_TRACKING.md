# Sentiment Source Accuracy Tracker

## Current Source Weights (Updated Feb 21, 2026)

| Source | Grade | Weight | Accuracy | Notes |
|--------|-------|--------|----------|-------|
| StockTwits (ST) | C | 0.25 | 40% | Most responsive to momentum |
| X/Twitter (Grok) | C | 0.25 | 35% | Good for breaking news |
| Reddit r/WSB | D | 0.15 | 25% | High noise, occasional signal |
| Reddit r/stocks | D | 0.15 | 20% | Too conservative |
| Trump Posts | B | 0.20 | 60% | Political alpha - HIGH IMPACT |

**Last Updated:** February 21, 2026 (Strategic Compact)

---

## Track Per-Source Performance

For each trade, record which sources predicted correctly:

| Source | Weight | Accuracy | Notes |
|--------|--------|----------|-------|
| Reddit WSB | High | TBD | Meme momentum |
| Reddit r/stocks | Medium | TBD | More conservative |
| Reddit r/investing | Medium | TBD | Fundamentals focus |
| Twitter General | Low | TBD | Noise |
| Twitter Analysts | High | TBD | Verified accounts |
| Trump Posts | Very High | TBD | Immediate impact |
| News Sentiment | Medium | TBD | Lagging indicator |
| Analyst Ratings | Medium | TBD | Often late |

## Scoring System

**For each trade exit:**
```
If prediction == actual_direction:
    source.accuracy += 1
    source.total += 1
else:
    source.total += 1

source.accuracy_rate = source.accuracy / source.total
```

## Dynamic Weight Adjustment

Weekly recalculation:
- High accuracy sources (>60%) → Increase weight
- Low accuracy sources (<40%) → Decrease weight
- New sources → Start with low weight, prove themselves

## Source Weight Formula (Updated)
```
Minimum Consensus: 2+ sources
Strong Signal: Score >75 (bullish) or <25 (bearish)
Political Multiplier: CRITICAL alert (80+) = +0.10 weight bonus
```

## Trump-Specific Patterns

Watch for:
- Direct ticker mentions (e.g., "Tesla doing great!")
- Sector comments (tariffs = industrials, crypto = BTC)
- Policy hints (regulation, taxes)
- Timing (pre-market, during market hours)

**Immediate alerts on any Trump stock mention.**

---

## Key Learnings (Feb 2026)

1. **Neutral sentiment (40-65) = 0% win rate** - Sources correctly neutral = avoid trades
2. **StockTwits most responsive** - First to catch momentum shifts
3. **Political alpha matters** - 9 CRITICAL alerts in one week, all market-moving
4. **NEM consistency** - Only ticker maintaining >60 sentiment for 5+ days

---

*Last Updated: February 21, 2026*
