#!/usr/bin/env python3
"""
Political Alpha Monitor - FREE Version
Uses Grok web search + news APIs + Reddit chatter
No $100/month X API needed!
"""

import os
import sys
import json
import sqlite3
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path

VAULT_PATH = Path("/Users/Shared/curtis/trader-curtis")
DB_PATH = VAULT_PATH / "data" / "trades.db"
ALERTS_PATH = VAULT_PATH / "alerts"
MEMORY_PATH = VAULT_PATH / "memory"

XAI_API_KEY = os.getenv('XAI_API_KEY')
BRAVE_API_KEY = os.getenv('BRAVE_API_KEY')

# Market-moving keywords
KEYWORDS = {
    'tariff': 10, 'tariffs': 10, 'china': 8, 'mexico': 8, 'canada': 8,
    'treasury': 8, 'yield': 8, 'dollar': 8, 'gold': 6, 'oil': 6,
    'bitcoin': 5, 'crypto': 5, 'trade war': 10, 'sanctions': 9
}

class FreePoliticalMonitor:
    def __init__(self):
        self.last_check = self._get_last_check()
        
    def _get_last_check(self):
        """Get timestamp of last check"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS political_checks (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT,
                    posts_found INTEGER
                )
            ''')
            cursor.execute('SELECT timestamp FROM political_checks ORDER BY id DESC LIMIT 1')
            row = cursor.fetchone()
            conn.close()
            if row:
                return datetime.fromisoformat(row[0])
        except:
            pass
        return datetime.now() - timedelta(hours=1)
    
    def search_grok_web(self, query):
        """Use Grok web search (free with your API key)"""
        if not XAI_API_KEY:
            return None
        
        try:
            response = requests.post(
                'https://api.x.ai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {XAI_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'grok-3',
                    'messages': [
                        {'role': 'system', 'content': 'You have web search access. Search for recent news and social media posts.'},
                        {'role': 'user', 'content': query}
                    ]
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            return None
        except Exception as e:
            print(f"❌ Grok search error: {e}")
            return None
    
    def search_brave_news(self, query):
        """Search Brave News API"""
        if not BRAVE_API_KEY:
            return None
        
        try:
            response = requests.get(
                'https://api.search.brave.com/res/v1/news/search',
                headers={'X-Subscription-Token': BRAVE_API_KEY},
                params={'q': query, 'count': 10, 'freshness': 'pd'},  # Past day
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"❌ Brave search error: {e}")
            return None
    
    def check_reddit_chatter(self):
        """Check if Trump/Bessent being discussed on Reddit"""
        try:
            result = subprocess.run(
                ['node', str(VAULT_PATH / 'reddit-scanner.js')],
                capture_output=True, text=True, timeout=30
            )
            
            # Look for Trump/Bessent mentions
            output = result.stdout.lower()
            mentions = []
            
            if 'trump' in output or 'bessent' in output:
                lines = result.stdout.split('\n')
                for line in lines:
                    if any(k in line.lower() for k in ['trump', 'bessent', 'tariff', 'treasury']):
                        mentions.append(line.strip())
            
            return mentions
        except:
            return []
    
    def check_trump_posts(self):
        """Check for Trump posts via web search"""
        print("🔍 Searching for Trump posts...")
        
        # Grok web search for Trump + market keywords
        grok_query = '''Search for any Trump posts or statements in the last hour about:
        - Tariffs, China, trade war
        - Treasury, yields, dollar
        - Gold, oil, bitcoin
        Return: post text, timestamp, platform (Truth Social/X), and market impact keywords found.'''
        
        grok_result = self.search_grok_web(grok_query)
        
        # Brave news search
        brave_result = self.search_brave_news('Trump tariff treasury market statement today')
        
        # Check Reddit
        reddit_mentions = self.check_reddit_chatter()
        
        # Analyze combined results
        combined_text = ""
        if grok_result:
            combined_text += grok_result.lower()
        if brave_result and 'results' in brave_result:
            for item in brave_result['results']:
                combined_text += f" {item.get('title', '')} {item.get('description', '')}".lower()
        
        # Score impact
        score = 0
        found_keywords = []
        for keyword, weight in KEYWORDS.items():
            if keyword in combined_text:
                score += weight
                found_keywords.append(keyword)
        
        return {
            'source': 'Trump',
            'grok_result': grok_result,
            'brave_result': brave_result,
            'reddit_mentions': reddit_mentions,
            'impact_score': score,
            'keywords': found_keywords,
            'timestamp': datetime.now().isoformat()
        }
    
    def check_bessent_posts(self):
        """Check for Bessent posts"""
        print("🔍 Searching for Bessent posts...")
        
        grok_query = '''Search for any Treasury Secretary Bessent statements in the last hour about:
        - Treasury yields, bonds, Fed
        - Dollar strength/weakness
        - Gold, commodities
        Return: statement text, timestamp, and market impact.'''
        
        grok_result = self.search_grok_web(grok_query)
        brave_result = self.search_brave_news('Bessent Treasury yield dollar statement')
        
        combined_text = ""
        if grok_result:
            combined_text += grok_result.lower()
        if brave_result and 'results' in brave_result:
            for item in brave_result['results']:
                combined_text += f" {item.get('title', '')} {item.get('description', '')}".lower()
        
        score = 0
        found_keywords = []
        for keyword, weight in KEYWORDS.items():
            if keyword in combined_text:
                score += weight
                found_keywords.append(keyword)
        
        return {
            'source': 'Bessent',
            'grok_result': grok_result,
            'brave_result': brave_result,
            'impact_score': score,
            'keywords': found_keywords,
            'timestamp': datetime.now().isoformat()
        }
    
    def generate_alert(self, data):
        """Generate alert if significant"""
        if data['impact_score'] < 8:
            return None
        
        score = data['impact_score']
        level = "CRITICAL" if score >= 15 else "HIGH" if score >= 10 else "MEDIUM"
        emoji = "🔥" if score >= 15 else "⚠️" if score >= 10 else "⚡"
        
        alert = f"""
{emoji} POLITICAL ALPHA ALERT - {level}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}
Source: {data['source']}
Impact Score: {score}/50

Keywords Detected: {', '.join(data['keywords'])}

Sources Checked:
- Grok web search: {'✓ Found' if data.get('grok_result') else '✗ No new posts'}
- Brave news: {'✓ Found' if data.get('brave_result') else '✗ No news'}
- Reddit chatter: {'✓ Detected' if data.get('reddit_mentions') else '✗ No discussion'}

"""
        
        if data.get('grok_result'):
            alert += f"\nGrok Summary:\n{data['grok_result'][:400]}...\n"
        
        if data.get('reddit_mentions'):
            alert += f"\nReddit Chatter:\n"
            for mention in data['reddit_mentions'][:3]:
                alert += f"- {mention}\n"
        
        alert += """
Suggested Actions:
- Check affected sector ETFs
- Review positions in related tickers
- Monitor for follow-up statements
- Consider hedging if high conviction
"""
        
        return alert
    
    def save_alert(self, alert, data):
        """Save alert to file"""
        ALERTS_PATH.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        score = data['impact_score']
        level = "CRITICAL" if score >= 15 else "HIGH" if score >= 10 else "MEDIUM"
        
        alert_file = ALERTS_PATH / f"political-{level}-{timestamp}.md"
        with open(alert_file, 'w') as f:
            f.write(alert)
        
        return alert_file
    
    def log_check(self, posts_found):
        """Log that we checked"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO political_checks (timestamp, posts_found)
                VALUES (?, ?)
            ''', (datetime.now().isoformat(), posts_found))
            conn.commit()
            conn.close()
        except:
            pass
    
    def run(self):
        """Run complete check"""
        print("=" * 70)
        print("🏛️ POLITICAL ALPHA MONITOR (FREE VERSION)")
        print("Sources: Grok web search + Brave news + Reddit chatter")
        print("=" * 70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M PST')}")
        print(f"Last check: {self.last_check.strftime('%H:%M PST')}")
        print()
        
        alerts_generated = 0
        
        # Check Trump
        trump_data = self.check_trump_posts()
        if trump_data['impact_score'] >= 8:
            alert = self.generate_alert(trump_data)
            if alert:
                alert_file = self.save_alert(alert, trump_data)
                print(alert)
                print(f"📄 Alert saved: {alert_file}")
                alerts_generated += 1
        else:
            print(f"✓ Trump: No significant posts (score: {trump_data['impact_score']})")
        
        print()
        
        # Check Bessent
        bessent_data = self.check_bessent_posts()
        if bessent_data['impact_score'] >= 8:
            alert = self.generate_alert(bessent_data)
            if alert:
                alert_file = self.save_alert(alert, bessent_data)
                print(alert)
                print(f"📄 Alert saved: {alert_file}")
                alerts_generated += 1
        else:
            print(f"✓ Bessent: No significant posts (score: {bessent_data['impact_score']})")
        
        # Log check
        self.log_check(alerts_generated)
        
        print("\n" + "=" * 70)
        print(f"✅ Check complete - {alerts_generated} alerts generated")
        print(f"⏰ Next check in 15 minutes")
        print("=" * 70)


def main():
    monitor = FreePoliticalMonitor()
    monitor.run()

if __name__ == '__main__':
    main()
