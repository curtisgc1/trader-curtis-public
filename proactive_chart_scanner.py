#!/usr/bin/env python3
"""
Proactive Chart Scanner — Auto-analyze charts for opportunities
Uses Chart-Img API + institutional pattern recognition
"""

import sys
sys.path.insert(0, '/Users/Shared/curtis/trader-curtis')

from live_chart_analyzer import get_chart, analyze_chart_for_patterns, get_api_status
from institutional_patterns import PATTERNS
from datetime import datetime

def scan_watchlist():
    """
    Proactively scan watchlist for institutional patterns
    Limited by API free tier — use wisely
    """
    
    # High priority tickers to scan
    watchlist = [
        'NEM',   # Gold play, current position
        'AEM',   # Gold play, current position  
        'MARA',  # Crypto, current position
        'PLTR',  # AI, current position
        'SPY',   # Market direction
        'QQQ',   # Tech direction
        'GLD',   # Gold ETF
    ]
    
    print("=" * 60)
    print("🔍 PROACTIVE CHART SCAN")
    print("=" * 60)
    print()
    
    # Check API limits
    status = get_api_status()
    calls_available = 50 - status['calls_today']
    
    print(f"API Calls Available Today: {calls_available}")
    print(f"Tickers to Scan: {len(watchlist)}")
    print()
    
    if calls_available < len(watchlist):
        print("⚠️ Not enough API calls for full scan")
        print("Prioritizing current positions...")
        watchlist = ['NEM', 'AEM', 'MARA', 'PLTR']  # Just positions
    
    opportunities = []
    
    for ticker in watchlist:
        print(f"\n📊 Analyzing {ticker}...")
        
        try:
            analysis = analyze_chart_for_patterns(ticker, "1h")
            
            if analysis:
                # Check if analysis mentions high-confidence pattern
                if any(pattern in analysis.upper() for pattern in ['QML', 'LIQUIDITY', 'ORDER BLOCK', 'STRONG']):
                    opportunities.append({
                        'ticker': ticker,
                        'analysis': analysis,
                        'confidence': 'HIGH'
                    })
                    print(f"  ✅ HIGH CONFIDENCE pattern found")
                else:
                    print(f"  ⚪ No clear pattern")
            else:
                print(f"  ❌ Analysis failed")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Report
    print("\n" + "=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)
    
    if opportunities:
        print(f"\n🎯 {len(opportunities)} HIGH CONFIDENCE setups found:")
        for opp in opportunities:
            print(f"\n  {opp['ticker']}:")
            print(f"  {opp['analysis'][:200]}...")
    else:
        print("\n⚪ No high-confidence patterns detected")
    
    return opportunities

if __name__ == '__main__':
    scan_watchlist()
