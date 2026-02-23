# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

---

## Trader Env & API Keys

- **Primary env file:** `/Users/Shared/curtis/trader-curtis/.env`
- **OpenClaw env:** `~/.openclaw/openclaw.json` → `env` section (fallback source)
- **Expected keys:** `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`, `XAI_API_KEY`, `BRAVE_API_KEY`

## Polymarket Secrets (Keychain)

- Stored in macOS Keychain (not `.env`) under services:
  - `trader-curtis-POLY_API_KEY`
  - `trader-curtis-POLY_API_SECRET`
  - `trader-curtis-POLY_API_PASSPHRASE`
- Runtime wrapper to inject these into env when needed:
  - `./scripts/with_polymarket_keychain.sh <command> [args...]`
- Live CLOB posting additionally requires:
  - `POLY_PRIVATE_KEY` (signing key for order creation)
  - optional: `POLY_FUNDER`, `POLY_SIGNATURE_TYPE`, `POLY_CLOB_HOST`, `POLY_CHAIN_ID`
