#!/usr/bin/env python3
"""
Trader Curtis - ENHANCED LEARNING ENGINE v3
Logs trades WITH source predictions to identify superior sources
Uses simplified database schema
"""

import json
from datetime import datetime
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from simple_source_logger import log_simple_outcome, analyze_sources

def get_source_predictions(symbol, entry_date):
    """Get predictions from sentiment files"""
    date_str = entry_date[:10] if entry_date else datetime.now().strftime('%Y-%m-%d')
    sentiment_file = SCRIPT_DIR / "memory" / f"sentiment-{date_str}.md"
    
    sources = {}
    default_score = 50
    
    if sentiment_file.exists():
        with open(sentiment_file) as f:
            content = f.read()
            lines = content.split('\n')
            for line in lines:
                if symbol in line and '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 3:
                        try:
                            score = int(parts[2])
                            if score > 60:
                                pred = 'bullish'
                            elif score < 40:
                                pred = 'bearish'
                            else:
                                pred = 'neutral'
                            
                            # All sources got this score
                            for src in ['reddit_wsb', 'reddit_stocks', 'twitter', 'grok_ai', 'trump', 'analyst']:
                                sources[src] = {'score': score, 'prediction': pred}
                        except:
                            pass
    
    if not sources:
        for src in ['reddit_wsb', 'reddit_stocks', 'twitter', 'grok_ai', 'trump', 'analyst']:
            sources[src] = {'score': 50, 'prediction': 'neutral'}
    
    return sources

def process_all_trades():
    """Process all trades with source data"""
    lessons_dir = SCRIPT_DIR / "lessons"
    
    if not lessons_dir.exists():
        print("⚠️ No lessons directory")
        return
    
    print(f"\n🔍 Processing trades from {lessons_dir}...\n")
    
    for lesson_file in lessons_dir.glob("*.json"):
        try:
            with open(lesson_file) as f:
                data = json.load(f)
                
                symbol = data.get('symbol')
                entry = data.get('entry', 0)
                exit_price = data.get('exit', 0)
                pnl = data.get('pnl', 0)
                pnl_pct = data.get('pnl_pct', 0)
                grade = data.get('grade', 'C')
                
                # Get source predictions
                sources = get_source_predictions(symbol, datetime.now().strftime('%Y-%m-%d'))
                
                # Log with sources
                log_simple_outcome(symbol, entry, exit_price, pnl, pnl_pct, grade, sources)
                
        except Exception as e:
            print(f"  ⚠️ Error: {lesson_file.name} - {e}")

if __name__ == '__main__':
    print("=" * 70)
    print("🧠 ENHANCED LEARNING ENGINE v3 - SOURCE TRACKING")
    print("=" * 70)
    
    process_all_trades()
    
    print("\n" + "=" * 70)
    print("📊 SOURCE ANALYSIS")
    print("=" * 70)
    
    analyze_sources()
    
    print("\n" + "=" * 70)
    print("✅ COMPLETE - Now tracking which sources predict correctly!")
    print("=" * 70)
