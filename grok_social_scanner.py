#!/usr/bin/env python3
"""
Unified Social Media Scanner - Uses Grok API (xAI) for X/Twitter, Reddit, StockTwits
Integrates with existing sentiment tracking system
"""

import os
import sys
import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# Configuration
VAULT_PATH = Path("/Users/Shared/curtis/trader-curtis")
DB_PATH = VAULT_PATH / "data" / "trades.db"
MEMORY_PATH = VAULT_PATH / "memory"

# API Keys from environment
XAI_API_KEY = os.getenv('XAI_API_KEY')
BRAVE_API_KEY = os.getenv('BRAVE_API_KEY')

# Tickers to monitor (from existing holdings)
HOLDINGS = ['NEM', 'ASTS', 'MARA', 'PLTR', 'AEM', 'FXI', 'MCHI', 'TLT', 'GLD']

class GrokSocialScanner:
    def __init__(self):
        self.api_key = XAI_API_KEY
        self.base_url = "https://api.x.ai/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
    def search_x_posts(self, query, count=20):
        """Search X/Twitter posts using Grok's x_search tool"""
        try:
            # Grok API with x_search tool
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json={
                    "model": "grok-3",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You have access to the x_search tool. Use it to search X/Twitter for stock-related posts. Return results as structured JSON."
                        },
                        {
                            "role": "user",
                            "content": f"Search X/Twitter for posts about {query}. Focus on stock market sentiment, price predictions, and trading discussions. Return the last {count} relevant posts with username, text, timestamp, and implied sentiment (bullish/bearish/neutral)."
                        }
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "x_search",
                                "description": "Search X (Twitter) posts, users, and threads"
                            }
                        }
                    ]
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                # Try to parse JSON from content
                try:
                    # Look for JSON in the response
                    if '```json' in content:
                        json_str = content.split('```json')[1].split('```')[0]
                        return json.loads(json_str)
                    elif '```' in content:
                        json_str = content.split('```')[1].split('```')[0]
                        return json.loads(json_str)
                    else:
                        # Try to parse the whole content
                        return json.loads(content)
                except:
                    # Return raw content if JSON parsing fails
                    return {"raw_response": content, "posts": []}
            else:
                print(f"❌ X search failed: {response.status_code}")
                return {"posts": []}
                
        except Exception as e:
            print(f"❌ X search error: {e}")
            return {"posts": []}
    
    def search_reddit(self, query, subreddits=['wallstreetbets', 'stocks', 'investing']):
        """Search Reddit using Grok + web search"""
        try:
            subreddit_list = ' '.join([f"r/{s}" for s in subreddits])
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json={
                    "model": "grok-3",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Search Reddit {subreddit_list} for discussions about {query}. Find posts from the last 24 hours about stock price, earnings, or trading. Return JSON with: posts (list of dicts with subreddit, title, sentiment_score 0-100, upvotes, comments)"
                        }
                    ]
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                try:
                    if '```json' in content:
                        json_str = content.split('```json')[1].split('```')[0]
                        return json.loads(json_str)
                    elif '```' in content:
                        json_str = content.split('```')[1].split('```')[0]
                        return json.loads(json_str)
                    else:
                        return json.loads(content)
                except:
                    return {"raw_response": content, "posts": []}
            else:
                return {"posts": []}
                
        except Exception as e:
            print(f"❌ Reddit search error: {e}")
            return {"posts": []}
    
    def search_stocktwits(self, ticker):
        """Search StockTwits sentiment using Grok"""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json={
                    "model": "grok-3",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Search StockTwits for ${ticker} sentiment. What are traders saying? Is sentiment bullish or bearish? Return JSON with: sentiment_score (0-100), bullish_count, bearish_count, messages (list of recent sentiment)"
                        }
                    ]
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                try:
                    if '```json' in content:
                        json_str = content.split('```json')[1].split('```')[0]
                        return json.loads(json_str)
                    elif '```' in content:
                        json_str = content.split('```')[1].split('```')[0]
                        return json.loads(json_str)
                    else:
                        return json.loads(content)
                except:
                    return {"sentiment_score": 50, "raw": content}
            else:
                return {"sentiment_score": 50}
                
        except Exception as e:
            print(f"❌ StockTwits search error: {e}")
            return {"sentiment_score": 50}
    
    def scan_all_sources(self, ticker):
        """Scan all social sources for a ticker"""
        print(f"\n🔍 Scanning {ticker}...")
        
        results = {
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "x_posts": [],
            "reddit_posts": [],
            "stocktwits": {}
        }
        
        # Search X/Twitter
        print("  📱 Searching X/Twitter...")
        x_results = self.search_x_posts(f"${ticker} stock", count=10)
        if isinstance(x_results, dict) and 'posts' in x_results:
            results['x_posts'] = x_results['posts']
        
        # Search Reddit
        print("  👽 Searching Reddit...")
        reddit_results = self.search_reddit(ticker)
        if isinstance(reddit_results, dict) and 'posts' in reddit_results:
            results['reddit_posts'] = reddit_results['posts']
        
        # Search StockTwits
        print("  📊 Searching StockTwits...")
        st_results = self.search_stocktwits(ticker)
        results['stocktwits'] = st_results
        
        return results
    
    def calculate_overall_sentiment(self, results):
        """Calculate overall sentiment from all sources"""
        scores = []
        
        # X posts sentiment
        if results['x_posts']:
            x_scores = []
            for post in results['x_posts']:
                sentiment = post.get('sentiment', 'neutral')
                if sentiment == 'bullish':
                    x_scores.append(70)
                elif sentiment == 'bearish':
                    x_scores.append(30)
                else:
                    x_scores.append(50)
            if x_scores:
                scores.append(sum(x_scores) / len(x_scores))
        
        # Reddit sentiment
        if results['reddit_posts']:
            reddit_scores = [p.get('sentiment_score', 50) for p in results['reddit_posts']]
            if reddit_scores:
                scores.append(sum(reddit_scores) / len(reddit_scores))
        
        # StockTwits sentiment
        if results['stocktwits']:
            st_score = results['stocktwits'].get('sentiment_score', 50)
            scores.append(st_score)
        
        # Calculate average
        if scores:
            return round(sum(scores) / len(scores))
        return 50
    
    def log_to_database(self, ticker, sentiment_score, x_count, reddit_count, st_score):
        """Log sentiment to database for source tracking"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Ensure table exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS grok_social_sentiment (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT,
                    ticker TEXT,
                    overall_score INTEGER,
                    x_posts_count INTEGER,
                    reddit_posts_count INTEGER,
                    stocktwits_score INTEGER
                )
            ''')
            
            cursor.execute('''
                INSERT INTO grok_social_sentiment 
                (timestamp, ticker, overall_score, x_posts_count, reddit_posts_count, stocktwits_score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                ticker,
                sentiment_score,
                x_count,
                reddit_count,
                st_score
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Database error: {e}")
            return False
    
    def log_to_memory(self, results, sentiment_score):
        """Log to daily memory file"""
        today = datetime.now().strftime("%Y-%m-%d")
        time = datetime.now().strftime("%H:%M")
        memory_file = MEMORY_PATH / f"sentiment-{today}.md"
        
        ticker = results['ticker']
        emoji = "🟢" if sentiment_score > 60 else "🔴" if sentiment_score < 40 else "⚪"
        
        content = f"""
## Grok Social Scan - {ticker} @ {time}

**Overall Sentiment:** {emoji} {sentiment_score}/100

**Sources:**
- X/Twitter: {len(results['x_posts'])} posts
- Reddit: {len(results['reddit_posts'])} posts
- StockTwits: {results['stocktwits'].get('sentiment_score', 'N/A')}/100

**Sample Posts:**
"""
        
        # Add sample X posts
        for post in results['x_posts'][:3]:
            content += f"- X/@{post.get('username', 'unknown')}: {post.get('text', '')[:80]}...\n"
        
        # Add sample Reddit posts
        for post in results['reddit_posts'][:2]:
            content += f"- Reddit r/{post.get('subreddit', 'unknown')}: {post.get('title', '')[:80]}...\n"
        
        content += "\n---\n"
        
        MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        with open(memory_file, 'a') as f:
            f.write(content)
        
        print(f"📝 Logged to {memory_file}")


def main():
    print("=" * 70)
    print("🤖 GROK SOCIAL SCANNER - X, Reddit, StockTwits")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}")
    print()
    
    if not XAI_API_KEY:
        print("❌ XAI_API_KEY not found in environment")
        print("Add to ~/.zshenv: export XAI_API_KEY='your_key'")
        return
    
    scanner = GrokSocialScanner()
    
    # Scan all holdings
    all_results = []
    for ticker in HOLDINGS:
        results = scanner.scan_all_sources(ticker)
        sentiment = scanner.calculate_overall_sentiment(results)
        
        print(f"\n📊 {ticker} Sentiment: {sentiment}/100")
        
        # Log to database
        scanner.log_to_database(
            ticker=ticker,
            sentiment_score=sentiment,
            x_count=len(results['x_posts']),
            reddit_count=len(results['reddit_posts']),
            st_score=results['stocktwits'].get('sentiment_score', 50)
        )
        
        # Log to memory
        scanner.log_to_memory(results, sentiment)
        
        all_results.append({
            'ticker': ticker,
            'sentiment': sentiment,
            'x_posts': len(results['x_posts']),
            'reddit_posts': len(results['reddit_posts'])
        })
    
    # Summary
    print("\n" + "=" * 70)
    print("📈 SENTIMENT SUMMARY")
    print("=" * 70)
    
    for r in all_results:
        emoji = "🟢" if r['sentiment'] > 60 else "🔴" if r['sentiment'] < 40 else "⚪"
        print(f"{emoji} {r['ticker']}: {r['sentiment']}/100 (X:{r['x_posts']}, Reddit:{r['reddit_posts']})")
    
    # Check for alerts
    bearish = [r for r in all_results if r['sentiment'] < 40]
    bullish = [r for r in all_results if r['sentiment'] > 60]
    
    if bearish:
        print(f"\n🔴 BEARISH ALERTS: {', '.join([r['ticker'] for r in bearish])}")
    if bullish:
        print(f"\n🟢 BULLISH: {', '.join([r['ticker'] for r in bullish])}")
    
    print("\n✅ Scan complete!")


if __name__ == '__main__':
    main()
