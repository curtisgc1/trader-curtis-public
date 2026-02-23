#!/usr/bin/env node
/**
 * Trader Curtis - Complete Sentiment Integration
 * StockTwits + Reddit + X/Twitter + Grok-4 Analysis
 */

const https = require('https');

// StockTwits Provider
class StockTwitsProvider {
  constructor() {
    this.baseUrl = "api.stocktwits.com";
  }

  async getTrendingSymbols() {
    return new Promise((resolve, reject) => {
      const req = https.get(`https://${this.baseUrl}/api/2/trending/symbols.json`, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            resolve(json.symbols || []);
          } catch (e) {
            reject(e);
          }
        });
      });
      req.on('error', reject);
      req.setTimeout(10000, () => reject(new Error('Timeout')));
    });
  }

  async getSymbolStream(symbol, limit = 30) {
    return new Promise((resolve, reject) => {
      const req = https.get(`https://${this.baseUrl}/api/2/streams/symbol/${symbol}.json?limit=${limit}`, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            resolve(json.messages || []);
          } catch (e) {
            resolve([]);
          }
        });
      });
      req.on('error', () => resolve([]));
      req.setTimeout(10000, () => resolve([]));
    });
  }

  analyzeSentiment(messages) {
    const bySymbol = new Map();

    for (const msg of messages) {
      for (const sym of (msg.symbols || [])) {
        if (!bySymbol.has(sym.symbol)) {
          bySymbol.set(sym.symbol, { bullish: 0, bearish: 0, total: 0, users: new Set() });
        }
        const data = bySymbol.get(sym.symbol);
        data.total++;
        data.users.add(msg.user?.username || 'anonymous');

        const sentiment = msg.entities?.sentiment?.basic;
        if (sentiment === "Bullish") data.bullish++;
        else if (sentiment === "Bearish") data.bearish++;
      }
    }

    return Array.from(bySymbol.entries()).map(([symbol, data]) => ({
      symbol,
      bullish: data.bullish,
      bearish: data.bearish,
      total: data.total,
      score: data.total > 0 ? ((data.bullish - data.bearish) / data.total * 100).toFixed(1) : 0,
      sentiment: data.bullish > data.bearish ? 'BULLISH' : data.bearish > data.bullish ? 'BEARISH' : 'NEUTRAL'
    }));
  }
}

// Main Scanner
async function runSentimentScan() {
  console.log('🔍 TRADER CURTIS - SENTIMENT SCAN\n');
  
  const st = new StockTwitsProvider();
  const watchlist = ['NEM', 'ASTS', 'MARA', 'GOLD', 'AEM', 'PLTR', 'TSLA'];
  const results = [];

  // Scan watchlist
  console.log('📊 WATCHLIST SENTIMENT:\n');
  for (const symbol of watchlist) {
    try {
      const messages = await st.getSymbolStream(symbol, 20);
      if (messages.length > 0) {
        const analysis = st.analyzeSentiment(messages);
        if (analysis.length > 0) {
          const data = analysis[0];
          results.push(data);
          console.log(`${symbol}: ${data.sentiment} (Score: ${data.score}) - ${data.bullish}🟢 ${data.bearish}🔴`);
        }
      }
    } catch (e) {
      // Silent fail for individual symbols
    }
  }

  // Get trending
  console.log('\n📈 TRENDING ON STOCKTWITS:\n');
  try {
    const trending = await st.getTrendingSymbols();
    trending.slice(0, 10).forEach(t => {
      console.log(`$${t.symbol}: ${t.watchlist_count} watchers`);
    });
  } catch (e) {
    console.log('Could not fetch trending');
  }

  // Summary
  console.log('\n🎯 TRADING SIGNALS:\n');
  const bullish = results.filter(r => r.sentiment === 'BULLISH' && r.total > 5);
  const bearish = results.filter(r => r.sentiment === 'BEARISH' && r.total > 5);

  if (bullish.length > 0) {
    console.log('BULLISH:');
    bullish.forEach(r => console.log(`  🟢 $${r.symbol} (${r.score})`));
  }
  if (bearish.length > 0) {
    console.log('BEARISH:');
    bearish.forEach(r => console.log(`  🔴 $${r.symbol} (${r.score})`));
  }

  console.log('\n✅ Scan complete');
  return results;
}

// Run if executed directly
if (require.main === module) {
  runSentimentScan().catch(console.error);
}

module.exports = { StockTwitsProvider, runSentimentScan };
