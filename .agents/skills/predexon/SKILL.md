---
name: predexon
description: Query prediction market data across Polymarket, Kalshi, Dflow, and
  Binance. Use when the user asks about prediction markets, market prices,
  trading activity, wallet analytics, smart money signals, or cross-platform
  arbitrage. Provides 37 MCP tools for market data, trades, positions, P&L,
  leaderboards, and smart wallet analytics.
metadata:
  mintlify-proj: predexon
---

# Predexon

> Prediction market data and smart-wallet analytics across Polymarket, Kalshi, Dflow, and Binance — 37 MCP tools.

API key: [https://dashboard.predexon.com](https://dashboard.predexon.com)

**IMPORTANT: All tools use the v2 API (`/v2/...`). Do NOT use v1 endpoints.**

## Gotchas

* **Timestamps are seconds** everywhere except orderbook tools (`get_polymarket_orderbooks`, `get_kalshi_orderbooks`) which use **milliseconds**
* **Kalshi price filters** (`min_price`/`max_price`) are in **cents 0–100**, but response prices are decimals 0–1
* **Candlestick `interval` is numeric**: 1 = 1min, 60 = 1hr, 1440 = 1day (not a string like "1m")
* **`get_polymarket_trades`** requires at least one of: `market_slug`, `condition_id`, `token_id`, or `wallet` — omitting all returns 400
* **`get_kalshi_trades`** requires at least one of: `ticker` or `event_ticker`
* **Smart money tools** require a strong filter or return 422. Thresholds differ per tool:
  * `get_polymarket_smart_money`: `min_realized_pnl` >= 1000, `min_total_pnl` >= 1000, `min_roi` >= 0.15, `min_trades` >= 100, or `min_volume` >= 10000
  * `get_polymarket_smart_activity`: `min_realized_pnl` >= 5000, `min_total_pnl` >= 5000, `min_roi` >= 0.15, `min_trades` >= 100, or `min_volume` >= 10000
  * If using only `min_win_rate` or `min_profit_factor`, also set `min_trades` >= 50
* **Leaderboard `sort_by` default is `total_pnl`** (realized + unrealized - net fees), not `realized_pnl`. Applies to: `get_polymarket_leaderboard`, `get_polymarket_market_leaderboard`, `get_polymarket_wallet_markets`, `get_polymarket_wallets_filter`
* **Leaderboard endpoints support `max_*` filters** (e.g. `max_realized_pnl`, `max_volume`, `max_trades`, `max_roi`, `max_win_rate`, etc.) — useful for filtering out whales or narrowing ranges
* **`get_polymarket_market_leaderboard`** does NOT have `min_roi`, `min_profit_factor`, or `min_win_rate` — only `min_total_pnl`, `max_total_pnl`, `min_trades`, `max_trades`, `min_volume`, `max_volume`, plus entry edge and price filters
* **Response fields include `first_trade_at`** (Unix timestamp) on leaderboard entries, wallet profiles, wallet markets, top holders, and Dflow positions
* **Cross-platform matching is LLM-powered** — a small number of matches may be hallucinated. Always verify before trading decisions
* **Dev plan required** for: smart wallet analytics, cross-platform matching, volume charts, wallet volume charts, Binance ticks/candles, leaderboards, top holders, similar wallets, cohort stats
* **Rate limits:** Free 30/min · Dev 120/min · Pro 600/min · Enterprise custom
* **Every tool** requires the `api_key` parameter

## ID Relationships

```
Event (slug) → Market (condition_id) → Outcome (token_id)
```

* **`condition_id`** identifies a market — used by: candlesticks, open\_interest, volume\_chart, market\_leaderboard, top\_holders, smart\_money, trades (optional)
* **`token_id`** identifies a YES/NO outcome — used by: price, volume, orderbooks, trades (optional)
* **`market_slug`** is a human-readable identifier — used by: trades (optional), activity (optional), positions (optional)
* To go from slug → IDs: call `list_polymarket_markets` with `market_slug` filter, then read `condition_id` and outcome `token_id` values from the response

## Tool Routing

### Finding Markets

| User wants…                        | Tool                           | Key params                                                                 |
| ---------------------------------- | ------------------------------ | -------------------------------------------------------------------------- |
| Search Polymarket markets          | `list_polymarket_markets`      | `search`, `sort`, `min_volume`, `tags`                                     |
| Browse Polymarket events           | `get_polymarket_events`        | `search`, `category`, `tag`                                                |
| Crypto up/down markets             | `get_polymarket_crypto_updown` | `asset`, `timeframe`, `status`                                             |
| Search Kalshi markets              | `list_kalshi_markets`          | `search`, `sort`, `min_volume`, `ticker`                                   |
| Find same market on both platforms | `find_matching_markets`        | one of: `polymarket_condition_id`, `kalshi_market_ticker`, etc. **\[Dev]** |
| Get all cross-platform pairs       | `get_matched_pairs`            | `min_similarity`, `active_only` **\[Dev]**                                 |

### Price & History

| User wants…                      | Tool                           | Key params                                                                |
| -------------------------------- | ------------------------------ | ------------------------------------------------------------------------- |
| Current or historical price      | `get_polymarket_price`         | `token_id` (required), `at_time`                                          |
| OHLCV candlesticks               | `get_polymarket_candlesticks`  | `condition_id`, `interval` (numeric: 1/60/1440), `start_time`, `end_time` |
| Cumulative volume over time      | `get_polymarket_volume`        | `token_id`, `granularity`                                                 |
| Per-period volume (YES/NO split) | `get_polymarket_volume_chart`  | `condition_id`, `start_time`, `end_time`, `granularity` **\[Dev]**        |
| Open interest history            | `get_polymarket_open_interest` | `condition_id`, `granularity`                                             |
| Orderbook snapshots (Polymarket) | `get_polymarket_orderbooks`    | `token_id`, `start_time`, `end_time` (**milliseconds!**)                  |
| Orderbook snapshots (Kalshi)     | `get_kalshi_orderbooks`        | `ticker`, `start_time`, `end_time` (**milliseconds!**, prices in cents)   |
| Binance raw book ticks           | `get_binance_ticks`            | `symbol`, `start_time`, `end_time` **\[Dev]**                             |
| Binance OHLCV candles            | `get_binance_candles`          | `symbol`, `interval`, `start_time`, `end_time` **\[Dev]**                 |

### Trades & Activity

| User wants…                    | Tool                      | Key params                                                           |
| ------------------------------ | ------------------------- | -------------------------------------------------------------------- |
| Polymarket trade history       | `get_polymarket_trades`   | at least one of: `market_slug`, `condition_id`, `token_id`, `wallet` |
| Kalshi trade history           | `get_kalshi_trades`       | at least one of: `ticker`, `event_ticker`                            |
| Dflow trade history            | `get_dflow_trades`        | `wallet` (required)                                                  |
| On-chain splits/merges/redeems | `get_polymarket_activity` | `wallet` (required)                                                  |

### Wallet Analysis

| User wants…                          | Tool                                 | Key params                                                                         |
| ------------------------------------ | ------------------------------------ | ---------------------------------------------------------------------------------- |
| Wallet positions + P\&L              | `get_polymarket_positions`           | `wallet` (required), `sort_by`, `include_closed`                                   |
| Wallet realized P\&L over time       | `get_polymarket_pnl`                 | `wallet`, `granularity` (both required)                                            |
| Wallet profile + style tags          | `get_polymarket_wallet_profile`      | `wallet` **\[Dev]**                                                                |
| Batch wallet profiles (up to 20)     | `get_polymarket_wallet_profiles`     | `addresses` (comma-separated) **\[Dev]**                                           |
| Per-market performance breakdown     | `get_polymarket_wallet_markets`      | `wallet`, `sort_by` (default: `total_pnl`) **\[Dev]**                              |
| Wallet volume chart (buy/sell split) | `get_polymarket_wallet_volume_chart` | `wallet`, `start_time`, `end_time` **\[Dev]**                                      |
| Dflow positions                      | `get_dflow_positions`                | `wallet` (required)                                                                |
| Dflow P\&L                           | `get_dflow_pnl`                      | `wallet`, `granularity` (both required)                                            |
| Positions across all wallets         | `get_polymarket_all_positions`       | `wallet`, `condition_id`, `token_id` (all optional filters, default order: `desc`) |

### Smart Money & Leaderboards

| User wants…                           | Tool                                | Key params                                                                                              |
| ------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Global smart wallet rankings          | `get_polymarket_leaderboard`        | `window`, `sort_by` (default: `total_pnl`), `style`, `min_roi`, `max_*` filters **\[Dev]**              |
| Market-specific wallet rankings       | `get_polymarket_market_leaderboard` | `condition_id`, `window`, `sort_by` (default: `total_pnl`) **\[Dev]**                                   |
| Top holders for a market              | `get_polymarket_top_holders`        | `condition_id`, `side` (yes/no) **\[Dev]**                                                              |
| Smart money signal (net buy/sell)     | `get_polymarket_smart_money`        | `condition_id` + strong filter, `min_total_pnl` **\[Dev]**                                              |
| Markets where smart money is active   | `get_polymarket_smart_activity`     | strong filter required, `sort_by` (default: `smart_volume`), `order` **\[Dev]**                         |
| Find wallets trading specific markets | `get_polymarket_wallets_filter`     | `markets` (condition IDs, comma-separated), `market_logic`, `sort_by` (default: `total_pnl`) **\[Dev]** |
| Find similar wallets (copy-trade)     | `get_polymarket_similar_wallets`    | `wallet` **\[Dev]**                                                                                     |
| Compare trading style cohorts         | `get_polymarket_cohort_stats`       | `window` **\[Dev]**                                                                                     |
| Verify API key works                  | `health_check`                      | `api_key`                                                                                               |

## Workflows

### Arbitrage Scanner

1. `get_matched_pairs` with `min_similarity: 98` — get cross-platform pairs **\[Dev]**
2. For each pair: `get_polymarket_price` (by token\_id) + `list_kalshi_markets` (by ticker) — compare YES prices
3. Flag pairs where price difference > 5 cents

### Smart Money Signal

1. `get_polymarket_smart_money` with `condition_id` + `min_realized_pnl: 5000` — get net smart positioning **\[Dev]**
2. `get_polymarket_top_holders` with same `condition_id` — see largest positions **\[Dev]**
3. `get_polymarket_candlesticks` — overlay price action to time entries

### Wallet Deep Dive

1. `get_polymarket_wallet_profile` — style classification + aggregate metrics **\[Dev]**
2. `get_polymarket_wallet_markets` — per-market P\&L breakdown **\[Dev]**
3. `get_polymarket_positions` — current open positions with unrealized P\&L
4. `get_polymarket_similar_wallets` — find potential copy-traders **\[Dev]**

### Market Research

1. `list_polymarket_markets` with `search` — find the market
2. `get_polymarket_candlesticks` — price history
3. `get_polymarket_volume_chart` — volume trends with YES/NO split **\[Dev]**
4. `get_polymarket_market_leaderboard` — who's trading it profitably **\[Dev]**
5. `get_polymarket_smart_money` + strong filter — smart money consensus **\[Dev]**

## Examples

Search for Bitcoin markets and get price data:

```
list_polymarket_markets(api_key="...", search="bitcoin", sort="volume", limit=5)
→ returns markets with condition_id and token_ids

get_polymarket_price(api_key="...", token_id="71321044878553530...")
→ { "price": 0.567, "timestamp": 1738800000 }
```

Get smart money positioning on a market:

```
get_polymarket_smart_money(api_key="...", condition_id="0x1234...", min_realized_pnl=5000)
→ { "net_smart_buyers": 12, "net_smart_sellers": 3, "smart_buy_volume": 45000, ... }
```

Wallet P\&L:

```
get_polymarket_pnl(api_key="...", wallet="0xabcd...", granularity="week")
→ { "summary": { "realized_pnl": 12340.5, ... }, "pnl_over_time": [...] }
```

## Auth & Links

Every tool requires `api_key`. Use `health_check` to verify your key works.

* **Get API key:** [https://dashboard.predexon.com](https://dashboard.predexon.com)
* **Full docs:** [https://docs.predexon.com](https://docs.predexon.com)
* **LLMs.txt (comprehensive reference):** [https://docs.predexon.com/llms.txt](https://docs.predexon.com/llms.txt)