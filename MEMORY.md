# 🧠 Trader Curtis Long-Term Memory

## 📋 Index (~120 tokens to scan)

| ID | Icon | Category | Summary | ~Tok |
|----|------|----------|---------|------|
| T1 | 🟢 | Trade | AAPL swing trade entry $175 | 80 |
| R1 | 🔴 | Rule | Never trade first 30 min of market open | 60 |
| P1 | 🟣 | Pattern | Buying support on 50-day MA works well | 70 |
| P2 | 🟣 | Pattern | NEUTRAL sentiment = NO TRADE (30 trades, 100% losses) | 90 |
| P3 | 🟣 | Pattern | High sentiment (>80) = test in progress (SNDK, META) | 85 |
| L1 | 🔴 | Lesson | FOMO cost me on TSLA Nov 2025 | 90 |
| W1 | 🟡 | Watch | Crypto positions small % only | 50 |
| S1 | 🔵 | System | Sentiment tracking + political alpha integration | 150 |
| PA1 | 🟠 | Policy | Trump/Bessent monitoring for trading edge | 120 |
| PL1 | 🔵 | Pattern Learning | Continuous learning system active (Feb 17) | 100 |
| R2 | 🔴 | Rule | Require 2+ sources >70 for entry (Feb 21) | 70 |
| S2 | 🔵 | System | ClickHouse archive operational (Feb 18) | 60 |
| E1 | 🟢 | Execution | 30 trades archived, 0% win rate, -$53,179 loss | 80 |

## Trading Rules

### R1 | 🔴 Never trade first 30 minutes
- Let market settle, avoid volatility
- Exception: major news event with clear direction

### R2 | 🔴 Require 2+ source consensus (Feb 21 Update)
- Minimum 2 sources bullish (>70) or bearish (<30)
- Single source = insufficient edge
- 3+ sources = strong signal
- Neutral range 40-70 = NO TRADE

### Position Sizing
- Max 5% risk per trade
- Max 20% in any single sector
- Keep 20% cash minimum

### Stop Loss Rules
- Hard stop: -15% (tightened from -20%)
- Time stop: 5 days max hold
- Sentiment stop: 2+ sources flip direction

## Successful Patterns

### P1 | 🟣 50-day MA bounces
- Wait for price to test 50-day MA
- Look for reversal candle
- Enter on confirmation
- Stop below MA

### P2 | 🟣 NEUTRAL SENTIMENT = NO TRADE (Feb 21 Update)
**Confidence:** EXTREME (100% of 30 analyzed trades)
**Evidence:** ALL 30 losing trades had neutral consensus (50-65 range)
**Total Losses:** PLTR -$39,728, ASTS -$7,889, MARA -$5,561
**Rule:** When sentiment is 40-65, BLOCK the trade completely
**Requirement:** Need 2+ sources bullish (>70) for entry (raised from >60)

### P3 | 🟣 High Sentiment (>80) = Test in Progress (Feb 18)
**Status:** Testing hypothesis that HIGH sentiment scores predict winners
**Open Positions:** 
- SNDK (sentiment 85) - 3 sources bullish
- META (sentiment 90) - 3 sources bullish
**Validation:** Will confirm if >80 sentiment = winning trades

## Lessons Learned

### L1 | 🔴 FOMO on TSLA Nov 2025
- Chased break above $300
- Entered without plan
- Lost 15% in 2 days
- **Rule:** No entries after 10% move in 1 day

## Watchlist Strategy

### W1 | 🟡 Crypto small positions only
- Max 10% portfolio in crypto
- BTC and ETH only for now
- No leverage

## Sentiment & Source Tracking System

### S1 | 🔵 Complete sentiment infrastructure deployed - FULLY OPERATIONAL

**Unified Scanner:** `unified_social_scanner.py`
- **X/Twitter:** Grok API (real-time search)
- **Reddit:** WSB, r/stocks, r/investing (public API)
- **StockTwits:** Grok API sentiment analysis
- **Schedule:** 6:30 AM & 2:00 PM PST daily
- **API Keys Used:** XAI_API_KEY (Grok), BRAVE_API_KEY

**Supporting Components:**
- `source_outcome_logger.py` - Tracks which sources predicted correctly
- `combo_analyzer.py` - Finds best 2-6 source combinations
- `social_vetter.py` - Grades individual Reddit/X users (A-F)
- `sentiment_tracker.py` - Aggregates accuracy metrics

**Critical Rules Discovered:**
- **"NEUTRAL SENTIMENT = NO TRADE"** - All 3 losing trades had neutral signals from all 6 sources
- Only enter when 2+ sources agree (bullish >60 OR bearish <30)

**Daily Cron Schedule (2:00 PM PST):**
- 6:30 AM - Unified social scan (Grok + Reddit + StockTwits)
- 2:00 PM - Unified social scan
- 2:00 PM - Enhanced learning (log trades with sources)
- 2:05 PM - Sentiment tracker (aggregate accuracy)
- 2:10 PM - Source comparator (grade sources)
- 2:15 PM - Combo analyzer (find best combinations)

**Sources Currently Tracked:**
- reddit_wsb, reddit_investing, reddit_stocks
- x_twitter (via Grok API search)
- stocktwits (via Grok sentiment analysis)
- grok_ai, analyst_research
- **trump_truth_social** ← NEW (political alpha)
- **bessent_x** ← NEW (treasury policy)

### S2 | 🔵 ClickHouse Archive Operational (Feb 18, 2026)
**Status:** Migration complete, 18 trades archived
**Location:** ClickHouse `trader_curtis.trades`
**Total PnL:** -$20,335.86 (all losses)
**Win Rate:** 0%
**Update Schedule:** Daily compact at 11:30 PM PST

## Political Alpha Monitoring

### PA1 | 🟠 Trump/Bessent posts = trading edge - FREE VERSION DEPLOYED

**Method:** FREE (no $100/month X API cost)
- Grok web search (XAI_API_KEY)
- Brave News API (BRAVE_API_KEY)
- Reddit chatter detection

**Why Free Works:** Major political posts are covered by news/social within 1-5 minutes. Trump tariff tweets hit Bloomberg/Reuters/WSB instantly.

**How it works:**
1. Grok searches web for "Trump/Bessent + keywords" every 15 min
2. Brave searches financial news
3. Reddit scanner detects chatter
4. Calculates impact score (0-50)
5. CRITICAL alerts (>=15) sent to Telegram
6. Logs to sentiment system like any other source

**Keywords Tracked:**
- Tariffs (China, Mexico, Canada) → FXI, MCHI, XLI
- Treasury/Yields → TLT, TMF (inverse)
- Dollar strength/weakness → UUP, commodities
- Gold/Oil → GLD, USO, XLE
- Bitcoin/Crypto → BTC, MSTR, COIN

**Alert Thresholds:**
- CRITICAL (>=15): Immediate Telegram alert
- HIGH (10-14): Log + review
- MEDIUM (8-9): Log only

**Test Result (19:34 PST):**
- Trump: Score 84/50 🔥 CRITICAL (tariff, china, treasury keywords)
- Bessent: Score 35/50 🔥 CRITICAL (treasury, yield keywords)

**Schedule:** 3X daily aligned with market hours
- 6:30 AM PST - Pre-market (overnight developments)
- 12:00 PM PST - Mid-day check
- 1:00 PM PST - Close check (before 1 PM market close)

**Files:**
- `political_monitor_free.py` - Main scanner (FREE)
- `tasks/monitor-*.md` - Implementation tasks
- `POLITICAL_ALPHA_SETUP.md` - Full setup guide

## Pattern Learning System

### PL1 | 🔵 Continuous Learning Active (Feb 17, 2026)
**Status:** System operational, collecting data

**Current Learnings:**
- 1 losing pattern identified (neutral consensus)
- 0 winning patterns identified (need winning trades)
- 2 open trades tracking for validation (SNDK, META)

**Auto-Trade Criteria Refined:**
1. Neutral sentiment (40-60) = HARD NO
2. Require 2+ sources agreeing (>60 or <30)
3. Track all source predictions vs outcomes
4. Grade sources A-F based on accuracy

**Next Update:** After SNDK/META close or Feb 18 EOD
**Full Report:** `memory/PATTERN-LEARNING-2026-02-17.md`

## Execution Record

### E1 | 🟢 Trading Performance Summary (Through Feb 18, 2026)
**Total Trades:** 18
**Win Rate:** 0%
**Total PnL:** -$20,335.86
**Average Loss:** -19.7%

**By Ticker:**
- PLTR: 6 trades, -$13,503.68
- ASTS: 6 trades, -$4,733.40
- MARA: 6 trades, -$2,098.78

**Key Insight:** All losing trades had neutral sentiment signals. Sources correctly gave no signal - I took trades with zero edge.

**Open Positions:**
- SNDK: $85.50 entry, sentiment 85
- META: $725.00 entry, sentiment 90

These HIGH sentiment trades will validate the refined criteria.

---
*Format: Progressive Memory v0.1 | Last updated: February 18, 2026*
