# SENTIMENT SOURCE TRACKING SYSTEM
## Active as of 2026-02-01

---

## 📊 TRACKED SOURCES

| Source | Priority | What We Track | Accuracy Score |
|--------|----------|---------------|----------------|
| **Trump Posts** | 🔴 CRITICAL | Truth Social, X mentions | TBD |
| **Bessent Posts** | 🟠 HIGH | X/Twitter, Policy statements | TBD |
| **WSB (Reddit)** | 🟠 HIGH | Daily trending, sentiment | TBD |
| **r/stocks** | 🟡 MEDIUM | Discussion quality | TBD |
| **r/investing** | 🟡 MEDIUM | Fundamental focus | TBD |
| **Twitter Analysts** | 🟠 HIGH | Verified accounts, price targets | TBD |
| **Twitter General** | 🟢 LOW | Noise, buzz | TBD |
| **News Headlines** | 🟡 MEDIUM | Bloomberg, CNBC, etc. | TBD |
| **Analyst Ratings** | 🟡 MEDIUM | Upgrades/downgrades | TBD |

---

## 🕐 SCAN SCHEDULE

| Time (PST) | Type | Focus |
|------------|------|-------|
| **6:30 AM** | Pre-Market | Trump overnight, order status, WSB |
| **10:00 AM** | Mid-Day | Positions, new tickers |
| **Every hour** | Trump Check | Any new posts mentioning stocks |
| **1:00 PM** | EOD | Full analysis, source accuracy grades |
| **2:00 PM** | Post-Market | Closed trade analysis, learning extraction |

---

## 🎯 PATTERN DETECTION

### What I Look For:

**Source Accuracy Patterns:**
- Which sources predict 1-day moves best?
- Which sources predict 1-week moves best?
- Does Trump accuracy vary by sector?
- Is WSB better for pumps or dumps?

**Market Condition Correlations:**
- Bull markets: Which sources work?
- Bear markets: Which sources work?
- High volatility: Trump impact amplified?

**Trump-Specific Patterns:**
- Direct ticker mentions = immediate move?
- Sector comments (tariffs, energy) = sector rotation?
- Time of post impact (pre-market vs intraday)?
- Follow-through or reversal next day?

---

## 📈 SCORING METHODOLOGY

### Per-Trade Grading:

**Entry Quality:** Did sources support entry?
- Grade: A (all sources aligned) → F (contradicted)

**Exit Quality:** Did sources predict exit timing?
- Grade: A (sources signaled reversal) → F (missed signals)

**Source-Specific Accuracy:**
```
For each source on each trade:
  Prediction: Bullish/Bearish/Neutral
  Actual: Price up/down/flat
  
  Match = +1 accuracy point
  Total predictions = denominator
  
Accuracy % = matches / total * 100
```

### Dynamic Weighting:
- Weekly recalculation of source weights
- >60% accuracy = increase weight
- <40% accuracy = decrease weight
- New sources start at 10% weight, prove themselves

---

## 🗄️ DATA STORAGE

**Database:** `data/trades.db`

**Tables:**
- `trades` — All trades with source sentiment scores
- `sentiment_accuracy` — Per-source prediction tracking
- `trump_posts` — All Trump mentions with impact analysis

**Files:**
- `trades/*.md` — Human-readable trade journal
- `SOURCE_TRACKING.md` — This file
- `SELF_IMPROVEMENT.md` — Learning framework

---

## 🚨 TRUMP ALERT PROTOCOL

**When Trump or Bessent mentions a stock:**
1. IMMEDIATE Telegram alert
2. Log post content + tickers
3. Check against watchlist
4. Assess sentiment (bullish/bearish)
5. Track price impact (1h, 1d, 1w)
6. Alert if actionable opportunity

**Bessent-specific tracking:**
- Dollar strength comments (gold impact)
- Treasury yield statements
- Fiscal policy hints
- Tariff/trade policy
- Gold/metals sector mentions

---

## 📋 CURRENT WATCHLIST

| Ticker | Sources Monitoring | Status |
|--------|-------------------|--------|
| NEM | All + Trump | Pending fill |
| ASTS | All + Trump | Pending fill |
| Gold miners | Reddit, Twitter, Analysts | Sector watch |
| Space stocks | WSB, Twitter | Sector watch |

---

## 🎯 SUCCESS METRICS

Track weekly:
- Overall sentiment prediction accuracy
- Per-source accuracy breakdown
- Trump mention hit rate
- WSB momentum prediction accuracy
- Best performing source combination

**Goal:** Identify the 2-3 most reliable sources and weight them highest.

---

*System active. Learning begins Monday.*
