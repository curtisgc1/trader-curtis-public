export interface StockTwitMessage {
  id: number;
  body: string;
  created_at: string;
  user: {
    username: string;
    followers: number;
  };
  symbols: Array<{ symbol: string }>;
  entities?: {
    sentiment?: { basic: "Bullish" | "Bearish" | null };
  };
}

export interface StockTwitsTrending {
  symbol: string;
  watchlist_count: number;
  title: string;
}

interface StockTwitsStreamResponse {
  messages: StockTwitMessage[];
}

interface StockTwitsTrendingResponse {
  symbols: StockTwitsTrending[];
}

export class StockTwitsProvider {
  private baseUrl = "https://api.stocktwits.com/api/2";

  async getTrendingSymbols(): Promise<StockTwitsTrending[]> {
    const response = await fetch(`${this.baseUrl}/trending/symbols.json`);
    if (!response.ok) {
      throw new Error(`StockTwits API error: ${response.status}`);
    }
    const data = (await response.json()) as StockTwitsTrendingResponse;
    return data.symbols || [];
  }

  async getSymbolStream(symbol: string, limit = 30): Promise<StockTwitMessage[]> {
    const response = await fetch(
      `${this.baseUrl}/streams/symbol/${symbol}.json?limit=${limit}`
    );
    if (!response.ok) {
      if (response.status === 404) return [];
      throw new Error(`StockTwits API error: ${response.status}`);
    }
    const data = (await response.json()) as StockTwitsStreamResponse;
    return data.messages || [];
  }

  async getTrendingStream(limit = 30): Promise<StockTwitMessage[]> {
    const response = await fetch(
      `${this.baseUrl}/streams/trending.json?limit=${limit}`
    );
    if (!response.ok) {
      throw new Error(`StockTwits API error: ${response.status}`);
    }
    const data = (await response.json()) as StockTwitsStreamResponse;
    return data.messages || [];
  }

  analyzeSentiment(messages: StockTwitMessage[]): {
    symbol: string;
    bullish: number;
    bearish: number;
    total: number;
    score: number;
    trending_users: string[];
  }[] {
    const bySymbol = new Map<string, { bullish: number; bearish: number; total: number; users: Set<string> }>();

    for (const msg of messages) {
      for (const sym of msg.symbols) {
        if (!bySymbol.has(sym.symbol)) {
          bySymbol.set(sym.symbol, { bullish: 0, bearish: 0, total: 0, users: new Set() });
        }
        const data = bySymbol.get(sym.symbol)!;
        data.total++;
        data.users.add(msg.user.username);

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
      score: data.total > 0 ? (data.bullish - data.bearish) / data.total : 0,
      trending_users: Array.from(data.users).slice(0, 5),
    }));
  }
}

export function createStockTwitsProvider(): StockTwitsProvider {
  return new StockTwitsProvider();
}
