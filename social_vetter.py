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
            platform TEXT,
            source_type TEXT,
            name TEXT,
            handle TEXT,
            focus TEXT,
            tier INTEGER,
            notes TEXT,
            status TEXT DEFAULT 'TESTING',
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
            call_type TEXT,
            call_date TEXT,
            price_at_call REAL,
            target_price REAL,
            timeframe TEXT,
            content_snippet TEXT,
            verified BOOLEAN DEFAULT 0,
            outcome TEXT,
            outcome_date TEXT,
            price_at_outcome REAL,
            pnl_pct REAL,
            grade TEXT,
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
    
    for user in SEED_SOURCES["reddit"]["users"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, focus, tier, notes, date_added)
            VALUES (?, 'user', ?, ?, ?, ?, ?)
        ''', ('reddit', user['name'], user.get('focus', 'general'), user['tier'], user['notes'], now))
    
    for sub in SEED_SOURCES["reddit"]["subreddits"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, focus, tier, notes, date_added)
            VALUES (?, 'subreddit', ?, ?, ?, ?, ?)
        ''', ('reddit', sub['name'], sub['focus'], sub['tier'], sub['notes'], now))
    
    for acct in SEED_SOURCES["x_twitter"]["accounts"]:
        cursor.execute('''
            INSERT OR IGNORE INTO social_sources 
            (platform, source_type, name, handle, focus, tier, notes, date_added)
            VALUES (?, 'account', ?, ?, ?, ?, ?, ?)
        ''', ('x_twitter', acct['name'], acct['handle'], acct['focus'], acct['tier'], acct['notes'], now))
    
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
    
    if outcome == 'correct':
        grade = 'A' if (pnl_pct and pnl_pct > 20) else ('B' if (pnl_pct and pnl_pct > 10) else 'C')
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
    
    cursor.execute('SELECT source_id FROM social_calls WHERE id = ?', (call_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return
    
    source_id = result[0]
    
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
    
    if accuracy >= 70 and total >= 5:
        grade, status = 'A', 'TRUSTED'
    elif accuracy >= 60 and total >= 5:
        grade, status = 'B', 'TRUSTED'
    elif accuracy >= 40:
        grade, status = 'C', 'TESTING'
    elif accuracy >= 30:
        grade, status = 'D', 'TESTING'
    else:
        grade, status = 'F', 'AVOID'
    
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

def get_vetted_sources(status=None, min_accuracy=0):
    """Get list of vetted sources"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = '''
        SELECT s.platform, s.name, s.handle, s.focus, s.tier,
               v.total_calls, v.correct_calls, v.accuracy_rate, v.grade, v.status
        FROM social_sources s
        LEFT JOIN source_vetting_scores v ON s.id = v.source_id
        WHERE 1=1
    '''
    params = []
    
    if status:
        query += ' AND v.status = ?'
        params.append(status)
    if min_accuracy > 0:
        query += ' AND v.accuracy_rate >= ?'
        params.append(min_accuracy)
    
    query += ' ORDER BY v.accuracy_rate DESC, s.tier ASC'
    
    cursor.execute(query, params)
    sources = cursor.fetchall()
    conn.close()
    
    return sources

def show_vetted_summary():
    """Display summary of vetted sources"""
    print("\n" + "=" * 70)
    print("🏆 VETTED SOCIAL SOURCES")
    print("=" * 70)
    
    trusted = get_vetted_sources(status='TRUSTED')
    testing = get_vetted_sources(status='TESTING')
    avoid = get_vetted_sources(status='AVOID')
    
    print(f"\n✅ TRUSTED ({len(trusted)} sources):")
    for s in trusted:
        platform, name, handle, focus, tier, total, correct, acc, grade, status = s
        handle_str = f" ({handle})" if handle else ""
        print(f"  • {platform}/{name}{handle_str} - {acc:.0f}% accuracy ({correct}/{total})")
    
    print(f"\n⚪ TESTING ({len(testing)} sources):")
    for s in testing:
        platform, name, handle, focus, tier, total, correct, acc, grade, status = s
        handle_str = f" ({handle})" if handle else ""
        print(f"  • {platform}/{name}{handle_str} - {acc:.0f}% accuracy ({correct}/{total})")
    
    print(f"\n❌ AVOID ({len(avoid)} sources):")
    for s in avoid:
        platform, name, handle, focus, tier, total, correct, acc, grade, status = s
        handle_str = f" ({handle})" if handle else ""
        print(f"  • {platform}/{name}{handle_str} - {acc:.0f}% accuracy ({correct}/{total})")
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    print("=" * 70)
    print("🕵️ SOCIAL SOURCE VETTER")
    print("=" * 70)
    
    init_social_vetting_db()
    seed_initial_sources()
    show_vetted_summary()
    
    print("\n📚 Sources seeded and ready to track!")
    print("\nTo log a call:")
    print("  log_social_call('x_twitter', 'OptionsHawk', 'AAPL', 'bullish', 'Large call flow', 175.00)")
    print("\nTo verify outcome:")
    print("  verify_call_outcome(call_id, 'correct', 190.00, 8.5)")
