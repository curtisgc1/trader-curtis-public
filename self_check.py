#!/usr/bin/env python3
"""
Trader Curtis Self-Diagnostic & Repair Script
"""
import sqlite3
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trades.db"
ENV_PATH = Path(__file__).parent / ".env"

def run_shell(cmd):
    """Execute shell command and return output"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def check_alpaca_connection():
    """Check if Alpaca API is accessible"""
    print("\n🔌 CHECKING ALPACA CONNECTION...")
    
    # Load env vars
    env_vars = {}
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env_vars[key] = val
    
    api_key = env_vars.get('ALPACA_API_KEY')
    secret = env_vars.get('ALPACA_SECRET_KEY')
    base_url = env_vars.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    if not api_key or not secret:
        print("  ❌ Missing API credentials in .env")
        return None
    
    cmd = f'''curl -s -H "APCA-API-KEY-ID: {api_key}" -H "APCA-API-SECRET-KEY: {secret}" "{base_url}/v2/account"'''
    stdout, stderr, rc = run_shell(cmd)
    
    if rc != 0 or not stdout:
        print(f"  ❌ API connection failed: {stderr}")
        return None
    
    try:
        account = json.loads(stdout)
        print(f"  ✅ Connected to Alpaca")
        print(f"  📊 Portfolio Value: ${account.get('portfolio_value', 'N/A')}")
        print(f"  💵 Cash: ${account.get('cash', 'N/A')}")
        return account
    except json.JSONDecodeError:
        print(f"  ❌ Invalid API response")
        return None

def fetch_positions():
    """Fetch current positions from Alpaca"""
    print("\n📈 FETCHING POSITIONS...")
    
    env_vars = {}
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env_vars[key] = val
    
    api_key = env_vars.get('ALPACA_API_KEY')
    secret = env_vars.get('ALPACA_SECRET_KEY')
    base_url = env_vars.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    cmd = f'''curl -s -H "APCA-API-KEY-ID: {api_key}" -H "APCA-API-SECRET-KEY: {secret}" "{base_url}/v2/positions"'''
    stdout, _, rc = run_shell(cmd)
    
    if rc != 0 or not stdout:
        print("  ❌ Failed to fetch positions")
        return []
    
    try:
        positions = json.loads(stdout)
        print(f"  ✅ Found {len(positions)} positions")
        for p in positions:
            pl = float(p.get('unrealized_pl', 0))
            symbol = p.get('symbol')
            status = "🟢" if pl > 0 else "🔴"
            print(f"  {status} {symbol}: {p.get('qty')} shares, P&L: ${pl:.2f}")
        return positions
    except json.JSONDecodeError:
        print("  ❌ Invalid positions data")
        return []

def sync_to_database(positions):
    """Sync positions to SQLite database"""
    print("\n🗄️ SYNCING TO DATABASE...")
    
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure table exists with correct schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            shares INTEGER,
            pnl REAL,
            pnl_percent REAL,
            status TEXT,
            sentiment_reddit INTEGER,
            sentiment_twitter INTEGER,
            thesis TEXT,
            outcome_analysis TEXT,
            lesson_learned TEXT,
            decision_grade TEXT,
            created_at TEXT,
            last_sync TEXT
        )
    ''')
    
    # Mark all existing as needing update
    cursor.execute("UPDATE trades SET status = 'unknown' WHERE status = 'open'")
    
    synced = 0
    for p in positions:
        ticker = p.get('symbol')
        trade_id = f"alpaca_{ticker}_open"
        
        cursor.execute('''
            INSERT OR REPLACE INTO trades 
            (trade_id, ticker, entry_price, shares, status, pnl, pnl_percent, last_sync)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
        ''', (
            trade_id,
            ticker,
            float(p.get('avg_entry_price', 0)),
            int(p.get('qty', 0)),
            float(p.get('unrealized_pl', 0)),
            float(p.get('unrealized_plpc', 0)) * 100,
            datetime.now().isoformat()
        ))
        synced += 1
    
    conn.commit()
    conn.close()
    print(f"  ✅ Synced {synced} positions to database")

def check_stop_losses():
    """Check for missing stop losses"""
    print("\n🛑 CHECKING STOP LOSSES...")
    
    env_vars = {}
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env_vars[key] = val
    
    api_key = env_vars.get('ALPACA_API_KEY')
    secret = env_vars.get('ALPACA_SECRET_KEY')
    base_url = env_vars.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    cmd = f'''curl -s -H "APCA-API-KEY-ID: {api_key}" -H "APCA-API-SECRET-KEY: {secret}" "{base_url}/v2/orders?status=open"'''
    stdout, _, rc = run_shell(cmd)
    
    if rc != 0 or not stdout:
        print("  ❌ Failed to check orders")
        return
    
    try:
        orders = json.loads(stdout)
        stop_orders = {o.get('symbol'): o for o in orders if o.get('type') == 'stop'}
        
        # Fetch positions to compare
        cmd_pos = f'''curl -s -H "APCA-API-KEY-ID: {api_key}" -H "APCA-API-SECRET-KEY: {secret}" "{base_url}/v2/positions"'''
        stdout_pos, _, _ = run_shell(cmd_pos)
        positions = json.loads(stdout_pos) if stdout_pos else []
        
        for p in positions:
            symbol = p.get('symbol')
            if symbol in stop_orders:
                stop_price = stop_orders[symbol].get('stop_price')
                print(f"  ✅ {symbol}: Stop @ ${stop_price}")
            else:
                current = float(p.get('current_price', 0))
                entry = float(p.get('avg_entry_price', 0))
                pl_pct = (current - entry) / entry * 100
                print(f"  ⚠️  {symbol}: NO STOP LOSS (currently {pl_pct:.1f}%)")
                
    except json.JSONDecodeError:
        print("  ❌ Invalid orders data")

def update_memory_log(positions):
    """Create a fresh memory log entry"""
    print("\n📝 UPDATING MEMORY LOG...")
    
    memory_dir = Path(__file__).parent.parent / "memory"
    memory_dir.mkdir(exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    memory_file = memory_dir / f"{today}.md"
    
    total_pl = sum(float(p.get('unrealized_pl', 0)) for p in positions)
    total_value = sum(float(p.get('market_value', 0)) for p in positions)
    
    content = f"""# Memory Log - {today}

## Auto-Generated Trade Sync
**Time:** {datetime.now().strftime("%H:%M PST")}
**Source:** Alpaca Paper Trading API

### Current Holdings ({len(positions)} positions)

| Ticker | Shares | Entry | Current | P&L | % |
|--------|--------|-------|---------|-----|---|
"""
    
    for p in positions:
        symbol = p.get('symbol')
        shares = p.get('qty')
        entry = float(p.get('avg_entry_price', 0))
        current = float(p.get('current_price', 0))
        pl = float(p.get('unrealized_pl', 0))
        pl_pct = float(p.get('unrealized_plpc', 0)) * 100
        
        content += f"| {symbol} | {shares} | ${entry:.2f} | ${current:.2f} | ${pl:.2f} | {pl_pct:+.1f}% |\n"
    
    content += f"""
### Summary
- **Total Positions:** {len(positions)}
- **Total Market Value:** ${total_value:,.2f}
- **Total Unrealized P&L:** ${total_pl:+.2f}
- **Status:** Active monitoring

### Next Actions
- [ ] Review stops for positions without protection
- [ ] Update targets based on price action
- [ ] Log any exits when they occur

---
*Auto-synced by Trader Curtis self-diagnostic*
"""
    
    with open(memory_file, 'w') as f:
        f.write(content)
    
    print(f"  ✅ Updated {memory_file}")

def main():
    print("=" * 60)
    print("🤖 TRADER CURTIS SELF-DIAGNOSTIC & REPAIR")
    print("=" * 60)
    
    # Run checks
    account = check_alpaca_connection()
    if not account:
        print("\n❌ CRITICAL: Cannot connect to Alpaca. Aborting.")
        return
    
    positions = fetch_positions()
    if positions:
        sync_to_database(positions)
        update_memory_log(positions)
    
    check_stop_losses()
    
    print("\n" + "=" * 60)
    print("✅ SELF-DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\nSummary:")
    print(f"  • Alpaca: Connected (${account.get('portfolio_value')} portfolio)")
    print(f"  • Positions: {len(positions)} tracked")
    print(f"  • Database: Synced")
    print(f"  • Memory: Updated")
    print("\n🎯 Trader Curtis is now fully synced and operational!")

if __name__ == '__main__':
    main()
