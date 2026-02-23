---
primitive: task
description: Trading task — market analysis, position management, alert monitoring, and research.
fields:
  status:
    type: string
    required: true
    default: open
    enum: [open, in-progress, blocked, done]
    description: Current task state
  priority:
    type: string
    default: medium
    enum: [critical, high, medium, low]
    description: Execution priority
  owner:
    type: string
    default: trader-curtis
    description: Agent responsible for this task
  project:
    type: string
    description: Project slug this task belongs to
  ticker:
    type: string
    description: Stock/crypto ticker symbol (e.g., AAPL, BTC)
  position_type:
    type: string
    enum: [long, short, watch, closed]
    description: Position direction or watchlist status
  entry_price:
    type: number
    description: Entry price for the position
  stop_loss:
    type: number
    description: Stop loss price level
  target:
    type: number
    description: Profit target price level
  risk_pct:
    type: number
    description: Portfolio risk percentage for this trade
  timeframe:
    type: string
    enum: [scalp, day, swing, position]
    description: Trading timeframe
  catalyst:
    type: string
    description: What triggered this trade idea (earnings, technical, news)
  due:
    type: date
    description: Due date or expiry (YYYY-MM-DD)
  blocked_by:
    type: string
    description: What is blocking this task
  depends_on:
    type: string[]
    description: Other task slugs this depends on
  tags:
    type: string[]
    description: Labels for filtering
  reason:
    type: string
    description: Why this status transition happened
---

# {{title}}

## Thesis


## Setup
- Entry:
- Stop:
- Target:
- R/R:

## Next Steps
- [ ]

## Notes

