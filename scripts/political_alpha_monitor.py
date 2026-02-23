#!/usr/bin/env python3
"""
Political Alpha Monitor - Trump & Bessent Social Media Scanner
INTEGRATED with sentiment tracking system
"""

import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import re

# Configuration
VAULT_PATH = Path("/Users/Shared/curtis/trader-curtis")
LOGS_PATH = VAULT_PATH / "logs"
ALERTS_PATH = VAULT_PATH / "alerts"
POSTS_DB = VAULT_PATH / "memory" / "policy_posts.jsonl"
DB_PATH = VAULT_PATH / "data" / "trades.db"

# Import sentiment tracking functions
sys.path.insert(0, str(VAULT_PATH))

def log_sentiment_source(source_name, ticker, sentiment, confidence, note=""):
    """Log political source to sentiment database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Ensure table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS political_sentiment (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                source TEXT,
                ticker TEXT,
                sentiment TEXT,
                confidence INTEGER,
                note TEXT,
                verified INTEGER DEFAULT 0,
                outcome TEXT
            )
        ''')
        
        cursor.execute('''
            INSERT INTO political_sentiment (timestamp, source, ticker, sentiment, confidence, note)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), source_name, ticker, sentiment, confidence, note))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Failed to log sentiment: {e}")
        return False

def get_sector_tickers(keywords):
    """Get affected tickers from keywords for sentiment tracking"""
    ticker_map = {
        'china': ['FXI', 'MCHI', 'KWEB', 'BABA', 'JD', 'PDD'],
        'tariff': ['XLI', 'XLB', 'XLK', 'QQQ', 'SPY'],
        'treasury': ['TLT', 'TMF', 'TBT', 'IEF'],
        'dollar': ['UUP', 'FXE', 'FXY'],
        'gold': ['GLD', 'GDX', 'NUGT', 'IAU'],
        'oil': ['USO', 'XLE', 'XOP', 'XOM', 'CVX'],
        'bitcoin': ['BTC', 'MSTR', 'COIN', 'RIOT', 'BITO'],
        'crypto': ['BTC', 'MSTR', 'COIN', 'RIOT'],
    }
    
    tickers = set()
    for kw in keywords:
        if kw in ticker_map:
            tickers.update(ticker_map[kw])
    return list(tickers)

# Market-moving keywords with sentiment implications
MARKET_KEYWORDS = {
    # Tariffs - BEARISH for China/Trade
    "tariff": {"weight": 10, "sentiment": "bearish", "sectors": ["china", "trade"]},
    "tariffs": {"weight": 10, "sentiment": "bearish", "sectors": ["china", "trade"]},
    "trade war": {"weight": 10, "sentiment": "bearish", "sectors": ["china", "trade"]},
    "china tariff": {"weight": 12, "sentiment": "bearish", "sectors": ["china"]},
    
    # Treasury - Context dependent
    "treasury": {"weight": 8, "sentiment": "neutral", "sectors": ["bonds"]},
    "yield": {"weight": 8, "sentiment": "neutral", "sectors": ["bonds"]},
    "10-year": {"weight": 8, "sentiment": "neutral", "sectors": ["bonds"]},
    "30-year": {"weight": 8, "sentiment": "neutral", "sectors": ["bonds"]},
    
    # Dollar - Context dependent
    "dollar": {"weight": 8, "sentiment": "neutral", "sectors": ["currency"]},
    "strong dollar": {"weight": 9, "sentiment": "bearish", "sectors": ["intl"]},
    "weak dollar": {"weight": 9, "sentiment": "bullish", "sectors": ["commodities"]},
    
    # Commodities
    "gold": {"weight": 6, "sentiment": "bullish", "sectors": ["gold"]},
    "silver": {"weight": 6, "sentiment": "bullish", "sectors": ["gold"]},
    "oil": {"weight": 6, "sentiment": "bullish", "sectors": ["oil"]},
    
    # Crypto
    "bitcoin": {"weight": 5, "sentiment": "bullish", "sectors": ["crypto"]},
    "crypto": {"weight": 5, "sentiment": "bullish", "sectors": ["crypto"]},
    
    # Market
    "crash": {"weight": 10, "sentiment": "bearish", "sectors": ["broad"]},
    "bear market": {"weight": 8, "sentiment": "bearish", "sectors": ["broad"]},
    "bull market": {"weight": 6, "sentiment": "bullish", "sectors": ["broad"]},
    "rally": {"weight": 5, "sentiment": "bullish", "sectors": ["broad"]},
}

class PoliticalMonitor:
    def __init__(self):
        self.seen_posts = self._load_seen_posts()
        
    def _load_seen_posts(self) -> set:
        """Load previously seen post IDs"""
        seen = set()
        if POSTS_DB.exists():
            with open(POSTS_DB) as f:
                for line in f:
                    try:
                        post = json.loads(line)
                        seen.add(post.get('id', ''))
                    except:
                        continue
        return seen
    
    def _log_post(self, post: Dict):
        """Log post to database"""
        with open(POSTS_DB, 'a') as f:
            f.write(json.dumps(post) + '\n')
    
    def _analyze_content(self, text: str) -> Dict:
        """Analyze content for impact and sentiment"""
        text_lower = text.lower()
        score = 0
        matched_keywords = []
        sentiments = []
        sectors = []
        
        for keyword, data in MARKET_KEYWORDS.items():
            if keyword in text_lower:
                score += data["weight"]
                matched_keywords.append(keyword)
                sentiments.append(data["sentiment"])
                sectors.extend(data["sectors"])
        
        # Determine overall sentiment
        if sentiments.count("bearish") > sentiments.count("bullish"):
            overall_sentiment = "BEARISH"
        elif sentiments.count("bullish") > sentiments.count("bearish"):
            overall_sentiment = "BULLISH"
        else:
            overall_sentiment = "NEUTRAL"
        
        # Get affected tickers
        tickers = get_sector_tickers(matched_keywords)
        
        return {
            "score": score,
            "keywords": matched_keywords,
            "sentiment": overall_sentiment,
            "sectors": list(set(sectors)),
            "tickers": tickers
        }
    
    def _generate_alert(self, source: str, text: str, analysis: Dict) -> str:
        """Generate trading alert with sentiment data"""
        tickers = analysis["tickers"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S PST")
        score = analysis["score"]
        
        # Determine urgency
        if score >= 15:
            urgency = "🔥 CRITICAL"
            confidence = 90
        elif score >= 10:
            urgency = "⚠️ HIGH"
            confidence = 75
        elif score >= 8:
            urgency = "⚡ MEDIUM"
            confidence = 60
        else:
            urgency = "ℹ️ LOW"
            confidence = 40
        
        alert = f"""
🔴 POLICY ALPHA ALERT - {timestamp}

Source: {source}
Impact Score: {score}/50 {urgency}
Sentiment: {analysis['sentiment']} (Confidence: {confidence}%)

Content Preview:
{text[:300]}{'...' if len(text) > 300 else ''}

Matched Keywords: {', '.join(analysis['keywords'])}
Affected Sectors: {', '.join(analysis['sectors'])}

Tickers to Watch: {', '.join(tickers) if tickers else 'None mapped'}

Suggested Actions:
"""
        
        # Add ticker-specific suggestions
        if analysis['sentiment'] == "BEARISH":
            for ticker in tickers[:3]:
                alert += f"- Consider trimming {ticker} or adding puts\n"
        elif analysis['sentiment'] == "BULLISH":
            for ticker in tickers[:3]:
                alert += f"- Monitor {ticker} for entry opportunity\n"
        else:
            alert += "- Monitor for directional clarity\n"
        
        alert += "- Check current positions\n- Set alerts for follow-up posts\n"
        
        return alert
    
    def _save_alert(self, alert: str, score: int, analysis: Dict):
        """Save alert and log to sentiment system"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        level = "CRITICAL" if score >= 15 else "HIGH" if score >= 10 else "MEDIUM"
        alert_file = ALERTS_PATH / f"policy-alert-{level}-{timestamp}.md"
        
        ALERTS_PATH.mkdir(parents=True, exist_ok=True)
        with open(alert_file, 'w') as f:
            f.write(alert)
        
        # Log to sentiment database for source tracking
        source_name = f"Political/{analysis.get('source_type', 'Unknown')}"
        for ticker in analysis.get('tickers', []):
            log_sentiment_source(
                source_name=source_name,
                ticker=ticker,
                sentiment=analysis['sentiment'].lower(),
                confidence=min(score * 2, 95),  # Convert score to confidence
                note=f"Keywords: {', '.join(analysis.get('keywords', []))}"
            )
        
        return alert_file
    
    def process_post(self, post_id: str, source: str, text: str, timestamp: str, url: str = "") -> Optional[Dict]:
        """Process a single post"""
        if post_id in self.seen_posts:
            return None
        
        self.seen_posts.add(post_id)
        
        analysis = self._analyze_content(text)
        
        post_record = {
            "id": post_id,
            "source": source,
            "text": text,
            "timestamp": timestamp,
            "url": url,
            "impact_score": analysis["score"],
            "sentiment": analysis["sentiment"],
            "keywords": analysis["keywords"],
            "tickers": analysis["tickers"],
            "detected_at": datetime.now().isoformat(),
        }
        
        self._log_post(post_record)
        
        # Generate alert if significant
        if analysis["score"] >= 8:
            alert_text = self._generate_alert(source, text, analysis)
            alert_file = self._save_alert(alert_text, analysis["score"], analysis)
            
            print(alert_text)
            print(f"\n📄 Alert saved: {alert_file}")
            
            post_record["alert_file"] = str(alert_file)
            post_record["alerted"] = True
            
            # Also log to clawvault memory
            self._clawvault_log(analysis, source, text)
        else:
            post_record["alerted"] = False
        
        return post_record
    
    def _clawvault_log(self, analysis: Dict, source: str, text: str):
        """Log to ClawVault for long-term memory"""
        try:
            import subprocess
            
            # Log as fact
            subprocess.run([
                "clawvault", "remember", "fact",
                f"Political post: {analysis['sentiment']} on {', '.join(analysis['tickers'][:3])}",
                "--content", f"Source: {source}, Keywords: {', '.join(analysis['keywords'])}, Score: {analysis['score']}"
            ], capture_output=True)
            
            # If high impact, log as decision
            if analysis['score'] >= 15:
                subprocess.run([
                    "clawvault", "remember", "decision",
                    f"CRITICAL political alert: {source}",
                    "--content", f"Score: {analysis['score']}, Sentiment: {analysis['sentiment']}, Tickers: {', '.join(analysis['tickers'])}"
                ], capture_output=True)
                
        except Exception as e:
            print(f"⚠️ ClawVault log failed: {e}")
    
    def scan_all_sources(self):
        """Scan all configured sources"""
        print(f"🚀 Political Alpha Monitor Started at {datetime.now()}")
        print(f"📊 Tracking {len(self.seen_posts)} previous posts")
        print("-" * 60)
        
        all_new_posts = []
        
        # These would be implemented with actual API calls
        # For now, framework is ready
        
        print("\n📱 Scanning sources...")
        print("⚠️  API credentials needed for live scanning")
        print("   - Truth Social: No API, need RSS/scraper")
        print("   - X/Twitter: Requires X API v2 Basic tier ($100/month)")
        
        return all_new_posts
    
    def generate_sentiment_report(self):
        """Generate report of political sentiment impact"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT source, ticker, sentiment, COUNT(*) as count 
                FROM political_sentiment 
                WHERE timestamp > datetime('now', '-7 days')
                GROUP BY source, ticker, sentiment
                ORDER BY count DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            if results:
                print("\n📊 Political Sentiment Last 7 Days:")
                for row in results:
                    print(f"   {row[0]} | {row[1]} | {row[2]} | {row[3]} posts")
            else:
                print("\n📊 No political sentiment data yet (API credentials needed)")
                
        except Exception as e:
            print(f"⚠️ Report error: {e}")

def main():
    monitor = PoliticalMonitor()
    monitor.scan_all_sources()
    monitor.generate_sentiment_report()
    
    print("\n" + "=" * 60)
    print("✅ Political Alpha Monitor Complete")
    print(f"⏰ Next run: {(datetime.now() + timedelta(minutes=15)).strftime('%H:%M')}")
    print("\n📝 To activate:")
    print("   1. Get X API v2 credentials")
    print("   2. Configure Truth Social access")
    print("   3. Add credentials to environment")

if __name__ == "__main__":
    main()
