#!/usr/bin/env python3
"""
Trader Curtis - SOURCE-OUTCOME LOGGER
Logs which sources predicted what, and what actually happened
Enables identification of superior sources and combinations
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"
SOURCE_LOG_PATH = SCRIPT_DIR / "data" / "source_outcomes.jsonl"

def init_source_outcome_db():
    """Initialize database for source-outcome tracking"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Detailed source-outcome tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            trade_grade TEXT,
            
            -- Individual source predictions (0-100 scores)
            reddit_wsb_score INTEGER,
            reddit_stocks_score INTEGER,
            reddit_investing_score INTEGER,
            twitter_score INTEGER,
            twitter_analysts_score INTEGER,
            stocktwits_score INTEGER,
            grok_ai_score INTEGER,
            grok_confidence INTEGER,
            trump_sentiment INTEGER,
            analyst_consensus INTEGER,
            
            -- Source predictions (bullish/bearish/neutral)
            reddit_wsb_pred TEXT,
            reddit_stocks_pred TEXT,
            twitter_pred TEXT,
            grok_ai_pred TEXT,
            trump_pred TEXT,
            analyst_pred TEXT,
            
            -- Which sources were bullish/bearish
            bullish_sources TEXT,  -- JSON array
            bearish_sources TEXT,  -- JSON array
            neutral_sources TEXT,  -- JSON array
            
            -- Outcome analysis
            outcome TEXT,  -- 'win' or 'loss'
            correct_predictions TEXT,  -- JSON array of sources that got it right
            wrong_predictions TEXT,    -- JSON array of sources that got it wrong
            
            -- Combo analysis
            combo_used TEXT,  -- Which sources agreed (e.g., "reddit_wsb+grok_ai")
            combo_correct BOOLEAN,
            
            created_at TEXT
        )
    ''')
    
    # Source performance summary
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_leaderboard (
            source TEXT PRIMARY KEY,
            total_trades INTEGER DEFAULT 0,
            wins_when_bullish INTEGER DEFAULT 0,
            losses_when_bullish INTEGER DEFAULT 0,
            wins_when_bearish INTEGER DEFAULT 0,
            losses_when_bearish INTEGER DEFAULT 0,
            neutral_calls INTEGER DEFAULT 0,
            accuracy_rate REAL DEFAULT 0.0,
            avg_pnl_when_followed REAL DEFAULT 0.0,
            combo_performance TEXT,  -- JSON of best/worst combos
            last_updated TEXT
        )
    ''')
    
    # Combo performance tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS combo_performance (
            combo TEXT PRIMARY KEY,
            sources TEXT,  -- JSON array of sources in combo
            total_uses INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            avg_pnl REAL DEFAULT 0.0,
            grade TEXT,
            last_updated TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Source-outcome database initialized")

def log_source_outcome(trade_data, source_data):
    """Log a complete trade with all source predictions"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Determine outcome
    outcome = 'win' if trade_data['pnl'] > 0 else 'loss'
    
    # Categorize sources by prediction
    bullish = []
    bearish = []
    neutral = []
    correct = []
    wrong = []
    
    for source, data in source_data.items():
        score = data.get('score', 50)
        pred = data.get('prediction', 'neutral')
        
        if score > 60:
            bullish.append(source)
            # Check if prediction was correct
            if trade_data['pnl'] > 0:
                correct.append(source)
            else:
                wrong.append(source)
        elif score < 40:
            bearish.append(source)
            # Check if prediction was correct
            if trade_data['pnl'] < 0:
                correct.append(source)
            else:
                wrong.append(source)
        else:
            neutral.append(source)
    
    # Identify combo used (sources that agreed)
    combo = []
    if len(bullish) >= 2:
        combo = bullish
    elif len(bearish) >= 2:
        combo = bearish
    
    combo_str = '+'.join(sorted(combo)) if combo else 'no_consensus'
    combo_correct = any(s in correct for s in combo) if combo else None
    
    cursor.execute('''
        INSERT INTO source_outcomes (
            trade_id, ticker, entry_date, exit_date, entry_price, exit_price,
            pnl, pnl_pct, trade_grade,
            reddit_wsb_score, reddit_stocks_score, reddit_investing_score,
            twitter_score, twitter_analysts_score, stocktwits_score,
            grok_ai_score, grok_confidence, trump_sentiment, analyst_consensus,
            reddit_wsb_pred, reddit_stocks_pred, twitter_pred, grok_ai_pred,
            trump_pred, analyst_pred,
            reddit_investing_pred,
            bullish_sources, bearish_sources, neutral_sources,
            outcome, correct_predictions, wrong_predictions,
            combo_used, combo_correct, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        trade_data.get('trade_id', ''),
        trade_data['symbol'],
        trade_data.get('entry_date', ''),
        trade_data.get('exit_date', ''),
        trade_data['entry'],
        trade_data['exit'],
        trade_data['pnl'],
        trade_data['pnl_pct'],
        trade_data['grade'],
        source_data.get('reddit_wsb', {}).get('score', 50),
        source_data.get('reddit_stocks', {}).get('score', 50),
        source_data.get('reddit_investing', {}).get('score', 50),
        source_data.get('twitter', {}).get('score', 50),
        source_data.get('twitter_analysts', {}).get('score', 50),
        source_data.get('stocktwits', {}).get('score', 50),
        source_data.get('grok_ai', {}).get('score', 50),
        source_data.get('grok_ai', {}).get('confidence', 50),
        source_data.get('trump', {}).get('score', 50),
        source_data.get('analyst', {}).get('score', 50),
        source_data.get('reddit_wsb', {}).get('prediction', 'neutral'),
        source_data.get('reddit_stocks', {}).get('prediction', 'neutral'),
        source_data.get('twitter', {}).get('prediction', 'neutral'),
        source_data.get('grok_ai', {}).get('prediction', 'neutral'),
        source_data.get('trump', {}).get('prediction', 'neutral'),
        source_data.get('analyst', {}).get('prediction', 'neutral'),
        source_data.get('reddit_investing', {}).get('prediction', 'neutral'),
        json.dumps(bullish),
        json.dumps(bearish),
        json.dumps(neutral),
        outcome,
        json.dumps(correct),
        json.dumps(wrong),
        combo_str,
        combo_correct,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()
    
    # Also append to JSONL for easy parsing
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'trade': trade_data,
        'sources': source_data,
        'outcome': outcome,
        'bullish_sources': bullish,
        'bearish_sources': bearish,
        'neutral_sources': neutral,
        'correct_predictions': correct,
        'wrong_predictions': wrong,
        'combo': combo_str,
        'combo_correct': combo_correct
    }
    
    with open(SOURCE_LOG_PATH, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    print(f"📝 Logged {trade_data['symbol']} with {len(source_data)} sources")
    return combo_str, combo_correct

def update_source_leaderboard():
    """Update performance stats for each source"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all outcomes
    cursor.execute('SELECT * FROM source_outcomes')
    outcomes = cursor.fetchall()
    
    # Calculate per-source stats
    source_stats = {}
    
    for row in outcomes:
        # Row indices based on table structure
        pnl = row[6]
        outcome = row[28]
        
        sources = [
            ('reddit_wsb', row[10], row[20]),
            ('reddit_stocks', row[11], row[21]),
            ('reddit_investing', row[12], row[22]),
            ('twitter', row[13], row[23]),
            ('grok_ai', row[15], row[24]),
            ('trump', row[17], row[25]),
            ('analyst', row[18], row[26])
        ]
        
        for source_name, score, pred in sources:
            if source_name not in source_stats:
                source_stats[source_name] = {
                    'total': 0, 'wins_bullish': 0, 'losses_bullish': 0,
                    'wins_bearish': 0, 'losses_bearish': 0, 'neutral': 0,
                    'total_pnl': 0
                }
            
            source_stats[source_name]['total'] += 1
            source_stats[source_name]['total_pnl'] += pnl
            
            if pred == 'bullish':
                if outcome == 'win':
                    source_stats[source_name]['wins_bullish'] += 1
                else:
                    source_stats[source_name]['losses_bullish'] += 1
            elif pred == 'bearish':
                if outcome == 'win':
                    source_stats[source_name]['wins_bearish'] += 1
                else:
                    source_stats[source_name]['losses_bearish'] += 1
            else:
                source_stats[source_name]['neutral'] += 1
    
    # Update database
    for source, stats in source_stats.items():
        total_calls = stats['wins_bullish'] + stats['losses_bullish'] + stats['wins_bearish'] + stats['losses_bearish']
        correct_calls = stats['wins_bullish'] + stats['losses_bearish']  # Bullish+win OR Bearish+loss
        accuracy = (correct_calls / total_calls * 100) if total_calls > 0 else 0
        avg_pnl = stats['total_pnl'] / stats['total'] if stats['total'] > 0 else 0
        
        cursor.execute('''
            INSERT OR REPLACE INTO source_leaderboard
            (source, total_trades, wins_when_bullish, losses_when_bullish,
             wins_when_bearish, losses_when_bearish, neutral_calls,
             accuracy_rate, avg_pnl_when_followed, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            source, stats['total'], stats['wins_bullish'], stats['losses_bullish'],
            stats['wins_bearish'], stats['losses_bearish'], stats['neutral'],
            accuracy, avg_pnl, datetime.now().isoformat()
        ))
    
    conn.commit()
    conn.close()
    print("✅ Source leaderboard updated")

def update_combo_leaderboard():
    """Track which source combinations work best"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT combo_used, outcome, pnl FROM source_outcomes WHERE combo_used != "no_consensus"')
    combos = cursor.fetchall()
    
    combo_stats = {}
    for combo, outcome, pnl in combos:
        if combo not in combo_stats:
            combo_stats[combo] = {'total': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0}
        
        combo_stats[combo]['total'] += 1
        combo_stats[combo]['total_pnl'] += pnl
        if outcome == 'win':
            combo_stats[combo]['wins'] += 1
        else:
            combo_stats[combo]['losses'] += 1
    
    # Update combo performance
    for combo, stats in combo_stats.items():
        win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        avg_pnl = stats['total_pnl'] / stats['total'] if stats['total'] > 0 else 0
        
        if win_rate >= 70:
            grade = 'A'
        elif win_rate >= 60:
            grade = 'B'
        elif win_rate >= 40:
            grade = 'C'
        elif win_rate >= 30:
            grade = 'D'
        else:
            grade = 'F'
        
        cursor.execute('''
            INSERT OR REPLACE INTO combo_performance
            (combo, sources, total_uses, wins, losses, win_rate, avg_pnl, grade, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            combo,
            json.dumps(combo.split('+')),
            stats['total'],
            stats['wins'],
            stats['losses'],
            win_rate,
            avg_pnl,
            grade,
            datetime.now().isoformat()
        ))
    
    conn.commit()
    conn.close()
    print("✅ Combo leaderboard updated")

def generate_superior_source_report():
    """Generate report showing which source/combo is superior"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get source rankings
    cursor.execute('''
        SELECT source, total_trades, accuracy_rate, avg_pnl_when_followed,
               wins_when_bullish + wins_when_bearish as correct_calls,
               losses_when_bullish + losses_when_bearish as wrong_calls
        FROM source_leaderboard
        ORDER BY accuracy_rate DESC, avg_pnl_when_followed DESC
    ''')
    source_rankings = cursor.fetchall()
    
    # Get combo rankings
    cursor.execute('''
        SELECT combo, total_uses, win_rate, avg_pnl, grade
        FROM combo_performance
        ORDER BY win_rate DESC, avg_pnl DESC
    ''')
    combo_rankings = cursor.fetchall()
    
    conn.close()
    
    report = f"""# 🏆 SUPERIOR SOURCE ANALYSIS
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M PST')}

---

## 📊 INDIVIDUAL SOURCE RANKINGS

| Rank | Source | Trades | Accuracy | Avg P&L | Correct | Wrong | Grade |
|------|--------|--------|----------|---------|---------|-------|-------|
"""
    
    for i, row in enumerate(source_rankings, 1):
        source, total, accuracy, avg_pnl, correct, wrong = row
        
        if accuracy >= 70:
            grade = "A 🟢"
        elif accuracy >= 60:
            grade = "B 🟡"
        elif accuracy >= 40:
            grade = "C ⚪"
        elif accuracy >= 30:
            grade = "D 🟠"
        else:
            grade = "F 🔴"
        
        emoji = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
        report += f"| {emoji} | {source} | {total} | {accuracy:.1f}% | ${avg_pnl:+.2f} | {correct} | {wrong} | {grade} |\n"
    
    report += """
---

## 🔥 COMBINATION PERFORMANCE

| Rank | Combo | Uses | Win Rate | Avg P&L | Grade | Status |
|------|-------|------|----------|---------|-------|--------|
"""
    
    for i, row in enumerate(combo_rankings, 1):
        combo, uses, win_rate, avg_pnl, grade = row
        sources = combo.split('+')
        status = "✅ USE THIS" if win_rate >= 60 and avg_pnl > 0 else ("⚪ TESTING" if uses < 5 else "❌ AVOID")
        
        emoji = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
        report += f"| {emoji} | {combo} | {uses} | {win_rate:.1f}% | ${avg_pnl:+.2f} | {grade} | {status} |\n"
    
    report += f"""
---

## 🎯 RECOMMENDATIONS

### ✅ TRUST THESE SOURCES (Accuracy >60%)
"""
    
    trusted = [r for r in source_rankings if r[2] >= 60]
    if trusted:
        for row in trusted:
            report += f"- **{row[0]}:** {row[2]:.1f}% accuracy, ${row[3]:+.2f} avg P&L\n"
    else:
        report += "_No sources have proven trustworthy yet. Need more winning trades._\n"
    
    report += """
### ❌ IGNORE THESE SOURCES (Accuracy <40%)
"""
    
    untrusted = [r for r in source_rankings if r[2] < 40 and r[1] >= 3]
    if untrusted:
        for row in untrusted:
            report += f"- **{row[0]}:** {row[2]:.1f}% accuracy, consistently wrong\n"
    else:
        report += "_No sources have proven unreliable yet._\n"
    
    report += """
### 🔥 BEST COMBINATIONS (Use when 2+ sources agree)
"""
    
    best_combos = [r for r in combo_rankings if r[3] >= 60]
    if best_combos:
        for row in best_combos[:3]:
            sources = row[0].split('+')
            report += f"- **{row[0]}:** {row[2]:.1f}% win rate when {', '.join(sources)} agree\n"
    else:
        report += "_No winning combinations identified yet._\n"
    
    report += f"""
---

## 🧠 WHAT TO REMEMBER

1. **Only trust sources with >60% accuracy**
2. **Best trades come when 2+ high-accuracy sources agree**
3. **Avoid trading when all sources are neutral (40-60)**
4. **If top sources disagree, skip the trade**

---
*Generated by Superior Source Analyzer*
"""
    
    # Save report
    report_file = SCRIPT_DIR / "memory" / f"SUPERIOR-SOURCES-{datetime.now().strftime('%Y-%m-%d')}.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n📄 Superior source report saved: {report_file}")
    return report

if __name__ == '__main__':
    print("=" * 70)
    print("🏆 SUPERIOR SOURCE LOGGER")
    print("=" * 70)
    
    init_source_outcome_db()
    update_source_leaderboard()
    update_combo_leaderboard()
    generate_superior_source_report()
    
    print("\n✅ Complete!")
