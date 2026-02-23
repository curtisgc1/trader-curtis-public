# 🎯 Trader Curtis - Complete System Architecture

**Date:** 2026-02-16  
**Purpose:** Show how ALL components connect (so I never forget again)

---

## 🧠 Core Philosophy: Everything Connects

This isn't a collection of separate tools. It's an **integrated trading intelligence system** where every component feeds into every other component.

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES                             │
├─────────────────────────────────────────────────────────────┤
│  Reddit (WSB)    X/Twitter    Trump Posts    Bessent Posts  │
│  StockTwits      Analysts     Grok AI        News Feeds     │
└──────────┬──────────────────────┬──────────────────────────┘
           │                      │
           ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│              SENTIMENT COLLECTION LAYER                     │
│         (sentiment_auto_trade.py - 2X daily)               │
├─────────────────────────────────────────────────────────────┤
│  • Scans all sources                                        │
│  • Calculates sentiment scores (0-100)                      │
│  • Identifies affected tickers                              │
│  • Auto-adds stop losses                                    │
│  • Logs to sentiment-YYYY-MM-DD.md                          │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              SOURCE TRACKING DATABASE                       │
├─────────────────────────────────────────────────────────────┤
│  political_sentiment    ← Trump/Bessent posts               │
│  simple_source_outcomes ← All trade outcomes                │
│  source_performance     ← Individual source accuracy        │
│  combo_stats            ← Multi-source win rates            │
│  social_calls           ← Individual user predictions       │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              ANALYSIS LAYER (2:00 PM Daily)                 │
├─────────────────────────────────────────────────────────────┤
│  2:00 - enhanced_learning.py     → Log trades with sources  │
│  2:05 - sentiment_tracker.py     → Grade source accuracy    │
│  2:10 - source_comparator.py     → Compare to outcomes      │
│  2:15 - combo_analyzer.py        → Find best combinations   │
│  2:20 - social_vetter.py         → Grade individual users   │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              DECISION LAYER                                 │
├─────────────────────────────────────────────────────────────┤
│  Only trade when:                                           │
│  • 2+ sources agree (bullish >60 OR bearish <30)            │
│  • NOT when all sources neutral (40-60) ← LOSSES!           │
│  • Political posts = HIGH CONFIDENCE when specific          │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              LEARNING LAYER                                 │
├─────────────────────────────────────────────────────────────┤
│  learning_engine.py          → Grades trades A-F            │
│  source_outcome_logger.py    → Tracks prediction outcomes   │
│  Git notes memory            → Cross-session persistence    │
│  MEMORY.md                   → Human-readable lessons       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔗 Integration Points

### Political Monitoring → Sentiment System

**Before (WRONG):**
- Political monitor was standalone
- Separate alerts, separate database
- No connection to existing infrastructure

**After (CORRECT):**
- Political posts logged to `political_sentiment` table
- Same schema as other sources
- Graded by combo_analyzer.py
- Included in "2+ sources agree" rule

**Code Integration:**
```python
# In political_alpha_monitor.py
from sentiment_auto_trade import log_sentiment_source

# When Trump posts about China:
log_sentiment_source(
    source_name="Trump/TruthSocial",
    ticker="FXI",
    sentiment="bearish",
    confidence=85,
    note="China tariff keywords detected"
)

# Now FXI shows bearish signal from political source
# Combo analyzer includes this in calculations
```

### Sentiment → Trading Decisions

**The "NEUTRAL = NO TRADE" Rule:**
```
MARA: -18.5% loss
├─ reddit_wsb:      neutral
├─ x_twitter:       neutral
├─ trump_posts:     neutral
├─ grok_ai:         neutral
├─ analyst_rbc:     neutral
└─ stocktwits:      neutral
Result: ALL NEUTRAL → Should NOT have entered

PLTR: -20.0% loss
├─ All 6 sources:   neutral
Result: Same pattern = predictable failure
```

### All Sources → Combo Analysis

**combo_analyzer.py finds patterns:**
```
2-Source Combos (Hypothetical - need winning trades):
├─ reddit_wsb + grok_ai = 75% win rate (HOLD)
├─ trump_posts + analyst = 70% win rate (STRONG)
└─ x_twitter + stocktwits = 35% win rate (AVOID)

3-Source Combos:
├─ reddit + trump + analyst = 85% win rate (HIGH CONVICTION)
└─ All 6 sources = 50% win rate (too noisy)
```

---

## 📁 File Relationships

```
trader-curtis/
├── 📊 SENTIMENT SYSTEM
│   ├── sentiment_auto_trade.py      ← MASTER SCANNER (2X daily)
│   ├── sentiment_tracker.py         ← Grades accuracy
│   ├── source_comparator.py         ← Compares to outcomes
│   ├── combo_analyzer.py            ← Finds best combos
│   ├── social_vetter.py             ← Grades individual users
│   └── source_outcome_logger.py     ← Tracks predictions
│
├── 🏛️ POLITICAL MONITORING
│   ├── scripts/
│   │   └── political_alpha_monitor.py  ← INTEGRATED with sentiment
│   └── tasks/
│       ├── monitor-trump-truth-social-market-impact.md
│       ├── monitor-trump-xtwitter-market-impact.md
│       └── monitor-sec-bessent-xtwitter-treasury-policy.md
│
├── 🧠 LEARNING SYSTEM
│   ├── learning_engine.py           ← Grades trades A-F
│   ├── enhanced_learning.py         ← Processes with sources
│   └── skills/git-notes-memory/     ← Persistent memory
│
├── 💾 DATABASE
│   └── data/
│       └── trades.db                ← SQLite with all tables
│
├── 📝 MEMORY
│   ├── MEMORY.md                    ← Human-readable index
│   ├── memory/
│   │   ├── sentiment-YYYY-MM-DD.md  ← Daily scan logs
│   │   ├── COMBO-ANALYSIS-*.md      ← Combo reports
│   │   └── SOURCE-COMPARISON-*.md   ← Source accuracy
│   └── lessons/
│       └── *.json                   ← Machine-readable lessons
│
└── ⚙️ AUTOMATION
    └── HEARTBEAT.md                 ← My instructions every wake
```

---

## ⏰ Cron Schedule (Daily)

| Time | Script | Purpose |
|------|--------|---------|
| 6:30 AM | sentiment_auto_trade.py | Pre-market sentiment scan |
| 2:00 PM | sentiment_auto_trade.py | Mid-day sentiment scan |
| 2:00 PM | enhanced_learning.py | Log trades with sources |
| 2:05 PM | sentiment_tracker.py | Grade source accuracy |
| 2:10 PM | source_comparator.py | Compare to outcomes |
| 2:15 PM | combo_analyzer.py | Find best combinations |
| 2:20 PM | social_vetter.py | Grade individual users |
| 6:30 AM, 12:00 PM, 1:00 PM | political_monitor_free.py | Trump/Bessent posts |

---

## 🎯 Key Principles (DON'T FORGET)

### 1. Nothing is Standalone
Every new component must connect to existing infrastructure:
- Uses same database tables?
- Logs to same memory system?
- Analyzed by existing analyzers?
- Follows same rules?

### 2. Source Diversity Matters
- Single source = RISKY
- 2+ agreeing sources = TRADE
- All neutral = NO TRADE (proven by 3 losses)
- Political = high weight when specific

### 3. Everything Gets Graded
- Trades: A-F by learning_engine.py
- Sources: A-F by accuracy
- Combos: Win rate % by combo_analyzer.py
- Users: TRUSTED/TESTING/AVOID by social_vetter.py

### 4. Memory is Layered
- **Session memory** - Current context
- **Git notes** - Structured facts/lessons/decisions
- **MEMORY.md** - Human-readable index
- **Daily files** - Raw logs
- **Database** - Queryable data

---

## 🔧 When Adding New Features

**Checklist:**
- [ ] Does it use existing database tables?
- [ ] Does it log to existing memory systems?
- [ ] Does it integrate with sentiment tracking?
- [ ] Does it follow the "2+ sources" rule?
- [ ] Does it get graded/analyzed by existing tools?
- [ ] Is it added to cron schedule if periodic?
- [ ] Is it documented in MEMORY.md?

**Example: Adding Reddit r/options**
```python
# 1. Add to sentiment_auto_trade.py scanner
# 2. Log to existing source_outcomes table
# 3. Automatically analyzed by combo_analyzer.py
# 4. Graded by source_comparator.py
# 5. Appears in daily reports
# NO NEW INFRASTRUCTURE NEEDED
```

---

## 📊 Current System Status

| Component | Status | Last Run |
|-----------|--------|----------|
| Sentiment Scanner | ✅ Active | 2:00 PM today |
| Source Tracking | ✅ Active | 2:10 PM today |
| Combo Analysis | ✅ Active | 2:15 PM today |
| Social Vetting | ✅ Active | 2:20 PM today |
| Political Monitor | ⚠️ Needs API keys | N/A |
| Git Notes Memory | ✅ Active | Continuous |

---

## 🚨 Critical Reminders

1. **ALWAYS check existing systems first**
2. **NEVER build standalone when integration possible**
3. **Political monitoring feeds INTO sentiment, not separate**
4. **All sources graded together in combo analysis**
5. **NEUTRAL consensus = NO TRADE (proven by losses)**

---

*This document exists so I NEVER forget how everything connects again.*
