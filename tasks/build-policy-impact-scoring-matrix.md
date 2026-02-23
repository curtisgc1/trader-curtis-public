---
status: open
priority: high
owner: trader-curtis
project: policy-trade-intel
due: '2026-02-20'
tags:
  - infrastructure
  - scoring
  - algorithm
created: '2026-02-17T01:52:43.949Z'
updated: '2026-02-17T01:52:43.949Z'
---
# Build Policy Impact Scoring Matrix

## Objective
Create a sophisticated scoring algorithm that accurately predicts market impact of political posts based on content, context, and historical reaction patterns.

## Current Implementation
Basic keyword matching with fixed weights. Needs enhancement.

## Proposed Scoring Factors

### 1. Content Analysis (Base Score: 0-30)
| Factor | Weight | Description |
|--------|--------|-------------|
| Keyword match | 0-15 | Sum of matched keyword weights |
| Specificity | 0-5 | Named countries, companies, tickers |
| Urgency words | 0-5 | "now", "immediate", "today", "ASAP" |
| Certainty words | 0-5 | "will", "is", "happening" vs "might", "considering" |

### 2. Context Multipliers (1x - 3x)
| Condition | Multiplier | Rationale |
|-----------|-----------|-----------|
| Market hours | 1.5x | Higher volatility during trading |
| Pre-market | 1.3x | Sets opening tone |
| Earnings season | 1.2x | Macro + micro叠加 |
| Post-Fed meeting | 1.4x | Policy coordination signal |
| Weekend/Friday close | 1.3x | Weekend risk pricing |

### 3. Source Authority (1x - 2x)
| Source | Weight | Rationale |
|--------|--------|-----------|
| Trump direct | 2.0x | Maximum market impact |
| Trump retweet | 1.2x | Endorsement, less direct |
| Bessent official | 1.8x | Treasury policy authority |
| Bessent personal | 1.3x | Less formal |

### 4. Historical Pattern Bonus (0-10)
Check against `lessons/` and `decisions/` for similar past posts:
- Similar post moved market 2%+ → +10
- Similar post moved market 1-2% → +5
- No similar historical pattern → 0

## Final Score Formula
```
FINAL_SCORE = (Content Score) × (Context Multiplier) × (Source Authority) + (Historical Bonus)

Alert Thresholds:
- CRITICAL: >= 40 (immediate Telegram alert)
- HIGH: 25-39 (log + check in next heartbeat)
- MEDIUM: 15-24 (log only)
- LOW: < 15 (ignore)
```

## Implementation Plan

### Phase 1: Enhanced Content Analysis
- [ ] Implement specificity detection (country/company/ticker extraction)
- [ ] Add urgency word detection
- [ ] Add certainty analysis
- [ ] Test against historical posts

### Phase 2: Context Awareness
- [ ] Build market hours detector (9:30 AM - 4:00 PM ET)
- [ ] Add earnings season calendar check
- [ ] Add Fed meeting dates (store in `facts/`)
- [ ] Implement context multiplier logic

### Phase 3: Source Weighting
- [ ] Tag posts by source type (direct vs retweet)
- [ ] Apply source multipliers
- [ ] Track source accuracy over time

### Phase 4: Historical Learning
- [ ] Link posts to market reactions (manual at first)
- [ ] Build pattern database
- [ ] Implement similarity matching
- [ ] Add historical bonus scoring

## Files to Create/Modify
- `scripts/political_alpha_monitor.py` - scoring engine
- `memory/policy_impact_patterns.json` - historical data
- `memory/fed_calendar.json` - Fed meeting dates
- `memory/earnings_calendar.json` - Earnings season dates

## Success Metrics
- CRITICAL alerts correlate with >2% moves in affected sectors
- < 10% false positive rate on HIGH alerts
- Average detection-to-market-move time < 3 minutes

## Testing
Run scoring on historical posts with known market reactions:
1. Pull post text
2. Apply scoring algorithm
3. Compare to actual market move
4. Tune weights

## Notes
- Start simple, add complexity only if needed
- Backtest before deploying enhancements
- Document WHY each weight was chosen

## Related
- All monitoring tasks
- [[create-sector-alert-mapping]]
