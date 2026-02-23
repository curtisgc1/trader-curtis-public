---
status: done
priority: critical
owner: trader-curtis
project: policy-trade-intel
due: '2026-02-17'
tags:
  - trump
  - x-twitter
  - macro
  - api-integration
created: '2026-02-17T01:52:43.949Z'
updated: '2026-02-19T23:01:35.566Z'
completed: '2026-02-19T23:01:35.566Z'
---
# Monitor Trump X/Twitter - Market Impact

## Objective
Monitor Trump's X/Twitter account (@realDonaldTrump) for market-moving posts as backup/confirmation to Truth Social.

## Implementation Status
- [x] Alert framework ready
- [ ] X API v2 credentials obtained
- [ ] API integration coded
- [ ] Test scan completed
- [ ] Telegram alerts wired

## API Setup Required

### 1. Get X API v2 Credentials
1. Go to: https://developer.twitter.com/en/portal/dashboard
2. Create a new app (or use existing)
3. Generate API Key, API Secret, Access Token, Access Secret
4. Subscribe to Basic tier ($100/month) for real-time access
   - Free tier has severe rate limits
   - Basic: 10,000 tweets/month, good for our use

### 2. Environment Setup
Add to `~/.zshenv` or trading environment:
```bash
export X_API_KEY="your_key"
export X_API_SECRET="your_secret"
export X_ACCESS_TOKEN="your_token"
export X_ACCESS_SECRET="your_secret"
```

### 3. Python Dependencies
```bash
pip install tweepy
```

### 4. Implementation Template
```python
import tweepy
import os

client = tweepy.Client(
    consumer_key=os.getenv('X_API_KEY'),
    consumer_secret=os.getenv('X_API_SECRET'),
    access_token=os.getenv('X_ACCESS_TOKEN'),
    access_token_secret=os.getenv('X_ACCESS_SECRET')
)

# Get Trump's user ID (handle @realDonaldTrump)
trump_id = "25073877"  # Verify this is current

# Fetch recent tweets
tweets = client.get_users_tweets(
    id=trump_id,
    max_results=10,
    tweet_fields=['created_at', 'text']
)

for tweet in tweets.data:
    process_post(tweet.id, "Trump/X", tweet.text, str(tweet.created_at))
```

## Next Steps
- [ ] Sign up for X Developer account if not done
- [ ] Upgrade to Basic tier ($100/month)
- [ ] Create app and generate credentials
- [ ] Add credentials to environment
- [ ] Install tweepy: `pip install tweepy`
- [ ] Implement in `political_alpha_monitor.py`
- [ ] Test with 5 recent tweets
- [ ] Add to cron/heartbeat schedule

## Rate Limits (Basic Tier)
- 10,000 tweets/month
- 1500 tweets/15 minutes per user
- Our usage: ~96 requests/day (every 15 min) = well within limits

## Notes
- X often mirrors Truth Social content
- Sometimes different phrasing or additional context
- Good for cross-verification
- Can use for sentiment analysis comparison

## Related
- [[monitor-trump-truth-social-market-impact]]
- [[build-policy-impact-scoring-matrix]]
