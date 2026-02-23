# Event Playbooks (Pipeline C)

Date: 2026-02-22
Purpose: Convert geopolitical/macro events into standardized trade responses.

## Operating Principle

No event headline is traded blindly.
Each event requires:
1. Event confirmation (multi-source).
2. Market confirmation (price/volatility structure).
3. Liquidity confirmation (entry quality).
4. Risk budget availability.

---

## Playbook 1: Middle East Military Escalation

Trigger examples:
- Naval deployment escalation.
- Confirmed strike/counter-strike cycle.
- Shipping lane disruption risk.

Primary assets:
- Risk-off basket candidate: BTC short / high-beta tech de-risk.
- Energy upside basket: oil proxies.
- Defensive hedge basket: gold proxies.

Signal template:
- `event_type`: `geopolitical_conflict`
- `confidence_threshold`: 0.75
- `ttl_minutes`: 180

Trade logic:
1. If escalation confirmed + BTC loses key intraday structure:
   - propose `BTC short` (scalp/event sleeve).
2. If oil shock confirms:
   - add energy-long hedge candidate.
3. If conflicting signals (risk-off but BTC resilient):
   - no trade; recheck in 15m.

Invalidation:
- De-escalation headlines + reversal through invalidation level.

---

## Playbook 2: Tariff/Trade-War Shock

Trigger examples:
- New tariff package, export controls, retaliation updates.

Primary assets:
- FX/rates-sensitive risk assets.
- Sector baskets: industrials, semis, logistics, commodities.

Logic:
- event confidence >= 0.70
- market confirmation on sector ETF breakdown/breakout
- route only if guard approves notional budget

---

## Playbook 3: Sanctions Announcement

Trigger examples:
- OFAC list updates on major entities/sectors.

Primary assets:
- energy, shipping, payment rails, country-sensitive ETFs

Logic:
- fast signal TTL (60-180m)
- smaller initial probe size
- scale only on confirmation

---

## Playbook 4: Central Bank Surprise

Trigger examples:
- unexpected policy statement or emergency action.

Primary assets:
- rates-sensitive equities
- USD, bonds, gold, BTC correlation shifts

Logic:
- require post-announcement volatility regime check
- avoid first impulse unless preplanned setup quality is high

---

## Alert Format (for agent prompts)

Required fields:
- `priority` (`high/critical`)
- `event_summary`
- `proposed_trade`
- `confidence`
- `entry_condition`
- `invalidation`
- `size_hint`
- `ttl`

Example:
`Critical Event Alpha: Escalation risk confirmed by 3 sources. Proposed BTC short (paper). Confidence 0.81. Entry only on structure break below X. Invalidate above Y. TTL 180m.`

---

## False-Positive Controls

- Require at least 2 independent source families.
- Reject stale events (timestamp decay).
- Require market-structure alignment.
- Log blocked events for model tuning.
