#!/usr/bin/env node

/**
 * MAHORAGA + Telegram + Reddit + Grok-4
 * Complete Sentiment Trading Agent
 * 
 * Features:
 * - StockTwits sentiment
 * - Reddit sentiment (wallstreetbets, stocks, investing)
 * - Grok-4 AI analysis
 * - Telegram alerts for all trading events
 * - Paper trading via Alpaca
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import http from "http";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ============================================================================
// Telegram Notifier (Embedded)
// ============================================================================

const TELEGRAM_API = 'https://api.telegram.org/bot';

async function sendTelegramMessage(message, options = {}) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  
  if (!token || !chatId) {
    console.warn('[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID');
    return;
  }
  
  try {
    const response = await fetch(`${TELEGRAM_API}${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        text: message,
        parse_mode: 'Markdown',
        disable_notification: options.silent || false,
        ...options
      })
    });
    
    if (!response.ok) {
      console.error('[Telegram] Error:', await response.text());
    }
  } catch (error) {
    console.error('[Telegram] Failed:', error.message);
  }
}

async function alertSignal(signal) {
  const emoji = signal.action === 'BUY' ? '🟢' : signal.action === 'SELL' ? '🔴' : '⚪';
  const message = `
${emoji} *TRADING SIGNAL*

*Ticker:* $${signal.ticker}
*Action:* ${signal.action}
*Confidence:* ${signal.confidence}%
*Sentiment:* ${signal.sentiment > 0 ? '+' : ''}${signal.sentiment}
*Sources:* ${signal.sources?.join(', ') || 'StockTwits'}

*Reason:*
${signal.reason}

⏱ _${new Date().toLocaleString()}_
  `.trim();
  await sendTelegramMessage(message);
}

async function alertTradeExecuted(trade) {
  const emoji = trade.side === 'buy' ? '✅' : '💰';
  const message = `
${emoji} *TRADE EXECUTED*

*Ticker:* $${trade.symbol}
*Action:* ${trade.side.toUpperCase()}
*Quantity:* ${trade.qty}
*Price:* $${trade.price}
*Total:* $${(trade.qty * trade.price).toFixed(2)}

📊 _Paper trading mode_
  `.trim();
  await sendTelegramMessage(message);
}

async function alertStopLoss(trade) {
  const message = `
🛑 *STOP LOSS TRIGGERED*

*Ticker:* $${trade.symbol}
*Sold at:* $${trade.price}
*Loss:* ${trade.lossPct}%

💡 _Risk management working._
  `.trim();
  await sendTelegramMessage(message);
}

async function alertTakeProfit(trade) {
  const message = `
🎯 *TAKE PROFIT!*

*Ticker:* $${trade.symbol}
*Sold at:* $${trade.price}
*Profit:* +${trade.profitPct}%

🚀 _Target reached!_
  `.trim();
  await sendTelegramMessage(message);
}

async function testTelegramConnection() {
  const message = `
🤖 *MAHORAGA Bot Online*

Sentiment trading agent activated.
*Data sources:* StockTwits, Reddit
*AI:* Grok-4
*Trading:* Alpaca Paper

Listening for signals...
  `.trim();
  await sendTelegramMessage(message);
}

// ============================================================================
// Grok-4 AI Analysis
// ============================================================================

async function analyzeWithGrok(signals, context = {}) {
  const apiKey = process.env.XAI_API_KEY;
  if (!apiKey) {
    console.warn('[Grok] Missing XAI_API_KEY');
    return null;
  }
  
  const prompt = `You are a quantitative trading analyst. Analyze these sentiment signals and provide a trading recommendation.

Signals:
${signals.map(s => `- $${s.symbol}: sentiment=${(s.sentiment * 100).toFixed(0)}%, volume=${s.volume}, sources=[${s.sources?.join(', ') || 'stocktwits'}]`).join('\n')}

Current positions: ${context.positions?.map(p => `$${p.symbol}`).join(', ') || 'None'}
Available cash: $${context.cash?.toFixed(2) || 'Unknown'}

Provide a JSON response:
{
  "recommendations": [
    {
      "symbol": "TICKER",
      "action": "BUY|HOLD|AVOID",
      "confidence": 0-100,
      "reason": "Brief explanation"
    }
  ],
  "market_sentiment": "bullish|neutral|bearish",
  "notes": "Any additional insights"
}`;

  try {
    const response = await fetch('https://api.x.ai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: 'grok-4-latest',
        messages: [
          { role: 'system', content: 'You are a quantitative trading analyst. Respond only with valid JSON.' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.2
      })
    });
    
    if (!response.ok) throw new Error(`Grok API error: ${response.status}`);
    
    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;
    
    // Extract JSON from response
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      return JSON.parse(jsonMatch[0]);
    }
    return null;
  } catch (err) {
    console.error('[Grok] Analysis failed:', err.message);
    return null;
  }
}

// ============================================================================
// Reddit Data Source
// ============================================================================

class RedditAgent {
  constructor(logger) {
    this.logger = logger;
    this.name = "Reddit";
    this.subreddits = ['wallstreetbets', 'stocks', 'investing', 'StockMarket'];
  }

  async getSubredditPosts(subreddit, sort = 'hot', limit = 25) {
    try {
      const url = `https://www.reddit.com/r/${subreddit}/${sort}.json?limit=${limit}`;
      const res = await fetch(url, {
        headers: { 'User-Agent': 'MAHORAGA-SentimentBot/1.0' }
      });
      
      if (!res.ok) {
        this.logger.log(this.name, 'fetch_error', { subreddit, status: res.status });
        return [];
      }
      
      const data = await res.json();
      return data.data?.children?.map(child => child.data) || [];
    } catch (err) {
      this.logger.log(this.name, 'error', { subreddit, message: err.message });
      return [];
    }
  }

  extractTickers(text) {
    if (!text) return [];
    // Match $TICKER or TICKER (common patterns)
    const matches = text.match(/\$([A-Z]{1,5})|\b([A-Z]{2,5})\b/g);
    if (!matches) return [];
    return matches.map(m => m.replace('$', '')).filter(t => t.length >= 2);
  }

  analyzeSentiment(posts) {
    const tickerData = {};
    
    for (const post of posts) {
      const tickers = this.extractTickers(post.title + ' ' + (post.selftext || ''));
      const score = post.score || 0;
      const comments = post.num_comments || 0;
      
      for (const ticker of tickers) {
        if (!tickerData[ticker]) {
          tickerData[ticker] = { mentions: 0, score: 0, comments: 0, posts: [] };
        }
        tickerData[ticker].mentions++;
        tickerData[ticker].score += score;
        tickerData[ticker].comments += comments;
        tickerData[ticker].posts.push(post.title);
      }
    }
    
    return tickerData;
  }

  async gatherSignals() {
    const allSignals = [];
    
    for (const subreddit of this.subreddits) {
      const posts = await this.getSubredditPosts(subreddit, 'hot', 25);
      const sentiment = this.analyzeSentiment(posts);
      
      for (const [ticker, data] of Object.entries(sentiment)) {
        if (data.mentions >= 2) {
          // Simple sentiment: more engagement = more bullish
          const sentimentScore = Math.min(1, Math.log(data.score + 1) / 10);
          
          allSignals.push({
            symbol: ticker,
            source: `reddit/${subreddit}`,
            sentiment: sentimentScore,
            volume: data.mentions,
            score: data.score,
            comments: data.comments,
            reason: `Reddit r/${subreddit}: ${data.mentions} mentions, ${data.score} score`,
            sources: ['reddit']
          });
        }
      }
      
      await sleep(500); // Rate limit respect
    }
    
    this.logger.log(this.name, 'gathered_signals', { count: allSignals.length });
    return allSignals;
  }
}

// ============================================================================
// StockTwits Data Source (from original)
// ============================================================================

class StockTwitsAgent {
  constructor(logger) {
    this.logger = logger;
    this.name = "StockTwits";
  }

  async getTrending() {
    try {
      const res = await fetch("https://api.stocktwits.com/api/2/trending/symbols.json");
      if (!res.ok) return [];
      const data = await res.json();
      return data.symbols || [];
    } catch (err) {
      return [];
    }
  }

  async getStream(symbol) {
    try {
      const res = await fetch(`https://api.stocktwits.com/api/2/streams/symbol/${symbol}.json?limit=30`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.messages || [];
    } catch (err) {
      return [];
    }
  }

  analyzeSentiment(messages) {
    let bullish = 0, bearish = 0;
    
    for (const msg of messages) {
      const sentiment = msg.entities?.sentiment?.basic;
      if (sentiment === "Bullish") bullish++;
      else if (sentiment === "Bearish") bearish++;
    }
    
    const total = messages.length;
    return {
      bullish,
      bearish,
      total,
      score: total > 0 ? (bullish - bearish) / total : 0,
    };
  }

  async gatherSignals() {
    const signals = [];
    const trending = await this.getTrending();
    
    for (const sym of trending.slice(0, 10)) {
      const messages = await this.getStream(sym.symbol);
      const sentiment = this.analyzeSentiment(messages);
      
      if (sentiment.total >= 5) {
        signals.push({
          symbol: sym.symbol,
          source: "stocktwits",
          sentiment: sentiment.score,
          volume: sentiment.total,
          bullish: sentiment.bullish,
          bearish: sentiment.bearish,
          reason: `StockTwits: ${sentiment.bullish}B/${sentiment.bearish}b (${(sentiment.score * 100).toFixed(0)}%)`,
          sources: ['stocktwits']
        });
      }
      await sleep(300);
    }
    
    return signals;
  }
}

// ============================================================================
// Rest of MAHORAGA (from original)
// ============================================================================

function loadEnvFile() {
  const envPath = path.join(__dirname, ".dev.vars");
  if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith("#")) {
        const [key, ...valueParts] = trimmed.split("=");
        const value = valueParts.join("=").trim();
        if (key && value && !process.env[key]) {
          process.env[key] = value;
        }
      }
    }
  }
}

loadEnvFile();

const CONFIG_PATH = path.join(process.cwd(), "agent-config.json");
const LOG_PATH = path.join(process.cwd(), "agent-logs.json");

const DEFAULT_CONFIG = {
  mcp_url: process.env.MCP_URL || "http://localhost:8787/mcp",
  data_poll_interval_ms: 60_000,
  analyst_interval_ms: 120_000,
  max_position_value: 2000,
  max_positions: 3,
  min_sentiment_score: 0.4,
  min_volume: 10,
  take_profit_pct: 8,
  stop_loss_pct: 4,
  position_size_pct_of_cash: 20,
  starting_equity: 100000,
  use_grok: true,
  use_reddit: true,
  use_stocktwits: true,
};

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const saved = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
      return { ...DEFAULT_CONFIG, ...saved };
    }
  } catch (e) {}
  return DEFAULT_CONFIG;
}

function saveConfig(config) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
}

class ActivityLogger {
  constructor(maxEntries = 500) {
    this.maxEntries = maxEntries;
    this.entries = [];
    this.costTracker = { total_usd: 0, calls: 0, tokens_in: 0, tokens_out: 0 };
    this.load();
  }

  load() {
    try {
      if (fs.existsSync(LOG_PATH)) {
        const data = JSON.parse(fs.readFileSync(LOG_PATH, "utf-8"));
        this.entries = data.entries || [];
        this.costTracker = data.costTracker || this.costTracker;
      }
    } catch {}
  }

  save() {
    const data = { entries: this.entries.slice(-this.maxEntries), costTracker: this.costTracker };
    fs.writeFileSync(LOG_PATH, JSON.stringify(data, null, 2));
  }

  log(agent, action, details = {}) {
    const entry = { timestamp: new Date().toISOString(), agent, action, ...details };
    this.entries.push(entry);
    console.log(`[${entry.timestamp}] [${agent}] ${action}`, details.symbol ? `(${details.symbol})` : "");
    if (this.entries.length % 10 === 0) this.save();
    return entry;
  }

  getRecentLogs(limit = 50) {
    return this.entries.slice(-limit);
  }
}

class TradingExecutor {
  constructor(mcpClient, logger, config) {
    this.mcp = mcpClient;
    this.logger = logger;
    this.config = config;
    this.name = "Executor";
    this.lastTrades = new Map();
  }

  async callTool(name, args = {}) {
    const result = await this.mcp.callTool({ name, arguments: args });
    return JSON.parse(result.content[0].text);
  }

  async executeBuy(symbol, confidence, reasonText = "") {
    const lastTrade = this.lastTrades.get(symbol);
    if (lastTrade && Date.now() - lastTrade < 300_000) {
      this.logger.log(this.name, "skipped_cooldown", { symbol });
      return null;
    }

    const account = await this.callTool("accounts-get");
    if (!account.ok) return null;

    const positionSize = Math.min(
      account.data.cash * (this.config.position_size_pct_of_cash / 100) * confidence,
      this.config.max_position_value
    );

    if (positionSize < 100) return null;

    const preview = await this.callTool("orders-preview", {
      symbol, side: "buy", notional: Math.round(positionSize * 100) / 100,
      order_type: "market", time_in_force: "day",
    });

    if (!preview.ok || !preview.data.policy.allowed) return null;

    const submit = await this.callTool("orders-submit", {
      approval_token: preview.data.policy.approval_token,
    });

    if (submit.ok) {
      this.lastTrades.set(symbol, Date.now());
      this.logger.log(this.name, "buy_executed", { symbol, size: positionSize.toFixed(2) });
      
      // Telegram alert
      await alertTradeExecuted({
        symbol, side: 'buy', qty: Math.floor(positionSize / submit.data.order.price),
        price: submit.data.order.price
      });
      
      return submit.data.order;
    }
    return null;
  }

  async executeSell(symbol, reason) {
    this.logger.log(this.name, "sell_initiated", { symbol, reason });
    const result = await this.callTool("positions-close", { symbol });
    
    if (result.ok) {
      this.logger.log(this.name, "sell_executed", { symbol, reason });
      
      // Determine if stop loss or take profit
      const match = reason.match(/([\d.]+)%/);
      const pct = match ? parseFloat(match[1]) : 0;
      
      if (reason.includes('Stop')) {
        await alertStopLoss({ symbol, price: result.data.order.price, lossPct: pct });
      } else {
        await alertTakeProfit({ symbol, price: result.data.order.price, profitPct: pct });
      }
      
      return result.data.order;
    }
    return null;
  }
}

class SimpleOrchestrator {
  constructor() {
    this.config = loadConfig();
    this.logger = new ActivityLogger();
    this.signalCache = [];
    this.lastAnalystRun = 0;
    
    this.stocktwits = new StockTwitsAgent(this.logger);
    this.reddit = new RedditAgent(this.logger);
    this.executor = null;
    this.mcp = null;
  }

  async connect() {
    const url = this.config.mcp_url;
    console.log(`Connecting to MCP server at ${url}...`);
    
    try {
      const transport = new SSEClientTransport(new URL(url));
      this.mcp = new Client({ name: "mahoraga-telegram", version: "1.0" }, { capabilities: {} });
      await this.mcp.connect(transport);
      this.executor = new TradingExecutor(this.mcp, this.logger, this.config);
      this.logger.log("System", "connected", { url });
      
      // Test Telegram
      await testTelegramConnection();
      
      return true;
    } catch (err) {
      console.error("Connection error:", err);
      return false;
    }
  }

  async getAccountState() {
    const [account, positions, clock] = await Promise.all([
      this.executor.callTool("accounts-get"),
      this.executor.callTool("positions-list"),
      this.executor.callTool("market-clock"),
    ]);
    return {
      account: account.ok ? account.data : null,
      positions: positions.ok ? positions.data.positions : [],
      clock: clock.ok ? clock.data : null,
    };
  }

  async runDataGatherers() {
    this.logger.log("System", "gathering_data");
    
    const signals = [];
    
    if (this.config.use_stocktwits) {
      const stSignals = await this.stocktwits.gatherSignals();
      signals.push(...stSignals);
    }
    
    if (this.config.use_reddit) {
      const rdSignals = await this.reddit.gatherSignals();
      signals.push(...rdSignals);
    }
    
    // Merge signals by symbol
    const merged = {};
    for (const s of signals) {
      if (!merged[s.symbol]) {
        merged[s.symbol] = { ...s, sources: [] };
      }
      merged[s.symbol].sentiment = (merged[s.symbol].sentiment + s.sentiment) / 2;
      merged[s.symbol].volume += s.volume;
      merged[s.symbol].sources.push(s.source);
      merged[s.symbol].reason += ` | ${s.reason}`;
    }
    
    this.signalCache = Object.values(merged);
    
    this.logger.log("System", "data_gathered", { count: this.signalCache.length });
    return this.signalCache;
  }

  async runTradingLogic() {
    const { account, positions, clock } = await this.getAccountState();
    
    if (!account) return;
    if (!clock?.is_open) return;

    const heldSymbols = new Set(positions.map(p => p.symbol));

    // Check exits
    for (const pos of positions) {
      const plPct = (pos.unrealized_pl / (pos.market_value - pos.unrealized_pl)) * 100;
      
      if (plPct >= this.config.take_profit_pct) {
        await this.executor.executeSell(pos.symbol, `Take profit at +${plPct.toFixed(1)}%`);
      } else if (plPct <= -this.config.stop_loss_pct) {
        await this.executor.executeSell(pos.symbol, `Stop loss at ${plPct.toFixed(1)}%`);
      }
    }

    // Grok analysis
    if (this.config.use_grok && this.signalCache.length > 0) {
      const analysis = await analyzeWithGrok(this.signalCache, {
        positions: positions,
        cash: account.cash
      });
      
      if (analysis?.recommendations) {
        for (const rec of analysis.recommendations) {
          if (rec.action === 'BUY' && rec.confidence >= 70 && !heldSymbols.has(rec.symbol)) {
            await alertSignal({
              ticker: rec.symbol,
              action: 'BUY',
              confidence: rec.confidence,
              sentiment: 0.6,
              sources: ['grok-4'],
              reason: rec.reason
            });
          }
        }
      }
    }

    // Regular buy logic
    if (positions.length >= this.config.max_positions) return;

    const buyCandidates = this.signalCache
      .filter(s => !heldSymbols.has(s.symbol))
      .filter(s => s.sentiment >= this.config.min_sentiment_score)
      .filter(s => s.volume >= this.config.min_volume)
      .sort((a, b) => b.sentiment - a.sentiment);

    for (const signal of buyCandidates.slice(0, 3)) {
      if (positions.length >= this.config.max_positions) break;
      
      const confidence = Math.min(1, Math.max(0.5, signal.sentiment + 0.3));
      
      await alertSignal({
        ticker: signal.symbol,
        action: 'BUY',
        confidence: Math.round(confidence * 100),
        sentiment: signal.sentiment,
        sources: signal.sources,
        reason: signal.reason
      });
      
      const result = await this.executor.executeBuy(signal.symbol, confidence, signal.reason);
      if (result) break;
    }

    this.lastAnalystRun = Date.now();
  }

  async run() {
    console.log("\n========================================");
    console.log("  MAHORAGA + Telegram + Reddit + Grok-4");
    console.log("========================================\n");
    
    if (!(await this.connect())) {
      console.error("Failed to connect. Start MCP server: npm run dev");
      process.exit(1);
    }

    const { account, positions, clock } = await this.getAccountState();
    if (account) {
      console.log(`Equity: $${account.equity.toFixed(2)} | Cash: $${account.cash.toFixed(2)} | Positions: ${positions.length}`);
    }
    console.log(`Market: ${clock?.is_open ? "OPEN" : "CLOSED"}\n`);

    saveConfig(this.config);
    await this.runDataGatherers();
    
    if (clock?.is_open) {
      await this.runTradingLogic();
    }

    setInterval(async () => {
      try { await this.runDataGatherers(); } catch {}
    }, this.config.data_poll_interval_ms);

    setInterval(async () => {
      try {
        const { clock } = await this.getAccountState();
        if (clock?.is_open) await this.runTradingLogic();
      } catch {}
    }, this.config.analyst_interval_ms);

    setInterval(() => {
      this.logger.save();
      saveConfig(this.config);
    }, 60_000);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Start
const orchestrator = new SimpleOrchestrator();
orchestrator.run().catch(console.error);
