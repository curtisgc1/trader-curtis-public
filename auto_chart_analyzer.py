#!/usr/bin/env python3
"""
Auto Chart Analyzer — Proactive Chart Analysis
Uses available APIs to fetch and analyze charts automatically
"""

import os
import json
import base64
import requests
from datetime import datetime
from pathlib import Path

# APIs we have
ALPACA_API_KEY = os.environ.get('ALPACA_API_KEY')
ALPACA_SECRET = os.environ.get('ALPACA_SECRET_KEY')
XAI_API_KEY = os.environ.get('XAI_API_KEY')
BRAVE_API_KEY = os.environ.get('BRAVE_API_KEY')

def get_chart_via_alpaca(ticker, timeframe='1H', limit=100):
    """
    Get chart data from Alpaca (candles)
    """
    url = f"https://data.alpaca.markets/v2/stocks/{ticker}/bars"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET
    }
    params = {
        "timeframe": timeframe,
        "limit": limit,
        "feed": "iex"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            bars = data.get('bars', [])
            return bars
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    
    return None

def analyze_chart_with_grok(ticker, bars, sentiment_score):
    """
    Send chart data to Grok for pattern analysis
    """
    if not bars or len(bars) < 20:
        return None
    
    # Format recent price action for Grok
    recent_bars = bars[-20:]  # Last 20 candles
    price_summary = []
    
    for bar in recent_bars:
        price_summary.append({
            'o': bar['o'],
            'h': bar['h'],
            'l': bar['l'],
            'c': bar['c'],
            'v': bar['v']
        })
    
    # Create prompt for Grok
    prompt = f"""
Analyze this price data for {ticker} and identify institutional patterns:

Recent Price Action (last 20 candles):
{json.dumps(price_summary, indent=2)}

Current Sentiment Score: {sentiment_score}/100

Identify:
1. Pattern present (QML, Liquidity Grab, S/D Flip, Fakeout, Compression, etc.)
2. Key support and resistance levels
3. Where liquidity pools are likely sitting
4. Trade direction (bullish/bearish/neutral)
5. Entry zone, stop loss, target
6. Confidence level (high/medium/low)

Return structured analysis.
"""
    
    try:
        response = requests.post(
            "https://api.x.ai/v1/grok/completions",
            headers={"Authorization": f"Bearer {XAI_API_KEY}"},
            json={
                "model": "grok",
                "prompt": prompt,
                "max_tokens": 1000
            }
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['text']
    except Exception as e:
        print(f"Grok analysis error: {e}")
    
    return None

def proactive_scan_and_analyze():
    """
    Proactively scan for opportunities and analyze charts
    """
    # Tickers to monitor (from our positions + watchlist)
    tickers = ['NEM', 'AEM', 'MARA', 'PLTR', 'GLD', 'SPY', 'QQQ']
    
    opportunities = []
    
    for ticker in tickers:
        print(f"\n📊 Analyzing {ticker}...")
        
        # Get chart data
        bars = get_chart_via_alpaca(ticker, timeframe='1H', limit=50)
        
        if bars:
            # Get sentiment (placeholder - would call sentiment scanner)
            sentiment = 65  # Mock sentiment
            
            # Analyze with Grok
            analysis = analyze_chart_with_grok(ticker, bars, sentiment)
            
            if analysis:
                opportunities.append({
                    'ticker': ticker,
                    'sentiment': sentiment,
                    'analysis': analysis,
                    'timestamp': datetime.now().isoformat()
                })
                
                print(f"  ✅ Pattern identified")
                print(f"  Analysis: {analysis[:200]}...")
        else:
            print(f"  ❌ No data available")
    
    return opportunities

def generate_chart_url(ticker, timeframe='1h'):
    """
    Generate TradingView chart URL for manual viewing
    """
    return f"https://www.tradingview.com/chart/?symbol={ticker}&interval={timeframe}"

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 AUTO CHART ANALYZER")
    print("=" * 60)
    print()
    print("Available:")
    print("  • Alpaca API — Market data & trading")
    print("  • Grok API — AI pattern analysis")
    print("  • Brave API — Web search")
    print()
    print("NEED FOR FULL AUTO-CHART:")
    print("  • TradingView API (chart screenshots)")
    print("  • OR Polygon.io (advanced charts)")
    print("  • OR Yahoo Finance (free data)")
    print()
    print("Current workflow:")
    print("  1. Alpaca fetches price data (candles)")
    print("  2. Grok analyzes for patterns")
    print("  3. Sentiment confirms direction")
    print("  4. Execute if all align")
    print()
    
    # Run proactive scan
    print("Running proactive scan...")
    ops = proactive_scan_and_analyze()
    
    if ops:
        print(f"\n✅ Found {len(ops)} opportunities")
        for op in ops:
            print(f"  {op['ticker']}: {op['analysis'][:100]}...")
    else:
        print("\n⚠️ No clear patterns found")
