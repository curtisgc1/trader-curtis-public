---
status: open
priority: medium
owner: trader-curtis
project: policy-trade-intel
due: '2026-02-22'
tags:
  - infrastructure
  - watchlist
  - mapping
created: '2026-02-17T01:52:43.949Z'
updated: '2026-02-17T01:52:43.949Z'
---
# Create Sector Alert Mapping

## Objective
Build a comprehensive mapping of policy keywords → affected ETFs, sectors, and individual stocks for rapid trade decision-making.

## Current Mapping (Basic)
```python
SECTOR_MAP = {
    "tariff": ["XLI", "XLB", "XLK", "QQQ", "MCHI", "FXI"],
    "china": ["FXI", "MCHI", "KWEB", "BABA", "JD"],
    # ... etc
}
```

## Proposed Enhanced Mapping

### 1. Tariff Keywords
| Keyword | Primary ETFs | Secondary ETFs | Individual Stocks | Direction |
|---------|-------------|----------------|-------------------|-----------|
| China tariff | FXI, MCHI, KWEB | QQQ, XLK | BABA, JD, PDD, TSLA | Bearish |
| Mexico tariff | EWW, XLI | XLE, XLU | FMX, GM, F | Bearish |
| Canada tariff | EWC, XLE | XLI, XLU | ENB, TRP, BMO | Bearish |
| Steel tariff | SLX, XME | XLI, XLB | NUE, STLD, MT | Bullish (US steel) |
| Auto tariff | CARZ, XLY | XLI | GM, F, TSLA, TM | Mixed |

### 2. Treasury/Yield Keywords
| Keyword | ETFs | Individual Stocks | Direction |
|---------|------|-------------------|-----------|
| Yield up | TLT↓, TMF↓, TBT↑ | Banks (JPM, BAC), Insurers | TLT bearish |
| Yield down | TLT↑, TMF↑, TBT↓ | REITs (VNQ), Utilities (XLU) | TLT bullish |
| QE/printing | GLD↑, SLV↑, BTC↑ | Miners (GDX) | Gold bullish |

### 3. Dollar Keywords
| Keyword | ETFs | Direction |
|---------|------|-----------|
| Strong dollar | UUP↑, FXE↓, FXF↓ | Bearish intl exporters |
| Weak dollar | UUP↓, FXE↑, GLD↑ | Bullish commodities |

### 4. Commodity Keywords
| Keyword | ETFs | Direction |
|---------|------|-----------|
| Gold | GLD, GDX, NUGT, IAU | Bullish gold |
| Oil/Energy | USO, XLE, XOP, UCO | Bullish energy |
| Strategic reserve | USO, XLE | Depends on context |

### 5. Crypto Keywords
| Keyword | ETFs/Stocks | Direction |
|---------|-------------|-----------|
| Bitcoin | BTC, MSTR, COIN, RIOT, BITO | Bullish crypto |
| Crypto regulation | COIN, MSTR | Depends on tone |

## Implementation

### File Structure
```
memory/
  sector_mappings/
    tariffs.json
    treasury.json
    dollar.json
    commodities.json
    crypto.json
```

### JSON Schema
```json
{
  "keyword": "china tariff",
  "primary_etfs": ["FXI", "MCHI"],
  "secondary_etfs": ["QQQ", "XLK"],
  "stocks": ["BABA", "JD", "PDD"],
  "direction": "bearish",
  "typical_move": "-2% to -5%",
  "duration": "same_day",
  "notes": "Immediate reaction, often reversed by close"
}
```

## Next Steps
- [ ] Create sector_mappings directory structure
- [ ] Build tariff mapping JSON
- [ ] Build treasury mapping JSON
- [ ] Build dollar mapping JSON
- [ ] Build commodities mapping JSON
- [ ] Build crypto mapping JSON
- [ ] Update `political_alpha_monitor.py` to load and use mappings
- [ ] Add "suggested positions" to alert output

## Testing
Verify mappings with historical events:
- April 2025 tariff announcements → did FXI/MCHI drop?
- Yield spike events → did TLT/TMF move as expected?
- Document accuracy in `lessons/`

## Integration with Alerts
Enhanced alert format:
```
🚨 POLICY ALERT

Affected Positions:
- LONG FXI: Consider trimming (-3% expected)
- LONG TLT: Add on weakness (+2% expected)
- CASH: Opportunity to enter QQQ dip

Suggested Actions:
1. Check current FXI position size
2. Set stop loss on XLI
3. Watch for reversal by 11 AM
```

## Related
- [[build-policy-impact-scoring-matrix]]
- All monitoring tasks
