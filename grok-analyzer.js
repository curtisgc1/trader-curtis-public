#!/usr/bin/env node
/**
 * Grok-4 AI Trade Analyzer
 * Uses XAI API for intelligent trade recommendations
 */

const https = require('https');

const XAI_API_KEY = process.env.XAI_API_KEY;

async function analyzeWithGrok(signals, context = {}) {
  if (!XAI_API_KEY) {
    console.warn('❌ XAI_API_KEY not set');
    return null;
  }

  const prompt = `You are an elite quantitative trading analyst. Analyze these market signals and provide actionable trading recommendations.

SENTIMENT SIGNALS:
${signals.map(s => `- $${s.symbol}: sentiment=${s.score}%, sources=${s.sources?.join(', ') || 'stocktwits'}`).join('\n')}

CURRENT POSITIONS:
${context.positions?.map(p => `- $${p.symbol}: ${p.shares} shares @ $${p.entry}, P&L: $${p.pnl}`).join('\n') || 'None'}

AVAILABLE CASH: $${context.cash || 'Unknown'}
MAX TRADE SIZE: $500

Provide a JSON response with this exact structure:
{
  "recommendations": [
    {
      "symbol": "TICKER",
      "action": "BUY|HOLD|SELL|AVOID",
      "confidence": 0-100,
      "position_size": 0-500,
      "entry_price": 0.00,
      "stop_loss": 0.00,
      "target": 0.00,
      "reason": "Brief technical/sentiment rationale"
    }
  ],
  "market_assessment": "bullish|neutral|bearish",
  "risk_level": "low|medium|high",
  "key_insights": ["insight 1", "insight 2"]
}`;

  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      model: 'grok-3',
      messages: [
        { role: 'system', content: 'You are a quantitative trading analyst. Respond only with valid JSON.' },
        { role: 'user', content: prompt }
      ],
      temperature: 0.2
    });

    const options = {
      hostname: 'api.x.ai',
      path: '/v1/chat/completions',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${XAI_API_KEY}`,
        'Content-Length': data.length
      }
    };

    const req = https.request(options, (res) => {
      let responseData = '';
      res.on('data', chunk => responseData += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(responseData);
          const content = json.choices?.[0]?.message?.content;
          const jsonMatch = content?.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            resolve(JSON.parse(jsonMatch[0]));
          } else {
            resolve(null);
          }
        } catch (e) {
          console.error('Grok parse error:', e.message);
          resolve(null);
        }
      });
    });

    req.on('error', (e) => {
      console.error('Grok API error:', e.message);
      resolve(null);
    });

    req.write(data);
    req.end();
  });
}

// Test function
async function testGrok() {
  console.log('🤖 Testing Grok-4 Analysis...\n');
  
  const testSignals = [
    { symbol: 'ASTS', score: 60, sources: ['stocktwits', 'reddit'] },
    { symbol: 'PLTR', score: 65, sources: ['stocktwits'] },
    { symbol: 'MARA', score: 100, sources: ['stocktwits'] }
  ];

  const context = {
    positions: [
      { symbol: 'NEM', shares: 100, entry: 111.50, pnl: 226 },
      { symbol: 'ASTS', shares: 35, entry: 109.36, pnl: -142 }
    ],
    cash: 85000
  };

  const analysis = await analyzeWithGrok(testSignals, context);
  
  if (analysis) {
    console.log('✅ GROK-4 ANALYSIS:\n');
    console.log(`Market Assessment: ${analysis.market_assessment?.toUpperCase()}`);
    console.log(`Risk Level: ${analysis.risk_level?.toUpperCase()}`);
    console.log('\nKey Insights:');
    analysis.key_insights?.forEach(i => console.log(`  • ${i}`));
    
    if (analysis.recommendations?.length > 0) {
      console.log('\n📊 RECOMMENDATIONS:\n');
      analysis.recommendations.forEach(r => {
        console.log(`${r.action}: $${r.symbol}`);
        console.log(`  Confidence: ${r.confidence}%`);
        console.log(`  Size: $${r.position_size}`);
        console.log(`  Reason: ${r.reason}`);
        console.log();
      });
    }
  } else {
    console.log('❌ Could not get Grok analysis');
  }
}

if (require.main === module) {
  testGrok().catch(console.error);
}

module.exports = { analyzeWithGrok };
