#!/usr/bin/env python3
"""
Live Chart Analyzer — Using Chart-Img API
Analyzes charts for institutional patterns in real-time
"""

import os
import requests
import base64
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("CHART_IMG_API_KEY", "")
BASE_URL = "https://api.chart-img.com/v1/tradingview"

# Track API usage
USAGE_FILE = Path(__file__).parent / "data" / "chart_api_usage.json"

def log_usage():
    """Track API calls to stay within free tier"""
    import json
    usage = {"calls_today": 0, "total_calls": 0, "last_reset": datetime.now().isoformat()}
    
    if USAGE_FILE.exists():
        with open(USAGE_FILE) as f:
            usage = json.load(f)
    
    # Reset daily
    last_reset = datetime.fromisoformat(usage["last_reset"])
    if (datetime.now() - last_reset).days >= 1:
        usage["calls_today"] = 0
        usage["last_reset"] = datetime.now().isoformat()
    
    usage["calls_today"] += 1
    usage["total_calls"] += 1
    
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage, f)
    
    return usage["calls_today"], usage["total_calls"]

def get_chart(ticker, timeframe="1h", indicators=None):
    """
    Fetch chart image from API
    Free tier limits: ~100-1000 requests/month
    """
    calls_today, total_calls = log_usage()
    
    # Check limits (adjust based on actual provider limits)
    if calls_today > 50:  # Conservative daily limit
        print(f"⚠️ Daily API limit reached ({calls_today} calls)")
        return None
    
    url = f"{BASE_URL}/chart"
    
    params = {
        "symbol": ticker,
        "interval": timeframe,
        "key": API_KEY,
        "theme": "dark",
        "width": 800,
        "height": 600
    }
    
    if indicators:
        params["indicators"] = indicators
    
    try:
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            print(f"✅ Chart fetched: {ticker} ({timeframe}) | Call #{calls_today}")
            return response.content  # Image bytes
        else:
            print(f"❌ API Error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error fetching chart: {e}")
        return None

def analyze_chart_for_patterns(ticker, timeframe="1h"):
    """
    Fetch chart and analyze for institutional patterns
    """
    from image import analyze
    
    # Get chart image
    chart_bytes = get_chart(ticker, timeframe)
    
    if not chart_bytes:
        return None
    
    # Save temporarily
    temp_path = f"/tmp/chart_{ticker}_{datetime.now().strftime('%H%M%S')}.png"
    with open(temp_path, 'wb') as f:
        f.write(chart_bytes)
    
    # Analyze with image tool
    prompt = """Analyze this stock chart for institutional trading patterns:

1. Identify the pattern present (QML, Liquidity Grab, Supply/Demand Flip, Fakeout, Compression, Stop Hunt, Flag Limit, Institutional Reversal)
2. Map key support and resistance levels
3. Identify where liquidity pools are sitting (equal highs/lows, swing points)
4. Determine trend direction
5. Suggest entry zone, stop loss, and target
6. Rate confidence (High/Medium/Low)

Be specific about price levels."""
    
    analysis = analyze(prompt, temp_path)
    
    # Clean up temp file
    os.remove(temp_path)
    
    return analysis

def get_api_status():
    """Check API usage status"""
    import json
    
    if not USAGE_FILE.exists():
        return {"calls_today": 0, "total_calls": 0}
    
    with open(USAGE_FILE) as f:
        return json.load(f)

if __name__ == '__main__':
    import sys
    
    print("=" * 60)
    print("📊 LIVE CHART ANALYZER")
    print("=" * 60)
    print()
    
    # Check status
    status = get_api_status()
    print(f"API Usage Today: {status['calls_today']} calls")
    print(f"Total Calls: {status['total_calls']}")
    print(f"Free Tier: ~50 calls/day (conservative)")
    print()
    
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        timeframe = sys.argv[2] if len(sys.argv) > 2 else "1h"
        
        print(f"Fetching chart for {ticker} ({timeframe})...")
        analysis = analyze_chart_for_patterns(ticker, timeframe)
        
        if analysis:
            print("\n" + "=" * 60)
            print(f"ANALYSIS: {ticker}")
            print("=" * 60)
            print(analysis)
        else:
            print("❌ Failed to analyze chart")
    else:
        print("Usage: python3 live_chart_analyzer.py <TICKER> [TIMEFRAME]")
        print("Example: python3 live_chart_analyzer.py AAPL 1h")
        print()
        print("Available timeframes: 1m, 5m, 15m, 1h, 4h, 1d")
