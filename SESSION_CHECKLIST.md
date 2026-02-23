# 🚨 TRADER CURTIS - SESSION START CHECKLIST

**MANDATORY:** Complete this checklist at the start of EVERY session.

---

## ✅ STEP 1: READ CORE FILES (5 minutes)

These files change rarely but contain CRITICAL context:

- [ ] **HEARTBEAT.md** - My daily schedule and trading rules
- [ ] **MEMORY.md** - Index of long-term memory (scan the table)
 [ ] **SYSTEM_ARCHITECTURE.md** - How everything connects
- [ ] **SOUL.md** - Who I am and my boundaries

**What to look for:**
- Trading rules (NEUTRAL = NO TRADE)
- Cron schedules (6:30 AM, 12:00 PM, 1:00 PM)
- Integration points (everything feeds into sentiment system)

---

## ✅ STEP 2: SYNC MEMORY (1 minute)

```bash
cd /Users/Shared/curtis/trader-curtis
python3 skills/git-notes-memory/memory.py -p . sync --start
```

**Why:** Ensures I have the latest lessons, facts, and decisions.

---

## ✅ STEP 3: CHECK DAILY CONTEXT (2 minutes)

**Read today's memory file:**
```bash
cat memory/$(date +%Y-%m-%d).md 2>/dev/null || echo "No entries today"
```

**Check recent alerts:**
```bash
ls -lt alerts/ | head -5
```

**Check positions:**
```bash
# If Alpaca API available
python3 check_account.py 2>/dev/null || echo "Check manually"
```

---

## ✅ STEP 4: VERIFY API KEYS (30 seconds)

```bash
echo "XAI_API_KEY: $([ -n \"$XAI_API_KEY\" ] && echo \"✅ Set\" || echo \"❌ Missing\")"
echo "BRAVE_API_KEY: $([ -n \"$BRAVE_API_KEY\" ] && echo \"✅ Set\" || echo \"❌ Missing\")"
echo "ALPACA_API_KEY: $([ -n \"$ALPACA_API_KEY\" ] && echo \"✅ Set\" || echo \"❌ Missing\")"
```

**Available keys:**
- XAI_API_KEY → Grok API (sentiment, political monitoring)
- BRAVE_API_KEY → News search
- ALPACA_API_KEY → Trading account

---

## ✅ STEP 5: KNOW THE HOLDINGS

**Current Holdings to Monitor:**
- NEM (Newmont - gold miner)
- ASTS (AST SpaceMobile)
- MARA (Marathon Digital - crypto)
- PLTR (Palantir)
- AEM (Agnico Eagle - gold miner)

**Why this matters:** Sentiment scans focus on these tickers.

---

## ✅ STEP 6: CRITICAL RULES (MEMORIZE)

| Rule | Consequence if Forgot |
|------|----------------------|
| **NEUTRAL sentiment = NO TRADE** | Lost 18-20% on MARA/PLTR/ASTS |
| **Only enter when 2+ sources agree** | Single source = risky |
| **Political feeds INTO sentiment** | Built standalone initially |
| **Follow HEARTBEAT.md schedule** | Wrong cron timing |
| **Max 5% risk per trade** | Curtis's rule |

---

## ✅ STEP 7: WHAT EXISTS (DON'T REBUILD)

**Before building anything new, check:**

| Component | File | Status |
|-----------|------|--------|
| Sentiment Scanner | unified_social_scanner.py | ✅ Active |
| Political Monitor | political_monitor_free.py | ✅ Active |
| Reddit Scanner | reddit-scanner.js | ✅ Active |
| Learning Engine | learning_engine.py | ✅ Active |
| Source Tracking | source_outcome_logger.py | ✅ Active |
| Combo Analyzer | combo_analyzer.py | ✅ Active |
| Social Vetter | social_vetter.py | ✅ Active |
| Git Notes | skills/git-notes-memory/ | ✅ Active |

**If it exists, INTEGRATE don't DUPLICATE.**

---

## ✅ STEP 8: CURRENT SCHEDULE (KNOW THIS)

| Time (PST) | Activity |
|------------|----------|
| 6:30 AM | Political scan + Sentiment scan |
| 9:30 AM | Market opens |
| 12:00 PM | Political check + Sentiment check |
| 1:00 PM | Close check + EOD summary |
| 2:00 PM | Learning engine + Source grading |

**NOT every 15 minutes.** Key trading moments only.

---

## ✅ STEP 9: QUICK SYSTEM TEST

```bash
# Test 1: Can I read the database?
sqlite3 data/trades.db ".tables" 2>/dev/null && echo "✅ Database OK" || echo "❌ DB issue"

# Test 2: Can I run Reddit scanner?
node reddit-scanner.js 2>&1 | head -3 && echo "✅ Reddit OK" || echo "❌ Reddit issue"

# Test 3: Can I access Grok?
python3 -c "import os; print('✅ Grok ready' if os.getenv('XAI_API_KEY') else '❌ No key')"
```

---

## ✅ STEP 10: COMMIT TO MEMORY

**Before doing ANY work, ask:**

1. Does this already exist? (Check STEP 7)
2. Does it integrate with sentiment system?
3. Does it follow HEARTBEAT.md schedule?
4. Am I using available API keys?
5. Will this be logged to git notes memory?

**If NO to any → STOP and reconsider.**

---

## 📝 AUDIT LOG

**Last Audit:** 2026-02-16 19:45 PST  
**Audited By:** Claude Code (Trader Curtis)  
**Status:** ✅ All systems operational  
**Issues Found:** Schedule alignment fixed  

**Next Audit:** Tomorrow 6:30 AM PST (pre-market)

---

## 🚨 REMEMBER

> "Memory is not a place you visit. It's a practice you maintain."

Every session I must:
1. **Read** the core files
2. **Sync** git notes memory
3. **Check** today's context
4. **Verify** I know what exists
5. **Integrate** don't duplicate
6. **Log** everything for next time

**If I skip these steps, I WILL forget critical information.**

---

*This checklist prevents the cycle of forgetting.*
