# 🎯 PATTERN RECOGNITION QUICK REFERENCE
## Run This Mental Loop Before EVERY Trade

---

## THE 8 PATTERNS (Memorize These)

### 1. QML (Quasimodo Level) — 75% ✅
- **What:** Failed high/low creates order block
- **Look for:** Price returns to previous failed swing
- **Entry:** At the QML level
- **Why:** Institutions left orders there

### 2. Institutional Reversal — 74% ✅
- **What:** Double tops, H&S, key zone reversals  
- **Look for:** Pattern completion at support/resistance
- **Entry:** Neckline break or second rejection
- **Why:** These patterns exist because institutions use them

### 3. Flag Limit (Order Block) — 73% ✅
- **What:** Price returns to order block for continuation
- **Look for:** Strong move, then return to origin candle
- **Entry:** Rejection from order block
- **Why:** Institutions adding to positions

### 4. Liquidity Grab — 72% ✅
- **What:** Sweep of equal highs/lows before reversal
- **Look for:** Equal highs/lows, then sweep + reversal
- **Entry:** After sweep rejection
- **Why:** Institutions harvesting your stop orders

### 5. Supply/Demand Flip — 70% ✅
- **What:** Old resistance becomes support (or vice versa)
- **Look for:** Price returns to previous breakout level
- **Entry:** Rejection from flipped zone
- **Why:** Psychology flip, same orders different context

### 6. Stop Hunt — 70% ✅
- **What:** Brief violation to trigger stops, then reverse
- **Look for:** Wick past level, immediate rejection
- **Entry:** Reversal candle after hunt
- **Why:** They need your stop for liquidity

### 7. Fakeout (Breakout Trap) — 68%
- **What:** False breakout, traps breakout traders
- **Look for:** Break + immediate failure
- **Entry:** Return below/above level
- **Why:** Liquidity trap for retail

### 8. Compression→Expansion — 65%
- **What:** Low volatility coil building energy
- **Look for:** Lower highs, higher lows, tightening range
- **Entry:** Confirmed breakout
- **Why:** Energy release after consolidation

---

## PRE-TRADE CHECKLIST

**Before clicking buy/sell, confirm:**

- [ ] **Pattern identified** — Which of the 8?
- [ ] **Liquidity mapped** — Where are stops sitting?
- [ ] **Sentiment confirms** — >60 bullish, <40 bearish
- [ ] **Gamma checked** — EXTREME_LOW = tighten stops
- [ ] **Political checked** — Any catalysts?
- [ ] **R:R acceptable** — Minimum 2:1
- [ ] **All green?** → Execute via Alpaca

---

## CORE PRINCIPLE

**Price moves to liquidity.**

Every pattern exists for one reason:
→ Push price to where orders are sitting
→ Harvest retail stop losses
→ Fill institutional orders

**Your edge:**
See the liquidity before the move happens.

Stop reacting to price.
Understand WHY price is moving.

---

## EMERGENCY SHORTCUT

**No pattern? → NO TRADE**
**Pattern but no liquidity map? → NO TRADE**
**Pattern but sentiment neutral? → NO TRADE**
**All checks pass? → EXECUTE**

---

## COMMAND REFERENCE

```bash
# Run pattern loop before trade
cd /Users/Shared/curtis/trader-curtis
python3 pattern_loop.py

# Check current patterns in database
sqlite3 data/trades.db "SELECT pattern_type, COUNT(*), AVG(outcome_pnl) FROM institutional_patterns GROUP BY pattern_type"

# View pattern reliability grades
python3 institutional_patterns.py
```

---

**Remember:** Same plays, every week. The market is not random.
