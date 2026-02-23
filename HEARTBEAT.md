# HEARTBEAT.md - Trader Curtis

## Schedule
Every 4 hours during market hours (6:30 AM - 1:00 PM PST for pre-market through close)

## OpenClaw Integrated Cycle (Canonical)

Use one canonical run path for scheduled scans:

```bash
/Users/Shared/curtis/trader-curtis/scripts/openclaw_trader_cycle.sh scheduled
```

What this does:
- Runs political monitor first
- Runs full `run-all-scans.sh` multi-pipeline stack
- Prints DB-backed summary (pipeline rows, routing decisions, execution status, source reliability)

Cron integration:
- `trader-curtis-integrated-cycle` (6:30 AM and 12:30 PM PST weekdays)
- `trader-curtis-eod-integrated-cycle` (1:00 PM PST weekdays)

Redundant political-only cron jobs are disabled to avoid duplicate/noisy runs.

## Task-Driven Autonomy

**Every heartbeat, execute this loop:**

### Step 1: Check Task Queue
```bash
clawvault task list --owner trader-curtis --status open
```
Sort by: **priority** (critical first), then **due date** (soonest first).

Tasks due within 24h get automatic priority boost.

### Step 2: Pick and Execute
- Pick the highest-impact task you can execute RIGHT NOW
- Update status: `clawvault task update <slug> --status in-progress`
- Execute (run analysis, check alerts, review positions, scan sources)

### Step 3: Complete and Learn
```bash
# On success
clawvault task done <slug> --reason "AAPL hit $195 target, closed +12%"

# On blocker
clawvault task update <slug> --status blocked --blocked-by "Waiting for earnings report tonight"

# Store lessons
clawvault remember lesson "Gap-up reversals on low volume" --content "3 of 4 gap-ups >3% reversed by noon when volume was <50% avg"

# Store decisions
clawvault remember decision "Exit NVDA before earnings" --content "IV crush risk too high, locked gains at +8%"

# Store commitments (trading rules)
clawvault remember commitment "No entries after 10% move in 1 day" --content "TSLA lesson from Nov 2025, lost 15% chasing"

# Store facts
clawvault remember fact "SPY/BTC 30d correlation 0.73" --content "Measured 2026-02-15, highest since Oct 2025"
```

### Step 4: Discover New Work
If analysis reveals follow-up needs:
```bash
clawvault task add "Review AAPL post-earnings price action" \
  --priority high \
  --owner trader-curtis \
  --project trading \
  --tags "earnings,aapl" \
  --due 2026-02-17

clawvault task add "Run sector rotation scan" \
  --priority medium \
  --owner trader-curtis \
  --project research
```

### Step 5: Checkpoint and Sleep
```bash
clawvault checkpoint --working-on "Monitoring 3 open positions" --focus "NVDA earnings tonight"
```

## Market Hours Checklist

### Pre-Market (6:30 AM PST)
```bash
clawvault task list --owner trader-curtis --status open --tags pre-market
```
- Check overnight price alerts
- Review futures / market sentiment
- Scan watchlist for gap up/down
- Note any earnings reports today

### Market Open (9:30 AM PST)
- Monitor open positions
- Check for stop loss triggers
- Review any triggered alerts
- **Rule: No trades first 30 minutes** (let market settle)

### Mid-Day (12:00 PM PST)
- Portfolio status check
- Unusual volume/price action on watchlist
- News affecting positions

### Market Close (1:00 PM PST)
- End-of-day summary
- Log any trades made today → `clawvault remember decision`
- Set overnight alerts
- Create tomorrow's tasks

### After-Hours
- Check for after-hours earnings
- Monitor crypto if relevant
- Review tomorrow's economic calendar

## When to Alert Curtis

### iMessage (preferred — fastest delivery):
```bash
/Users/Shared/curtis/imsg-notify.sh TRADER "message" <info|alert|critical>
```
- Price alert triggered (alert — immediate)
- Stop loss hit (critical — immediate)
- Political alpha detected (critical — immediate)
- Unusual market event (alert — as it happens)
- Major position moves >5% (alert — immediate)
- Daily summary ready (info — end of day)

## Trading Safety Rules
- **Max 5% risk per trade** — non-negotiable commitment
- **Max 20% in any single sector**
- **Keep 20% cash minimum**
- **No leverage without explicit Curtis approval**
- **No entries after 10% daily move** (TSLA lesson)

## Political Alpha Monitoring

**Trump & Bessent Posts → Trading Edge**

Schedule aligned with market hours:
- **6:30 AM PST** - Pre-market check (overnight developments)
- **12:00 PM PST** - Mid-day check  
- **1:00 PM PST** - Close check (before 1 PM market close)

```bash
# Check political intel tasks
clawvault task list --owner trader-curtis --project policy-trade-intel --status open
```

### Market-Moving Keywords (Immediate Alert)
- **Tariffs**: `tariff`, `tariffs`, `trade war`, `china`, `mexico`, `canada`
- **Currency**: `dollar`, `usd`, `currency`, `weak dollar`, `strong dollar`
- **Treasury**: `treasury`, `yield`, `bonds`, `10-year`, `30-year`
- **Commodities**: `gold`, `silver`, `oil`, `energy`, `strategic reserve`
- **Markets**: `stock market`, `nasdaq`, `dow`, `spy`, `crash`, `rally`
- **Policy**: `sanctions`, `deals`, `agreement`, `executive order`

### Alert Decision Matrix
| Keyword Detected | Urgency | Action |
|-----------------|---------|--------|
| Tariff mention + specific country | **CRITICAL** | Alert immediately, check affected sectors |
| Treasury yield comment | **HIGH** | Alert, check TLT/TMF positions |
| Dollar strength/weakness | **HIGH** | Alert, check UUP/FXE exposure |
| Gold/commodities | **MEDIUM** | Log, watch for follow-up |
| Vague market comment | **LOW** | Log only |

### Sector Impact Map
```
Tariffs on China    → XLI (industrials), XLB (materials), XLK (tech), QQQ
Tariffs on Canada   → XLE (energy), XLI, XLU (utilities)
Treasury yields     → TLT (inverse), TMF (3x inverse), XLRE (REITs)
Dollar strength     → XLV (healthcare), XLU, international (VEA, VEU)
Dollar weakness     → XLE, XLB, GLD, SLV, international exporters
Oil mentions        → XLE, XOP, USO, energy majors (XOM, CVX)
Gold mentions       → GLD, GDX, NUGT (3x gold miners)
Crypto mentions     → BTC, MSTR, COIN, RIOT
```

### Logging Protocol
Every post detected (even non-market):
```bash
clawvault remember fact "Trump post: [summary]" --content "Timestamp, platform, sentiment"
```

Market-moving posts:
```bash
clawvault remember decision "Policy alert: [topic]" --content "Action taken: checked positions, set alerts, etc."
```

## Silent Hours
22:00 - 06:30 PST (unless major market event)

---
*Last updated: 2026-02-16 — Added Political Alpha monitoring protocol*
