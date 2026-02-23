#!/usr/bin/env node
/**
 * Reddit Sentiment Scanner
 * Monitors WSB, r/stocks, r/investing
 */

const https = require('https');

class RedditProvider {
  constructor() {
    this.baseUrl = "www.reddit.com";
  }

  async getSubredditPosts(subreddit, limit = 25) {
    return new Promise((resolve, reject) => {
      const req = https.get(`https://${this.baseUrl}/r/${subreddit}/hot.json?limit=${limit}`, {
        headers: {
          'User-Agent': 'TraderCurtis/1.0'
        }
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            resolve(json.data?.children || []);
          } catch (e) {
            resolve([]);
          }
        });
      });
      req.on('error', () => resolve([]));
      req.setTimeout(15000, () => resolve([]));
    });
  }

  extractTickers(text) {
    const tickerPattern = /\$[A-Z]{1,5}\b/g;
    const matches = text.match(tickerPattern) || [];
    return matches.map(t => t.replace('$', ''));
  }

  analyzeSubreddit(subreddit, posts) {
    const tickerMentions = new Map();

    for (const post of posts) {
      const data = post.data;
      const text = `${data.title} ${data.selftext || ''}`;
      const tickers = this.extractTickers(text);
      
      for (const ticker of tickers) {
        if (!tickerMentions.has(ticker)) {
          tickerMentions.set(ticker, { count: 0, upvotes: 0, comments: 0 });
        }
        const stats = tickerMentions.get(ticker);
        stats.count++;
        stats.upvotes += data.ups || 0;
        stats.comments += data.num_comments || 0;
      }
    }

    return Array.from(tickerMentions.entries())
      .map(([ticker, stats]) => ({
        ticker,
        mentions: stats.count,
        upvotes: stats.upvotes,
        comments: stats.comments,
        score: stats.upvotes + (stats.comments * 2)
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 10);
  }
}

async function runRedditScan() {
  console.log('🔍 REDDIT SENTIMENT SCAN\n');
  
  const reddit = new RedditProvider();
  const subreddits = ['wallstreetbets', 'stocks', 'investing'];
  const allMentions = [];

  for (const sub of subreddits) {
    try {
      console.log(`📱 r/${sub}:`);
      const posts = await reddit.getSubredditPosts(sub, 25);
      const analysis = reddit.analyzeSubreddit(sub, posts);
      
      analysis.slice(0, 5).forEach(item => {
        console.log(`  $${item.ticker}: ${item.mentions} mentions, ${item.upvotes}⬆️`);
        allMentions.push({...item, source: sub});
      });
      console.log();
    } catch (e) {
      console.log(`  Could not fetch r/${sub}\n`);
    }
  }

  // Aggregate across all subreddits
  console.log('📊 TOP MENTIONS ACROSS REDDIT:\n');
  const aggregated = new Map();
  for (const item of allMentions) {
    if (!aggregated.has(item.ticker)) {
      aggregated.set(item.ticker, { mentions: 0, upvotes: 0, sources: [] });
    }
    const agg = aggregated.get(item.ticker);
    agg.mentions += item.mentions;
    agg.upvotes += item.upvotes;
    agg.sources.push(item.source);
  }

  Array.from(aggregated.entries())
    .sort((a, b) => b[1].upvotes - a[1].upvotes)
    .slice(0, 10)
    .forEach(([ticker, data]) => {
      console.log(`$${ticker}: ${data.mentions} mentions, ${data.upvotes}⬆️ [${[...new Set(data.sources)].join(', ')}]`);
    });

  console.log('\n✅ Reddit scan complete');
  return allMentions;
}

if (require.main === module) {
  runRedditScan().catch(console.error);
}

module.exports = { RedditProvider, runRedditScan };
