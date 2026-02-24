#!/usr/bin/env python3
import os
from datetime import datetime

print("🚀 POLYMARKET ORDER ATTEMPT")
print("=" * 60)

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
    
    # Get credentials
    api_key = os.environ.get('POLY_API_KEY')
    api_secret = os.environ.get('POLY_API_SECRET')
    api_passphrase = os.environ.get('POLY_API_PASSPHRASE')
    private_key = os.environ.get('POLY_PRIVATE_KEY')
    funder = os.environ.get('HL_WALLET_ADDRESS')
    
    print(f"Wallet: {funder[:20]}...")
    
    # Initialize client
    creds = ApiCreds(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase
    )
    
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=private_key,
        chain_id=137,
        creds=creds,
        signature_type=1,
        funder=funder
    )
    
    print("✅ Client initialized")
    
    # Get a simple market
    markets = client.get_markets()
    
    if markets and 'data' in markets:
        # Find a market with decent liquidity
        for m in markets['data'][:10]:
            if m.get('active', False) and float(m.get('liquidity', 0)) > 10000:
                question = m.get('question', 'Unknown')
                print(f"\n🎯 Market: {question[:60]}")
                
                tokens = m.get('tokens', [])
                if tokens:
                    token_id = tokens[0].get('token_id', '')
                    print(f"Token: {token_id[:30]}...")
                    
                    # Try to create order
                    order_args = OrderArgs(
                        token_id=token_id,
                        price=0.50,
                        size=2.0,  # Small $2 trade
                        side=BUY
                    )
                    
                    print("\n⚡ Creating order...")
                    signed_order = client.create_order(order_args)
                    print("✅ Order signed")
                    
                    print("Submitting...")
                    result = client.post_order(signed_order, OrderType.GTC)
                    
                    print(f"\n🎉 RESULT:")
                    print(f"   Order ID: {result.get('orderID')}")
                    print(f"   Status: {result.get('status')}")
                    print(f"   ✅ SUCCESS!")
                    break
    else:
        print("❌ No markets")
                
except Exception as e:
    print(f"\n❌ Error: {str(e)[:200]}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
