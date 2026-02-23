# TRADER CURTIS - MASTER SKILL INTEGRATION
## Updated: 2026-02-02

---

## 🧠 **ALL SKILLS INSTALLED**

| Skill | Purpose | Trading Application |
|-------|---------|---------------------|
| **clickhouse-io** | Analytics database | Store/analyze millions of trades |
| **eval-harness** | Testing framework | Validate strategies before deployment |
| **git-notes-memory** | Structured memory | Trade journal, decisions, learnings |
| **continuous-learning** | Pattern extraction | Auto-learn from wins/losses |
| **backend-patterns** | API design | Build trading APIs |
| **coding-standards** | Code quality | Clean, maintainable trading tools |
| **security-review** | Security checklist | Protect API keys, trading data |
| **tdd-workflow** | Test-driven dev | Test strategies before risking money |
| **strategic-compact** | Context management | Optimize memory/token usage |
| **verification-loop** | Verification system | Double-check trade decisions |

---

## 🎯 **TRADING MASTERY SYSTEM**

### Phase 1: Data Infrastructure (clickhouse-io)
```sql
-- Trade database schema
CREATE TABLE trade_performance (
    timestamp DateTime64(3),
    trade_id String,
    ticker String,
    entry_price Float64,
    exit_price Float64,
    position_size Float64,
    pnl Float64,
    pnl_percent Float64,
    sentiment_reddit Int8,
    sentiment_twitter Int8,
    source_accuracy Float64,
    decision_grade String,
    lesson_learned String
) ENGINE = MergeTree()
ORDER BY (timestamp, ticker)
```

### Phase 2: Strategy Validation (eval-harness + tdd-workflow)
```
[CAPABILITY EVAL: sentiment-accuracy]
Test: Does WSB sentiment predict 3-day moves?
Data: Last 100 WSB mentions vs actual price action
Success: >60% accuracy rate
```

### Phase 3: Security (security-review)
- API keys in environment only
- No hardcoded credentials
- Trading authorization logged
- Position limits enforced

### Phase 4: Memory & Learning (git-notes-memory + continuous-learning)
- Every trade logged with context
- Auto-extract patterns from outcomes
- Build "what works" database

### Phase 5: Optimization (strategic-compact)
- Run skill analysis once daily (10 PM)
- Compact context periodically
- Minimize token usage

---

## ⏰ **DAILY SCHEDULE (Optimized)**

| Time (PST) | Task | Tokens Used |
|------------|------|-------------|
| **6:30 AM** | Quick sentiment scan (no skills) | Low |
| **10:00 AM** | Mid-day check (no skills) | Low |
| **1:00 PM** | EOD summary (no skills) | Low |
| **10:00 PM** | **FULL SKILL ANALYSIS** | Higher |

**Nightly Skill Run (10 PM):**
1. ClickHouse analytics query
2. Eval harness - test predictions
3. Continuous learning - extract patterns
4. Git notes - sync memories
5. Strategic compact - optimize

---

## 🤖 **AUTO-IMPROVEMENT LOOP**

```
1. TRADE (during market hours)
   ↓
2. LOG (immediate)
   ↓
3. ANALYZE (10 PM skill run)
   - ClickHouse queries
   - Eval harness tests
   - Pattern extraction
   ↓
4. LEARN (auto-update strategy)
   - Which sources work?
   - What setups win?
   - Adjust weights
   ↓
5. IMPROVE (next day)
   - Better predictions
   - Refined strategy
```

---

## 🔒 **SECURITY CHECKLIST (Per Trade)**

- [ ] Position size ≤ $500
- [ ] Stop loss defined
- [ ] Risk ≤ 2% account
- [ ] API credentials secure
- [ ] Trade logged
- [ ] Source tracked

---

## 📊 **SUCCESS METRICS TRACKED**

| Metric | Target | Measured By |
|--------|--------|-------------|
| Win Rate | >55% | ClickHouse query |
| Sentiment Accuracy | >60% | Eval harness |
| Risk/Reward | 1:2+ | Trade log |
| Max Drawdown | <10% | Portfolio tracking |
| Source Prediction | Grade A-F | Nightly analysis |

---

*All skills integrated. Nightly optimization active. Trading mastery in progress.*
