#!/usr/bin/env python3
"""
Trader Curtis - SOURCE ACCURACY COMPARATOR
Compares sentiment sources to actual trade outcomes
Logs which sources predict correctly for future trust weighting
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"
LESSONS_PATH = SCRIPT_DIR / "lessons"
MEMORY_PATH = SCRIPT_DIR / "memory"

def get_trade_outcomes():
    """Get completed trades with outcomes"""
    outcomes = {}
    
    for lesson_file in LESSONS_PATH.glob("*.json"):
        try:
            with open(lesson_file) as f:
                data = json.load(f)
                symbol = data.get('symbol')
                if symbol:
                    outcomes[symbol] = {
                        'pnl': data.get('pnl', 0),
                        'pnl_pct': data.get('pnl_pct', 0),
                        'grade': data.get('grade', 'C'),
                        'entry': data.get('entry', 0),
                        'exit': data.get('exit', 0),
                        'sentiment': data.get('sentiment', {})
                    }
        except:
            pass
    
    return outcomes

def get_source_predictions(symbol):
    """
    Get predictions from each source for a symbol
    This is where we'd integrate with actual source data
    For now, using placeholder structure
    """
    # Placeholder - in real implementation, this would query:
    # - Reddit WSB mentions/score
    # - Reddit r/stocks mentions/score
    # - Twitter sentiment
    # - Grok AI prediction
    # - Trump posts
    # - Analyst ratings
    
    return {
        'reddit_wsb': {'score': 50, 'prediction': 'neutral', 'confidence': 0.5},
        'reddit_stocks': {'score': 50, 'prediction': 'neutral', 'confidence': 0.5},
        'twitter': {'score': 50, 'prediction': 'neutral', 'confidence': 0.5},
        'grok_ai': {'score': 50, 'prediction': 'neutral', 'confidence': 0.5},
        'trump_posts': {'score': 50, 'prediction': 'neutral', 'confidence': 0.5},
        'analyst_ratings': {'score': 50, 'prediction': 'neutral', 'confidence': 0.5}
    }

def compare_source_to_outcome(symbol, outcome, predictions):
    """Compare each source's prediction to actual outcome"""
    actual_gain = outcome['pnl'] > 0
    results = {}
    
    for source, pred in predictions.items():
        predicted_bullish = pred['score'] > 60
        predicted_bearish = pred['score'] < 40
        
        if predicted_bullish and actual_gain:
            correct = True
            result = "✅ CORRECT - Predicted UP, went UP"
        elif predicted_bearish and not actual_gain:
            correct = True
            result = "✅ CORRECT - Predicted DOWN, went DOWN"
        elif predicted_bullish and not actual_gain:
            correct = False
            result = f"❌ WRONG - Predicted UP, lost {abs(outcome['pnl_pct']):.1f}%"
        elif predicted_bearish and actual_gain:
            correct = False
            result = f"❌ WRONG - Predicted DOWN, gained +{outcome['pnl_pct']:.1f}%"
        else:
            correct = None  # Neutral
            result = "⚪ NEUTRAL - No strong prediction"
        
        results[source] = {
            'correct': correct,
            'result': result,
            'predicted': 'bullish' if predicted_bullish else ('bearish' if predicted_bearish else 'neutral'),
            'actual': 'gain' if actual_gain else 'loss',
            'score': pred['score']
        }
    
    return results

def log_source_accuracy(symbol, source_results, outcome):
    """Log source accuracy to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure table exists with source column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS source_accuracy_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            date TEXT,
            source TEXT,
            predicted TEXT,
            actual TEXT,
            correct INTEGER,  -- 1=yes, 0=no, -1=neutral
            pnl_pct REAL,
            trade_grade TEXT,
            created_at TEXT
        )
    ''')
    
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    for source, result in source_results.items():
        correct_val = 1 if result['correct'] == True else (0 if result['correct'] == False else -1)
        
        cursor.execute('''
            INSERT INTO source_accuracy_log 
            (ticker, date, source, predicted, actual, correct, pnl_pct, trade_grade, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            symbol,
            date_str,
            source,
            result['predicted'],
            result['actual'],
            correct_val,
            outcome['pnl_pct'],
            outcome['grade'],
            datetime.now().isoformat()
        ))
    
    conn.commit()
    conn.close()

def calculate_source_stats():
    """Calculate accuracy stats for each source"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                source,
                COUNT(*) as total,
                SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct_count,
                SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) as wrong_count,
                SUM(CASE WHEN correct = -1 THEN 1 ELSE 0 END) as neutral_count,
                AVG(CASE WHEN correct = 1 THEN pnl_pct ELSE NULL END) as avg_gain_when_right,
                AVG(CASE WHEN correct = 0 THEN pnl_pct ELSE NULL END) as avg_loss_when_wrong
            FROM source_accuracy_log
            GROUP BY source
        ''')
        
        stats = cursor.fetchall()
    except:
        stats = []
    
    conn.close()
    return stats

def generate_source_report():
    """Generate comprehensive source accuracy report"""
    outcomes = get_trade_outcomes()
    
    if not outcomes:
        print("⚠️ No trade outcomes found yet")
        return
    
    print("\n" + "=" * 70)
    print("📊 COMPARING SENTIMENT SOURCES TO ACTUAL OUTCOMES")
    print("=" * 70)
    
    all_comparisons = {}
    
    for symbol, outcome in outcomes.items():
        print(f"\n🔍 {symbol}:")
        print(f"   Actual: ${outcome['entry']:.2f} → ${outcome['exit']:.2f} ({outcome['pnl_pct']:+.1f}%)")
        print(f"   Grade: {outcome['grade']}")
        
        predictions = get_source_predictions(symbol)
        comparisons = compare_source_to_outcome(symbol, outcome, predictions)
        all_comparisons[symbol] = comparisons
        
        # Log to database
        log_source_accuracy(symbol, comparisons, outcome)
        
        # Display results
        for source, result in comparisons.items():
            emoji = "✅" if result['correct'] == True else ("❌" if result['correct'] == False else "⚪")
            print(f"   {emoji} {source}: {result['result']}")
    
    # Calculate overall stats
    stats = calculate_source_stats()
    
    if stats:
        print("\n" + "=" * 70)
        print("📈 SOURCE ACCURACY RANKINGS")
        print("=" * 70)
        print(f"{'Source':<20} {'Total':<8} {'Correct':<8} {'Wrong':<8} {'Accuracy':<12} {'Grade'}")
        print("-" * 70)
        
        for row in stats:
            source, total, correct, wrong, neutral, avg_gain, avg_loss = row
            accuracy = (correct / (correct + wrong) * 100) if (correct + wrong) > 0 else 0
            
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
            
            print(f"{source:<20} {total:<8} {correct:<8} {wrong:<8} {accuracy:>5.1f}%       {grade}")
    
    # Generate report file
    generate_comparison_report(all_comparisons, outcomes, stats)

def generate_comparison_report(comparisons, outcomes, stats):
    """Generate detailed markdown report"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    report = f"""# 📊 SOURCE ACCURACY COMPARISON REPORT
**Date:** {date_str}  
**Generated:** {datetime.now().strftime('%H:%M PST')}

---

## 🎯 TRADE-BY-TRADE SOURCE COMPARISON

"""
    
    for symbol, outcome in outcomes.items():
        report += f"### {symbol}: {outcome['pnl_pct']:+.1f}% (Grade {outcome['grade']})\n\n"
        report += f"- Entry: ${outcome['entry']:.2f} → Exit: ${outcome['exit']:.2f}\n"
        report += f"- P&L: ${outcome['pnl']:+.2f}\n\n"
        
        if symbol in comparisons:
            report += "| Source | Prediction | Actual | Result |\n"
            report += "|--------|------------|--------|--------|\n"
            
            for source, result in comparisons[symbol].items():
                emoji = "✅" if result['correct'] == True else ("❌" if result['correct'] == False else "⚪")
                report += f"| {source} | {result['predicted']} | {result['actual']} | {emoji} {result['result'][:30]}... |\n"
        
        report += "\n"
    
    if stats:
        report += """---

## 📈 OVERALL SOURCE ACCURACY RANKINGS

| Source | Total | Correct | Wrong | Neutral | Accuracy | Avg Gain (Right) | Avg Loss (Wrong) | Grade |
|--------|-------|---------|-------|---------|----------|------------------|------------------|-------|
"""
        
        for row in stats:
            source, total, correct, wrong, neutral, avg_gain, avg_loss = row
            accuracy = (correct / (correct + wrong) * 100) if (correct + wrong) > 0 else 0
            
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
            
            avg_gain_str = f"{avg_gain:+.1f}%" if avg_gain is not None else "N/A"
            avg_loss_str = f"{avg_loss:.1f}%" if avg_loss is not None else "N/A"
            report += f"| {source} | {total} | {correct} | {wrong} | {neutral} | {accuracy:.1f}% | {avg_gain_str} | {avg_loss_str} | {grade} |\n"
        
        report += """
---

## 🧠 TRUSTED SOURCES (Use These)

Sources with >60% accuracy should be weighted heavily in future decisions.

## ⚠️ UNTRUSTED SOURCES (Ignore These)

Sources with <40% accuracy should be ignored or inverted.

## 🆕 NEW SOURCES (Prove Themselves)

Sources with <10 predictions need more data before trusting.

---

## 💡 KEY INSIGHTS

"""
        
        # Find best and worst sources
        if stats:
            best = max(stats, key=lambda x: (x[2] / (x[2] + x[3]) * 100) if (x[2] + x[3]) > 0 else 0)
            worst = min(stats, key=lambda x: (x[2] / (x[2] + x[3]) * 100) if (x[2] + x[3]) > 0 else 0)
            
            report += f"**🏆 Most Accurate Source:** {best[0]}\n"
            report += f"**🔴 Least Accurate Source:** {worst[0]}\n"
    
    report += f"""
---
*Generated by Source Accuracy Comparator*
"""
    
    # Save report
    report_file = MEMORY_PATH / f"SOURCE-COMPARISON-{date_str}.md"
    report_file.parent.mkdir(exist_ok=True)
    
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n📄 Source comparison report saved: {report_file}")

def remember_best_sources():
    """Log best sources to git-notes memory"""
    stats = calculate_source_stats()
    
    if not stats:
        return
    
    # Sort by accuracy
    ranked = sorted(stats, key=lambda x: (x[2] / (x[2] + x[3]) * 100) if (x[2] + x[3]) > 0 else 0, reverse=True)
    
    print("\n" + "=" * 70)
    print("🧠 REMEMBERING BEST SOURCES")
    print("=" * 70)
    
    for i, row in enumerate(ranked[:3]):  # Top 3
        source, total, correct, wrong, neutral, avg_gain, avg_loss = row
        accuracy = (correct / (correct + wrong) * 100) if (correct + wrong) > 0 else 0
        
        if accuracy >= 60:
            print(f"✅ TRUST: {source} - {accuracy:.1f}% accuracy")
            # Would log to git-notes here
        elif accuracy <= 40:
            print(f"❌ IGNORE: {source} - {accuracy:.1f}% accuracy")
            # Would log to git-notes here

if __name__ == '__main__':
    print("=" * 70)
    print("📊 SOURCE ACCURACY COMPARATOR")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}\n")
    
    generate_source_report()
    remember_best_sources()
    
    print("\n" + "=" * 70)
    print("✅ SOURCE COMPARISON COMPLETE")
    print("=" * 70)
