# trader-curtis

An elephant never forgets.

## Structure

### Memory Categories
- `rules/` — Injectable operational constraints, guardrails, and runbooks
- `preferences/` — Likes, dislikes, how I want things
- `decisions/` — Choices made with context and reasoning
- `patterns/` — Recurring behaviors (→ lessons)
- `people/` — Relationships, one file per person
- `projects/` — Active work, ventures, ongoing efforts
- `goals/` — Long-term and short-term objectives
- `transcripts/` — Session summaries and logs
- `inbox/` — Quick capture → process later
- `lessons/` — What I learned, insights, patterns observed
- `agents/` — Other agents — capabilities, trust levels, coordination notes
- `commitments/` — Promises, goals, obligations to fulfill
- `handoffs/` — Session bridges — what I was doing, what comes next
- `research/` — Deep dives, analysis, reference material

### Work Tracking


### Observational Memory
- `ledger/raw/` — Raw session transcripts (source of truth)
- `ledger/observations/` — Compressed observations with importance scores
- `ledger/reflections/` — Weekly reflection summaries

## Quick Reference

```bash
# Capture a thought
clawvault capture "important insight about X"

# Store structured memory
clawvault store --category decisions --title "Choice" --content "We chose X because..."

# Search
clawvault search "query"
clawvault vsearch "semantic query"    # vector search

# Knowledge graph
clawvault graph                       # vault stats
clawvault context "topic"             # graph-aware context retrieval

# Session lifecycle
clawvault checkpoint --working-on "task"
clawvault sleep "what I did" --next "what's next"
clawvault wake                        # restore context on startup
```

---

*Managed by [ClawVault](https://clawvault.dev)*
