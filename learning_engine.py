#!/usr/bin/env python3
"""
Trader Curtis - ULTIMATE LEARNING ENGINE v2
Tracks RIGHT vs WRONG, grades decisions A-F, extracts patterns
"""

import sqlite3
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import os

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "data" / "trades.db"
MEMORY_PATH = SCRIPT_DIR / "memory"
LESSONS_PATH = SCRIPT_DIR / "lessons"
PATTERNS_PATH = SCRIPT_DIR / "patterns"

def load_env():
    env = {}
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env[key] = val
    return env

def get_alpaca_data(endpoint):
    """Get data from Alpaca API"""
    env = load_env()
    headers = {
        "APCA-API-KEY-ID": env.get('ALPACA_API_KEY'),
        "APCA-API-SECRET-KEY": env.get('ALPACA_SECRET_KEY')
    }
    base_url = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    try:
        r = requests.get(f"{base_url}/v2/{endpoint}", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"❌ API error: {e}")
    return []

def pair_trades(orders):
    """Pair buy and sell orders to calculate P&L"""
    trades = {}
    
    for order in orders:
        if order.get('status') != 'filled':
            continue
            
        symbol = order.get('symbol')
        side = order.get('side')
        price = float(order.get('filled_avg_price', 0))
        qty = float(order.get('filled_qty', 0))
        order_type = order.get('type', 'market')
        
        if symbol not in trades:
            trades[symbol] = {'buys': [], 'sells': []}
        
        if side == 'buy':
            trades[symbol]['buys'].append({
                'price': price,
                'qty': qty,
                'type': order_type,
                'date': order.get('filled_at', '')
            })
        else:
            trades[symbol]['sells'].append({
                'price': price,
                'qty': qty,
                'type': order_type,
                'date': order.get('filled_at', '')
            })
    
    return trades

def get_sentiment_at_entry(symbol, entry_date):
    """Retrieve sentiment scores from when trade was entered"""
    sentiment = {'reddit': 50, 'twitter': 50, 'grok': 50, 'overall': 50}
    
    # Check sentiment scan files
    date_str = entry_date[:10] if entry_date else datetime.now().strftime('%Y-%m-%d')
    sentiment_file = MEMORY_PATH / f"sentiment-{date_str}.md"
    
    if sentiment_file.exists():
        with open(sentiment_file) as f:
            content = f.read()
            # Parse the table for this symbol
            lines = content.split('\n')
            for line in lines:
                if symbol in line and '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 3:
                        try:
                            score = int(parts[2])
                            sentiment['overall'] = score
                            sentiment['source'] = 'sentiment_scan'
                        except:
                            pass
    
    return sentiment

def analyze_sentiment_accuracy(symbol, sentiment, pnl):
    """Grade whether sentiment predictions were correct"""
    predicted_bullish = sentiment.get('overall', 50) > 60
    predicted_bearish = sentiment.get('overall', 50) < 40
    actual_bullish = pnl > 0
    
    sentiment_grade = "C"
    sentiment_correct = False
    sentiment_lesson = ""
    
    if predicted_bullish and actual_bullish:
        sentiment_correct = True
        sentiment_grade = "A"
        sentiment_lesson = f"✅ SENTIMENT CORRECT: Bullish prediction for {symbol} matched +{pnl:.1f}% gain"
    elif predicted_bearish and not actual_bullish:
        sentiment_correct = True
        sentiment_grade = "A"
        sentiment_lesson = f"✅ SENTIMENT CORRECT: Bearish prediction for {symbol} saved from loss"
    elif predicted_bullish and not actual_bullish:
        sentiment_correct = False
        sentiment_grade = "F"
        sentiment_lesson = f"❌ SENTIMENT WRONG: Predicted bullish for {symbol}, lost {abs(pnl):.1f}%"
    elif predicted_bearish and actual_bullish:
        sentiment_correct = False
        sentiment_grade = "F"
        sentiment_lesson = f"❌ SENTIMENT WRONG: Predicted bearish for {symbol}, missed +{pnl:.1f}% gain"
    else:
        sentiment_lesson = f"⚪ SENTIMENT NEUTRAL: No strong signal for {symbol}"
    
    return {
        'correct': sentiment_correct,
        'grade': sentiment_grade,
        'lesson': sentiment_lesson,
        'predicted': 'bullish' if predicted_bullish else ('bearish' if predicted_bearish else 'neutral'),
        'actual': 'gain' if pnl > 0 else 'loss',
        'score': sentiment.get('overall', 50)
    }

def analyze_trade(symbol, buys, sells):
    """Analyze a completed trade and grade it A-F"""
    
    if not buys or not sells:
        return None
    
    # Calculate totals
    total_bought = sum(b['price'] * b['qty'] for b in buys)
    total_qty_bought = sum(b['qty'] for b in buys)
    avg_entry = total_bought / total_qty_bought if total_qty_bought > 0 else 0
    
    total_sold = sum(s['price'] * s['qty'] for s in sells)
    total_qty_sold = sum(s['qty'] for s in sells)
    avg_exit = total_sold / total_qty_sold if total_qty_sold > 0 else 0
    
    # Calculate P&L
    pnl = total_sold - total_bought
    pnl_pct = ((avg_exit - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
    
    # Determine if stop loss was hit
    stop_hit = any(s['type'] == 'stop' for s in sells)
    
    # Get sentiment at entry
    entry_date = buys[0].get('date', '') if buys else ''
    sentiment = get_sentiment_at_entry(symbol, entry_date)
    sentiment_analysis = analyze_sentiment_accuracy(symbol, sentiment, pnl)
    
    # GRADE THE DECISION (A-F)
    grade = "C"
    what_right = []
    what_wrong = []
    lesson = ""
    
    if pnl > 0:
        # WIN
        if pnl_pct > 10:
            grade = "A"
            what_right.append(f"🏆 EXCELLENT: {symbol} gained {pnl_pct:.1f}% - thesis validated")
            lesson = f"REPEAT THIS: {symbol} setup worked perfectly"
        elif pnl_pct > 5:
            grade = "B"
            what_right.append(f"✅ GOOD: {symbol} gained {pnl_pct:.1f}% - solid execution")
            lesson = f"REPEAT: {symbol} approach was correct"
        else:
            grade = "C"
            what_right.append(f"🟡 OK: {symbol} small win +{pnl_pct:.1f}%")
            lesson = f"OK but aim for bigger winners like NEM"
            
    else:
        # LOSS
        if stop_hit:
            if pnl_pct > -15:
                grade = "C"
                what_right.append(f"🛑 GOOD: Honored stop loss on {symbol} at {abs(pnl_pct):.1f}% loss")
                what_wrong.append(f"❌ Thesis wrong on {symbol} but preserved capital")
                lesson = f"STOP LOSS SAVED ME: {symbol} stopped at {abs(pnl_pct):.1f}% instead of larger loss"
            else:
                grade = "D"
                what_wrong.append(f"⚠️ Stop too wide on {symbol} - lost {abs(pnl_pct):.1f}%")
                lesson = f"FIX: Tighter stops needed - {symbol} was too loose"
        else:
            if pnl_pct < -20:
                grade = "F"
                what_wrong.append(f"🔴 CRITICAL: No stop on {symbol}! Lost {abs(pnl_pct):.1f}%")
                lesson = f"NEVER AGAIN: Always set stops - {symbol} disaster"
            else:
                grade = "D"
                what_wrong.append(f"❌ Manual exit too late on {symbol}")
                lesson = f"Use stops, don't hope - {symbol}"
    
    # Add sentiment accuracy to what_right/what_wrong
    if sentiment_analysis['correct']:
        what_right.append(sentiment_analysis['lesson'])
    else:
        what_wrong.append(sentiment_analysis['lesson'])
    
    # Additional analysis
    if symbol == 'ASTS' and pnl < 0:
        what_wrong.append(f"❌ Meme stock volatility crushed {symbol}")
        lesson = "AVOID: Meme stocks too volatile for my strategy"
    
    if symbol == 'MARA' and pnl < 0:
        what_wrong.append(f"❌ Crypto exposure via {symbol} too risky")
        lesson = "LIMIT: Keep crypto exposure under 5% max"
    
    return {
        'symbol': symbol,
        'entry': avg_entry,
        'exit': avg_exit,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'grade': grade,
        'stop_hit': stop_hit,
        'sentiment': sentiment_analysis,
        'what_right': what_right,
        'what_wrong': what_wrong,
        'lesson': lesson,
        'shares': total_qty_bought
    }

def log_lesson(analysis):
    """Log learning to lessons folder"""
    LESSONS_PATH.mkdir(exist_ok=True)
    
    filename = f"{analysis['symbol']}-{datetime.now().strftime('%Y%m%d')}.json"
    filepath = LESSONS_PATH / filename
    
    with open(filepath, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print(f"📝 Logged: {filepath}")

def extract_patterns():
    """Extract winning patterns from lessons"""
    patterns = {'winners': [], 'losers': []}
    
    if not LESSONS_PATH.exists():
        return patterns
    
    for f in LESSONS_PATH.glob("*.json"):
        try:
            with open(f) as file:
                data = json.load(file)
                if data.get('pnl', 0) > 0:
                    patterns['winners'].append(data)
                else:
                    patterns['losers'].append(data)
        except:
            pass
    
    # Save aggregated
    PATTERNS_PATH.mkdir(exist_ok=True)
    with open(PATTERNS_PATH / "all_patterns.json", 'w') as f:
        json.dump(patterns, f, indent=2)
    
    return patterns

def generate_report(analyses):
    """Generate comprehensive learning report"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    wins = [a for a in analyses if a['pnl'] > 0]
    losses = [a for a in analyses if a['pnl'] < 0]
    total_pnl = sum(a['pnl'] for a in analyses)
    
    report = f"""# 🧠 TRADER CURTIS - DAILY LEARNING REPORT
**Date:** {today}  
**Time:** {datetime.now().strftime('%H:%M PST')}

---

## 📊 PERFORMANCE SUMMARY

| Metric | Value |
|--------|-------|
| **Trades Analyzed** | {len(analyses)} |
| **Wins** | {len(wins)} 🟢 |
| **Losses** | {len(losses)} 🔴 |
| **Win Rate** | {len(wins)/len(analyses)*100:.1f}% |
| **Total P&L** | ${total_pnl:+.2f} |

---

## 🎓 DECISION GRADES

"""
    
    grade_counts = {}
    for a in analyses:
        g = a['grade']
        grade_counts[g] = grade_counts.get(g, 0) + 1
    
    grade_emoji = {'A': '🏆', 'B': '✅', 'C': '⚪', 'D': '⚠️', 'F': '❌'}
    for g in ['A', 'B', 'C', 'D', 'F']:
        if g in grade_counts:
            report += f"{grade_emoji[g]} **{g}:** {grade_counts[g]} trades\n"
    
    # Trade details
    report += "\n---\n\n## 📈 TRADE-BY-TRADE ANALYSIS\n\n"
    
    for a in analyses:
        emoji = '🟢' if a['pnl'] > 0 else '🔴'
        stop_info = " (STOP HIT)" if a['stop_hit'] else ""
        report += f"### {emoji} {a['symbol']} - Grade {a['grade']}{stop_info}\n"
        report += f"- Entry: ${a['entry']:.2f} → Exit: ${a['exit']:.2f}\n"
        report += f"- P&L: ${a['pnl']:+.2f} ({a['pnl_pct']:+.1f}%)\n\n"
    
    # What I did RIGHT
    report += "---\n\n## ✅ WHAT I DID RIGHT (DO THIS AGAIN)\n\n"
    for a in analyses:
        for item in a['what_right']:
            report += f"- {item}\n"
    
    # What I did WRONG
    report += "\n---\n\n## ❌ WHAT I DID WRONG (NEVER REPEAT)\n\n"
    for a in analyses:
        for item in a['what_wrong']:
            report += f"- {item}\n"
    
    # Lessons
    report += "\n---\n\n## 🧠 KEY LESSONS LEARNED\n\n"
    for a in analyses:
        if a['lesson']:
            report += f"- **{a['symbol']}:** {a['lesson']}\n"
    
    # Sentiment Accuracy Section
    sentiment_correct = [a for a in analyses if a.get('sentiment', {}).get('correct', False)]
    sentiment_wrong = [a for a in analyses if not a.get('sentiment', {}).get('correct', False)]
    
    report += "\n---\n\n## 📊 SENTIMENT ACCURACY\n\n"
    report += f"**Predictions Correct:** {len(sentiment_correct)}/{len(analyses)} ({len(sentiment_correct)/len(analyses)*100:.0f}%)\n\n"
    
    if sentiment_correct:
        report += "### ✅ CORRECT Predictions:\n"
        for a in sentiment_correct:
            s = a.get('sentiment', {})
            report += f"- **{a['symbol']}:** {s.get('lesson', '')[:60]}...\n"
    
    if sentiment_wrong:
        report += "\n### ❌ WRONG Predictions:\n"
        for a in sentiment_wrong:
            s = a.get('sentiment', {})
            report += f"- **{a['symbol']}:** {s.get('lesson', '')[:60]}...\n"
    
    # Patterns
    patterns = extract_patterns()
    report += f"\n---\n\n## ✨ PATTERN DATABASE\n\n"
    report += f"**Winning Patterns:** {len(patterns['winners'])}\n"
    report += f"**Losing Patterns:** {len(patterns['losers'])}\n\n"
    
    if patterns['winners']:
        report += "### 🏆 Winning Patterns to Repeat:\n"
        for p in patterns['winners'][-3:]:  # Last 3
            report += f"- {p['symbol']}: {p['lesson'][:80]}...\n"
    
    if patterns['losers']:
        report += "\n### ⚠️ Losing Patterns to Avoid:\n"
        for p in patterns['losers'][-3:]:  # Last 3
            report += f"- {p['symbol']}: {p['lesson'][:80]}...\n"
    
    report += f"\n---\n*Generated by Trader Curtis Learning Engine v2*\n"
    
    # Save report
    MEMORY_PATH.mkdir(exist_ok=True)
    report_file = MEMORY_PATH / f"LEARNING-REPORT-{today}.md"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n📄 Report saved: {report_file}")
    return report

def main():
    print("=" * 70)
    print("🧠 TRADER CURTIS - ULTIMATE LEARNING ENGINE v2")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}\n")
    
    # Get orders
    orders = get_alpaca_data("orders?status=all&limit=50")
    if not orders:
        print("❌ No orders found")
        return
    
    # Pair trades
    trades = pair_trades(orders)
    print(f"📊 Found {len(trades)} symbols with trading activity\n")
    
    # Analyze each completed trade
    analyses = []
    for symbol, data in trades.items():
        if data['buys'] and data['sells']:
            print(f"🔍 Analyzing {symbol}...")
            analysis = analyze_trade(symbol, data['buys'], data['sells'])
            if analysis:
                analyses.append(analysis)
                log_lesson(analysis)
                print(f"   Grade: {analysis['grade']} | P&L: ${analysis['pnl']:+.2f}")
    
    if not analyses:
        print("\n⚠️ No completed round-trip trades found")
        return
    
    # Generate report
    print("\n" + "=" * 70)
    print("📄 GENERATING LEARNING REPORT")
    print("=" * 70)
    report = generate_report(analyses)
    
    print("\n" + "=" * 70)
    print("✅ LEARNING ENGINE COMPLETE")
    print("=" * 70)
    print(f"\n📊 SUMMARY:")
    print(f"   Trades Analyzed: {len(analyses)}")
    print(f"   Winners: {len([a for a in analyses if a['pnl'] > 0])}")
    print(f"   Losers: {len([a for a in analyses if a['pnl'] < 0])}")
    print(f"   Total P&L: ${sum(a['pnl'] for a in analyses):+.2f}")

if __name__ == '__main__':
    main()
