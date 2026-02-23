#!/usr/bin/env python3
"""
Trader Curtis - 2X Daily Sentiment Scanner & Auto-Trader
Runs at 6:30 AM and 2:00 PM PST on trading days
"""

import subprocess
import sqlite3
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trades.db"
ENV_PATH = Path(__file__).parent / ".env"

def load_env():
    """Load environment variables"""
    env = {}
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env[key] = val
    return env

def get_alpaca_positions():
    """Get current positions from Alpaca"""
    env = load_env()
    api_key = env.get('ALPACA_API_KEY')
    secret = env.get('ALPACA_SECRET_KEY')
    base_url = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret
    }
    
    try:
        r = requests.get(f"{base_url}/v2/positions", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"❌ Alpaca error: {e}")
    return []

def run_reddit_scan():
    """Run Reddit sentiment scan"""
    print("🔍 Scanning Reddit...")
    try:
        result = subprocess.run(
            ["node", str(Path(__file__).parent / "reddit-scanner.js")],
            capture_output=True, text=True, timeout=30
        )
        # Parse output for mentions of our holdings
        holdings = ['NEM', 'ASTS', 'MARA', 'PLTR', 'AEM']
        mentions = {h: 0 for h in holdings}
        
        for line in result.stdout.split('\n'):
            for ticker in holdings:
                if f'${ticker}' in line or ticker in line:
                    mentions[ticker] += 1
        
        return mentions
    except Exception as e:
        print(f"❌ Reddit scan error: {e}")
        return {}

def run_bird_scan():
    """Run Bird (Twitter/X) scan for market chatter"""
    print("🔍 Scanning X/Twitter...")
    try:
        # Use bird CLI if available
        result = subprocess.run(
            ["bird", "search", "NEM OR ASTS OR MARA OR PLTR OR AEM", "-n", "10"],
            capture_output=True, text=True, timeout=30
        )
        # Simple mention count
        holdings = ['NEM', 'ASTS', 'MARA', 'PLTR', 'AEM']
        mentions = {h: 0 for h in holdings}
        
        for line in result.stdout.split('\n'):
            for ticker in holdings:
                if ticker in line.upper():
                    mentions[ticker] += 1
        
        return mentions
    except Exception as e:
        print(f"⚠️ Bird scan unavailable: {e}")
        return {}

def calculate_sentiment_scores(reddit_mentions, bird_mentions):
    """Calculate sentiment scores (0-100) for each holding"""
    holdings = ['NEM', 'ASTS', 'MARA', 'PLTR', 'AEM']
    scores = {}
    
    for ticker in holdings:
        reddit_count = reddit_mentions.get(ticker, 0)
        bird_count = bird_mentions.get(ticker, 0)
        
        # Simple scoring: base 50, +10 per mention (capped at 90)
        score = min(50 + (reddit_count * 10) + (bird_count * 5), 90)
        scores[ticker] = score
    
    return scores

def check_existing_stop(symbol):
    """Check if position has stop loss"""
    env = load_env()
    api_key = env.get('ALPACA_API_KEY')
    secret = env.get('ALPACA_SECRET_KEY')
    base_url = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret
    }
    
    try:
        r = requests.get(f"{base_url}/v2/orders?status=open", headers=headers, timeout=10)
        if r.status_code == 200:
            orders = r.json()
            for order in orders:
                if order.get('symbol') == symbol and order.get('type') == 'stop':
                    return True, order.get('stop_price')
    except:
        pass
    return False, None

def place_stop_loss(symbol, qty, stop_price):
    """Place stop loss order"""
    env = load_env()
    api_key = env.get('ALPACA_API_KEY')
    secret = env.get('ALPACA_SECRET_KEY')
    base_url = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json"
    }
    
    order = {
        "symbol": symbol,
        "qty": str(qty),
        "side": "sell",
        "type": "stop",
        "time_in_force": "gtc",
        "stop_price": str(stop_price)
    }
    
    try:
        r = requests.post(f"{base_url}/v2/orders", headers=headers, json=order, timeout=10)
        return r.status_code == 200
    except:
        return False

def auto_trade_logic(positions, sentiment_scores):
    """Execute auto-trading based on sentiment and positions"""
    actions_taken = []
    
    for pos in positions:
        symbol = pos['symbol']
        qty = int(pos['qty'])
        current = float(pos['current_price'])
        entry = float(pos['avg_entry_price'])
        pnl_pct = (current - entry) / entry * 100
        sentiment = sentiment_scores.get(symbol, 50)
        
        # Check if stop exists
        has_stop, stop_price = check_existing_stop(symbol)
        
        print(f"\n📊 {symbol}:")
        print(f"   Price: ${current:.2f} (Entry: ${entry:.2f})")
        print(f"   P&L: {pnl_pct:+.1f}%")
        print(f"   Sentiment: {sentiment}/100")
        print(f"   Stop: {'✅ @ $' + str(stop_price) if has_stop else '❌ None'}")
        
        # ACTION 1: Add stop loss if missing
        if not has_stop:
            # Calculate stop (10% below entry, or 15% if already down)
            if pnl_pct < -10:
                stop = round(entry * 0.85, 2)  # Wider stop if underwater
            else:
                stop = round(entry * 0.90, 2)  # Normal 10% stop
            
            if place_stop_loss(symbol, qty, stop):
                actions_taken.append(f"🛑 {symbol}: Added stop @ ${stop}")
                print(f"   ✅ ACTION: Stop placed @ ${stop}")
            else:
                print(f"   ❌ Failed to place stop")
        
        # ACTION 2: Trim if high sentiment bearish and in profit
        if sentiment < 30 and pnl_pct > 5:
            print(f"   ⚠️ BEARISH sentiment + profit - consider trim")
            actions_taken.append(f"📉 {symbol}: Bearish sentiment ({sentiment}), consider trim")
        
        # ACTION 3: Alert if bullish but underwater
        if sentiment > 70 and pnl_pct < -5:
            print(f"   ⚠️ BULLISH sentiment but underwater - monitor for bounce")
            actions_taken.append(f"📈 {symbol}: Bullish sentiment ({sentiment}) despite loss")
    
    return actions_taken

def log_sentiment_scan(scores, actions):
    """Log scan results to memory"""
    memory_dir = Path(__file__).parent / "memory"
    memory_dir.mkdir(exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    time = datetime.now().strftime("%H:%M")
    
    memory_file = memory_dir / f"sentiment-{today}.md"
    
    content = f"""# Sentiment Scan - {today} {time}

## Sentiment Scores (0-100)

| Ticker | Score | Interpretation |
|--------|-------|----------------|
"""
    
    for ticker, score in scores.items():
        interp = "🟢 Bullish" if score > 60 else "🔴 Bearish" if score < 40 else "⚪ Neutral"
        content += f"| {ticker} | {score} | {interp} |\n"
    
    content += f"""
## Actions Taken

"""
    if actions:
        for action in actions:
            content += f"- {action}\n"
    else:
        content += "- No trades executed\n"
    
    content += f"""
---
*Auto-generated by 2X Daily Sentiment Scanner*
"""
    
    with open(memory_file, 'a') as f:
        f.write(content)
    
    print(f"\n📝 Logged to {memory_file}")

def main():
    print("=" * 70)
    print("🤖 TRADER CURTIS - 2X DAILY SENTIMENT SCAN + AUTO-TRADE")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}")
    print()
    
    # Get positions
    positions = get_alpaca_positions()
    if not positions:
        print("ℹ️ No positions found or API error")
        return
    
    print(f"📊 {len(positions)} positions to analyze\n")
    
    # Run sentiment scans
    reddit_mentions = run_reddit_scan()
    bird_mentions = run_bird_scan()
    
    # Calculate scores
    sentiment_scores = calculate_sentiment_scores(reddit_mentions, bird_mentions)
    
    print("\n📈 SENTIMENT SCORES:")
    for ticker, score in sentiment_scores.items():
        emoji = "🟢" if score > 60 else "🔴" if score < 40 else "⚪"
        print(f"   {emoji} {ticker}: {score}/100")
    
    # Execute auto-trade logic
    print("\n" + "=" * 70)
    print("⚡ AUTO-TRADE EXECUTION")
    print("=" * 70)
    
    actions = auto_trade_logic(positions, sentiment_scores)
    
    # Log results
    log_sentiment_scan(sentiment_scores, actions)
    
    print("\n" + "=" * 70)
    print("✅ SCAN COMPLETE")
    print("=" * 70)
    
    if actions:
        print("\n📋 Actions Taken:")
        for action in actions:
            print(f"   {action}")
    else:
        print("\n📋 No actions needed - all positions protected")

if __name__ == '__main__':
    main()
