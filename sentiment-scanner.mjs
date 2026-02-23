#!/usr/bin/env node
/**
 * Trader Curtis - Integrated Social Sentiment
 * Uses StockTwits, Reddit, X/Twitter for trading signals
 */

// StockTwits Sentiment Scanner for Trader Curtis
// Fetches real-time sentiment from StockTwits API

const stocktwits = createStockTwitsProvider();

async function scanSentiment() {
  console.log('🔍 Scanning StockTwits...');
  
  // Get trending symbols
  const trending = await stocktwits.getTrendingSymbols();
  console.log('📈 Trending:', trending.slice(0, 5).map(t => t.symbol));
  
  // Get messages for our watchlist
  const watchlist = ['NEM', 'ASTS', 'MARA', 'GOLD', 'BTC'];
  
  for (const symbol of watchlist) {
    try {
      const messages = await stocktwits.getSymbolStream(symbol, 20);
      const analysis = stocktwits.analyzeSentiment(messages);
      
      if (analysis.length > 0) {
        const data = analysis[0];
        console.log(`${symbol}: Score ${data.score.toFixed(2)} (${data.bullish} bullish, ${data.bearish} bearish)`);
      }
    } catch (e) {
      console.error(`Error scanning ${symbol}:`, e.message);
    }
  }
}

scanSentiment().catch(console.error);
