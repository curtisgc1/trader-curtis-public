#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/Users/Shared/curtis/trader-curtis')

# Set environment
os.environ['HL_WALLET_ADDRESS'] = '0x41597a1F7b3dada71Eaa9E709E74629e6D755548'
os.environ['HL_USE_TESTNET'] = '1'

print("🚀 HYPERLIQUID TRADE EXECUTION")
print("=" * 60)

from execution_adapters import hyperliquid_submit_notional_live

print("\n💰 Submitting: BUY $20 ETH...")

try:
    success, message, details = hyperliquid_submit_notional_live("ETH", "buy", 20)
    
    print(f"\n✅ Success: {success}")
    print(f"📝 Message: {message}")
    
    if details:
        print(f"\n📊 Details:")
        for k, v in details.items():
            print(f"   {k}: {v}")
    
    if success:
        print("\n🎉 TRADE EXECUTED ON HYPERLIQUID!")
    else:
        print(f"\n⚠️ Trade failed: {message}")
        
except Exception as e:
    print(f"\n❌ Exception: {e}")
    import traceback
    traceback.print_exc()

print("=" * 60)
