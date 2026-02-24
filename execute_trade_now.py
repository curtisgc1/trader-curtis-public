#!/usr/bin/env python3
"""Execute a test trade on Hyperliquid"""
import os
import sys
sys.path.insert(0, '/Users/Shared/curtis/trader-curtis')

print("🚀 EXECUTING LIVE TRADE")
print("=" * 60)

# Import after setting up path
from execution_adapters import hyperliquid_submit_notional_live

# Execute
success, message, details = hyperliquid_submit_notional_live("ETH", "buy", 20)

print(f"\nSuccess: {success}")
print(f"Message: {message}")

if details:
    print(f"\nDetails:")
    for key, value in details.items():
        print(f"  {key}: {value}")

if success:
    print("\n🎉 TRADE EXECUTED SUCCESSFULLY!")
else:
    print("\n⚠️ Trade did not execute")

print("=" * 60)
