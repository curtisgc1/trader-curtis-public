#!/usr/bin/env python3
"""
Trader Curtis - SOURCE COMBO ANALYZER
Tracks individual sources AND combinations (2-source, 3-source, etc.)
Identifies which combos produce best outcomes
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from itertools import combinations

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"

def init_combo_tracking():
    """Initialize combo tracking tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Individual source performance
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_performance (
            source TEXT PRIMARY KEY,
            total_signals INTEGER DEFAULT 0,
            bullish_signals INTEGER DEFAULT 0,
            bearish_signals INTEGER DEFAULT 0,
            wins_when_bullish INTEGER DEFAULT 0,
            losses_when_bullish INTEGER DEFAULT 0,
            wins_when_bearish INTEGER DEFAULT 0,
            losses_when_bearish INTEGER DEFAULT 0,
            neutral_signals INTEGER DEFAULT 0,
            win_rate_bullish REAL DEFAULT 0,
            win_rate_bearish REAL DEFAULT 0,
            overall_accuracy REAL DEFAULT 0,
            avg_pnl_when_followed REAL DEFAULT 0,
            grade TEXT DEFAULT 'C',
            last_updated TEXT
        )
    ''')
    
    # Combo performance (2-source, 3-source, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS combo_stats (
            combo TEXT PRIMARY KEY,
            sources TEXT,  -- JSON array
            combo_size INTEGER,
            total_trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            avg_pnl REAL DEFAULT 0,
            avg_pnl_wins REAL DEFAULT 0,
            avg_pnl_losses REAL DEFAULT 0,
            best_trade TEXT,
            worst_trade TEXT,
            grade TEXT DEFAULT 'C',
            status TEXT DEFAULT 'TESTING',  -- TESTING, TRUSTED, AVOID
            last_updated TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Combo tracking tables initialized")

def get_all_trades_with_sources():
    """Get all trades from simple_source_outcomes table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT ticker, entry_price, exit_price, pnl, pnl_pct, trade_grade, outcome, sources FROM simple_source_outcomes')
        rows = cursor.fetchall()
    except:
        rows = []
    
    conn.close()
    
    trades = []
    for row in rows:
        ticker, entry, exit, pnl, pnl_pct, grade, outcome, sources_json = row
        sources = json.loads(sources_json)
        trades.append({
            'ticker': ticker,
            'entry': entry,
            'exit': exit,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'grade': grade,
            'outcome': outcome,
            'sources': sources
        })
    
    return trades

def analyze_individual_sources(trades):
    """Analyze each source individually"""
    source_stats = {}
    
    for trade in trades:
        outcome = trade['outcome']
        pnl = trade['pnl']
        
        for source_name, data in trade['sources'].items():
            score = data.get('score', 50)
            prediction = data.get('prediction', 'neutral')
            
            if source_name not in source_stats:
                source_stats[source_name] = {
                    'total': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0,
                    'wins_bullish': 0, 'losses_bullish': 0,
                    'wins_bearish': 0, 'losses_bearish': 0,
                    'total_pnl_bullish': 0, 'total_pnl_bearish': 0
                }
            
            source_stats[source_name]['total'] += 1
            
            if prediction == 'bullish':
                source_stats[source_name]['bullish'] += 1
                if outcome == 'win':
                    source_stats[source_name]['wins_bullish'] += 1
                else:
                    source_stats[source_name]['losses_bullish'] += 1
                source_stats[source_name]['total_pnl_bullish'] += pnl
                    
            elif prediction == 'bearish':
                source_stats[source_name]['bearish'] += 1
                if outcome == 'win':
                    source_stats[source_name]['wins_bearish'] += 1
                else:
                    source_stats[source_name]['losses_bearish'] += 1
                source_stats[source_name]['total_pnl_bearish'] += pnl
            else:
                source_stats[source_name]['neutral'] += 1
    
    return source_stats

def analyze_combinations(trades):
    """Analyze all possible source combinations"""
    combo_stats = {}
    
    for trade in trades:
        outcome = trade['outcome']
        pnl = trade['pnl']
        ticker = trade['ticker']
        
        # Get bullish and bearish sources
        bullish = [name for name, data in trade['sources'].items() if data.get('score', 50) > 60]
        bearish = [name for name, data in trade['sources'].items() if data.get('score', 50) < 40]
        
        # Analyze all combo sizes (2, 3, 4, 5, 6)
        for combo_size in range(2, 7):
            if len(bullish) >= combo_size:
                for combo in combinations(sorted(bullish), combo_size):
                    combo_key = '+'.join(combo)
                    
                    if combo_key not in combo_stats:
                        combo_stats[combo_key] = {
                            'sources': combo,
                            'size': combo_size,
                            'total': 0, 'wins': 0, 'losses': 0,
                            'total_pnl': 0, 'total_pnl_wins': 0, 'total_pnl_losses': 0,
                            'best_trade': None, 'worst_trade': None,
                            'best_pnl': float('-inf'), 'worst_pnl': float('inf')
                        }
                    
                    cs = combo_stats[combo_key]
                    cs['total'] += 1
                    cs['total_pnl'] += pnl
                    
                    if outcome == 'win':
                        cs['wins'] += 1
                        cs['total_pnl_wins'] += pnl
                    else:
                        cs['losses'] += 1
                        cs['total_pnl_losses'] += pnl
                    
                    # Track best/worst trade
                    if pnl > cs['best_pnl']:
                        cs['best_pnl'] = pnl
                        cs['best_trade'] = f"{ticker}: {pnl:+.1f}%"
                    if pnl < cs['worst_pnl']:
                        cs['worst_pnl'] = pnl
                        cs['worst_trade'] = f"{ticker}: {pnl:+.1f}%"
    
    return combo_stats

def save_to_database(source_stats, combo_stats):
    """Save analysis to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Save individual source stats
    for source, stats in source_stats.items():
        bullish_total = stats['wins_bullish'] + stats['losses_bullish']
        bearish_total = stats['wins_bearish'] + stats['losses_bearish']
        
        win_rate_bullish = (stats['wins_bullish'] / bullish_total * 100) if bullish_total > 0 else 0
        win_rate_bearish = (stats['losses_bearish'] / bearish_total * 100) if bearish_total > 0 else 0  # Bearish correct when market drops
        
        total_calls = bullish_total + bearish_total
        correct_calls = stats['wins_bullish'] + stats['losses_bearish']
        overall_accuracy = (correct_calls / total_calls * 100) if total_calls > 0 else 0
        
        total_pnl = stats['total_pnl_bullish'] + stats['total_pnl_bearish']
        avg_pnl = total_pnl / stats['total'] if stats['total'] > 0 else 0
        
        if overall_accuracy >= 70:
            grade = 'A'
        elif overall_accuracy >= 60:
            grade = 'B'
        elif overall_accuracy >= 40:
            grade = 'C'
        elif overall_accuracy >= 30:
            grade = 'D'
        else:
            grade = 'F'
        
        cursor.execute('''
            INSERT OR REPLACE INTO source_performance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            source, stats['total'], stats['bullish'], stats['bearish'],
            stats['wins_bullish'], stats['losses_bullish'],
            stats['wins_bearish'], stats['losses_bearish'], stats['neutral'],
            win_rate_bullish, win_rate_bearish, overall_accuracy,
            avg_pnl, grade, datetime.now().isoformat()
        ))
    
    # Save combo stats
    for combo_key, stats in combo_stats.items():
        win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        avg_pnl = stats['total_pnl'] / stats['total'] if stats['total'] > 0 else 0
        avg_pnl_wins = stats['total_pnl_wins'] / stats['wins'] if stats['wins'] > 0 else 0
        avg_pnl_losses = stats['total_pnl_losses'] / stats['losses'] if stats['losses'] > 0 else 0
        
        if win_rate >= 70 and avg_pnl > 0:
            grade = 'A'
            status = 'TRUSTED'
        elif win_rate >= 60 and avg_pnl > 0:
            grade = 'B'
            status = 'TRUSTED'
        elif win_rate >= 40:
            grade = 'C'
            status = 'TESTING'
        elif win_rate >= 30:
            grade = 'D'
            status = 'TESTING'
        else:
            grade = 'F'
            status = 'AVOID'
        
        cursor.execute('''
            INSERT OR REPLACE INTO combo_stats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            combo_key, json.dumps(stats['sources']), stats['size'], stats['total'],
            stats['wins'], stats['losses'], win_rate, avg_pnl,
            avg_pnl_wins, avg_pnl_losses,
            stats['best_trade'], stats['worst_trade'],
            grade, status, datetime.now().isoformat()
        ))
    
    conn.commit()
    conn.close()
    print(f"✅ Saved {len(source_stats)} sources and {len(combo_stats)} combos to database")

def generate_superior_combo_report():
    """Generate comprehensive combo analysis report"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get source rankings
    cursor.execute('''
        SELECT source, total_signals, bullish_signals, bearish_signals,
               win_rate_bullish, win_rate_bearish, overall_accuracy,
               avg_pnl_when_followed, grade
        FROM source_performance
        ORDER BY overall_accuracy DESC, avg_pnl_when_followed DESC
    ''')
    sources = cursor.fetchall()
    
    # Get combo rankings by size
    combo_by_size = {}
    for size in range(2, 7):
        cursor.execute('''
            SELECT combo, combo_size, total_trades, wins, losses, win_rate,
                   avg_pnl, avg_pnl_wins, avg_pnl_losses, grade, status
            FROM combo_stats
            WHERE combo_size = ?
            ORDER BY win_rate DESC, avg_pnl DESC
        ''', (size,))
        combo_by_size[size] = cursor.fetchall()
    
    conn.close()
    
    report = f"""# 🏆 SUPERIOR SOURCE & COMBO ANALYSIS
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M PST')}

---

## 📊 INDIVIDUAL SOURCE PERFORMANCE

| Source | Total | Bullish | Bearish | Win% (Bull) | Win% (Bear) | Overall | Avg P&L | Grade |
|--------|-------|---------|---------|-------------|-------------|---------|---------|-------|
"""
    
    for row in sources:
        source, total, bull, bear, win_bull, win_bear, overall, avg_pnl, grade = row
        emoji = "🟢" if overall >= 60 else ("🟡" if overall >= 40 else "🔴")
        report += f"| {emoji} {source} | {total} | {bull} | {bear} | {win_bull:.0f}% | {win_bear:.0f}% | {overall:.0f}% | ${avg_pnl:+.2f} | {grade} |\n"
    
    # Combo analysis by size
    for size in range(2, 7):
        combos = combo_by_size.get(size, [])
        if not combos:
            continue
        
        report += f"""
---

## 🔥 {size}-SOURCE COMBINATIONS

**{size} sources must agree for signal**

| Combo | Trades | Wins | Losses | Win Rate | Avg P&L | Avg Win | Avg Loss | Grade | Status |
|-------|--------|------|--------|----------|---------|---------|----------|-------|--------|
"""
        
        for row in combos[:10]:  # Top 10
            combo, sz, total, wins, losses, win_rate, avg_pnl, avg_win, avg_loss, grade, status = row
            emoji = "✅" if status == 'TRUSTED' else ("⚪" if status == 'TESTING' else "❌")
            report += f"| {emoji} {combo} | {total} | {wins} | {losses} | {win_rate:.0f}% | ${avg_pnl:+.1f} | ${avg_win:+.1f} | ${avg_loss:.1f} | {grade} | {status} |\n"
    
    # Key insights
    report += """
---

## 🎯 KEY INSIGHTS

### Best Performing Individual Sources
"""
    
    best_sources = [s for s in sources if s[6] >= 60]  # overall accuracy >= 60
    if best_sources:
        for row in best_sources[:3]:
            report += f"- **{row[0]}:** {row[6]:.0f}% accuracy, ${row[7]:+.2f} avg P&L\n"
    else:
        report += "_Need more winning trades to identify best sources_\n"
    
    report += """
### Best 2-Source Combinations
"""
    best_2 = combo_by_size.get(2, [])
    if best_2:
        for row in best_2[:3]:
            if row[5] >= 50:  # win rate >= 50%
                report += f"- **{row[0]}:** {row[5]:.0f}% win rate, ${row[6]:+.2f} avg P&L\n"
    else:
        report += "_Need more 2-source consensus trades_\n"
    
    report += """
### Best 3-Source Combinations
"""
    best_3 = combo_by_size.get(3, [])
    if best_3:
        for row in best_3[:3]:
            if row[5] >= 50:  # win rate >= 50%
                report += f"- **{row[0]}:** {row[5]:.0f}% win rate, ${row[6]:+.2f} avg P&L\n"
    else:
        report += "_Need more 3-source consensus trades_\n"
    
    report += f"""
---

## 🧠 TRADING RULES (Auto-Updated)

### ✅ USE These Combos (Win Rate >60%):
"""
    
    trusted = []
    for size in range(2, 7):
        for row in combo_by_size.get(size, []):
            if row[10] == 'TRUSTED':  # status
                trusted.append(row)
    
    if trusted:
        for row in trusted[:5]:
            report += f"- **{row[0]}** ({row[1]} sources): {row[5]:.0f}% win rate\n"
    else:
        report += "_No combos have proven trustworthy yet (need 60%+ win rate)_\n"
    
    report += """
### ❌ AVOID These Combos (Win Rate <40%):
"""
    
    avoid = []
    for size in range(2, 7):
        for row in combo_by_size.get(size, []):
            if row[10] == 'AVOID':  # status
                avoid.append(row)
    
    if avoid:
        for row in avoid[:5]:
            report += f"- **{row[0]}** ({row[1]} sources): {row[5]:.0f}% win rate\n"
    else:
        report += "_No combos have proven unreliable yet_\n"
    
    report += """
### ⚠️ IMPORTANT DISCOVERIES

1. **Individual sources** with <50% accuracy should be ignored
2. **2-source combos** are often more reliable than individual sources
3. **3-source combos** with >70% win rate are GOLD
4. **4+ source combos** may be too rare to be useful
5. **Neutral consensus (all 40-60)** = No trade

---

## 📈 NEXT STEPS

To identify superior sources:
1. Complete more trades with source tracking
2. Look for 2-3 source combinations with >60% win rates
3. Once identified, ONLY trade when those combos agree
4. Continuously update as more data accumulates

---
*Generated by Source Combo Analyzer*
"""
    
    # Save report
    report_file = SCRIPT_DIR / "memory" / f"COMBO-ANALYSIS-{datetime.now().strftime('%Y-%m-%d')}.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"📄 Combo analysis report saved: {report_file}")
    return report

def main():
    print("=" * 70)
    print("🏆 SOURCE COMBO ANALYZER")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}\n")
    
    # Initialize
    init_combo_tracking()
    
    # Get trades
    trades = get_all_trades_with_sources()
    print(f"📊 Analyzing {len(trades)} trades...\n")
    
    if not trades:
        print("⚠️ No trades found. Complete some trades first!")
        return
    
    # Analyze
    print("🔍 Analyzing individual sources...")
    source_stats = analyze_individual_sources(trades)
    
    print("🔍 Analyzing source combinations (2-6 sources)...")
    combo_stats = analyze_combinations(trades)
    
    # Save
    print("\n💾 Saving to database...")
    save_to_database(source_stats, combo_stats)
    
    # Generate report
    print("\n📄 Generating report...")
    report = generate_superior_combo_report()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Individual sources analyzed: {len(source_stats)}")
    print(f"Source combinations found: {len(combo_stats)}")
    
    # Show top performers
    if source_stats:
        print("\n🏆 Top Individual Sources:")
        sorted_sources = sorted(source_stats.items(), 
                               key=lambda x: (x[1]['wins_bullish'] + x[1]['losses_bearish']) / max(x[1]['total'], 1),
                               reverse=True)
        for source, stats in sorted_sources[:3]:
            total_correct = stats['wins_bullish'] + stats['losses_bearish']
            accuracy = (total_correct / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"  - {source}: {accuracy:.0f}% accuracy ({stats['total']} signals)")
    
    if combo_stats:
        print("\n🔥 Top Combinations:")
        sorted_combos = sorted(combo_stats.items(),
                              key=lambda x: x[1]['wins'] / max(x[1]['total'], 1),
                              reverse=True)
        for combo, stats in sorted_combos[:3]:
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"  - {combo}: {win_rate:.0f}% win rate ({stats['total']} trades)")
    
    print("\n" + "=" * 70)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 70)

if __name__ == '__main__':
    main()
