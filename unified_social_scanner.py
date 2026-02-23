#!/usr/bin/env python3
"""
Unified Social Scanner - X/Twitter, Reddit, StockTwits
Uses Grok API + Bird CLI + Reddit public API
"""

import os
import sys
import json
import sqlite3
import subprocess
import requests
from datetime import datetime
from pathlib import Path

# Paths
VAULT_PATH = Path("/Users/Shared/curtis/trader-curtis")
DB_PATH = VAULT_PATH / "data" / "trades.db"
MEMORY_PATH = VAULT_PATH / "memory"

# API Keys
XAI_API_KEY = os.getenv('XAI_API_KEY')
BRAVE_API_KEY = os.getenv('BRAVE_API_KEY')

# Holdings to monitor
HOLDINGS = ['NEM', 'ASTS', 'MARA', 'PLTR', 'AEM']

class UnifiedSocialScanner:
    def __init__(self):
        self.xai_key = XAI_API_KEY
        self.results = []
        
    def scan_x_with_grok(self, ticker):
        """Use Grok API to search X/Twitter"""
        if not self.xai_key:
            return {"error": "No XAI_API_KEY"}
        
        try:
            response = requests.post(
                'https://api.x.ai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.xai_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'grok-3',
                    'messages': [
                        {'role': 'system', 'content': 'You have real-time X/Twitter search access. Search for stock-related posts and analyze sentiment.'},
                        {'role': 'user', 'content': f'Search X/Twitter for ${ticker} stock posts from last 24 hours. Return JSON: {{"sentiment_score": 0-100, "bullish_count": N, "bearish_count": N, "posts": [{{"user": "...", "text": "...", "sentiment": "bullish/bearish/neutral"}}]}}'}
                    ]
                },
                timeout=45
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                # Extract JSON
                try:
                    if '```json' in content:
                        json_str = content.split('```json')[1].split('```')[0]
                    elif '```' in content:
                        json_str = content.split('```')[1].split('```')[0]
                    else:
                        json_str = content
                    return json.loads(json_str)
                except:
                    return {"sentiment_score": 50, "posts": [], "raw": content[:200]}
            else:
                return {"error": f"API error {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def scan_reddit(self, ticker):
        """Use existing reddit-scanner.js"""
        try:
            result = subprocess.run(
                ['node', str(VAULT_PATH / 'reddit-scanner.js')],
                capture_output=True, text=True, timeout=30
            )
            
            # Parse output for mentions of our ticker
            mentions = 0
            upvotes = 0
            for line in result.stdout.split('\n'):
                if f'${ticker}' in line or ticker in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        mentions += 1
                        # Extract upvotes if present
                        for part in parts:
                            if '⬆️' in part:
                                try:
                                    upvotes += int(part.replace('⬆️', ''))
                                except:
                                    pass
            
            return {
                "mentions": mentions,
                "upvotes": upvotes,
                "raw_output": result.stdout[:500]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def scan_stocktwits_with_grok(self, ticker):
        """Use Grok to search StockTwits sentiment"""
        if not self.xai_key:
            return {"sentiment_score": 50}
        
        try:
            response = requests.post(
                'https://api.x.ai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.xai_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'grok-3',
                    'messages': [
                        {'role': 'user', 'content': f'What is the current sentiment on StockTwits for ${ticker}? Are traders bullish or bearish? Return JSON: {{"sentiment_score": 0-100, "bullish_pct": N, "bearish_pct": N, "trend": "up/down/flat"}}'}
                    ]
                },
                timeout=45
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                try:
                    if '```json' in content:
                        json_str = content.split('```json')[1].split('```')[0]
                    elif '```' in content:
                        json_str = content.split('```')[1].split('```')[0]
                    else:
                        json_str = content
                    return json.loads(json_str)
                except:
                    return {"sentiment_score": 50, "raw": content[:200]}
            return {"sentiment_score": 50}
        except:
            return {"sentiment_score": 50}
    
    def scan_ticker(self, ticker):
        """Scan all sources for a ticker"""
        print(f"\n🔍 {ticker}")
        print("  📱 X/Twitter (Grok)...")
        x_data = self.scan_x_with_grok(ticker)
        
        print("  👽 Reddit...")
        reddit_data = self.scan_reddit(ticker)
        
        print("  📊 StockTwits (Grok)...")
        st_data = self.scan_stocktwits_with_grok(ticker)
        
        # Calculate overall sentiment
        scores = []
        if 'sentiment_score' in x_data and x_data['sentiment_score']:
            scores.append(x_data['sentiment_score'])
        if 'sentiment_score' in st_data:
            scores.append(st_data['sentiment_score'])
        
        # Reddit contribution based on mentions
        if reddit_data.get('mentions', 0) > 0:
            reddit_score = min(50 + (reddit_data['mentions'] * 5), 90)
            scores.append(reddit_score)
        
        overall = round(sum(scores) / len(scores)) if scores else 50
        
        result = {
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "x_sentiment": x_data.get('sentiment_score', 50),
            "x_posts": len(x_data.get('posts', [])),
            "reddit_mentions": reddit_data.get('mentions', 0),
            "reddit_upvotes": reddit_data.get('upvotes', 0),
            "stocktwits_sentiment": st_data.get('sentiment_score', 50),
            "overall_sentiment": overall
        }
        
        self.results.append(result)
        return result
    
    def log_to_database(self, result):
        """Log to sentiment database"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS unified_social_sentiment (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT,
                    ticker TEXT,
                    overall_score INTEGER,
                    x_score INTEGER,
                    x_posts INTEGER,
                    reddit_mentions INTEGER,
                    reddit_upvotes INTEGER,
                    stocktwits_score INTEGER
                )
            ''')
            
            cursor.execute('''
                INSERT INTO unified_social_sentiment 
                (timestamp, ticker, overall_score, x_score, x_posts, reddit_mentions, reddit_upvotes, stocktwits_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result['timestamp'],
                result['ticker'],
                result['overall_sentiment'],
                result['x_sentiment'],
                result['x_posts'],
                result['reddit_mentions'],
                result['reddit_upvotes'],
                result['stocktwits_sentiment']
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"  ❌ DB error: {e}")
            return False
    
    def log_to_memory(self):
        """Log results to daily memory file"""
        today = datetime.now().strftime("%Y-%m-%d")
        time = datetime.now().strftime("%H:%M")
        memory_file = MEMORY_PATH / f"sentiment-{today}.md"
        
        content = f"""# Social Sentiment Scan - {today} {time}

## Holdings Sentiment (Grok + Reddit + StockTwits)

| Ticker | Overall | X | Reddit | ST | Signal |
|--------|---------|---|--------|-----|--------|
"""
        
        for r in self.results:
            emoji = "🟢" if r['overall_sentiment'] > 60 else "🔴" if r['overall_sentiment'] < 40 else "⚪"
            signal = "BULLISH" if r['overall_sentiment'] > 60 else "BEARISH" if r['overall_sentiment'] < 40 else "NEUTRAL"
            content += f"| {r['ticker']} | {r['overall_sentiment']} {emoji} | {r['x_sentiment']} | {r['reddit_mentions']} mentions | {r['stocktwits_sentiment']} | {signal} |\n"
        
        content += """
## Notes
- X/Twitter: Real-time posts via Grok API
- Reddit: r/wallstreetbets, r/stocks, r/investing
- StockTwits: Trader sentiment via Grok

---
"""
        
        MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        with open(memory_file, 'a') as f:
            f.write(content)
        
        print(f"\n📝 Logged to {memory_file}")
    
    def run_scan(self):
        """Run complete scan"""
        print("=" * 70)
        print("🤖 UNIFIED SOCIAL SCANNER")
        print("Sources: X/Twitter (Grok) + Reddit + StockTwits")
        print("=" * 70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}")
        print(f"Holdings: {', '.join(HOLDINGS)}")
        print()
        
        if not self.xai_key:
            print("❌ XAI_API_KEY not set - X and StockTwits scanning disabled")
            print("Set with: export XAI_API_KEY='your_key'")
            return
        
        # Scan all holdings
        for ticker in HOLDINGS:
            result = self.scan_ticker(ticker)
            self.log_to_database(result)
            
            emoji = "🟢" if result['overall_sentiment'] > 60 else "🔴" if result['overall_sentiment'] < 40 else "⚪"
            print(f"  → Overall: {result['overall_sentiment']}/100 {emoji}")
        
        # Summary
        print("\n" + "=" * 70)
        print("📊 SUMMARY")
        print("=" * 70)
        
        for r in self.results:
            emoji = "🟢" if r['overall_sentiment'] > 60 else "🔴" if r['overall_sentiment'] < 40 else "⚪"
            print(f"{emoji} {r['ticker']}: {r['overall_sentiment']}/100")
        
        # Alerts
        bearish = [r for r in self.results if r['overall_sentiment'] < 40]
        bullish = [r for r in self.results if r['overall_sentiment'] > 60]
        neutral = [r for r in self.results if 40 <= r['overall_sentiment'] <= 60]
        
        if bearish:
            print(f"\n🔴 BEARISH: {', '.join([r['ticker'] for r in bearish])}")
        if bullish:
            print(f"\n🟢 BULLISH: {', '.join([r['ticker'] for r in bullish])}")
        if neutral:
            print(f"\n⚪ NEUTRAL ({len(neutral)}): {', '.join([r['ticker'] for r in neutral])}")
            print("   ⚠️  Remember: NEUTRAL sentiment = NO NEW TRADES")
        
        self.log_to_memory()
        print("\n✅ Scan complete!")


def main():
    scanner = UnifiedSocialScanner()
    scanner.run_scan()

if __name__ == '__main__':
    main()
