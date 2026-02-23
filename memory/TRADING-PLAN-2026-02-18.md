# 🎯 OPTIMIZED TRADING RULES - February 17, 2026
*Strategic Compact & Optimize Output*

---

## 📊 UPDATED SOURCE WEIGHTS

### Current Source Grades (Post-Analysis)
| Source | Grade | Status | Weight | Rationale |
|--------|-------|--------|--------|-----------|
| reddit_wsb | F | TESTING | 0.00 | 0% accuracy on 3 signals - neutral consensus only |
| reddit_stocks | F | TESTING | 0.00 | 0% accuracy on 3 signals - neutral consensus only |
| twitter | F | TESTING | 0.00 | 0% accuracy on 3 signals - neutral consensus only |
| grok_ai | F | TESTING | 0.00 | 0% accuracy on 3 signals - neutral consensus only |
| trump_posts | F | TESTING | 0.00 | 0% accuracy on 3 signals - neutral consensus only |
| analyst_ratings | F | TESTING | 0.00 | 0% accuracy on 3 signals - neutral consensus only |

**Note:** All sources currently show 0% accuracy because:
1. All 3 completed trades had NEUTRAL sentiment across ALL sources
2. No source gave a directional signal (bullish >60 or bearish <30)
3. Sources were essentially "silent" - not wrong, just not signaling

### Source Weight Adjustment Strategy
- **Current:** Equal weights until proven otherwise
- **Target:** Dynamic weights based on 60%+ accuracy threshold
- **Minimum sample:** 5 calls per source before grade assignment

---

## 🚫 REFINED ENTRY/EXIT CRITERIA

### HARD ENTRY RULES (All Must Be Met)

1. **SENTIMENT CONSENSUS REQUIRED**
   - ❌ NO ENTRY if ALL sources score 40-60 (neutral)
   - ✅ REQUIRE: At least 2 sources with score >60 (bullish) OR <30 (bearish)
   - ✅ PREFER: 3+ sources in agreement

2. **MINIMUM SENTIMENT THRESHOLDS**
   | Signal Type | Minimum Score | Sources Required |
   |-------------|---------------|------------------|
   | STRONG BUY | >75 | 3+ sources |
   | BUY | >60 | 2+ sources |
   | NEUTRAL | 40-60 | **NO TRADE** |
   | SELL | <40 | 2+ sources |
   | STRONG SELL | <25 | 3+ sources |

3. **POLITICAL ALPHA INTEGRATION**
   - Trump/Bessent posts with score >=15 = CRITICAL ALERT
   - Tariff keywords → Check China exposure (MCHI, FXI, XLK)
   - Treasury/Yield keywords → Check TLT, TMF, financials
   - Wait 30 minutes after political post for market digest

4. **POSITION SIZING RULES**
   - Max 5% risk per trade (unchanged)
   - Max 20% in any single sector (unchanged)
   - Keep 20% cash minimum (unchanged)
   - **NEW:** Reduce size to 3% if only 2 sources agree

### EXIT RULES (Refined)

1. **STOP LOSS: -15% Hard Stop** (tightened from -20%)
   - 3 consecutive losses at -18% to -20% = adjust strategy
   - Trailing stop: 50% of gains after +10% move

2. **TAKE PROFIT: Tiered Exit**
   | Gain Level | Action |
   |------------|--------|
   | +15% | Sell 25% of position |
   | +25% | Sell 50% of position |
   | +35% | Sell 75% of position |
   | Remaining | Trail with 10% stop |

3. **TIME-BASED EXITS**
   - Swing trades: 5-10 day max hold unless trending
   - Re-evaluate at 3 days if no momentum

4. **SENTIMENT REVERSAL EXIT**
   - If sentiment drops from >60 to <40 on 2+ sources = consider exit
   - If political alpha shifts (new Trump/Bessent post) = re-evaluate

---

## ✅ CURRENT OPEN POSITIONS (Feb 17, 2026)

| Symbol | Entry | Shares | Position | Stop | Target | Status |
|--------|-------|--------|----------|------|--------|--------|
| SNDK | $85.50 | 5 | $427.50 | $72.67 (-15%) | $98.32 (+15%) | OPEN |
| META | $725.00 | 1 | $725.00 | $616.25 (-15%) | $833.75 (+15%) | OPEN |

**Entry Sentiment:** SNDK (85), META (90) - HIGH conviction entries
**Validating:** These trades will test if HIGH sentiment (>80) = winning trades
**Monitoring:** Daily sentiment scans at 6:30 AM and 2:00 PM PST

---

## 📈 TOMORROW'S TRADING PLAN

### Wednesday, February 18, 2026

**PRE-MARKET (6:30 AM PST)**
1. ✅ Run unified_social_scanner.py for all holdings
2. ✅ Check political_monitor_free.py for overnight posts
3. ✅ Review futures and overnight market action
4. ✅ Check if SNDK/META hit any alerts

**MARKET OPEN (9:30 AM PST)**
1. ⚠️ **NO TRADES** first 30 minutes (Rule R1)
2. Observe price action on open positions
3. Note any gap-ups or gap-downs on watchlist

**MID-DAY (12:00 PM PST)**
1. ✅ Political alpha check (Bessent/Trump posts)
2. ✅ Review any triggered alerts
3. ✅ Update stop losses if needed

**PRE-CLOSE (1:00 PM PST)**
1. ✅ Final political check before close
2. ✅ Log any trade decisions
3. ✅ Prepare EOD summary

**POST-MARKET (2:00 PM PST)**
1. ✅ Run sentiment_tracker.py (source accuracy update)
2. ✅ Run source_comparator.py (grade sources)
3. ✅ Run combo_analyzer.py (find best combinations)
4. ✅ Log trades if any closed

---

## 🎯 WATCHLIST FOR FEB 18

### Current Holdings (Monitor Closely)
- **SNDK** - Testing high-sentiment thesis (85 score)
- **META** - Testing high-sentiment thesis (90 score)
- **NEM** - Gold play, watch Trump/Bessent posts
- **AEM** - Gold play, watch Trump/Bessent posts
- **MARA** - Crypto exposure, BTC correlation

### Potential New Entries (Pending Sentiment)
- **XLK** - Tech sector ETF (watch China tariff news)
- **GLD** - Gold ETF (Trump/Bessent gold mentions)
- **TLT** - Treasuries (Bessent yield discussion)

### Sectors to Watch
- **Tech (XLK)** - China tariff exposure
- **Gold (GLD)** - Dollar/yield discussion from Bessent
- **Crypto (MARA, COIN)** - BTC momentum

---

## 🧠 KEY LEARNINGS (Archive to MEMORY)

### Pattern L1: NEUTRAL CONSENSUS = LOSING TRADE
- **Evidence:** 3/3 losing trades (MARA -18.5%, ASTS -20.6%, PLTR -20.0%)
- **Confidence:** VERY HIGH (100% of analyzed trades)
- **Action:** HARD BLOCK on auto-trade system

### Source Accuracy Status
- **Current:** All sources at 0% accuracy (neutral on all trades)
- **Interpretation:** Sources correctly stayed neutral (no signal = no edge)
- **Next:** Need winning trades with directional signals to grade sources

### Political Alpha Effectiveness
- **Status:** ACTIVE (3x daily monitoring)
- **Alerts:** 2 CRITICAL alerts on Feb 16 (Trump: 84, Bessent: 41)
- **Next:** Track if alerts predict next-day sector moves

---

## 📋 SYSTEM STATUS

| Component | Status | Last Run |
|-----------|--------|----------|
| Unified Social Scanner | ✅ Operational | Feb 17, 2:00 PM |
| Political Monitor | ✅ Operational | Feb 17, 1:00 PM |
| Sentiment Tracker | ✅ Operational | Feb 17, 11:32 PM |
| Source Comparator | ✅ Operational | Feb 17, 11:32 PM |
| Combo Analyzer | ✅ Operational | Feb 17, 11:32 PM |
| Trade Database | ✅ SQLite Active | Real-time |
| ClickHouse Archive | ⏸️ Local instance paused | Pending migration |

---

## 🎯 SUCCESS METRICS FOR NEXT WEEK

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Total Trades Analyzed | 10+ | 3 | 🟡 In Progress |
| Winning Trades | 5+ | 0 | 🔴 Pending |
| Source Accuracy >60% | 2+ sources | 0 | 🟡 Testing |
| Pattern Confidence | Statistical | Anecdotal | 🟡 Building |
| Open Position Closes | 2+ (SNDK/META) | 2 open | 🟡 Active |

---

## 📁 FILES GENERATED/UPDATED

- `memory/TRADING-PLAN-2026-02-18.md` - This file
- `memory/OPTIMIZED-RULES-2026-02-17.md` - Refined criteria
- `archive/trades/` - Exported trade data
- `archive/memory/` - Archived old analysis reports

---

*Generated: Tuesday, February 17, 2026 @ 11:32 PM PST*
*Next Optimization: After SNDK/META close or Feb 18 EOD*
