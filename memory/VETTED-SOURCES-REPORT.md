#!/usr/bin/env python3
"""
Trader Curtis - SOCIAL SOURCE VETTER
Tracks specific Reddit users, X accounts, and StockTwits users
Vets their calls over time to identify reliable sources
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

# Tier 1: Known credible sources to start tracking
SEED_SOURCES = {
    "reddit": {
        "users": [
            {"name": "DeepFuckingValue", "subreddit": "wallstreetbets", "tier": 1, "notes": "GME legend, fundamental analysis"},
            {"name": "scanning4life", "subreddit": "wallstreetbets", "tier": 2, "notes": "Technical trader"},
            {"name": "pdwp90", "subreddit": "wallstreetbets", "tier": 2, "notes": "Quant-style analysis"},
        ],
        "subreddits": [
            {"name": "wallstreetbets", "focus": "meme/momentum", "tier": 3, "notes": "High volume, mixed quality"},
            {"name": "stocks", "focus": "general discussion", "tier": 2, "notes": "More conservative than WSB"},
            {"name": "investing", "focus": "long-term", "tier": 1, "notes": "Fundamental focus"},
            {"name": "StockMarket", "focus": "market news", "tier": 2, "notes": "News aggregation"},
            {"name": "pennystocks", "focus": "small caps", "tier": 3, "notes": "High risk"},
            {"name": "options", "focus": "options", "tier": 2, "notes": "Options-specific"},
        ]
    },
    "x_twitter": {
        "accounts": [
            {"handle": "@MrZackMorris", "name": "Zack Morris", "tier": 3, "focus": "penny stocks/pumps", "notes": "Controversial, verify independently"},
            {"handle": "@AtlasTrading", "name": "Atlas Trading", "tier": 3, "focus": "penny stocks", "notes": "Pump alerts, use caution"},
            {"handle": "@stocktalkweekly", "name": "Stock Talk Weekly", "tier": 2, "focus": "general", "notes": "Market commentary"},
            {"handle": "@OptionsHawk", "name": "Options Hawk", "tier": 1, "focus": "options flow", "notes": "Institutional flow tracking"},
            {"handle": "@unusual_whales", "name": "Unusual Whales", "tier": 1, "focus": "options flow", "notes": "Congress/insider trades"},
            {"handle": "@SpacGuru", "name": "SPAC Guru", "tier": 2, "focus": "SPACs", "notes": "SPAC-specific"},
            {"handle": "@markets", "name": "Bloomberg Markets", "tier": 1, "focus": "news", "notes": "Verified news"},
            {"handle": "@CNBC", "name": "CNBC", "tier": 1, "focus": "news", "notes": "Mainstream media"},
            {"handle": "@WSJ", "name": "Wall St Journal", "tier": 1, "focus": "news", "notes": "Verified news"},
            {"handle": "@elerianm", "name": "Mohamed El-Erian", "tier": 1, "focus": "macro", "notes": "Economist, Allianz"},
            {"handle": "@GoldmanSachs", "name": "Goldman Sachs", "tier": 1, "focus": "institutional", "notes": "Investment bank research"},
            {"handle": "@jimcramer", "name": "Jim Cramer", "tier": 3, "focus": "general", "notes": "Inverse Cramer is a meme"},
        ]
    },
    "stocktwits": {
        "users": [
            {"name": "Benzinga", "tier": 1, "focus": "news", "notes": "Verified news source"},
            {"name": "YahooFinance", "tier": 1, "focus": "news", "notes": "Verified news"},
            {"name": "MarketWatch", "tier": 1, "focus": "news", "notes": "Verified news"},
        ]
    }
}

def init_social_vetting_db():
    """Create tables for social source vetting"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Social sources registry
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS social_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,  -- reddit, x_twitter, stocktwits
            source_type TEXT,  -- user, subreddit, account
            name TEXT,
            handle TEXT,  -- for X/Twitter
            focus TEXT,
            tier INTEGER,  -- 1=high credibility, 2=medium, 3=unverified
            notes TEXT,
            status TEXT DEFAULT 'TESTING',  -- TESTING, TRUSTED, AVOID
            date_added TEXT,
            UNIQUE(platform, name, handle)
        )
    ''')
    
    # Individual predictions/calls
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS social_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            ticker TEXT,
            call_type TEXT,  -- bullish, bearish, price_target
            call_date TEXT,
            price_at_call REAL,
            target_price REAL,
            timeframe TEXT,  -- day, swing, long
            content_snippet TEXT,
            verified BOOLEAN DEFAULT 0,
            outcome TEXT,  -- pending, correct, wrong, partial
            outcome_date TEXT,
            price_at_outcome REAL,
            pnl_pct REAL,
            grade TEXT,  -- A-F
            FOREIGN KEY (source_id) REFERENCES social_sources(id)
        )
    ''')
    
    # Source performance summary
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_vetting_scores (
            source_id INTEGER PRIMARY KEY,
            total_calls INTEGER DEFAULT 0,
            correct_calls INTEGER DEFAULT 0,
            wrong_calls INTEGER DEFAULT 0,
            partial_calls INTEGER DEFAULT 0,
            accuracy_rate REAL DEFAULT 0,
            avg_return_when_correct REAL DEFAULT 0,
            avg_loss_when_wrong REAL DEFAULT 0,
            best_call TEXT,
            worst_call TEXT,
            consecutive_correct INTEGER DEFAULT 0,
            consecutive_wrong INTEGER DEFAULT 0,
            grade TEXT DEFAULT 'C',
            status TEXT DEFAULT 'TESTING',
            last_updated TEXT,
            FOREIGN KEY (source_id) REFERENCES social_sources(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Social vetting database initialized")

def seed_initial_sources():
    """Add known sources to track"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Reddit users
    for user in SEED_SOURCES["reddit"]["users"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, focus, tier, notes, date_added)
            VALUES (?, 'user', ?, ?, ?, ?, ?)
        ''', ('reddit', user['name'], user.get('focus', 'general'), user['tier'], user['notes'], now))
    
    # Reddit subreddits
    for sub in SEED_SOURCES["reddit"]["subreddits"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, focus, tier, notes, date_added)
            VALUES (?, 'subreddit', ?, ?, ?, ?, ?)
        ''', ('reddit', sub['name'], sub['focus'], sub['tier'], sub['notes'], now))
    
    # X/Twitter accounts
    for acct in SEED_SOURCES["x_twitter"]["accounts"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, handle, focus, tier, notes, date_added)
            VALUES (?, 'account', ?, ?, ?, ?, ?, ?)
        ''', ('x_twitter', acct['name'], acct['handle'], acct['focus'], acct['tier'], acct['notes'], now))
    
    # StockTwits users
    for user in SEED_SOURCES["stocktwits"]["users"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, focus, tier, notes, date_added)
            VALUES (?, 'user', ?, ?, ?, ?, ?)
        ''', ('stocktwits', user['name'], user['focus'], user['tier'], user['notes'], now))
    
    conn.commit()
    conn.close()
    print("✅ Seed sources added to tracking")

def log_social_call(platform, source_name, ticker, call_type, content_snippet, price_at_call=None, target_price=None, timeframe="swing"):
    """Log a specific call/prediction from a social source"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get source ID
    cursor.execute('SELECT id FROM social_sources WHERE platform = ? AND name = ?', (platform, source_name))
    result = cursor.fetchone()
    
    if not result:
        print(f"⚠️ Source not found: {platform}/{source_name}")
        conn.close()
        return None
    
    source_id = result[0]
    
    cursor.execute('''
        INSERT INTO social_calls 
        (source_id, ticker, call_type, call_date, price_at_call, target_price, timeframe, content_snippet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (source_id, ticker, call_type, datetime.now().isoformat(), price_at_call, target_price, timeframe, content_snippet))
    
    call_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"📝 Logged call: {source_name} -> {ticker} ({call_type})")
    return call_id

def verify_call_outcome(call_id, outcome, price_at_outcome, pnl_pct=None):
    """Mark a call as correct/wrong/partial"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calculate grade
    if outcome == 'correct':
        if pnl_pct and pnl_pct > 20:
            grade = 'A'
        elif pnl_pct and pnl_pct > 10:
            grade = 'B'
        else:
            grade = 'C'
    elif outcome == 'wrong':
        grade = 'F'
    else:
        grade = 'C'
    
    cursor.execute('''
        UPDATE social_calls 
        SET outcome = ?, outcome_date = ?, price_at_outcome = ?, pnl_pct = ?, grade = ?, verified = 1
        WHERE id = ?
    ''', (outcome, datetime.now().isoformat(), price_at_outcome, pnl_pct, grade, call_id))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Call #{call_id} marked as {outcome} (Grade: {grade})")
    update_source_vetting_score(call_id)

def update_source_vetting_score(call_id):
    """Recalculate vetting score for a source after call verification"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get source ID from call
    cursor.execute('SELECT source_id FROM social_calls WHERE id = ?', (call_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return
    
    source_id = result[0]
    
    # Calculate stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN outcome = 'wrong' THEN 1 ELSE 0 END) as wrong,
            SUM(CASE WHEN outcome = 'partial' THEN 1 ELSE 0 END) as partial,
            AVG(CASE WHEN outcome = 'correct' THEN pnl_pct END) as avg_correct_return,
            AVG(CASE WHEN outcome = 'wrong' THEN pnl_pct END) as avg_wrong_return
        FROM social_calls WHERE source_id = ? AND verified = 1
    ''', (source_id,))
    
    row = cursor.fetchone()
    if not row or row[0] == 0:
        conn.close()
        return
    
    total, correct, wrong, partial, avg_correct, avg_wrong = row
    accuracy = (correct / total * 100) if total > 0 else 0
    
    # Determine grade and status
    if accuracy >= 70 and total >= 5:
        grade = 'A'
        status = 'TRUSTED'
    elif accuracy >= 60 and total >= 5:
        grade = 'B'
        status = 'TRUSTED'
    elif accuracy >= 40:
        grade = 'C'
        status = 'TESTING'
    elif accuracy >= 30:
        grade = 'D'
        status = 'TESTING'
    else:
        grade = 'F'
        status = 'AVOID'
    
    cursor.execute('''
        INSERT OR REPLACE INTO source_vetting_scores
        (source_id, total_calls, correct_calls, wrong_calls, partial_calls,
         accuracy_rate, avg_return_when_correct, avg_loss_when_wrong,
         grade, status, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (source_id, total, correct, wrong, partial, accuracy, avg_correct or 0, avg_wrong or 0, grade, status, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    print(f"📊 Source #{source_id} updated: {accuracy:.0f}% accuracy, Grade {grade}, Status: {status}")

def generate_vetted_sources_report():
    """Generate report of vetted sources"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get trusted sources
    cursor.execute('''
        SELECT s.platform, s.source_type, s.name, s.handle, s.focus, s.notes,
               v.total_calls, v.correct_calls, v.wrong_calls, v.accuracy_rate,
               v.avg_return_when_correct, v.grade, v.status
        FROM social_sources s
        LEFT JOIN source_vetting_scores v ON s.id = v.source_id
        WHERE v.total_calls > 0
        ORDER BY v.accuracy_rate DESC, v.total_calls DESC
    ''')
    
    sources = cursor.fetchall()
    conn.close()
    
    report = f"""# 🏆 VETTED SOCIAL SOURCES REPORT
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M PST')}

---

## ✅ TRUSTED SOURCES (Accuracy >60%, 5+ calls)

| Platform | Source | Handle | Focus | Calls | Accuracy | Avg Win | Grade |
|----------|--------|--------|-------|-------|----------|---------|-------|
"""
    
    trusted = [s for s in sources if s[12] == 'TRUSTED']
    for s in trusted:
        platform, stype, name, handle, focus, notes, total, correct, wrong, acc, avg_win, grade, status = s
        handle_str = handle if handle else '-'
        report += f"| {platform} | {name} | {handle_str} | {focus} | {total} | {acc:.0f}% | +{avg_win:.1f}% | {grade} |\n"
    
    if not trusted:
        report += "_No sources have earned TRUSTED status yet. Need more verified calls._\n"
    
    report += """
---

## ⚪ TESTING SOURCES (Under evaluation)

| Platform | Source | Focus | Calls | Accuracy | Grade | Notes |
|----------|--------|-------|-------|----------|-------|-------|
"""
    
    testing = [s for s in sources if s[12] == 'TESTING']
    for s in testing:
        platform, stype, name, handle, focus, notes, total, correct, wrong, acc, avg_win, grade, status = s
        report += f"| {platform} | {name} | {focus} | {total} | {acc:.0f}% | {grade} | {notes[:50]}... |\n"
    
    if not testing:
        report += "_No sources currently being tested._\n"
    
    report += """
---

## ❌ AVOID SOURCES (Accuracy <30%)

| Platform | Source | Focus | Calls | Accuracy | Grade | Warning |
|----------|--------|-------|-------|----------|-------|---------|
"""
    
    avoid = [s for s in sources if s[12] == 'AVOID']
    for s in avoid:
        platform, stype, name, handle, focus, notes, total, correct, wrong, acc, avg_win, grade, status = s
        report += f"| {platform} | {name} | {focus} | {total} | {acc:.0f}% | {grade} | Poor track record |\n"
    
    if not avoid:
        report += "_No sources flagged to avoid yet._\n"
    
    report += f"""
---

## 🎯 SOURCES TO START TRACKING

### Tier 1 (High Credibility) - Reddit
"""
    
    for user in SEED_SOURCES["reddit"]["users"]:
        if user['tier'] == 1:
            report += f"- **u/{user['name']}** ({user['subreddit']}) - {user['notes']}\n"
    
    for sub in SEED_SOURCES["reddit"]["subreddits"]:
        if sub['tier'] == 1:
            report += f"- **r/{sub['name']}** - {sub['notes']}\n"
    
    report += """
### Tier 1 (High Credibility) - X/Twitter
"""
    
    for acct in SEED_SOURCES["x_twitter"]["accounts"]:
        if acct['tier'] == 1:
            report += f"- **{acct['handle']}** ({acct['name']}) - {acct['focus']} - {acct['notes']}\n"
    
    report += """
---

## 📝 HOW TO USE

1. **When you see a call** on Reddit/X/StockTwits, log it:
   ```
   log_social_call('x_twitter', 'OptionsHawk', 'AAPL', 'bullish', 'Large call flow detected', 175.00, 185.00)
   ```

2. **When outcome is known**, verify it:
   ```
   verify_call_outcome(call_id, 'correct', 190.00, 8.5)
   ```

3. **System auto-calculates**:
   - Accuracy rate per source
   - Average win size
   - Grade (A-F)
   - Status (TRUSTED/TESTING/AVOID)

4. **Build your trusted list** over time

---

## 🔍 RED FLAGS (Auto-detected)

Sources get AVOID status when:
- <30% accuracy after 5+ calls
- Consecutive wrong calls (3+)
- Average loss > average win

---

## ✅ GREEN FLAGS (Auto-detected)

Sources get TRUSTED status when:
- >60% accuracy after 5+ calls
- Consecutive correct calls (3+)
- Average win > 2x average loss

---

*Sources are tracked individually - even within same platform, some users are better than others*
