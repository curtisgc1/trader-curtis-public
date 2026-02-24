# Trading System Guide (Explain Like I'm 14)

## 1) What this system is
This is a **trading factory** with a **control room**.

- The factory = pipelines + subagents that collect info, score ideas, and prepare trades.
- The control room = dashboard where you see what is happening and change rules.
- The brain memory = database (`data/trades.db`) that stores truth.

Think of it like this:
- Scouts find clues.
- Judges score clues.
- Risk guards block bad ideas.
- Trader executes safe ideas.
- Coach learns from wins/losses.

## 2) The macro architecture (big picture)
Your front-facing agent (`trader-curtis`) is the **orchestrator**.
It does not invent everything from scratch each time.
It reads what sub-systems already found in the database.

Main flow:
1. Data pipelines run (news, sentiment, liquidity, innovation, weather, polymarket, etc.).
2. Candidate engine builds trade ideas.
3. Consensus + quant checks score and filter ideas.
4. Router decides approve/block based on your controls.
5. Execution workers place paper/live orders.
6. Sync + learning loops record outcomes and update source quality.
7. Dashboard shows everything.

## 3) Where the truth lives
Database is the source of truth:
- File: `trader-curtis/data/trades.db`

Dashboard pages read from this database.
If the dashboard says an order happened, it should be in DB tables.

Important DB concepts:
- `trade_candidates` = ideas
- `signal_routes` = approved/blocked decisions
- `execution_orders` / `polymarket_orders` = actual execution lifecycle
- `source_learning_stats` = source quality over time
- `polymarket_aligned_setups` = high-signal ideas mapped to polymarket bets

## 4) Dashboard pages and what they do
Open dashboard:
- Main: `http://127.0.0.1:8090/`
- Polymarket: `http://127.0.0.1:8090/polymarket`
- Consensus: `http://127.0.0.1:8090/consensus`
- Signals: `http://127.0.0.1:8090/signals`
- Learning: `http://127.0.0.1:8090/learning`

What each page is for:
1. Main page
- Snapshot of health, routes, orders, and performance.
- Good for "is system alive and behaving?"

2. Polymarket page
- Markets, candidates, orders, wallet watch, wallet scores.
- Good for "what can we trade on polymarket right now?"

3. Consensus page
- Best confirmed ideas from multiple sources.
- New section: **High-Signal -> Polymarket Aligned Bets**.
- Good for "show me only high-quality setups".

4. Signals page
- Raw signal outputs from each pipeline.
- Good for debugging where ideas came from.

5. Learning page
- Source accuracy, outcomes, learning health.
- Good for deciding what to trust more/less.

## 5) Your control switches (what you can control)
You control risk and behavior with dashboard controls (`execution_controls` table).

Most important controls:
1. `agent_master_enabled`
- Master ON/OFF for autonomous behavior.

2. `consensus_enforce`
- If ON, only ideas with enough confirmations can route.

3. `consensus_min_confirmations`, `consensus_min_ratio`, `consensus_min_score`
- How strict your confirmation gate is.

4. `enable_polymarket_auto`, `allow_polymarket_live`
- Auto mode and real-money permission for polymarket.

5. `polymarket_max_notional_usd`, `polymarket_max_daily_exposure`
- Max size per trade and daily risk cap.

6. `polymarket_fee_gate_enabled`, `polymarket_taker_fee_pct`, `polymarket_fee_buffer_pct`
- Prevent trades where fees destroy edge.

7. `high_beta_only`, `high_beta_min_beta`
- Restrict equity signals to higher-beta symbols.

8. `weather_strict_station_required`
- Only take weather setups with strict station/resolution confidence.

9. `quant_gate_enforce`
- Enforce quant validation before routing.

## 6) New edge model: high signal + low interest
You asked for less crowded alpha. This is now built.

`polymarket_aligned_setups` now scores each aligned market using:
- signal strength
- source quality
- resolution clarity
- crowding penalty
- fee drag

It tags each setup as:
1. `high_signal_low_interest`
- Best for your edge thesis (less crowded + strong signal).

2. `high_signal_direct`
- More direct tradable markets (faster, usually more crowded).

3. `watchlist`
- Monitor only, not strong enough yet.

Use the **Aligned view** selector on the Consensus page to switch modes.

## 7) Daily operating playbook (simple)
1. Open `/consensus`.
2. Check Trust State first.
3. Set Aligned view to `high_signal_low_interest`.
4. Click `Build Poly Alignments`.
5. Review top setups by `Alpha` and low `Crowding`.
6. If testing, keep paper/test mode on.
7. If quality looks good for days, slowly increase size.
8. Re-check `/learning` every day to confirm sources stay strong.

## 8) Safety rules (important)
1. Never jump size after one good day.
2. If system health turns bad or fills fail repeatedly, disable auto.
3. Keep daily cap small until win-rate + execution quality are stable.
4. Trust DB-confirmed execution only, not text claims.

## 9) What to do when confused
If something looks wrong, check in this order:
1. `signal_routes` reason (why blocked/approved)
2. `execution_orders`/`polymarket_orders` status (what really happened)
3. `source_learning_stats` (is source quality weak?)
4. `polymarket_aligned_setups` class/alpha/crowding (is setup actually good?)

## 10) One-sentence summary
Your system is a **multi-agent signal factory** where the database is truth, the dashboard is mission control, and your main edge goal is **high-signal, lower-interest bets with strict risk controls**.
