# Trading System (Simple Version)

## Big Picture
Think of this system like a smart robot team.
It reads lots of signals, gives each signal a score, decides if a trade is worth it, then learns from what happened.

You have 3 trade places:
1. Alpaca (paper first)
2. Hyperliquid
3. Polymarket

## How a Trade Idea Is Made
1. Pipelines collect information:
- news
- X accounts
- reddit/stocktwits/grok sentiment
- liquidity/chart patterns
- world events
- innovation/breakthrough feeds
- weather/polymarket market data

2. Candidate builder combines that data and scores it.

3. Router checks safety rules and thresholds per exchange.

4. If approved, execution workers place the order (or block it if rules fail).

## Why It Is Safer Now
- It does not trust one source.
- It uses weighted inputs (good sources get more weight over time).
- It has hard controls (size limits, confidence thresholds, route limits, daily caps).
- It records what really happened so fake "claimed trades" get caught.

## Learning Loop (Important)
After trades resolve, the system logs:
- win/loss,
- source used,
- strategy used,
- route quality,
- outcome details.

Then it updates source quality stats so better inputs matter more next time.

## New Part: GRPO Alignment (What It Means)
GRPO is a way to train a model by comparing multiple answers and rewarding the better ones.

In this build, we use a "GRPO-style" weekly alignment pass:
- score real decisions with a hierarchical reward,
- direction first (hard gate), then magnitude/pnl,
- update input weights slowly (only if enabled).

So GRPO here = improving decision policy from real outcomes, not random guessing.

## Is GRPO the Model?
No.
- GRPO is the training/optimization method.
- A model (like Qwen) is the brain being tuned.

Why use `qwen2.5:14b` locally:
- strong reasoning,
- works on your Mac,
- good balance of quality + speed for weekly policy notes/alignment.

## Your Main Controls
Look in dashboard controls for:
- per-exchange thresholds
- max trade size
- leverage/notional caps
- auto/manual modes
- consensus requirements
- GRPO alignment toggles

Important GRPO toggles:
- `grpo_alignment_enabled` (run weekly alignment)
- `grpo_apply_weight_updates` (actually change weights; off by default)
- `grpo_local_model` (local model name)

## Recommended Operating Mode
1. Keep live execution guarded.
2. Run daily integrated cycle.
3. Run weekly GRPO alignment in shadow mode first.
4. Turn on weight updates only after enough real outcomes.
5. Keep reviewing top/bottom sources monthly.

That gives you what you want: freedom through a system that gets smarter and more reliable over time.
